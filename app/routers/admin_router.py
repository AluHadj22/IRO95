from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app import models, schemas, auth
from app.database import get_db
from app.services.excel_service import generate_full_registrations_excel
from app.services.excel_export_service import ExcelExportService, generate_export_filename
from app.services.document_export_service import DocumentExportService
from typing import List
import os
import shutil
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Создаем папку для загрузок, если её нет
UPLOAD_DIR = "app/static/uploads"
COURSE_IMAGES_DIR = os.path.join(UPLOAD_DIR, "courses")
SPEAKER_PHOTOS_DIR = os.path.join(UPLOAD_DIR, "speakers")

# Создаем директории рекурсивно
os.makedirs(COURSE_IMAGES_DIR, exist_ok=True)
os.makedirs(SPEAKER_PHOTOS_DIR, exist_ok=True)


@router.post("/upload/course-image")
async def upload_course_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Загрузка изображения для курса"""
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат изображения. Используйте JPG, PNG или WEBP")
    
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(COURSE_IMAGES_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения файла: {str(e)}")
    
    file_url = f"/static/uploads/courses/{filename}"
    return {"url": file_url, "filename": filename, "message": "Изображение загружено"}


@router.post("/upload/speaker-photo")
async def upload_speaker_photo(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Загрузка фото спикера"""
    allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат изображения. Используйте JPG, PNG или WEBP")
    
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(SPEAKER_PHOTOS_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения файла: {str(e)}")
    
    file_url = f"/static/uploads/speakers/{filename}"
    return {"url": file_url, "filename": filename, "message": "Фото загружено"}


@router.get("/stats")
def get_admin_stats(db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_admin)):
    total_users = db.query(models.User).count()
    total_courses = db.query(models.Course).count()
    total_registrations = db.query(models.CourseRegistration).count()
    total_categories = db.query(models.Category).count()
    
    return {
        "total_users": total_users,
        "total_courses": total_courses,
        "total_registrations": total_registrations,
        "total_categories": total_categories
    }


@router.get("/categories")
def get_categories(db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_admin)):
    categories = db.query(models.Category).order_by(models.Category.id).all()
    result = []
    for c in categories:
        result.append({
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "courses_count": len(c.courses)
        })
    return result


@router.post("/categories")
def create_category(category: schemas.CategoryCreate, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_admin)):
    existing = db.query(models.Category).filter(models.Category.name == category.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Категория с таким названием уже существует")
    
    db_category = models.Category(
        name=category.name,
        description=category.description
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return {"message": "Category created", "id": db_category.id, "name": db_category.name}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_admin)):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    db.query(models.Course).filter(models.Course.category_id == category_id).update({models.Course.category_id: None})
    
    db.delete(category)
    db.commit()
    return {"message": "Category deleted"}


@router.get("/courses")
def get_all_courses(db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_admin)):
    courses = db.query(models.Course).order_by(desc(models.Course.created_at)).all()
    result = []
    for c in courses:
        result.append({
            "id": c.id,
            "title": c.title,
            "price": c.price,
            "current_participants": c.current_participants,
            "max_participants": c.max_participants,
            "is_active": c.is_active,
            "category_name": c.category.name if c.category else None,
            "format_type": c.format_type,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "created_at": c.created_at
        })
    return result


@router.delete("/courses/{course_id}")
def admin_delete_course(course_id: int, db: Session = Depends(get_db),
                        current_user: models.User = Depends(auth.get_current_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    db.query(models.CourseSpeaker).filter(models.CourseSpeaker.course_id == course_id).delete()
    db.query(models.UserFavorite).filter(models.UserFavorite.course_id == course_id).delete()
    db.query(models.UserWatchLater).filter(models.UserWatchLater.course_id == course_id).delete()
    db.query(models.CourseRegistration).filter(models.CourseRegistration.course_id == course_id).delete()
    db.query(models.UserProgress).filter(models.UserProgress.course_id == course_id).delete()
    db.query(models.Certificate).filter(models.Certificate.course_id == course_id).delete()
    
    db.delete(course)
    db.commit()
    return {"message": "Course deleted successfully"}


@router.get("/courses/{course_id}/registrations")
def get_course_registrations(course_id: int, db: Session = Depends(get_db),
                             current_user: models.User = Depends(auth.get_current_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    registrations = db.query(models.CourseRegistration, models.User).join(
        models.User
    ).filter(models.CourseRegistration.course_id == course_id).order_by(
        models.CourseRegistration.registered_at.desc()
    ).all()
    
    return {
        "course": {"id": course.id, "title": course.title, "price": course.price},
        "registrations": [{
            "id": r.CourseRegistration.id,
            "user_id": r.User.id,
            "full_name": r.User.full_name,
            "email": r.User.email,
            "position": r.User.position,
            "phone": r.User.phone,
            "organization": r.User.organization,
            "is_paid": r.CourseRegistration.is_paid,
            "registered_at": r.CourseRegistration.registered_at
        } for r in registrations]
    }


@router.get("/courses/{course_id}/export")
def export_course_registrations(
    course_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Экспорт регистраций на курс в Excel с ПОЛНЫМИ данными пользователей.
    Использует те же поля, что и основной экспорт пользователей.
    """
    # Проверяем существование курса
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Используем новую функцию с полными данными
    buffer = generate_full_registrations_excel(db, course_id, course.title)
    
    # Формируем имя файла
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"registrations_course_{course_id}_{timestamp}.xlsx"
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users")
def get_users(db: Session = Depends(get_db),
              current_user: models.User = Depends(auth.get_current_admin)):
    users = db.query(models.User).order_by(models.User.id).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role.value,
             "is_blocked": u.is_blocked, "registrations_count": len(u.registrations)} for u in users]


@router.post("/users/{user_id}/block")
def block_user(user_id: int, db: Session = Depends(get_db),
               current_user: models.User = Depends(auth.get_current_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_blocked = True
    db.commit()
    return {"message": "User blocked"}


@router.post("/users/{user_id}/unblock")
def unblock_user(user_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.get_current_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_blocked = False
    db.commit()
    return {"message": "User unblocked"}


# ============================================================
# НОВЫЕ ЭНДПОИНТЫ ДЛЯ ЭКСПОРТА ДАННЫХ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

@router.get("/users/list")
def get_users_with_data(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получить список пользователей с их данными для отображения в админке.
    Используется для вкладки "Данные пользователей".
    """
    export_service = ExcelExportService(db)
    users_list = export_service.get_users_list_with_data()
    return users_list


@router.get("/users/export-all")
def export_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Экспорт данных всех пользователей в Excel по шаблону.
    """
    export_service = ExcelExportService(db)
    buffer = export_service.export_users_to_excel()
    
    filename = generate_export_filename("all")
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users/{user_id}/export")
def export_single_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Экспорт данных одного пользователя в Excel по шаблону.
    """
    # Проверяем существование пользователя
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    export_service = ExcelExportService(db)
    buffer = export_service.export_single_user(user_id)
    
    if not buffer:
        raise HTTPException(status_code=404, detail="User not found")
    
    filename = generate_export_filename("single", user_id)
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users/export-selected")
def export_selected_users(
    user_ids: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Экспорт данных выбранных пользователей в Excel по шаблону.
    
    Args:
        user_ids: Список ID пользователей через запятую (например: "1,2,3,4")
    """
    if not user_ids:
        raise HTTPException(status_code=400, detail="Не указаны ID пользователей")
    
    try:
        ids_list = [int(id_str.strip()) for id_str in user_ids.split(',') if id_str.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный формат ID пользователей")
    
    if not ids_list:
        raise HTTPException(status_code=400, detail="Не указаны ID пользователей")
    
    export_service = ExcelExportService(db)
    buffer = export_service.export_users_to_excel(ids_list)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"selected_users_{len(ids_list)}_{timestamp}.xlsx"
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# ============================================================
# НОВЫЕ ЭНДПОИНТЫ ДЛЯ РАБОТЫ С ДОКУМЕНТАМИ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

@router.get("/users/{user_id}/documents")
def get_user_documents(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получить список документов пользователя с их статусами.
    """
    doc_service = DocumentExportService(db)
    return doc_service.get_user_documents_list(user_id)


@router.get("/users/{user_id}/documents/download")
def download_user_documents(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Скачать все документы пользователя в ZIP-архиве.
    """
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_user_zip(user_id)
    
    # Кодируем имя файла для заголовка
    encoded_filename = filename.encode('utf-8').decode('latin-1', errors='ignore')
    
    return StreamingResponse(
        iter([zip_content]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users/documents/download-selected")
def download_selected_users_documents(
    user_ids: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Скачать документы выбранных пользователей в ZIP-архиве.
    Каждый пользователь получает отдельную папку.
    
    Args:
        user_ids: Список ID пользователей через запятую (например: "1,2,3,4")
    """
    if not user_ids:
        raise HTTPException(status_code=400, detail="Не указаны ID пользователей")
    
    try:
        ids_list = [int(id_str.strip()) for id_str in user_ids.split(',') if id_str.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный формат ID пользователей")
    
    if not ids_list:
        raise HTTPException(status_code=400, detail="Не указаны ID пользователей")
    
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_multiple_users_zip(ids_list)
    
    # Кодируем имя файла для заголовка
    encoded_filename = filename.encode('utf-8').decode('latin-1', errors='ignore')
    
    return StreamingResponse(
        iter([zip_content]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users/documents/download-all")
def download_all_users_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Скачать документы ВСЕХ пользователей в ZIP-архиве.
    Каждый пользователь получает отдельную папку.
    """
    # Получаем всех пользователей
    users = db.query(models.User).all()
    if not users:
        raise HTTPException(status_code=404, detail="Нет пользователей")
    
    user_ids = [user.id for user in users]
    
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_multiple_users_zip(user_ids)
    
    # Кодируем имя файла для заголовка
    encoded_filename = filename.encode('utf-8').decode('latin-1', errors='ignore')
    
    return StreamingResponse(
        iter([zip_content]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.get("/users/{user_id}/documents/{doc_type}/download")
def download_user_document(
    user_id: int,
    doc_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Скачать конкретный документ пользователя.
    
    Args:
        user_id: ID пользователя
        doc_type: Тип документа (snils, diploma, passport, inn, marriage)
    """
    doc_service = DocumentExportService(db)
    content, filename, mime_type = doc_service.get_document_file(user_id, doc_type)
    
    # Кодируем имя файла для заголовка
    encoded_filename = filename.encode('utf-8').decode('latin-1', errors='ignore')
    
    return StreamingResponse(
        iter([content]),
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


@router.delete("/users/{user_id}/documents/{doc_type}")
def delete_user_document(
    user_id: int,
    doc_type: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Удалить документ пользователя (админское удаление).
    
    Args:
        user_id: ID пользователя
        doc_type: Тип документа (snils, diploma, passport, inn, marriage)
    """
    doc_service = DocumentExportService(db)
    result = doc_service.delete_document(user_id, doc_type)
    return result