# app/routers/admin_router.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_, delete
from sqlalchemy.orm import selectinload, joinedload, Session
from app import models, schemas, auth
from app.database import get_async_db, get_db, SessionLocal
from app.services.excel_service import generate_full_registrations_excel
from app.services.excel_export_service import ExcelExportService, generate_export_filename
from app.services.document_export_service import DocumentExportService
from app.services.moodle_service import MoodleService
from app.services.cache_service import cached, cache_service
from typing import List, Optional
import os
import shutil
import uuid
import magic
import json
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


def delete_file_from_disk(file_url: str) -> bool:
    if not file_url:
        return False
    
    file_path = file_url.replace("/static/", "app/static/")
    file_path = os.path.normpath(file_path)
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        try:
            os.remove(file_path)
            return True
        except Exception:
            return False
    return False


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


async def get_admin_stats_from_db(db: AsyncSession) -> dict:
    """Вспомогательная функция для получения статистики из БД"""
    total_users_stmt = select(func.count()).select_from(models.User)
    total_users_result = await db.execute(total_users_stmt)
    total_users = total_users_result.scalar() or 0
    
    total_courses_stmt = select(func.count()).select_from(models.Course)
    total_courses_result = await db.execute(total_courses_stmt)
    total_courses = total_courses_result.scalar() or 0
    
    total_registrations_stmt = select(func.count()).select_from(models.CourseRegistration)
    total_registrations_result = await db.execute(total_registrations_stmt)
    total_registrations = total_registrations_result.scalar() or 0
    
    total_categories_stmt = select(func.count()).select_from(models.Category)
    total_categories_result = await db.execute(total_categories_stmt)
    total_categories = total_categories_result.scalar() or 0
    
    return {
        "total_users": total_users,
        "total_courses": total_courses,
        "total_registrations": total_registrations,
        "total_categories": total_categories
    }


@router.get("/stats")
async def get_admin_stats(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    # Пробуем получить из кэша
    cache_key = "admin_stats"
    cached_data = await cache_service.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Получаем из БД
    stats = await get_admin_stats_from_db(db)
    
    # Сохраняем в кэш
    await cache_service.set(cache_key, stats, ttl=60)
    
    return stats


async def get_categories_from_db(db: AsyncSession) -> List[dict]:
    """Вспомогательная функция для получения категорий из БД"""
    stmt = select(models.Category).order_by(models.Category.id)
    result = await db.execute(stmt)
    categories = result.scalars().all()
    
    result_list = []
    for c in categories:
        count_stmt = select(func.count()).select_from(models.Course).where(models.Course.category_id == c.id)
        count_result = await db.execute(count_stmt)
        courses_count = count_result.scalar() or 0
        
        result_list.append({
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "courses_count": courses_count
        })
    return result_list


@router.get("/categories")
async def get_categories(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    # Пробуем получить из кэша
    cache_key = "categories_list"
    cached_data = await cache_service.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Получаем из БД
    categories = await get_categories_from_db(db)
    
    # Сохраняем в кэш
    await cache_service.set(cache_key, categories, ttl=600)
    
    return categories


@router.post("/categories")
async def create_category(
    category: schemas.CategoryCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.Category).where(models.Category.name == category.name)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
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
    await db.commit()
    await db.refresh(db_category)
    
    # Очищаем кэш категорий
    await cache_service.delete_pattern("categories_list*")
    
    return {
        "message": "Category created",
        "id": db_category.id,
        "name": db_category.name
    }


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.Category).where(models.Category.id == category_id)
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    await db.execute(
        models.Course.__table__.update().where(
            models.Course.category_id == category_id
        ).values(category_id=None)
    )
    
    await db.delete(category)
    await db.commit()
    
    # Очищаем кэш категорий
    await cache_service.delete_pattern("categories_list*")
    
    return {"message": "Category deleted"}


@router.get("/moodle-courses")
async def get_moodle_courses(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    moodle = MoodleService()
    try:
        courses = moodle.get_courses()
        return courses
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка загрузки курсов из Moodle: {str(e)}"
        )


@router.get("/courses")
async def get_all_courses(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.Course).options(
        joinedload(models.Course.category)
    ).order_by(desc(models.Course.created_at)).offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    courses = result.unique().scalars().all()
    
    count_stmt = select(func.count()).select_from(models.Course)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    result_list = []
    for c in courses:
        result_list.append({
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
        "items": result_list
    }


@router.delete("/courses/{course_id}")
async def admin_delete_course(
    course_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.Course).where(models.Course.id == course_id)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
    speakers_stmt = select(models.CourseSpeaker).where(models.CourseSpeaker.course_id == course_id)
    speakers_result = await db.execute(speakers_stmt)
    speakers = speakers_result.scalars().all()
    
    for speaker in speakers:
        if speaker.photo_url:
            delete_file_from_disk(speaker.photo_url)
    
    if course.image_url:
        delete_file_from_disk(course.image_url)
    
    await db.execute(delete(models.CourseSpeaker).where(models.CourseSpeaker.course_id == course_id))
    await db.execute(delete(models.UserFavorite).where(models.UserFavorite.course_id == course_id))
    await db.execute(delete(models.UserWatchLater).where(models.UserWatchLater.course_id == course_id))
    await db.execute(delete(models.CourseRegistration).where(models.CourseRegistration.course_id == course_id))
    await db.execute(delete(models.UserProgress).where(models.UserProgress.course_id == course_id))
    await db.execute(delete(models.Certificate).where(models.Certificate.course_id == course_id))
    
    await db.delete(course)
    await db.commit()
    
    # Очищаем кэш
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete(f"course_detail:{course_id}")
    await cache_service.delete("admin_stats")
    
    return {"message": "Course deleted successfully"}


@router.get("/courses/{course_id}/registrations")
async def get_course_registrations(
    course_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
    registrations_stmt = select(models.CourseRegistration).options(
        selectinload(models.CourseRegistration.user)
    ).where(
        models.CourseRegistration.course_id == course_id
    ).order_by(
        models.CourseRegistration.registered_at.desc()
    )
    
    registrations_result = await db.execute(registrations_stmt)
    registrations = registrations_result.scalars().all()
    
    return {
        "course": {
            "id": course.id,
            "title": course.title,
            "moodle_course_id": course.moodle_course_id,
            "current_participants": course.current_participants,
            "max_participants": course.max_participants
        },
        "registrations": [{
            "id": r.id,
            "user_id": r.user.id,
            "full_name": r.user.full_name,
            "email": r.user.email,
            "position": r.user.position,
            "phone": r.user.phone,
            "organization": r.user.organization,
            "registered_at": r.registered_at,
            "is_active": not r.user.is_blocked
        } for r in registrations],
        "total": len(registrations)
    }


@router.delete("/courses/{course_id}/registrations")
async def remove_course_registrations(
    course_id: int,
    user_ids: List[int] = Query(..., description="Список ID пользователей для удаления"),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Курс не найден"
        )
    
    if not user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей для удаления"
        )
    
    users_stmt = select(models.User).where(models.User.id.in_(user_ids))
    users_result = await db.execute(users_stmt)
    existing_users = users_result.scalars().all()
    existing_user_ids = [u.id for u in existing_users]
    not_found = set(user_ids) - set(existing_user_ids)
    
    if not_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователи с ID {list(not_found)} не найдены"
        )
    
    registrations_stmt = select(models.CourseRegistration).where(
        models.CourseRegistration.course_id == course_id,
        models.CourseRegistration.user_id.in_(user_ids)
    )
    registrations_result = await db.execute(registrations_stmt)
    registrations = registrations_result.scalars().all()
    
    if not registrations:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ни один из указанных пользователей не зарегистрирован на этот курс"
        )
    
    registered_user_ids = [r.user_id for r in registrations]
    not_registered = set(user_ids) - set(registered_user_ids)
    
    for reg in registrations:
        await db.delete(reg)
    
    await db.flush()
    
    count_stmt = select(func.count()).select_from(models.CourseRegistration).where(
        models.CourseRegistration.course_id == course_id
    )
    count_result = await db.execute(count_stmt)
    new_count = count_result.scalar() or 0
    
    course.current_participants = new_count
    
    for user_id in registered_user_ids:
        activity = models.UserActivityLog(
            user_id=user_id,
            action_type="course_unregister_admin",
            course_id=course_id,
            extra_data=json.dumps({
                "course_title": course.title,
                "admin_id": current_user.id,
                "admin_name": current_user.full_name
            })
        )
        db.add(activity)
    
    await db.commit()
    await db.refresh(course)
    
    # Очищаем кэш
    await cache_service.delete("admin_stats")
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete(f"course_detail:{course_id}")
    
    return {
        "message": f"Успешно удалено {len(registered_user_ids)} пользователей с курса",
        "course_id": course_id,
        "course_title": course.title,
        "removed_users": registered_user_ids,
        "not_registered": list(not_registered) if not_registered else [],
        "remaining_participants": course.current_participants,
        "updated_participants": course.current_participants,
        "moodle_course_id": course.moodle_course_id
    }


@router.delete("/courses/{course_id}/registrations/all")
async def remove_all_course_registrations(
    course_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Курс не найден"
        )
    
    registrations_stmt = select(models.CourseRegistration).where(
        models.CourseRegistration.course_id == course_id
    )
    registrations_result = await db.execute(registrations_stmt)
    registrations = registrations_result.scalars().all()
    
    if not registrations:
        return {
            "message": "На курсе нет зарегистрированных пользователей",
            "course_id": course_id,
            "course_title": course.title,
            "removed_count": 0,
            "remaining_participants": 0
        }
    
    removed_user_ids = [r.user_id for r in registrations]
    
    for reg in registrations:
        await db.delete(reg)
    
    await db.flush()
    course.current_participants = 0
    
    for user_id in removed_user_ids:
        activity = models.UserActivityLog(
            user_id=user_id,
            action_type="course_unregister_all_admin",
            course_id=course_id,
            extra_data=json.dumps({
                "course_title": course.title,
                "admin_id": current_user.id,
                "admin_name": current_user.full_name
            })
        )
        db.add(activity)
    
    await db.commit()
    await db.refresh(course)
    
    # Очищаем кэш
    await cache_service.delete("admin_stats")
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete(f"course_detail:{course_id}")
    
    return {
        "message": f"Все {len(removed_user_ids)} пользователей удалены с курса",
        "course_id": course_id,
        "course_title": course.title,
        "removed_count": len(removed_user_ids),
        "removed_users": removed_user_ids,
        "remaining_participants": 0
    }


@router.get("/courses/{course_id}/export")
async def export_course_registrations(
    course_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found"
        )
    
    sync_db = SessionLocal()
    try:
        buffer = generate_full_registrations_excel(sync_db, course_id, course.title)
    finally:
        sync_db.close()
    
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
async def get_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).options(
        selectinload(models.User.registrations)
    ).order_by(models.User.id).offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    users = result.unique().scalars().all()
    
    count_stmt = select(func.count()).select_from(models.User)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0
    
    return [{
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role.value,
        "is_blocked": u.is_blocked,
        "registrations_count": len(u.registrations)
    } for u in users]


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).where(models.User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
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
    await db.commit()
    
    # Очищаем кэш статистики
    await cache_service.delete("admin_stats")
    
    return {"message": "User blocked"}


@router.post("/users/{user_id}/unblock")
async def unblock_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).where(models.User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_blocked = False
    await db.commit()
    
    # Очищаем кэш статистики
    await cache_service.delete("admin_stats")
    
    return {"message": "User unblocked"}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_update: schemas.UserAdminUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).where(models.User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)
    
    await db.commit()
    await db.refresh(user)
    
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
async def change_user_role(
    user_id: int,
    role_update: schemas.UserRoleUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).where(models.User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
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
    
    admin_count_stmt = select(func.count()).select_from(models.User).where(
        models.User.role == models.UserRole.ADMIN
    )
    admin_count_result = await db.execute(admin_count_stmt)
    admin_count = admin_count_result.scalar() or 0
    
    if user.role == models.UserRole.ADMIN and admin_count <= 1 and role_update.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить последнего администратора. Сначала назначьте другого администратора."
        )
    
    old_role = user.role.value
    user.role = role_update.role
    await db.commit()
    await db.refresh(user)
    
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
async def get_users_with_data(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        export_service = ExcelExportService(sync_db)
        result = export_service.get_users_list_with_data(limit, offset)
        return result
    finally:
        sync_db.close()


@router.get("/users/export-all")
async def export_all_users(
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        export_service = ExcelExportService(sync_db)
        buffer = export_service.export_users_to_excel()
    finally:
        sync_db.close()
    
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
async def export_single_user(
    user_id: int,
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        export_service = ExcelExportService(sync_db)
        buffer = export_service.export_single_user(user_id)
    finally:
        sync_db.close()
    
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
async def export_selected_users(
    user_ids: str,
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
    
    sync_db = SessionLocal()
    try:
        export_service = ExcelExportService(sync_db)
        buffer = export_service.export_users_to_excel(ids_list)
    finally:
        sync_db.close()
    
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
async def get_user_documents(
    user_id: int,
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        return doc_service.get_user_documents_list(user_id)
    finally:
        sync_db.close()


@router.get("/users/{user_id}/documents/download")
async def download_user_documents(
    user_id: int,
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        zip_content, filename = doc_service.create_user_zip(user_id)
    finally:
        sync_db.close()
    
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
async def download_selected_users_documents(
    user_ids: str,
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
    
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        zip_content, filename = doc_service.create_multiple_users_zip(ids_list)
    finally:
        sync_db.close()
    
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
async def download_all_users_documents(
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        users = sync_db.query(models.User).all()
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Нет пользователей"
            )
        
        user_ids = [user.id for user in users]
        
        doc_service = DocumentExportService(sync_db)
        zip_content, filename = doc_service.create_multiple_users_zip(user_ids)
    finally:
        sync_db.close()
    
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
async def download_user_document(
    user_id: int,
    doc_type: str,
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        content, filename, mime_type = doc_service.get_document_file(user_id, doc_type)
    finally:
        sync_db.close()
    
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
async def delete_user_document(
    user_id: int,
    doc_type: str,
    current_user: models.User = Depends(auth.get_current_admin)
):
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        result = doc_service.delete_document(user_id, doc_type)
        return result
    finally:
        sync_db.close()


@router.delete("/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.User).where(models.User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить самого себя"
        )
    
    if user.role == models.UserRole.ADMIN:
        admin_count_stmt = select(func.count()).select_from(models.User).where(
            models.User.role == models.UserRole.ADMIN
        )
        admin_count_result = await db.execute(admin_count_stmt)
        admin_count = admin_count_result.scalar() or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя удалить последнего администратора. Сначала назначьте другого администратора."
            )
    
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)
        doc_service.delete_all_user_documents(user)
    finally:
        sync_db.close()
    
    await db.delete(user)
    await db.commit()
    
    # Очищаем кэш статистики
    await cache_service.delete("admin_stats")
    
    return {"message": "User deleted successfully"}