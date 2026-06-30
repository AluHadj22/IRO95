# app/services/document_export_service.py
import os
import zipfile
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models


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
            "filename_prefix": "СНИЛС"
        },
        "diploma": {
            "field_url": "diploma_file_url",
            "field_name": "diploma_file_name",
            "label": "Диплом",
            "filename_prefix": "Диплом"
        },
        "passport": {
            "field_url": "passport_file_url",
            "field_name": "passport_file_name",
            "label": "Паспорт",
            "filename_prefix": "Паспорт"
        },
        "inn": {
            "field_url": "inn_file_url",
            "field_name": "inn_file_name",
            "label": "ИНН",
            "filename_prefix": "ИНН"
        },
        "marriage": {
            "field_url": "marriage_certificate_file_url",
            "field_name": "marriage_certificate_file_name",
            "label": "Свидетельство о браке",
            "filename_prefix": "Свидетельство_о_браке"
        }
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def _get_user_documents(self, user: models.User) -> Dict[str, Dict[str, Any]]:
        """
        Получает все документы пользователя.
        
        Returns:
            Dict: {doc_type: {"url": str, "filename": str, "exists": bool, "path": str}}
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
        
        # СНИЛС
        if additional_info:
            for doc_type, config in self.DOCUMENT_TYPES.items():
                if doc_type == "diploma":
                    # Для диплома данные из education
                    if education:
                        url = getattr(education, "diploma_file_url", None)
                        filename = getattr(education, "diploma_file_name", None)
                    else:
                        url = None
                        filename = None
                else:
                    # Для остальных из additional_info
                    url = getattr(additional_info, config["field_url"], None)
                    filename = getattr(additional_info, config["field_name"], None)
                
                if url and filename:
                    # Определяем реальный путь к файлу
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
        else:
            # Если нет дополнительной информации, все документы отсутствуют
            for doc_type, config in self.DOCUMENT_TYPES.items():
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
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Dict: Информация о документах пользователя
        """
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        documents = self._get_user_documents(user)
        
        # Формируем ФИО для имени файла
        full_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
        if not full_name:
            full_name = user.full_name.replace(" ", "_") or f"user_{user.id}"
        
        return {
            "user_id": user.id,
            "full_name": full_name,
            "documents": documents,
            "has_any_document": any(doc["exists"] for doc in documents.values())
        }
    
    def create_user_zip(self, user_id: int) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив со всеми документами пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Tuple[bytes, str]: (содержимое ZIP, имя файла)
        """
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        documents = self._get_user_documents(user)
        
        # Проверяем, есть ли хоть один документ
        has_documents = any(doc["exists"] for doc in documents.values())
        if not has_documents:
            raise HTTPException(status_code=404, detail="No documents found for this user")
        
        # Создаем ZIP в памяти
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for doc_type, doc_info in documents.items():
                if doc_info["exists"] and doc_info["path"]:
                    # Определяем имя файла в архиве
                    file_ext = os.path.splitext(doc_info["filename"])[1]
                    archive_filename = f"{doc_info['prefix']}{file_ext}"
                    
                    # Добавляем файл в архив
                    zip_file.write(doc_info["path"], archive_filename)
        
        zip_buffer.seek(0)
        
        # Формируем имя файла
        full_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
        if not full_name:
            full_name = user.full_name.replace(" ", "_") or f"user_{user.id}"
        
        filename = f"{full_name}_документы.zip"
        
        return zip_buffer.getvalue(), filename
    
    def create_multiple_users_zip(self, user_ids: List[int]) -> Tuple[bytes, str]:
        """
        Создает ZIP-архив с документами нескольких пользователей.
        Каждый пользователь получает отдельную папку в архиве.
        
        Args:
            user_ids: Список ID пользователей
            
        Returns:
            Tuple[bytes, str]: (содержимое ZIP, имя файла)
        """
        if not user_ids:
            raise HTTPException(status_code=400, detail="No user IDs provided")
        
        users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        
        if not users:
            raise HTTPException(status_code=404, detail="No users found")
        
        # Создаем ZIP в памяти
        zip_buffer = BytesIO()
        total_files = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for user in users:
                # Формируем имя папки для пользователя
                folder_name = f"{user.last_name or ''}_{user.first_name or ''}_{user.middle_name or ''}".strip("_")
                if not folder_name:
                    folder_name = user.full_name.replace(" ", "_") or f"user_{user.id}"
                folder_name = f"{folder_name}_{user.id}"
                
                documents = self._get_user_documents(user)
                
                for doc_type, doc_info in documents.items():
                    if doc_info["exists"] and doc_info["path"]:
                        # Определяем имя файла в архиве
                        file_ext = os.path.splitext(doc_info["filename"])[1]
                        archive_filename = f"{folder_name}/{doc_info['prefix']}{file_ext}"
                        
                        # Добавляем файл в архив
                        zip_file.write(doc_info["path"], archive_filename)
                        total_files += 1
        
        zip_buffer.seek(0)
        
        if total_files == 0:
            raise HTTPException(status_code=404, detail="No documents found for selected users")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"документы_пользователей_{timestamp}.zip"
        
        return zip_buffer.getvalue(), filename
    
    def get_document_file(self, user_id: int, doc_type: str) -> Tuple[bytes, str, str]:
        """
        Получает содержимое конкретного документа пользователя.
        
        Args:
            user_id: ID пользователя
            doc_type: Тип документа (snils, diploma, passport, inn, marriage)
            
        Returns:
            Tuple[bytes, str, str]: (содержимое файла, имя файла, mime-тип)
        """
        if doc_type not in self.DOCUMENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown document type: {doc_type}")
        
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Определяем, откуда брать данные
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
                raise HTTPException(status_code=404, detail="Document not found")
            
            file_url = education.diploma_file_url
            filename = education.diploma_file_name or "диплом"
        else:
            additional_info = self.db.query(models.UserAdditionalInfo).filter(
                models.UserAdditionalInfo.user_id == user.id
            ).first()
            
            if not additional_info:
                raise HTTPException(status_code=404, detail="Document not found")
            
            config = self.DOCUMENT_TYPES[doc_type]
            file_url = getattr(additional_info, config["field_url"], None)
            filename = getattr(additional_info, config["field_name"], None)
            
            if not file_url:
                raise HTTPException(status_code=404, detail="Document not found")
        
        # Определяем реальный путь
        file_path = file_url.replace("/static/", "app/static/")
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found on server")
        
        # Читаем файл
        with open(file_path, "rb") as f:
            content = f.read()
        
        # Определяем mime-тип
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
        
        Args:
            user_id: ID пользователя
            doc_type: Тип документа
            
        Returns:
            Dict: Сообщение об успехе
        """
        if doc_type not in self.DOCUMENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unknown document type: {doc_type}")
        
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Определяем, откуда брать данные
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
                raise HTTPException(status_code=404, detail="Document not found")
            
            file_url = education.diploma_file_url
            
            # Удаляем физический файл
            file_path = file_url.replace("/static/", "app/static/")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Очищаем поля в БД
            education.diploma_file_url = None
            education.diploma_file_name = None
            self.db.commit()
            
            return {"message": f"Document {doc_type} deleted successfully"}
        
        else:
            additional_info = self.db.query(models.UserAdditionalInfo).filter(
                models.UserAdditionalInfo.user_id == user.id
            ).first()
            
            if not additional_info:
                raise HTTPException(status_code=404, detail="Document not found")
            
            config = self.DOCUMENT_TYPES[doc_type]
            file_url = getattr(additional_info, config["field_url"], None)
            
            if not file_url:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Удаляем физический файл
            file_path = file_url.replace("/static/", "app/static/")
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Очищаем поля в БД
            setattr(additional_info, config["field_url"], None)
            setattr(additional_info, config["field_name"], None)
            self.db.commit()
            
            return {"message": f"Document {doc_type} deleted successfully"}