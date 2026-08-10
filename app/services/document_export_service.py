# app/services/document_export_service.py
import os
import zipfile
import logging
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app import models
import tempfile
import time
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class DocumentExportService:
    UPLOAD_BASE = "app/static/uploads/profile/documents"

    # Максимальный размер архива в байтах (500 MB)
    MAX_ZIP_SIZE = 500 * 1024 * 1024
    # Максимальное количество файлов в архиве
    MAX_FILES_IN_ZIP = 1000
    # Таймаут на создание архива (в секундах)
    ZIP_TIMEOUT = 300  # 5 минут

    # ✅ Новые настройки для оптимизации
    # Количество потоков для параллельного сбора файлов
    PARALLEL_WORKERS = 10
    # Минимальный размер файла для пропуска (0 байт)
    MIN_FILE_SIZE = 1024  # 1 KB
    # Использовать STORED (без сжатия) для быстрых ZIP
    USE_STORED = True

    DOCUMENT_TYPES = {
        "snils": {
            "field_url": "snils_file_url",
            "field_name": "snils_file_name",
            "label": "СНИЛС",
            "filename_prefix": "SNILS"
        },
        "diploma": {
            "field_url": "diploma_file_url",
            "field_name": "diploma_file_name",
            "label": "Диплом",
            "filename_prefix": "Diploma"
        },
        "passport": {
            "field_url": "passport_file_url",
            "field_name": "passport_file_name",
            "label": "Паспорт",
            "filename_prefix": "Passport"
        },
        "inn": {
            "field_url": "inn_file_url",
            "field_name": "inn_file_name",
            "label": "ИНН",
            "filename_prefix": "INN"
        },
        "marriage": {
            "field_url": "marriage_certificate_file_url",
            "field_name": "marriage_certificate_file_name",
            "label": "Свидетельство о браке",
            "filename_prefix": "Marriage"
        }
    }

    def __init__(self, db: Session):
        self.db = db
        # ✅ Пул потоков для параллельной обработки
        self.executor = ThreadPoolExecutor(max_workers=self.PARALLEL_WORKERS)

    def _sanitize_folder_name(self, name: str) -> str:
        if not name:
            return "user"

        forbidden = r'[<>:"/\\|?*]'
        import re
        safe_name = re.sub(forbidden, '_', name)
        safe_name = safe_name.strip('. ')
        if not safe_name:
            safe_name = "user"
        return safe_name

    def _sanitize_filename(self, filename: str) -> str:
        if not filename:
            return "unknown"

        forbidden = r'[<>:"/\\|?*]'
        import re
        safe_name = re.sub(forbidden, '_', filename)
        safe_name = safe_name.strip('. ')
        if not safe_name:
            safe_name = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return safe_name

    def _generate_unique_name(self, base_name: str, used_names: set, extension: str = "") -> str:
        final_name = f"{base_name}{extension}"
        counter = 1

        while final_name in used_names:
            final_name = f"{base_name}_{counter}{extension}"
            counter += 1

        used_names.add(final_name)
        return final_name

    def _get_user_display_name(self, user: models.User) -> str:
        parts = []
        if user.last_name:
            parts.append(user.last_name)
        if user.first_name:
            parts.append(user.first_name)
        if user.middle_name:
            parts.append(user.middle_name)

        if parts:
            return " ".join(parts)
        return user.full_name or f"user_{user.id}"

    def _get_user_folder_name(self, user: models.User) -> str:
        parts = []
        if user.last_name:
            parts.append(user.last_name)
        if user.first_name:
            parts.append(user.first_name)
        if user.middle_name:
            parts.append(user.middle_name)

        if parts:
            folder_name = "_".join(parts)
        else:
            folder_name = user.full_name.replace(" ", "_") if user.full_name else f"user_{user.id}"

        return self._sanitize_folder_name(folder_name)

    def _get_user_documents(self, user: models.User) -> Dict[str, Dict[str, Any]]:
        """Быстрое получение документов пользователя (одним запросом)"""
        additional_info = self.db.query(models.UserAdditionalInfo).filter(
            models.UserAdditionalInfo.user_id == user.id
        ).first()

        education = self.db.query(models.UserEducation).filter(
            models.UserEducation.user_id == user.id,
            models.UserEducation.is_main == True
        ).first()

        if not education:
            education = self.db.query(models.UserEducation).filter(
                models.UserEducation.user_id == user.id
            ).order_by(models.UserEducation.created_at.desc()).first()

        documents = {}

        for doc_type, config in self.DOCUMENT_TYPES.items():
            if doc_type == "diploma":
                if education:
                    url = getattr(education, "diploma_file_url", None)
                    filename = getattr(education, "diploma_file_name", None)
                else:
                    url = None
                    filename = None
            else:
                if additional_info:
                    url = getattr(additional_info, config["field_url"], None)
                    filename = getattr(additional_info, config["field_name"], None)
                else:
                    url = None
                    filename = None

            if url and filename:
                file_path = url.replace("/static/", "app/static/")
                exists = os.path.exists(file_path)

                file_size = 0
                if exists:
                    try:
                        file_size = os.path.getsize(file_path)
                    except Exception:
                        pass

                documents[doc_type] = {
                    "url": url,
                    "filename": filename,
                    "exists": exists,
                    "path": file_path if exists else None,
                    "label": config["label"],
                    "prefix": config["filename_prefix"],
                    "size": file_size
                }
            else:
                documents[doc_type] = {
                    "url": None,
                    "filename": None,
                    "exists": False,
                    "path": None,
                    "label": config["label"],
                    "prefix": config["filename_prefix"],
                    "size": 0
                }

        return documents

    # ============================================================
    # ✅ НОВЫЙ МЕТОД: ПОЛУЧЕНИЕ ВСЕХ ФАЙЛОВ ДЛЯ ZIP (ПАРАЛЛЕЛЬНО)
    # ============================================================
    def _collect_files_parallel(self, users: List[models.User]) -> List[Dict[str, Any]]:
        """
        Параллельный сбор всех файлов для ZIP-архива.
        Возвращает список словарей с информацией о файлах.
        """
        all_files = []
        used_names = set()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        logger.info(f"Collecting files for {len(users)} users in parallel...")
        start_time = time.time()

        # Функция для обработки одного пользователя
        def process_user(user):
            user_files = []
            folder_name = self._get_user_folder_name(user)
            documents = self._get_user_documents(user)

            for doc_type, doc_info in documents.items():
                if doc_info["exists"] and doc_info["path"]:
                    # Проверяем файл
                    if not os.path.exists(doc_info["path"]) or not os.access(doc_info["path"], os.R_OK):
                        continue

                    file_size = doc_info.get("size", 0)
                    if file_size == 0:
                        try:
                            file_size = os.path.getsize(doc_info["path"])
                        except Exception:
                            continue

                    # Пропускаем слишком маленькие файлы (повреждённые)
                    if file_size < self.MIN_FILE_SIZE:
                        continue

                    # Пропускаем слишком большие файлы (> 20 MB для быстрого сбора)
                    if file_size > 20 * 1024 * 1024:
                        logger.warning(f"Skipping large file ({file_size / (1024 * 1024):.1f} MB): {doc_info['path']}")
                        continue

                    file_ext = os.path.splitext(doc_info["filename"])[1]
                    if not file_ext:
                        file_ext = ".pdf"

                    safe_prefix = self._sanitize_filename(doc_info['prefix'])
                    if not safe_prefix:
                        safe_prefix = f"doc_{doc_type}"

                    base_name = f"{safe_prefix}_{timestamp}"
                    archive_filename = f"{folder_name}/{base_name}{file_ext}"

                    # Уникализируем имя
                    counter = 1
                    final_name = archive_filename
                    while final_name in used_names:
                        final_name = f"{folder_name}/{base_name}_{counter}{file_ext}"
                        counter += 1
                    used_names.add(final_name)

                    user_files.append({
                        "user_id": user.id,
                        "user_name": self._get_user_display_name(user),
                        "doc_type": doc_type,
                        "doc_label": doc_info["label"],
                        "path": doc_info["path"],
                        "archive_name": final_name,
                        "size": file_size
                    })

            return user_files

        # Параллельная обработка пользователей
        with ThreadPoolExecutor(max_workers=self.PARALLEL_WORKERS) as executor:
            futures = {executor.submit(process_user, user): user for user in users}

            for idx, future in enumerate(as_completed(futures)):
                try:
                    user_files = future.result()
                    all_files.extend(user_files)
                    if idx % 10 == 0:
                        logger.info(f"Processed {idx + 1}/{len(users)} users, found {len(all_files)} files")
                except Exception as e:
                    logger.error(f"Error processing user: {str(e)}")

        elapsed = time.time() - start_time
        logger.info(f"Collected {len(all_files)} files from {len(users)} users in {elapsed:.2f}s")

        return all_files

    def get_user_documents_list(self, user_id: int) -> Dict[str, Any]:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        documents = self._get_user_documents(user)
        display_name = self._get_user_display_name(user)
        folder_name = self._get_user_folder_name(user)

        return {
            "user_id": user.id,
            "full_name": folder_name,
            "display_name": display_name,
            "documents": documents,
            "has_any_document": any(doc["exists"] for doc in documents.values())
        }

    def create_user_zip(self, user_id: int) -> Tuple[bytes, str]:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        documents = self._get_user_documents(user)

        has_documents = any(doc["exists"] for doc in documents.values())
        if not has_documents:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No documents found for this user"
            )

        zip_buffer = BytesIO()
        added_files = 0
        used_names = set()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = self._get_user_folder_name(user)

        # ✅ Используем ZIP_STORED для быстрого сжатия (файлы уже сжаты)
        compression = zipfile.ZIP_STORED if self.USE_STORED else zipfile.ZIP_DEFLATED

        try:
            with zipfile.ZipFile(zip_buffer, 'w', compression) as zip_file:
                for doc_type, doc_info in documents.items():
                    if doc_info["exists"] and doc_info["path"]:
                        try:
                            file_ext = os.path.splitext(doc_info["filename"])[1]
                            if not file_ext:
                                file_ext = ".pdf"

                            safe_prefix = self._sanitize_filename(doc_info['prefix'])
                            if not safe_prefix:
                                safe_prefix = f"doc_{doc_type}"

                            base_name = f"{safe_prefix}_{timestamp}"
                            archive_filename = self._generate_unique_name(base_name, used_names, file_ext)
                            archive_filename = f"{folder_name}/{archive_filename}"

                            if os.path.exists(doc_info["path"]) and os.access(doc_info["path"], os.R_OK):
                                zip_file.write(doc_info["path"], archive_filename)
                                added_files += 1
                                logger.info(f"Added file to ZIP: {archive_filename}")
                            else:
                                logger.warning(f"File not accessible: {doc_info['path']}")
                        except Exception as e:
                            logger.error(f"Error adding file to ZIP: {str(e)}")
                            continue

            zip_buffer.seek(0)

            if added_files == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid documents found"
                )

        except Exception as e:
            logger.error(f"Error creating ZIP: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating ZIP archive: {str(e)}"
            )

        filename = f"{folder_name}_documents_{timestamp}.zip"

        return zip_buffer.getvalue(), filename

    # ============================================================
    # ✅ ОПТИМИЗИРОВАННЫЙ МЕТОД create_multiple_users_zip
    # ============================================================
    def create_multiple_users_zip(self, user_ids: List[int]) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив с документами для нескольких пользователей.
        ОПТИМИЗИРОВАН для больших объёмов:
        - Параллельный сбор файлов
        - Быстрое сжатие (ZIP_STORED)
        - Временный файл на диске
        - Прогресс-логирование
        """
        if not user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user IDs provided"
            )

        # Увеличиваем лимит для 300+ пользователей
        if len(user_ids) > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Слишком много пользователей ({len(user_ids)}). Максимум 1000."
            )

        users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()

        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No users found"
            )

        logger.info(f"🚀 Starting optimized ZIP creation for {len(users)} users")
        start_time = time.time()

        # ✅ ШАГ 1: Параллельный сбор всех файлов
        all_files = self._collect_files_parallel(users)

        if not all_files:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid documents found for selected users"
            )

        logger.info(
            f"📦 Collected {len(all_files)} files, total size: {sum(f['size'] for f in all_files) / (1024 * 1024):.1f} MB")

        # ✅ ШАГ 2: Создание ZIP-архива (без сжатия для скорости)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_path = temp_file.name
        temp_file.close()

        compression = zipfile.ZIP_STORED if self.USE_STORED else zipfile.ZIP_DEFLATED
        total_size = 0
        added_count = 0

        try:
            with zipfile.ZipFile(temp_path, 'w', compression) as zip_file:
                for idx, file_info in enumerate(all_files):
                    # Проверяем лимиты
                    if added_count >= self.MAX_FILES_IN_ZIP:
                        logger.warning(f"Reached max files limit: {self.MAX_FILES_IN_ZIP}")
                        break

                    if total_size >= self.MAX_ZIP_SIZE:
                        logger.warning(f"Reached max ZIP size limit: {self.MAX_ZIP_SIZE / (1024 * 1024):.1f} MB")
                        break

                    try:
                        # Добавляем файл в архив
                        zip_file.write(file_info["path"], file_info["archive_name"])
                        total_size += file_info["size"]
                        added_count += 1

                        # Логируем прогресс
                        if added_count % 50 == 0:
                            logger.info(
                                f"📦 Added {added_count}/{len(all_files)} files ({total_size / (1024 * 1024):.1f} MB)")

                    except Exception as e:
                        logger.error(f"Error adding file {file_info['path']}: {str(e)}")
                        continue

            # Проверяем, что есть файлы в архиве
            if added_count == 0:
                os.unlink(temp_path)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid documents could be added to ZIP"
                )

            # Читаем zip-файл
            with open(temp_path, 'rb') as f:
                zip_content = f.read()

            elapsed = time.time() - start_time
            logger.info(
                f"✅ ZIP created: {added_count} files, {total_size / (1024 * 1024):.1f} MB, elapsed: {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"Error creating ZIP: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating ZIP archive: {str(e)}"
            )
        finally:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file: {str(e)}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"documents_{len(users)}_users_{timestamp}.zip"

        return zip_content, filename

    def get_document_file(self, user_id: int, doc_type: str) -> Tuple[bytes, str, str]:
        if doc_type not in self.DOCUMENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown document type: {doc_type}"
            )

        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if doc_type == "diploma":
            education = self.db.query(models.UserEducation).filter(
                models.UserEducation.user_id == user.id,
                models.UserEducation.is_main == True
            ).first()
            if not education:
                education = self.db.query(models.UserEducation).filter(
                    models.UserEducation.user_id == user.id
                ).order_by(models.UserEducation.created_at.desc()).first()

            if not education or not education.diploma_file_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

            file_url = education.diploma_file_url
            filename = education.diploma_file_name or "diploma"
        else:
            additional_info = self.db.query(models.UserAdditionalInfo).filter(
                models.UserAdditionalInfo.user_id == user.id
            ).first()

            if not additional_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

            config = self.DOCUMENT_TYPES[doc_type]
            file_url = getattr(additional_info, config["field_url"], None)
            filename = getattr(additional_info, config["field_name"], None)

            if not file_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

        file_path = file_url.replace("/static/", "app/static/")
        file_path = os.path.normpath(file_path)

        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on server"
            )

        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error reading file"
            )

        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')

        return content, filename, mime_type

    def delete_document(self, user_id: int, doc_type: str) -> Dict[str, str]:
        if doc_type not in self.DOCUMENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown document type: {doc_type}"
            )

        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if doc_type == "diploma":
            education = self.db.query(models.UserEducation).filter(
                models.UserEducation.user_id == user.id,
                models.UserEducation.is_main == True
            ).first()
            if not education:
                education = self.db.query(models.UserEducation).filter(
                    models.UserEducation.user_id == user.id
                ).order_by(models.UserEducation.created_at.desc()).first()

            if not education or not education.diploma_file_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

            file_url = education.diploma_file_url
            file_path = file_url.replace("/static/", "app/static/")
            file_path = os.path.normpath(file_path)

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Error deleting file"
                    )

            education.diploma_file_url = None
            education.diploma_file_name = None
            self.db.commit()

            return {"message": f"Document {doc_type} deleted successfully"}

        else:
            additional_info = self.db.query(models.UserAdditionalInfo).filter(
                models.UserAdditionalInfo.user_id == user.id
            ).first()

            if not additional_info:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

            config = self.DOCUMENT_TYPES[doc_type]
            file_url = getattr(additional_info, config["field_url"], None)

            if not file_url:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )

            file_path = file_url.replace("/static/", "app/static/")
            file_path = os.path.normpath(file_path)

            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Error deleting file"
                    )

            setattr(additional_info, config["field_url"], None)
            setattr(additional_info, config["field_name"], None)
            self.db.commit()

            return {"message": f"Document {doc_type} deleted successfully"}

    def delete_all_user_documents(self, user: models.User) -> None:
        if not user:
            return

        documents = self._get_user_documents(user)

        for doc_type, doc_info in documents.items():
            if doc_info["exists"] and doc_info["path"]:
                try:
                    if os.path.exists(doc_info["path"]) and os.access(doc_info["path"], os.R_OK):
                        os.remove(doc_info["path"])
                        logger.info(f"Deleted file: {doc_info['path']}")
                except Exception as e:
                    logger.error(f"Error deleting file {doc_info['path']}: {str(e)}")

        if user.additional_info:
            for config in self.DOCUMENT_TYPES.values():
                if config["field_url"] != "diploma_file_url":
                    setattr(user.additional_info, config["field_url"], None)
                    setattr(user.additional_info, config["field_name"], None)

        for edu in user.education:
            if edu.diploma_file_url:
                try:
                    file_path = edu.diploma_file_url.replace("/static/", "app/static/")
                    file_path = os.path.normpath(file_path)
                    if os.path.exists(file_path) and os.access(file_path, os.R_OK):
                        os.remove(file_path)
                        logger.info(f"Deleted diploma file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting diploma file: {str(e)}")
                edu.diploma_file_url = None
                edu.diploma_file_name = None

        self.db.commit()

    def get_zip_info(self, user_ids: List[int]) -> Dict[str, Any]:
        """
        Получает информацию о документах для выбранных пользователей
        (размер, количество файлов) без создания ZIP-архива.
        Используется для прогресс-бара на фронтенде.
        """
        if not user_ids:
            return {"total_users": 0, "total_files": 0, "total_size": 0, "users": []}

        users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()

        result = {
            "total_users": len(users),
            "total_files": 0,
            "total_size": 0,
            "users": []
        }

        for user in users:
            documents = self._get_user_documents(user)
            user_files = []
            user_size = 0

            for doc_type, doc_info in documents.items():
                if doc_info["exists"] and doc_info["path"]:
                    size = doc_info.get("size", 0)
                    if size == 0:
                        try:
                            size = os.path.getsize(doc_info["path"])
                        except Exception:
                            size = 0

                    if size > 0:
                        user_files.append({
                            "type": doc_type,
                            "label": doc_info["label"],
                            "size": size,
                            "filename": doc_info["filename"]
                        })
                        user_size += size

            if user_files:
                result["total_files"] += len(user_files)
                result["total_size"] += user_size
                result["users"].append({
                    "id": user.id,
                    "name": self._get_user_display_name(user),
                    "files": user_files,
                    "total_size": user_size
                })

        return result