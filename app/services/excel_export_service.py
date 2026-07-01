# app/services/excel_export_service.py
import os
import json
import re
import logging
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session
from app import models
from app.services.encryption_service import EncryptionService

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализируем сервис шифрования
encryption = EncryptionService()


class ExcelExportService:
    """Сервис для экспорта данных пользователей в Excel по шаблону"""
    
    # Путь к шаблону
    TEMPLATE_PATH = "app/static/templates/export_template.xlsx"
    
    # Маппинг колонок шаблона (индексы начинаются с 1)
    COLUMN_MAPPING = {
        "municipality": 3,   # C
        "organization": 4,   # D
        "last_name": 5,      # E
        "first_name": 6,     # F
        "middle_name": 7,    # G
        "birth_date": 8,     # H
        "gender": 9,         # I
        "snils": 10,         # J
        "position": 11,      # K
        "activity_type": 12, # L
        "subjects": 13,      # M
        "education": 14,     # N
        "document_series": 15, # O
        "document_number": 16, # P
        "teaching_experience": 17, # Q
        "work_experience": 18, # R
        "email": 19,         # S
        "phone": 20          # T
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def _escape_excel_string(self, value: Any) -> str:
        """
        Экранирует строку для безопасной вставки в Excel.
        ✅ Защита от формульных инъекций (формулы, начинающиеся с =, +, -, @)
        ✅ Защита от HTML-инъекций
        """
        if value is None:
            return ""
        
        if not isinstance(value, str):
            return str(value)
        
        if not value:
            return ""
        
        # Защита от формульных инъекций
        if value and value[0] in '=+-@':
            return "'" + value
        
        # Защита от HTML-инъекций
        value = value.replace('<', '&lt;').replace('>', '&gt;')
        
        return value
    
    def _sanitize_snils(self, snils: str) -> str:
        """
        Возвращает СНИЛС в полностью читабельном виде.
        ✅ Расшифровывает зашифрованный СНИЛС
        ✅ БЕЗ маскировки — показывает полный номер
        """
        if not snils:
            return ""
        
        # Расшифровываем (если зашифрован)
        try:
            decrypted = encryption.decrypt(snils)
            if decrypted:
                return decrypted
        except Exception:
            # Если не удалось расшифровать - оставляем как есть
            pass
        
        return snils
    
    def _sanitize_phone(self, phone: str) -> str:
        """
        Санитизация телефона для экспорта.
        ✅ Приводим к единому формату
        """
        if not phone:
            return ""
        
        cleaned = re.sub(r'[^0-9+]', '', phone)
        
        if cleaned.startswith('8') and len(cleaned) == 11:
            cleaned = '+7' + cleaned[1:]
        
        if not cleaned.startswith('+') and len(cleaned) >= 10:
            if cleaned.startswith('7'):
                cleaned = '+' + cleaned
            else:
                cleaned = '+7' + cleaned
        
        return cleaned
    
    def _get_user_export_data(self, user: models.User) -> Dict[str, Any]:
        """Собирает данные пользователя для экспорта с санитизацией"""
        
        current_work = self.db.query(models.UserWork).filter(
            models.UserWork.user_id == user.id,
            models.UserWork.is_current == True
        ).first()
        
        if not current_work:
            current_work = self.db.query(models.UserWork).filter(
                models.UserWork.user_id == user.id
            ).order_by(models.UserWork.created_at.desc()).first()
        
        main_education = self.db.query(models.UserEducation).filter(
            models.UserEducation.user_id == user.id,
            models.UserEducation.is_main == True
        ).first()
        
        if not main_education:
            main_education = self.db.query(models.UserEducation).filter(
                models.UserEducation.user_id == user.id
            ).order_by(models.UserEducation.created_at.desc()).first()
        
        additional_info = self.db.query(models.UserAdditionalInfo).filter(
            models.UserAdditionalInfo.user_id == user.id
        ).first()
        
        subjects = []
        if current_work and current_work.subjects:
            try:
                subjects = json.loads(current_work.subjects)
                if not isinstance(subjects, list):
                    subjects = []
            except (json.JSONDecodeError, TypeError):
                subjects = []
        
        birth_date_str = ""
        if user.birth_date:
            try:
                birth_date_str = user.birth_date.strftime("%d.%m.%Y")
            except Exception:
                birth_date_str = ""
        
        gender_str = ""
        if user.gender == "male":
            gender_str = "Мужской"
        elif user.gender == "female":
            gender_str = "Женский"
        
        # Получаем СНИЛС (расшифровываем, БЕЗ маскировки)
        snils_value = ""
        if additional_info and additional_info.snils:
            snils_value = self._sanitize_snils(additional_info.snils)
        
        phone_value = user.phone_raw or user.phone or ""
        phone_value = self._sanitize_phone(phone_value)
        
        return {
            "municipality": self._escape_excel_string(user.municipality),
            "organization": self._escape_excel_string(current_work.organization if current_work else ""),
            "last_name": self._escape_excel_string(user.last_name),
            "first_name": self._escape_excel_string(user.first_name),
            "middle_name": self._escape_excel_string(user.middle_name),
            "birth_date": self._escape_excel_string(birth_date_str),
            "gender": self._escape_excel_string(gender_str),
            "snils": self._escape_excel_string(snils_value),  # ✅ Полностью читабельный СНИЛС
            "position": self._escape_excel_string(current_work.position if current_work else ""),
            "activity_type": self._escape_excel_string(current_work.activity_type if current_work else ""),
            "subjects": self._escape_excel_string("; ".join(subjects) if subjects else ""),
            "education": self._escape_excel_string(main_education.education_level if main_education else ""),
            "document_series": self._escape_excel_string(main_education.document_series if main_education else ""),
            "document_number": self._escape_excel_string(main_education.document_number if main_education else ""),
            "teaching_experience": current_work.teaching_experience_years if current_work and current_work.teaching_experience_years is not None else "",
            "work_experience": current_work.work_experience_years if current_work and current_work.work_experience_years is not None else "",
            "email": self._escape_excel_string(user.email),
            "phone": self._escape_excel_string(phone_value)
        }
    
    def _get_headers(self) -> List[str]:
        return [
            "Муниципалитет",
            "Место работы",
            "Фамилия",
            "Имя",
            "Отчество",
            "Дата рождения получателя",
            "Пол получателя",
            "СНИЛС",
            "Должность",
            "Вид деятельности",
            "Предмет",
            "Образование",
            "Серия диплома",
            "Номер диплома",
            "Педагогический стаж",
            "Стаж в должности",
            "Личный электронный адрес",
            "Номер телефона"
        ]
    
    def export_users_to_excel(self, user_ids: List[int] = None) -> BytesIO:
        try:
            if user_ids:
                users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()
            else:
                users = self.db.query(models.User).all()
            
            if not users:
                return self._get_empty_template()
            
            wb = self._load_template()
            ws = wb.active
            
            start_row = 5
            
            for row_idx, user in enumerate(users, start=start_row):
                data = self._get_user_export_data(user)
                
                for field, col_idx in self.COLUMN_MAPPING.items():
                    value = data.get(field, "")
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            
            for row in range(start_row, start_row + len(users)):
                ws.row_dimensions[row].height = 30
            
            output = BytesIO()
            wb.save(output)
            output.seek(0)
            
            logger.info(f"Exported {len(users)} users to Excel")
            return output
            
        except Exception as e:
            logger.error(f"Error exporting users to Excel: {str(e)}")
            raise
    
    def export_single_user(self, user_id: int) -> Optional[BytesIO]:
        try:
            user = self.db.query(models.User).filter(models.User.id == user_id).first()
            if not user:
                return None
            
            return self.export_users_to_excel([user_id])
        except Exception as e:
            logger.error(f"Error exporting single user {user_id}: {str(e)}")
            return None
    
    def _load_template(self) -> Any:
        template_path = os.path.join(os.getcwd(), self.TEMPLATE_PATH)
        
        if os.path.exists(template_path):
            return load_workbook(template_path)
        else:
            return self._create_template()
    
    def _create_template(self) -> Any:
        from openpyxl import Workbook
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Данные пользователей"
        
        headers = self._get_headers()
        header_row = 4
        
        header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='0057A4', end_color='0057A4', fill_type='solid')
        header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        for col_idx, header in enumerate(headers, start=3):
            cell = ws.cell(row=header_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        column_widths = {
            1: 6, 2: 6, 3: 30, 4: 50, 5: 22, 6: 22, 7: 22,
            8: 22, 9: 16, 10: 20, 11: 30, 12: 25, 13: 35,
            14: 30, 15: 20, 16: 20, 17: 18, 18: 18, 19: 35, 20: 20
        }
        
        for col_idx, width in column_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        ws.row_dimensions[header_row].height = 35
        ws.freeze_panes = 'C5'
        
        os.makedirs(os.path.dirname(self.TEMPLATE_PATH), exist_ok=True)
        wb.save(self.TEMPLATE_PATH)
        
        return wb
    
    def _get_empty_template(self) -> BytesIO:
        wb = self._load_template()
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output
    
    def get_users_list_with_data(self) -> List[Dict[str, Any]]:
        try:
            users = self.db.query(models.User).all()
            result = []
            
            for user in users:
                data = self._get_user_export_data(user)
                
                full_name = f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip()
                if not full_name:
                    full_name = user.full_name or ""
                
                result.append({
                    "id": user.id,
                    "email": self._escape_excel_string(user.email),
                    "role": user.role.value if user.role else "teacher",
                    "is_blocked": user.is_blocked,
                    "created_at": user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "",
                    "full_name": self._escape_excel_string(full_name),
                    "data": data,
                    "has_complete_profile": user.is_profile_complete()
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting users list: {str(e)}")
            return []


def generate_export_filename(export_type: str = "all", user_id: int = None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if export_type == "single" and user_id:
        return f"user_{user_id}_data_{timestamp}.xlsx"
    else:
        return f"all_users_data_{timestamp}.xlsx"