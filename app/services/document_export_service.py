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

# Настройка логирования
logger = logging.getLogger(__name__)


class DocumentExportService:
    """Сервис для экспорта документов пользователей в ZIP-архивы"""
    
    # Базовый путь для загрузок
    UPLOAD_BASE = "app/static/uploads/profile/documents"
    
    # Маппинг типов документов
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
    
    # ✅ Только безопасные символы (латиница, цифры, подчёркивание, дефис)
    SAFE_FILENAME_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    
    def __init__(self, db: Session):
        self.db = db
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Санитизация имени файла для безопасного использования в ZIP.
        ✅ Только латиница, цифры, подчёркивание, дефис
        ✅ Защита от path traversal
        """
        if not filename:
            return "unknown"
        
        # Удаляем path traversal
        filename = os.path.basename(filename)
        
        # Оставляем только безопасные символы (латиница, цифры, _, -, .)
        safe_name = ''.join(c for c in filename if c in self.SAFE_FILENAME_CHARS or c == '.')
        
        # Если имя пустое - генерируем
        if not safe_name:
            safe_name = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Убираем лишние точки в начале и конце
        safe_name = safe_name.strip('.')
        
        return safe_name
    
    def _sanitize_folder_name(self, name: str) -> str:
        """
        Санитизация имени папки для ZIP.
        ✅ Только латиница, цифры, подчёркивание, дефис
        """
        if not name:
            return "user"
        
        # Удаляем path traversal
        name = os.path.basename(name)
        
        # Оставляем только безопасные символы
        safe_name = ''.join(c for c in name if c in self.SAFE_FILENAME_CHARS)
        
        if not safe_name:
            safe_name = f"user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return safe_name
    
    def _generate_unique_name(self, base_name: str, used_names: set, extension: str = "") -> str:
        """
        Генерирует уникальное имя файла.
        ✅ Добавляет счётчик если имя уже существует
        """
        final_name = f"{base_name}{extension}"
        counter = 1
        
        while final_name in used_names:
            final_name = f"{base_name}_{counter}{extension}"
            counter += 1
        
        used_names.add(final_name)
        return final_name
    
    def _get_user_documents(self, user: models.User) -> Dict[str, Dict[str, Any]]:
        """
        Получает все документы пользователя.
        """
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
                
                documents[doc_type] = {
                    "url": url,
                    "filename": filename,
                    "exists": exists,
                    "path": file_path if exists else None,
                    "label": config["label"],
                    "prefix": config["filename_prefix"]
                }
            else:
                documents[doc_type] = {
                    "url": None,
                    "filename": None,
                    "exists": False,
                    "path": None,
                    "label": config["label"],
                    "prefix": config["filename_prefix"]
                }
        
        return documents
    
    def get_user_documents_list(self, user_id: int) -> Dict[str, Any]:
        """
        Получить список документов пользователя с их статусами.
        """
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        documents = self._get_user_documents(user)
        
        full_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
        if not full_name:
            full_name = self._sanitize_filename(user.full_name.replace(" ", "_")) or f"user_{user.id}"
        else:
            full_name = self._sanitize_filename(full_name)
        
        return {
            "user_id": user.id,
            "full_name": full_name,
            "documents": documents,
            "has_any_document": any(doc["exists"] for doc in documents.values())
        }
    
    def create_user_zip(self, user_id: int) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив со всеми документами пользователя.
        ✅ Уникальные имена файлов внутри архива
        ✅ Только латиница, цифры, подчёркивание
        ✅ Добавлен timestamp для уникальности имени архива
        """
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
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for doc_type, doc_info in documents.items():
                    if doc_info["exists"] and doc_info["path"]:
                        try:
                            # ✅ Получаем расширение файла
                            file_ext = os.path.splitext(doc_info["filename"])[1]
                            if not file_ext:
                                file_ext = ".pdf"  # fallback
                            
                            # ✅ Создаём безопасное имя (только латиница)
                            safe_prefix = self._sanitize_filename(doc_info['prefix'])
                            if not safe_prefix:
                                safe_prefix = f"doc_{doc_type}"
                            
                            # ✅ Добавляем ID пользователя для уникальности
                            base_name = f"{safe_prefix}_{user_id}_{timestamp}"
                            
                            # ✅ Генерируем уникальное имя
                            archive_filename = self._generate_unique_name(base_name, used_names, file_ext)
                            
                            # ✅ Проверяем, что файл существует и доступен
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
        
        # ✅ Имя ZIP-архива — только латиница, цифры, подчёркивание
        full_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
        if not full_name:
            full_name = self._sanitize_filename(user.full_name.replace(" ", "_")) or f"user_{user.id}"
        else:
            full_name = self._sanitize_filename(full_name)
        
        filename = f"{full_name}_documents_{timestamp}.zip"
        
        return zip_buffer.getvalue(), filename
    
    def create_multiple_users_zip(self, user_ids: List[int]) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив с документами нескольких пользователей.
        ✅ Уникальные имена файлов
        ✅ Только латиница, цифры, подчёркивание
        """
        if not user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user IDs provided"
            )
        
        users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No users found"
            )
        
        zip_buffer = BytesIO()
        total_files = 0
        used_names = set()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for user in users:
                    # ✅ Безопасное имя папки (только латиница)
                    folder_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
                    if not folder_name:
                        folder_name = self._sanitize_filename(user.full_name.replace(" ", "_")) or f"user_{user.id}"
                    else:
                        folder_name = self._sanitize_filename(folder_name)
                    folder_name = f"{folder_name}_{user.id}"
                    
                    documents = self._get_user_documents(user)
                    
                    for doc_type, doc_info in documents.items():
                        if doc_info["exists"] and doc_info["path"]:
                            try:
                                if os.path.exists(doc_info["path"]) and os.access(doc_info["path"], os.R_OK):
                                    file_ext = os.path.splitext(doc_info["filename"])[1]
                                    if not file_ext:
                                        file_ext = ".pdf"
                                    
                                    safe_prefix = self._sanitize_filename(doc_info['prefix'])
                                    if not safe_prefix:
                                        safe_prefix = f"doc_{doc_type}"
                                    
                                    base_name = f"{safe_prefix}_{user.id}_{timestamp}"
                                    archive_filename = f"{folder_name}/{base_name}{file_ext}"
                                    
                                    # ✅ Проверяем уникальность полного пути
                                    if archive_filename in used_names:
                                        counter = 1
                                        while f"{folder_name}/{base_name}_{counter}{file_ext}" in used_names:
                                            counter += 1
                                        archive_filename = f"{folder_name}/{base_name}_{counter}{file_ext}"
                                    
                                    used_names.add(archive_filename)
                                    
                                    zip_file.write(doc_info["path"], archive_filename)
                                    total_files += 1
                                    logger.info(f"Added file to ZIP: {archive_filename}")
                            except Exception as e:
                                logger.error(f"Error adding file for user {user.id}: {str(e)}")
                                continue
            
            zip_buffer.seek(0)
            
            if total_files == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid documents found for selected users"
                )
            
        except Exception as e:
            logger.error(f"Error creating ZIP for multiple users: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating ZIP archive: {str(e)}"
            )
        
        filename = f"documents_users_{timestamp}.zip"
        
        return zip_buffer.getvalue(), filename
    
    def get_document_file(self, user_id: int, doc_type: str) -> Tuple[bytes, str, str]:
        """
        Получает содержимое конкретного документа пользователя.
        """
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
        
        if not file_path.startswith(self.UPLOAD_BASE):
            logger.error(f"Path traversal attempt: {file_path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
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
        """
        Удаляет документ пользователя (админское удаление).
        """
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
            
            if not file_path.startswith(self.UPLOAD_BASE):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
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
            
            if not file_path.startswith(self.UPLOAD_BASE):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
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