from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app import models, schemas, auth
from app.database import get_db
from app.services.excel_service import generate_registrations_excel
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
    """Экспорт регистраций на курс в Excel с красивым форматированием"""
    # Проверяем существование курса
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Получаем все регистрации с данными пользователей
    registrations = db.query(models.CourseRegistration, models.User).join(
        models.User
    ).filter(models.CourseRegistration.course_id == course_id).order_by(
        models.CourseRegistration.registered_at.desc()
    ).all()
    
    # Подготавливаем данные для Excel
    data = []
    for idx, reg in enumerate(registrations, 1):
        data.append({
            "number": idx,
            "full_name": reg.User.full_name,
            "email": reg.User.email,
            "phone": reg.User.phone or "",
            "position": reg.User.position or "",
            "organization": reg.User.organization or "",
            "is_paid": "Да" if reg.CourseRegistration.is_paid else "Нет",
            "registered_at": reg.CourseRegistration.registered_at.strftime("%d.%m.%Y %H:%M") if reg.CourseRegistration.registered_at else ""
        })
    
    # Генерируем Excel файл с информацией о курсе
    buffer = generate_registrations_excel(data, course.title)
    
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