# app/services/excel_export_service.py
import os
import json
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session
from app import models


class ExcelExportService:
    """Сервис для экспорта данных пользователей в Excel по шаблону"""
    
    # Путь к шаблону
    TEMPLATE_PATH = "app/static/templates/export_template.xlsx"
    
    # Маппинг колонок шаблона (индексы начинаются с 1)
    # В шаблоне: колонка A - пустая (индекс 1), B - пустая (индекс 2), C - Муниципалитет (индекс 3) и т.д.
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
    
    def _get_user_export_data(self, user: models.User) -> Dict[str, Any]:
        """Собирает данные пользователя для экспорта"""
        
        # Получаем текущее место работы (is_current=True)
        current_work = self.db.query(models.UserWork).filter(
            models.UserWork.user_id == user.id,
            models.UserWork.is_current == True
        ).first()
        
        # Если нет текущего места работы, берем последнее добавленное
        if not current_work:
            current_work = self.db.query(models.UserWork).filter(
                models.UserWork.user_id == user.id
            ).order_by(models.UserWork.created_at.desc()).first()
        
        # Получаем основное образование (is_main=True)
        main_education = self.db.query(models.UserEducation).filter(
            models.UserEducation.user_id == user.id,
            models.UserEducation.is_main == True
        ).first()
        
        # Если нет основного, берем первое попавшееся
        if not main_education:
            main_education = self.db.query(models.UserEducation).filter(
                models.UserEducation.user_id == user.id
            ).order_by(models.UserEducation.created_at.desc()).first()
        
        # Получаем дополнительную информацию
        additional_info = self.db.query(models.UserAdditionalInfo).filter(
            models.UserAdditionalInfo.user_id == user.id
        ).first()
        
        # Обработка предметов
        subjects = []
        if current_work and current_work.subjects:
            try:
                subjects = json.loads(current_work.subjects)
            except:
                subjects = []
        
        # Форматирование даты рождения
        birth_date_str = ""
        if user.birth_date:
            birth_date_str = user.birth_date.strftime("%d.%m.%Y")
        
        # Форматирование пола
        gender_str = ""
        if user.gender == "male":
            gender_str = "Мужской"
        elif user.gender == "female":
            gender_str = "Женский"
        
        # Форматирование телефона
        phone_value = user.phone_raw or user.phone or ""
        if phone_value and not phone_value.startswith('+'):
            phone_value = f"+7{phone_value}"
        
        return {
            "municipality": user.municipality or "",
            "organization": current_work.organization if current_work else "",
            "last_name": user.last_name or "",
            "first_name": user.first_name or "",
            "middle_name": user.middle_name or "",
            "birth_date": birth_date_str,
            "gender": gender_str,
            "snils": additional_info.snils if additional_info else "",
            "position": current_work.position if current_work else "",
            "activity_type": current_work.activity_type if current_work else "",
            "subjects": "; ".join(subjects) if subjects else "",
            "education": main_education.education_level if main_education else "",
            "document_series": main_education.document_series if main_education else "",
            "document_number": main_education.document_number if main_education else "",
            "teaching_experience": current_work.teaching_experience_years if current_work and current_work.teaching_experience_years is not None else "",
            "work_experience": current_work.work_experience_years if current_work and current_work.work_experience_years is not None else "",
            "email": user.email or "",
            "phone": phone_value
        }
    
    def _get_headers(self) -> List[str]:
        """Возвращает список заголовков колонок"""
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
        """
        Экспортирует данные пользователей в Excel по шаблону.
        
        Args:
            user_ids: Список ID пользователей для экспорта. Если None - экспортирует всех.
            
        Returns:
            BytesIO: Excel файл в виде байтового потока
        """
        # Получаем пользователей
        if user_ids:
            users = self.db.query(models.User).filter(models.User.id.in_(user_ids)).all()
        else:
            users = self.db.query(models.User).all()
        
        # Если пользователей нет, возвращаем пустой шаблон
        if not users:
            return self._get_empty_template()
        
        # Загружаем шаблон
        wb = self._load_template()
        ws = wb.active
        
        # Определяем строку, с которой начинаются данные (после заголовков)
        # В шаблоне заголовки находятся на строке 4 (индекс 4, т.к. строки с 1)
        start_row = 5  # Строка 5 - первая строка данных
        
        # Заполняем данными
        for row_idx, user in enumerate(users, start=start_row):
            data = self._get_user_export_data(user)
            
            # Заполняем каждую колонку
            for field, col_idx in self.COLUMN_MAPPING.items():
                value = data.get(field, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                # Включаем перенос текста для всех ячеек с данными
                cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
        
        # Настраиваем высоту строк для лучшего отображения
        for row in range(start_row, start_row + len(users)):
            ws.row_dimensions[row].height = 30
        
        # Сохраняем в BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return output
    
    def export_single_user(self, user_id: int) -> Optional[BytesIO]:
        """
        Экспортирует данные одного пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            BytesIO: Excel файл или None, если пользователь не найден
        """
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            return None
        
        return self.export_users_to_excel([user_id])
    
    def _load_template(self) -> Any:
        """Загружает Excel шаблон из файла"""
        template_path = os.path.join(os.getcwd(), self.TEMPLATE_PATH)
        
        if os.path.exists(template_path):
            return load_workbook(template_path)
        else:
            # Если шаблон не найден, создаем его
            return self._create_template()
    
    def _create_template(self) -> Any:
        """Создает шаблон Excel с заголовками"""
        from openpyxl import Workbook
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Данные пользователей"
        
        # Заголовки (строка 4)
        headers = self._get_headers()
        header_row = 4
        
        # Стили для заголовков
        header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='0057A4', end_color='0057A4', fill_type='solid')
        header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        # Заполняем заголовки начиная с колонки C (индекс 3)
        for col_idx, header in enumerate(headers, start=3):  # Начинаем с колонки C (индекс 3)
            cell = ws.cell(row=header_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Настройка ширины колонок (увеличиваем для длинных текстов)
        column_widths = {
            1: 6,   # A - пустая
            2: 6,   # B - пустая
            3: 30,  # C - Муниципалитет
            4: 50,  # D - Место работы (увеличено)
            5: 22,  # E - Фамилия
            6: 22,  # F - Имя
            7: 22,  # G - Отчество
            8: 22,  # H - Дата рождения
            9: 16,  # I - Пол
            10: 20, # J - СНИЛС
            11: 30, # K - Должность (увеличено)
            12: 25, # L - Вид деятельности
            13: 35, # M - Предмет (увеличено)
            14: 30, # N - Образование (увеличено)
            15: 20, # O - Серия диплома
            16: 20, # P - Номер диплома
            17: 18, # Q - Пед. стаж
            18: 18, # R - Стаж в должности
            19: 35, # S - Email
            20: 20  # T - Телефон
        }
        
        for col_idx, width in column_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        # Высота строки заголовков
        ws.row_dimensions[header_row].height = 35
        
        # Заморозка панели
        ws.freeze_panes = 'C5'
        
        # Сохраняем шаблон для будущего использования
        os.makedirs(os.path.dirname(self.TEMPLATE_PATH), exist_ok=True)
        wb.save(self.TEMPLATE_PATH)
        
        return wb
    
    def _get_empty_template(self) -> BytesIO:
        """Возвращает пустой шаблон с заголовками"""
        wb = self._load_template()
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output
    
    def get_users_list_with_data(self) -> List[Dict[str, Any]]:
        """
        Возвращает список пользователей с их данными для отображения в админке.
        
        Returns:
            List[Dict]: Список пользователей с данными
        """
        users = self.db.query(models.User).all()
        result = []
        
        for user in users:
            data = self._get_user_export_data(user)
            result.append({
                "id": user.id,
                "email": user.email,
                "role": user.role.value if user.role else "teacher",
                "is_blocked": user.is_blocked,
                "created_at": user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "",
                "full_name": f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip() or user.full_name,
                "data": data,
                "has_complete_profile": user.is_profile_complete()
            })
        
        return result


def generate_export_filename(export_type: str = "all", user_id: int = None) -> str:
    """
    Генерирует имя файла для экспорта.
    
    Args:
        export_type: Тип экспорта ('all' или 'single')
        user_id: ID пользователя (для одиночного экспорта)
        
    Returns:
        str: Имя файла
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if export_type == "single" and user_id:
        return f"user_{user_id}_data_{timestamp}.xlsx"
    else:
        return f"all_users_data_{timestamp}.xlsx"