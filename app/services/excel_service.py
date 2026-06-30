# app/services/excel_service.py
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from io import BytesIO
from typing import List, Dict
from sqlalchemy.orm import Session
from app import models
import json
from datetime import datetime


def generate_registrations_excel(data: List[Dict], course_title: str = "") -> BytesIO:
    """Генерация Excel файла с регистрациями (упрощенный вариант)"""
    wb = Workbook()
    ws = wb.active
    ws.title = f"Регистрации"
    
    # Стили
    header_font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='0057A4', end_color='0057A4', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    cell_alignment = Alignment(horizontal='left', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Заголовок курса
    if course_title:
        ws.merge_cells('A1:G1')
        title_cell = ws['A1']
        title_cell.value = f"Регистрации на курс: {course_title}"
        title_cell.font = Font(name='Arial', size=14, bold=True)
        title_cell.alignment = Alignment(horizontal='center')
    
    # Заголовки колонок
    headers = ["№", "ФИО", "Email", "Телефон", "Должность", "Организация", "Оплата", "Дата регистрации"]
    start_row = 3 if course_title else 1
    
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
    
    # Данные
    for idx, row in enumerate(data, start=start_row + 1):
        ws.cell(row=idx, column=1, value=idx - start_row).border = thin_border
        ws.cell(row=idx, column=2, value=row.get('full_name', '')).border = thin_border
        ws.cell(row=idx, column=3, value=row.get('email', '')).border = thin_border
        ws.cell(row=idx, column=4, value=row.get('phone', '')).border = thin_border
        ws.cell(row=idx, column=5, value=row.get('position', '')).border = thin_border
        ws.cell(row=idx, column=6, value=row.get('organization', '')).border = thin_border
        ws.cell(row=idx, column=7, value=row.get('is_paid', 'Нет')).border = thin_border
        ws.cell(row=idx, column=8, value=row.get('registered_at', '')).border = thin_border
    
    # Настройка ширины колонок
    column_widths = [5, 30, 30, 15, 25, 35, 10, 20]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[chr(64 + i)].width = width
    
    # Заморозка панели
    ws.freeze_panes = f'A{start_row + 1}'
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ============================================================
# НОВАЯ ФУНКЦИЯ: ЭКСПОРТ РЕГИСТРАЦИЙ С ПОЛНЫМИ ДАННЫМИ
# ============================================================

def generate_full_registrations_excel(
    db: Session, 
    course_id: int, 
    course_title: str = ""
) -> BytesIO:
    """
    Генерация Excel файла с регистрациями на курс с ПОЛНЫМИ данными пользователей.
    Использует те же поля, что и ExcelExportService.
    """
    from app.services.excel_export_service import ExcelExportService
    
    # Получаем все регистрации на курс
    registrations = db.query(models.CourseRegistration, models.User).join(
        models.User
    ).filter(models.CourseRegistration.course_id == course_id).order_by(
        models.CourseRegistration.registered_at.desc()
    ).all()
    
    if not registrations:
        # Если нет регистраций, возвращаем пустой шаблон
        return generate_empty_registrations_excel(course_title)
    
    # Создаем ExcelExportService для получения данных пользователей
    export_service = ExcelExportService(db)
    
    # Собираем данные для каждого пользователя
    data = []
    for idx, (reg, user) in enumerate(registrations, 1):
        user_data = export_service._get_user_export_data(user)
        data.append({
            "number": idx,
            "municipality": user_data.get("municipality", ""),
            "organization": user_data.get("organization", ""),
            "last_name": user_data.get("last_name", ""),
            "first_name": user_data.get("first_name", ""),
            "middle_name": user_data.get("middle_name", ""),
            "birth_date": user_data.get("birth_date", ""),
            "gender": user_data.get("gender", ""),
            "snils": user_data.get("snils", ""),
            "position": user_data.get("position", ""),
            "activity_type": user_data.get("activity_type", ""),
            "subjects": user_data.get("subjects", ""),
            "education": user_data.get("education", ""),
            "document_series": user_data.get("document_series", ""),
            "document_number": user_data.get("document_number", ""),
            "teaching_experience": user_data.get("teaching_experience", ""),
            "work_experience": user_data.get("work_experience", ""),
            "email": user_data.get("email", ""),
            "phone": user_data.get("phone", ""),
            "registered_at": reg.registered_at.strftime("%d.%m.%Y %H:%M") if reg.registered_at else "",
            "is_paid": "Да" if reg.is_paid else "Нет"
        })
    
    return generate_full_registrations_excel_from_data(data, course_title)


def generate_full_registrations_excel_from_data(data: List[Dict], course_title: str = "") -> BytesIO:
    """
    Генерация Excel файла с ПОЛНЫМИ данными регистраций.
    
    Args:
        data: Список словарей с данными пользователей
        course_title: Название курса (для заголовка)
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Регистрации"
    
    # Стили
    header_font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='0057A4', end_color='0057A4', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    cell_alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    start_row = 1
    
    # Заголовок курса (если есть)
    if course_title:
        ws.merge_cells('A1:T1')
        title_cell = ws['A1']
        title_cell.value = f"Регистрации на курс: {course_title}"
        title_cell.font = Font(name='Arial', size=14, bold=True)
        title_cell.alignment = Alignment(horizontal='center')
        start_row = 3
    else:
        start_row = 1
    
    # Заголовки колонок (полный набор)
    headers = [
        "№", "Муниципалитет", "Место работы", "Фамилия", "Имя", "Отчество",
        "Дата рождения", "Пол", "СНИЛС", "Должность", "Вид деятельности",
        "Предмет", "Образование", "Серия диплома", "Номер диплома",
        "Педагогический стаж", "Стаж в должности", "Email", "Телефон",
        "Статус оплаты", "Дата регистрации"
    ]
    
    # Индексы колонок (с 1)
    col_indices = {
        "number": 1,
        "municipality": 2,
        "organization": 3,
        "last_name": 4,
        "first_name": 5,
        "middle_name": 6,
        "birth_date": 7,
        "gender": 8,
        "snils": 9,
        "position": 10,
        "activity_type": 11,
        "subjects": 12,
        "education": 13,
        "document_series": 14,
        "document_number": 15,
        "teaching_experience": 16,
        "work_experience": 17,
        "email": 18,
        "phone": 19,
        "is_paid": 20,
        "registered_at": 21
    }
    
    # Заполняем заголовки
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
    
    # Заполняем данные
    for row_idx, row_data in enumerate(data, start=start_row + 1):
        for field, col_idx in col_indices.items():
            value = row_data.get(field, "")
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = cell_alignment
            cell.border = thin_border
    
    # Настройка ширины колонок
    column_widths = {
        1: 5,   # №
        2: 30,  # Муниципалитет
        3: 40,  # Место работы
        4: 20,  # Фамилия
        5: 20,  # Имя
        6: 20,  # Отчество
        7: 18,  # Дата рождения
        8: 15,  # Пол
        9: 20,  # СНИЛС
        10: 25, # Должность
        11: 25, # Вид деятельности
        12: 30, # Предмет
        13: 25, # Образование
        14: 18, # Серия диплома
        15: 18, # Номер диплома
        16: 18, # Педагогический стаж
        17: 18, # Стаж в должности
        18: 30, # Email
        19: 18, # Телефон
        20: 15, # Статус оплаты
        21: 20  # Дата регистрации
    }
    
    for col_idx, width in column_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # Устанавливаем высоту строк
    ws.row_dimensions[start_row].height = 35
    for row_idx in range(start_row + 1, start_row + 1 + len(data)):
        ws.row_dimensions[row_idx].height = 25
    
    # Заморозка панели
    ws.freeze_panes = f'A{start_row + 1}'
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generate_empty_registrations_excel(course_title: str = "") -> BytesIO:
    """Генерирует пустой Excel с заголовками"""
    return generate_full_registrations_excel_from_data([], course_title)


def get_column_letter(col_idx: int) -> str:
    """Возвращает букву колонки по индексу (1-based)"""
    result = ""
    while col_idx > 0:
        col_idx -= 1
        result = chr(65 + col_idx % 26) + result
        col_idx //= 26
    return result