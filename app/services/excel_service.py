from openpyxl import Workbook
from io import BytesIO
from typing import List, Dict

def generate_registrations_excel(data: List[Dict]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Registrations"
    
    headers = ["ФИО", "Email", "Телефон", "Должность", "Организация", "Оплачен", "Дата регистрации"]
    ws.append(headers)
    
    for row in data:
        ws.append([
            row.get('full_name', ''),
            row.get('email', ''),
            row.get('phone', ''),
            row.get('position', ''),
            row.get('organization', ''),
            row.get('is_paid', 'Нет'),
            row.get('registered_at').strftime("%d.%m.%Y %H:%M") if row.get('registered_at') else ''
        ])
    
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer