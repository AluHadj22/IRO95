# app/routers/admin_router.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_, delete, or_
from sqlalchemy.orm import selectinload, joinedload, Session
from app import models, schemas, auth
from app.database import get_async_db, get_db, SessionLocal
from app.services.excel_service import generate_full_registrations_excel
from app.services.excel_export_service import ExcelExportService, generate_export_filename
from app.services.document_export_service import DocumentExportService
from app.services.moodle_service import MoodleService
from app.services.cache_service import cached, cache_service
from app.services.password_reminder_service import PasswordReminderService
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


# ============================================================
# ✅ ОБНОВЛЁННЫЙ ЭНДПОИНТ /courses/{course_id}/registrations
#    теперь возвращает информацию о документах каждого пользователя
# ============================================================
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

    # Получаем регистрации с подгрузкой пользователей и связанных данных
    registrations_stmt = select(models.CourseRegistration).options(
        selectinload(models.CourseRegistration.user).selectinload(models.User.education),
        selectinload(models.CourseRegistration.user).selectinload(models.User.additional_info),
        selectinload(models.CourseRegistration.user).selectinload(models.User.work),
    ).where(
        models.CourseRegistration.course_id == course_id
    ).order_by(
        models.CourseRegistration.registered_at.desc()
    )

    registrations_result = await db.execute(registrations_stmt)
    registrations = registrations_result.unique().scalars().all()

    # Формируем ответ с информацией о документах
    registrations_data = []
    for r in registrations:
        user = r.user
        has_documents = False

        # Проверяем наличие документов у пользователя (только СНИЛС, диплом, свидетельство о браке)
        if user.additional_info:
            if (user.additional_info.snils_file_url or
                user.additional_info.marriage_certificate_file_url):
                has_documents = True

        # Проверяем диплом
        if not has_documents and user.education:
            for edu in user.education:
                if edu.diploma_file_url:
                    has_documents = True
                    break

        registrations_data.append({
            "id": r.id,
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "position": user.position,
            "phone": user.phone,
            "organization": user.organization,
            "registered_at": r.registered_at,
            "is_active": not user.is_blocked,
            "has_documents": has_documents
        })

    return {
        "course": {
            "id": course.id,
            "title": course.title,
            "moodle_course_id": course.moodle_course_id,
            "current_participants": course.current_participants,
            "max_participants": course.max_participants
        },
        "registrations": registrations_data,
        "total": len(registrations_data)
    }



# НОВЫЙ ЭНДПОИНТ: СКАЧИВАНИЕ ДОКУМЕНТОВ ЗАРЕГИСТРИРОВАННЫХ НА КУРС

@router.get("/courses/{course_id}/registrations/documents")
async def download_course_registrations_documents(
        course_id: int,
        user_ids: Optional[str] = Query(None, description="Список ID пользователей через запятую. Если не указан - скачиваются все"),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Скачивает документы зарегистрированных на курс пользователей в ZIP-архиве.
    - Если передан user_ids - скачивает документы только выбранных пользователей
    - Если user_ids не передан - скачивает документы всех зарегистрированных на курс
    """
    # Проверяем существование курса
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Курс не найден"
        )

    # Получаем список пользователей, зарегистрированных на курс
    registrations_stmt = select(models.CourseRegistration.user_id).where(
        models.CourseRegistration.course_id == course_id
    )
    registrations_result = await db.execute(registrations_stmt)
    all_registered_user_ids = [r[0] for r in registrations_result.all()]

    if not all_registered_user_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="На курсе нет зарегистрированных пользователей"
        )

    # Определяем, каких пользователей включать
    if user_ids:
        try:
            selected_ids = [int(id_str.strip()) for id_str in user_ids.split(',') if id_str.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный формат ID пользователей"
            )

        if not selected_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не указаны ID пользователей"
            )

        # Проверяем, что все выбранные пользователи зарегистрированы на курс
        invalid_ids = set(selected_ids) - set(all_registered_user_ids)
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Пользователи с ID {list(invalid_ids)} не зарегистрированы на этот курс"
            )

        user_ids_to_export = selected_ids
    else:
        user_ids_to_export = all_registered_user_ids

    # Используем синхронную сессию для DocumentExportService
    sync_db = SessionLocal()
    try:
        doc_service = DocumentExportService(sync_db)

        # Проверяем, есть ли у выбранных пользователей документы
        users_with_docs = []
        for uid in user_ids_to_export:
            user = sync_db.query(models.User).filter(models.User.id == uid).first()
            if user:
                doc_list = doc_service.get_user_documents_list(uid)
                if doc_list.get('has_any_document', False):
                    users_with_docs.append(uid)

        if not users_with_docs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У выбранных пользователей нет загруженных документов"
            )

        # Создаём ZIP-архив
        zip_content, filename = doc_service.create_multiple_users_zip(users_with_docs)

    finally:
        sync_db.close()

    # Формируем имя файла с информацией о курсе
    safe_title = course.title.replace(' ', '_').replace('/', '_')[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_filename = f"documents_course_{course_id}_{safe_title}_{timestamp}.zip"

    encoded_filename = final_filename.encode('utf-8').decode('latin-1', errors='ignore')

    return StreamingResponse(
        iter([zip_content]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={encoded_filename}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


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



#  ИСПРАВЛЕННЫЙ ЭНДПОИНТ /users С ПОДДЕРЖКОЙ ПОИСКА

@router.get("/users")
async def get_users(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        search: Optional[str] = Query(None, description="Поиск по ФИО, email или ID"),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получает список пользователей с их данными.
    Поддерживает поиск по ФИО (включая отдельные части), email и ID.
    """
    # Базовый запрос с подгрузкой связанных данных
    stmt = select(models.User).options(
        selectinload(models.User.registrations)
    ).order_by(models.User.id)

    # === ПОИСК (если передан) ===
    if search:
        search_term = f"%{search}%"
        # Проверяем, не является ли search числом (поиск по ID)
        is_numeric = False
        try:
            int(search)
            is_numeric = True
        except ValueError:
            pass

        if is_numeric:
            # Поиск по ID
            stmt = stmt.where(models.User.id == int(search))
        else:
            # Поиск по ФИО (составные части) и email
            search_parts = search.strip().split()

            # Строим условия для поиска по ФИО
            name_conditions = []

            # Ищем по полному ФИО (full_name)
            name_conditions.append(models.User.full_name.ilike(search_term))

            # Ищем по отдельным частям (фамилия, имя, отчество)
            if len(search_parts) >= 1:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[0]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[0]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[0]}%"))

            if len(search_parts) >= 2:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[1]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[1]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[1]}%"))

            if len(search_parts) >= 3:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[2]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[2]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[2]}%"))

            # Также ищем по email
            name_conditions.append(models.User.email.ilike(search_term))

            # Применяем все условия через OR
            if name_conditions:
                stmt = stmt.where(or_(*name_conditions))

    # Пагинация
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    users = result.unique().scalars().all()

    # Общее количество (с учётом поиска)
    count_stmt = select(func.count()).select_from(models.User)

    # Повторяем условия поиска для подсчёта
    if search:
        search_term = f"%{search}%"
        is_numeric = False
        try:
            int(search)
            is_numeric = True
        except ValueError:
            pass

        if is_numeric:
            count_stmt = count_stmt.where(models.User.id == int(search))
        else:
            search_parts = search.strip().split()
            name_conditions = []

            name_conditions.append(models.User.full_name.ilike(search_term))

            if len(search_parts) >= 1:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[0]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[0]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[0]}%"))

            if len(search_parts) >= 2:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[1]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[1]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[1]}%"))

            if len(search_parts) >= 3:
                name_conditions.append(models.User.last_name.ilike(f"%{search_parts[2]}%"))
                name_conditions.append(models.User.first_name.ilike(f"%{search_parts[2]}%"))
                name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[2]}%"))

            name_conditions.append(models.User.email.ilike(search_term))

            if name_conditions:
                count_stmt = count_stmt.where(or_(*name_conditions))

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



#  ИСПРАВЛЕННЫЙ ЭНДПОИНТ /users/list С ПОДДЕРЖКОЙ ПОИСКА

@router.get("/users/list")
async def get_users_with_data(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        search: Optional[str] = Query(None, description="Поиск по ФИО, email или ID"),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получает список пользователей с их данными.
    Поддерживает поиск по ФИО (включая отдельные части), email и ID.
    """
    sync_db = SessionLocal()
    try:
        # Базовый запрос с подгрузкой связанных данных
        query = sync_db.query(models.User).options(
            joinedload(models.User.work),
            joinedload(models.User.education),
            joinedload(models.User.additional_info)
        )

        # === ПОИСК (если передан) ===
        if search:
            search_term = f"%{search}%"
            # Проверяем, не является ли search числом (поиск по ID)
            is_numeric = False
            try:
                int(search)
                is_numeric = True
            except ValueError:
                pass

            if is_numeric:
                # Поиск по ID
                query = query.filter(models.User.id == int(search))
            else:
                # Поиск по ФИО (составные части) и email
                # Разбиваем поисковый запрос на слова для поиска по частям ФИО
                search_parts = search.strip().split()

                # Строим условия для поиска по ФИО
                name_conditions = []

                # Ищем по полному ФИО (full_name)
                name_conditions.append(models.User.full_name.ilike(search_term))

                # Ищем по отдельным частям (фамилия, имя, отчество)
                if len(search_parts) >= 1:
                    name_conditions.append(models.User.last_name.ilike(f"%{search_parts[0]}%"))
                    name_conditions.append(models.User.first_name.ilike(f"%{search_parts[0]}%"))
                    name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[0]}%"))

                if len(search_parts) >= 2:
                    name_conditions.append(models.User.last_name.ilike(f"%{search_parts[1]}%"))
                    name_conditions.append(models.User.first_name.ilike(f"%{search_parts[1]}%"))
                    name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[1]}%"))

                if len(search_parts) >= 3:
                    name_conditions.append(models.User.last_name.ilike(f"%{search_parts[2]}%"))
                    name_conditions.append(models.User.first_name.ilike(f"%{search_parts[2]}%"))
                    name_conditions.append(models.User.middle_name.ilike(f"%{search_parts[2]}%"))

                # Также ищем по email
                name_conditions.append(models.User.email.ilike(search_term))

                # Применяем все условия через OR
                if name_conditions:
                    from sqlalchemy import or_
                    query = query.filter(or_(*name_conditions))

        total = query.count()

        if limit is not None:
            query = query.offset(offset).limit(limit)

        users = query.all()

        # Получаем данные для всех пользователей одним запросом
        export_service = ExcelExportService(sync_db)
        users_data = export_service._get_user_export_data_batch(users)

        result = []
        for user in users:
            data = users_data.get(user.id, {})

            full_name = f"{user.last_name or ''} {user.first_name or ''} {user.middle_name or ''}".strip()
            if not full_name:
                full_name = user.full_name or ""

            result.append({
                "id": user.id,
                "email": export_service._escape_excel_string(user.email),
                "role": user.role.value if user.role else "teacher",
                "is_blocked": user.is_blocked,
                "created_at": user.created_at.strftime("%d.%m.%Y %H:%M") if user.created_at else "",
                "full_name": export_service._escape_excel_string(full_name),
                "data": data,
                "has_complete_profile": user.is_profile_complete()
            })

        return {
            "total": total,
            "items": result
        }

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting users list: {str(e)}")
        return {"total": 0, "items": []}
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
    from sqlalchemy import select, func

    result = await db.execute(
        select(models.User).filter(models.User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

    if user.role == models.UserRole.ADMIN:
        result = await db.execute(
            select(func.count()).select_from(models.User).filter(
                models.User.role == models.UserRole.ADMIN
            )
        )
        admin_count = result.scalar()
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Нельзя удалить последнего администратора. Сначала назначьте другого администратора."
            )

    # Используем run_sync для синхронных операций с документами
    def delete_documents_sync(session):
        doc_service = DocumentExportService(session)
        doc_service.delete_all_user_documents(user)

    await db.run_sync(delete_documents_sync)

    await db.delete(user)
    await db.commit()

    # Очищаем кэш статистики
    await cache_service.delete("admin_stats")

    return {"message": "User deleted successfully"}


@router.post("/users/send-password-reminders")
async def send_password_reminders(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Отправляет напоминания о паролях пользователям,
    у которых был аккаунт в Moodle до регистрации на платформе.
    """
    sync_db = SessionLocal()
    try:
        service = PasswordReminderService(sync_db)
        result = service.send_password_reminders_to_all()
        return result
    finally:
        sync_db.close()


@router.get("/users/existing-moodle-accounts")
async def get_users_with_existing_moodle_accounts(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получает список пользователей, у которых был аккаунт в Moodle до регистрации.
    """
    sync_db = SessionLocal()
    try:
        service = PasswordReminderService(sync_db)
        users = service.get_users_with_existing_moodle_account()

        result = []
        for user in users:
            moodle_service = MoodleService()
            moodle_user = moodle_service.get_user_by_email(user.email)
            username = moodle_user.get('username', user.email.split('@')[0]) if moodle_user else user.email.split('@')[
                0]

            result.append({
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "username": username,
                "password_sent": user.moodle_password_sent,
                "registered_at": user.created_at.isoformat() if user.created_at else None
            })

        return {
            "total": len(result),
            "users": result
        }
    finally:
        sync_db.close()


@router.get("/users/moodle-accounts")
async def get_moodle_accounts_paginated(
        page: int = Query(1, ge=1, description="Номер страницы"),
        per_page: int = Query(20, ge=1, le=100, description="Записей на странице"),
        search: Optional[str] = Query(None, description="Поиск по email или ФИО"),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Получает список ВСЕХ пользователей с аккаунтами в Moodle с пагинацией.
    """
    sync_db = SessionLocal()
    try:
        service = PasswordReminderService(sync_db)
        result = service.get_all_moodle_users_with_pagination(page, per_page, search)
        return result
    finally:
        sync_db.close()


@router.post("/users/send-password-reminders-selected")
async def send_password_reminders_selected(
        user_ids: List[int] = Query(..., description="Список ID пользователей"),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    """
    Отправляет напоминания о паролях выбранным пользователям.
    """
    if not user_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не указаны ID пользователей"
        )

    sync_db = SessionLocal()
    try:
        service = PasswordReminderService(sync_db)
        result = service.send_password_reminders_to_selected(user_ids)
        return result
    finally:
        sync_db.close()