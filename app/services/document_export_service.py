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

logger = logging.getLogger(__name__)


class DocumentExportService:
    
    UPLOAD_BASE = "app/static/uploads/profile/documents"
    
    # Максимальный размер архива в байтах (500 MB)
    MAX_ZIP_SIZE = 500 * 1024 * 1024
    # Максимальное количество файлов в архиве
    MAX_FILES_IN_ZIP = 1000
    # Таймаут на создание архива (в секундах)
    ZIP_TIMEOUT = 300  # 5 минут
    
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
                
                # Получаем размер файла
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
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
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
    
    def create_multiple_users_zip(self, user_ids: List[int]) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив с документами для нескольких пользователей.
        Оптимизирован для больших объемов данных:
        - Использует временный файл на диске вместо памяти
        - Проверяет лимиты по размеру и количеству файлов
        - Обрабатывает ошибки по каждому файлу отдельно
        - Логирует прогресс
        """
        if not user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user IDs provided"
            )
        
        # Ограничиваем количество пользователей для предотвращения таймаута
        if len(user_ids) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Слишком много пользователей ({len(user_ids)}). Максимум 500."
            )
        
        users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No users found"
            )
        
        logger.info(f"Starting ZIP creation for {len(users)} users")
        start_time = time.time()
        
        # Используем временный файл на диске вместо BytesIO
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_path = temp_file.name
        temp_file.close()
        
        total_files = 0
        failed_files = 0
        used_names = set()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        total_size = 0
        
        try:
            with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for user_idx, user in enumerate(users):
                    # Логируем прогресс каждые 10 пользователей
                    if user_idx % 10 == 0:
                        logger.info(f"Processing user {user_idx + 1}/{len(users)}...")
                    
                    folder_name = self._get_user_folder_name(user)
                    documents = self._get_user_documents(user)
                    
                    for doc_type, doc_info in documents.items():
                        if doc_info["exists"] and doc_info["path"]:
                            try:
                                # Проверяем лимиты
                                if total_files >= self.MAX_FILES_IN_ZIP:
                                    logger.warning(f"Reached max files limit: {self.MAX_FILES_IN_ZIP}")
                                    break
                                
                                if total_size >= self.MAX_ZIP_SIZE:
                                    logger.warning(f"Reached max ZIP size limit: {self.MAX_ZIP_SIZE / (1024*1024):.1f} MB")
                                    break
                                
                                if not os.path.exists(doc_info["path"]) or not os.access(doc_info["path"], os.R_OK):
                                    logger.warning(f"File not accessible: {doc_info['path']}")
                                    failed_files += 1
                                    continue
                                
                                # Проверяем размер файла
                                file_size = doc_info.get("size", 0)
                                if file_size == 0:
                                    try:
                                        file_size = os.path.getsize(doc_info["path"])
                                    except Exception:
                                        file_size = 0
                                
                                # Пропускаем пустые файлы
                                if file_size == 0:
                                    logger.warning(f"Skipping empty file: {doc_info['path']}")
                                    failed_files += 1
                                    continue
                                
                                # Пропускаем слишком большие файлы (> 50 MB)
                                if file_size > 50 * 1024 * 1024:
                                    logger.warning(f"Skipping too large file ({file_size / (1024*1024):.1f} MB): {doc_info['path']}")
                                    failed_files += 1
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
                                if archive_filename in used_names:
                                    counter = 1
                                    while f"{folder_name}/{base_name}_{counter}{file_ext}" in used_names:
                                        counter += 1
                                    archive_filename = f"{folder_name}/{base_name}_{counter}{file_ext}"
                                
                                used_names.add(archive_filename)
                                
                                # Добавляем файл в архив
                                zip_file.write(doc_info["path"], archive_filename)
                                total_files += 1
                                total_size += file_size
                                
                                if total_files % 50 == 0:
                                    logger.info(f"Added {total_files} files to ZIP ({total_size / (1024*1024):.1f} MB)")
                                    
                            except Exception as e:
                                logger.error(f"Error adding file for user {user.id} ({doc_type}): {str(e)}")
                                failed_files += 1
                                continue
                    
                    # Проверяем лимиты после каждого пользователя
                    if total_files >= self.MAX_FILES_IN_ZIP or total_size >= self.MAX_ZIP_SIZE:
                        logger.warning(f"Stopping due to limits: files={total_files}, size={total_size / (1024*1024):.1f} MB")
                        break
            
            # Проверяем, что есть файлы в архиве
            if total_files == 0:
                os.unlink(temp_path)
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid documents found for selected users"
                )
            
            # Читаем zip-файл в память для отправки
            with open(temp_path, 'rb') as f:
                zip_content = f.read()
            
            elapsed = time.time() - start_time
            logger.info(f"ZIP created successfully: {total_files} files, {total_size / (1024*1024):.1f} MB, {failed_files} failed, elapsed: {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"Error creating ZIP for multiple users: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating ZIP archive: {str(e)}"
            )
        finally:
            # Удаляем временный файл
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_path}: {str(e)}")
        
        filename = f"documents_users_{timestamp}.zip"
        
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