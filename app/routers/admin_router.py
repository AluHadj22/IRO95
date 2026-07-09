from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import desc, func
from app import models, schemas, auth
from app.database import get_db
from app.services.excel_service import generate_full_registrations_excel
from app.services.excel_export_service import ExcelExportService, generate_export_filename
from app.services.document_export_service import DocumentExportService
from typing import List, Optional
import os
import shutil
import uuid
import magic
from datetime import datetime

router = APIRouter(prefix="/api/admin", tags=["Admin"])

UPLOAD_DIR = "app/static/uploads"
COURSE_IMAGES_DIR = os.path.join(UPLOAD_DIR, "courses")
SPEAKER_PHOTOS_DIR = os.path.join(UPLOAD_DIR, "speakers")

os.makedirs(COURSE_IMAGES_DIR, exist_ok=True)
os.makedirs(SPEAKER_PHOTOS_DIR, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_MIMES = ['image/jpeg', 'image/png', 'image/webp']
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def validate_file(file: UploadFile, allowed_mimes: List[str], max_size: int = MAX_FILE_SIZE) -> None:
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    
    if size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл слишком большой (макс. {max_size // (1024 * 1024)}MB)"
        )
    
    try:
        file.file.seek(0)
        mime = magic.from_buffer(file.file.read(1024), mime=True)
        file.file.seek(0)
        
        if mime not in allowed_mimes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Неподдерживаемый тип файла: {mime}. Разрешены: {', '.join(allowed_mimes)}"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ошибка проверки файла: {str(e)}"
        )


def get_safe_filename(original_filename: str, extension: str = None) -> str:
    if extension is None:
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            ext = '.jpg'
    else:
        ext = extension if extension.startswith('.') else f'.{extension}'
    
    return f"{uuid.uuid4().hex}{ext}"


def save_upload_file(file: UploadFile, save_dir: str, allowed_mimes: List[str] = None) -> dict:
    if allowed_mimes is None:
        allowed_mimes = ALLOWED_IMAGE_MIMES
    
    validate_file(file, allowed_mimes)
    
    safe_filename = get_safe_filename(file.filename)
    filepath = os.path.join(save_dir, safe_filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка сохранения файла: {str(e)}"
        )
    
    rel_path = os.path.relpath(save_dir, "app/static/uploads")
    url = f"/static/uploads/{rel_path}/{safe_filename}".replace('\\', '/')
    
    return {
        "url": url,
        "filename": safe_filename,
        "original_filename": file.filename,
        "file_size": os.path.getsize(filepath)
    }


@router.post("/upload/course-image")
async def upload_course_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_admin)
):
    result = save_upload_file(file, COURSE_IMAGES_DIR)
    return {
        "url": result["url"],
        "filename": result["filename"],
        "message": "Изображение загружено"
    }


@router.post("/upload/speaker-photo")
async def upload_speaker_photo(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_admin)
):
    result = save_upload_file(file, SPEAKER_PHOTOS_DIR)
    return {
        "url": result["url"],
        "filename": result["filename"],
        "message": "Фото загружено"
    }


@router.get("/stats")
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
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
def get_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
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
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    existing = db.query(models.Category).filter(models.Category.name == category.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Категория с таким названием уже существует"
        )
    
    db_category = models.Category(
        name=category.name,
        description=category.description
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return {
        "message": "Category created",
        "id": db_category.id,
        "name": db_category.name
    }


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    category = db.query(models.Category).filter(models.Category.id == category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    db.query(models.Course).filter(
        models.Course.category_id == category_id
    ).update({models.Course.category_id: None})
    
    db.delete(category)
    db.commit()
    return {"message": "Category deleted"}


@router.get("/courses")
def get_all_courses(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    query = db.query(models.Course).options(
        joinedload(models.Course.category)
    )
    
    total = query.count()
    courses = query.order_by(desc(models.Course.created_at)).offset(offset).limit(limit).all()
    
    result = []
    for c in courses:
        result.append({
            "id": c.id,
            "title": c.title,
            "current_participants": c.current_participants,
            "max_participants": c.max_participants,
            "is_active": c.is_active,
            "category_name": c.category.name if c.category else None,
            "format_type": c.format_type,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "created_at": c.created_at,
            "moodle_course_id": c.moodle_course_id
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": result
    }


@router.delete("/courses/{course_id}")
def admin_delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
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
def get_course_registrations(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
    registrations = db.query(models.CourseRegistration).options(
        selectinload(models.CourseRegistration.user)
    ).filter(
        models.CourseRegistration.course_id == course_id
    ).order_by(
        models.CourseRegistration.registered_at.desc()
    ).all()
    
    return {
        "course": {
            "id": course.id,
            "title": course.title,
            "moodle_course_id": course.moodle_course_id
        },
        "registrations": [{
            "id": r.id,
            "user_id": r.user.id,
            "full_name": r.user.full_name,
            "email": r.user.email,
            "position": r.user.position,
            "phone": r.user.phone,
            "organization": r.user.organization,
            "registered_at": r.registered_at
        } for r in registrations]
    }


@router.get("/courses/{course_id}/export")
def export_course_registrations(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
    buffer = generate_full_registrations_excel(db, course_id, course.title)
    
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
def get_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    users = db.query(models.User).options(
        selectinload(models.User.registrations)
    ).order_by(models.User.id).offset(offset).limit(limit).all()
    
    total = db.query(models.User).count()
    
    return [{
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value,
        "is_blocked": u.is_blocked,
        "registrations_count": len(u.registrations)
    } for u in users]


@router.post("/users/{user_id}/block")
def block_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block yourself"
        )
    
    user.is_blocked = True
    db.commit()
    return {"message": "User blocked"}


@router.post("/users/{user_id}/unblock")
def unblock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_blocked = False
    db.commit()
    return {"message": "User unblocked"}


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    user_update: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    
    return {
        "message": "User updated successfully",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "position": user.position,
            "phone": user.phone,
            "organization": user.organization,
            "is_blocked": user.is_blocked
        }
    }


@router.put("/users/{user_id}/role")
def change_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя изменить свою собственную роль"
        )
    
    admin_count = db.query(models.User).filter(
        models.User.role == models.UserRole.ADMIN
    ).count()
    
    if user.role == models.UserRole.ADMIN and admin_count <= 1 and role_update.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить последнего администратора. Сначала назначьте другого администратора."
        )
    
    old_role = user.role.value
    user.role = role_update.role
    db.commit()
    db.refresh(user)
    
    role_names = {
        "admin": "Администратор",
        "teacher": "Преподаватель"
    }
    
    return {
        "message": f"Роль пользователя изменена с '{role_names.get(old_role, old_role)}' на '{role_names.get(user.role.value, user.role.value)}'",
        "user_id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "old_role": old_role,
        "new_role": user.role.value,
        "new_role_display": role_names.get(user.role.value, user.role.value)
    }


@router.get("/users/list")
def get_users_with_data(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    """Получить список пользователей с их данными для отображения в админке"""
    export_service = ExcelExportService(db)
    result = export_service.get_users_list_with_data(limit, offset)
    return result


@router.get("/users/export-all")
def export_all_users(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
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
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    export_service = ExcelExportService(db)
    buffer = export_service.export_single_user(user_id)
    
    if not buffer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
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
    if not user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей"
        )
    
    try:
        ids_list = [int(id_str.strip()) for id_str in user_ids.split(',') if id_str.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный формат ID пользователей"
        )
    
    if not ids_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей"
        )
    
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


@router.get("/users/{user_id}/documents")
def get_user_documents(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    doc_service = DocumentExportService(db)
    return doc_service.get_user_documents_list(user_id)


@router.get("/users/{user_id}/documents/download")
def download_user_documents(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_user_zip(user_id)
    
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
    if not user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей"
        )
    
    try:
        ids_list = [int(id_str.strip()) for id_str in user_ids.split(',') if id_str.strip()]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный формат ID пользователей"
        )
    
    if not ids_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей"
        )
    
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_multiple_users_zip(ids_list)
    
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
    users = db.query(models.User).all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Нет пользователей"
        )
    
    user_ids = [user.id for user in users]
    
    doc_service = DocumentExportService(db)
    zip_content, filename = doc_service.create_multiple_users_zip(user_ids)
    
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
    doc_service = DocumentExportService(db)
    content, filename, mime_type = doc_service.get_document_file(user_id, doc_type)
    
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
    doc_service = DocumentExportService(db)
    result = doc_service.delete_document(user_id, doc_type)
    return result