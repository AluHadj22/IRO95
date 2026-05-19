from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from io import BytesIO
from typing import List, Dict

def generate_registrations_excel(data: List[Dict], course_title: str = "") -> BytesIO:
    """Генерация Excel файла с регистрациями"""
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