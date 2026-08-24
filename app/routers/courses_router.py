# app/routers/courses_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, delete
from sqlalchemy.orm import selectinload, joinedload
from app import models, schemas, auth
from app.database import get_async_db, SessionLocal
from app.services.moodle_service import MoodleService
from app.services.moodle_sync_service import MoodleSyncService
from app.services.cache_service import cached, cache_service
from app.dependencies import require_complete_profile
from app.services.notification_service import create_notification
from typing import Optional
import json
import os
from datetime import datetime
import hashlib

router = APIRouter(prefix="/api/courses", tags=["Courses"])


def convert_video_url(url: str, platform: str = "youtube") -> str:
    if not url:
        return url

    if platform == "youtube":
        if "youtu.be" in url:
            video_id = url.split("/")[-1].split("?")[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif "watch?v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif "embed" in url:
            return url
    elif platform == "vk":
        if "vk.com" in url or "vkvideo.ru" in url:
            return url
    elif platform == "rutube":
        if "rutube.ru" in url:
            if "video" in url:
                video_id = url.split("/")[-1].split("?")[0]
                return f"https://rutube.ru/embed/{video_id}/"
    return url


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


def generate_courses_cache_key(category_id: Optional[int], search: Optional[str], limit: int, offset: int) -> str:
    """Генерация ключа кэша для списка курсов"""
    parts = ["courses_list"]
    if category_id is not None:
        parts.append(f"cat={category_id}")
    if search is not None:
        # Ограничиваем длину поискового запроса для ключа
        search_part = search[:50] if search else ""
        parts.append(f"q={search_part}")
    parts.append(f"l={limit}")
    parts.append(f"o={offset}")
    return ":".join(parts)


async def get_courses_from_db(
        category_id: Optional[int],
        search: Optional[str],
        limit: int,
        offset: int,
        db: AsyncSession,
        current_user: Optional[models.User] = None
) -> dict:
    """Вспомогательная функция для получения списка курсов из БД"""
    stmt = select(models.Course).where(models.Course.is_active == True)

    if category_id:
        stmt = stmt.where(models.Course.category_id == category_id)

    if search:
        stmt = stmt.where(
            or_(
                models.Course.title.ilike(f"%{search}%"),
                models.Course.description.ilike(f"%{search}%"),
                models.Course.hashtags.ilike(f"%{search}%")
            )
        )

    stmt = stmt.options(
        joinedload(models.Course.category),
        selectinload(models.Course.speakers)
    ).order_by(models.Course.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    courses = result.unique().scalars().all()

    count_stmt = select(func.count()).select_from(models.Course).where(models.Course.is_active == True)
    if category_id:
        count_stmt = count_stmt.where(models.Course.category_id == category_id)
    if search:
        count_stmt = count_stmt.where(
            or_(
                models.Course.title.ilike(f"%{search}%"),
                models.Course.description.ilike(f"%{search}%"),
                models.Course.hashtags.ilike(f"%{search}%")
            )
        )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    user_favorites = set()
    user_watch_later = set()
    user_registered = set()

    if current_user:
        fav_stmt = select(models.UserFavorite).where(models.UserFavorite.user_id == current_user.id)
        fav_result = await db.execute(fav_stmt)
        favorites = fav_result.scalars().all()
        user_favorites = {fav.course_id for fav in favorites}

        wl_stmt = select(models.UserWatchLater).where(models.UserWatchLater.user_id == current_user.id)
        wl_result = await db.execute(wl_stmt)
        watch_later = wl_result.scalars().all()
        user_watch_later = {wl.course_id for wl in watch_later}

        reg_stmt = select(models.CourseRegistration).where(models.CourseRegistration.user_id == current_user.id)
        reg_result = await db.execute(reg_stmt)
        registrations = reg_result.scalars().all()
        user_registered = {reg.course_id for reg in registrations}

    result_items = []
    for c in courses:
        result_items.append({
            "id": c.id,
            "title": c.title,
            "short_description": c.short_description,
            "description": c.description,
            "image_url": c.image_url,
            "video_url": c.video_url,
            "video_platform": c.video_platform or "youtube",
            "hashtags": c.hashtags,
            "keywords": c.keywords,
            "current_participants": c.current_participants,
            "max_participants": c.max_participants,
            "format_type": c.format_type or "online",
            "is_open_ended": c.is_open_ended or False,
            "category_name": c.category.name if c.category else None,
            "category_id": c.category_id,
            "moodle_course_id": c.moodle_course_id,
            "is_favorite": c.id in user_favorites,
            "is_watch_later": c.id in user_watch_later,
            "is_registered": c.id in user_registered,
            "start_date": c.start_date,
            "end_date": c.end_date,
            "speakers": [
                {
                    "id": s.id,
                    "full_name": s.full_name,
                    "bio": s.bio,
                    "photo_url": s.photo_url,
                    "position": s.position
                } for s in c.speakers
            ]
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": result_items
    }


async def get_course_data_from_db(course_id: int, db: AsyncSession) -> Optional[dict]:
    """
    Вспомогательная функция для получения данных курса из БД.
    Явно загружаем все связи, чтобы избежать MissingGreenlet.
    """
    stmt = select(models.Course).options(
        joinedload(models.Course.category),
        selectinload(models.Course.speakers),
        # Если есть другие связи, которые могут понадобиться, добавляем их:
        # joinedload(models.Course.created_by_user),  # если есть
        # selectinload(models.Course.registrations),  # если будут использоваться
    ).where(models.Course.id == course_id)

    result = await db.execute(stmt)
    course = result.unique().scalar_one_or_none()

    if not course:
        return None

    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "short_description": course.short_description,
        "image_url": course.image_url,
        "video_url": course.video_url,
        "video_platform": course.video_platform or "youtube",
        "hashtags": course.hashtags,
        "keywords": course.keywords,
        "current_participants": course.current_participants,
        "max_participants": course.max_participants,
        "format_type": course.format_type or "online",
        "is_open_ended": course.is_open_ended or False,
        "category_id": course.category_id,
        "category_name": course.category.name if course.category else None,
        "start_date": course.start_date,
        "end_date": course.end_date,
        "is_active": course.is_active,
        "moodle_course_id": course.moodle_course_id,
        "speakers": [
            {
                "id": s.id,
                "full_name": s.full_name,
                "bio": s.bio,
                "photo_url": s.photo_url,
                "position": s.position
            } for s in course.speakers
        ]
    }


@router.get("/")
async def get_courses(
        category_id: Optional[int] = Query(None),
        search: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        db: AsyncSession = Depends(get_async_db),
        current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    # Для неавторизованных пользователей используем кэш
    if current_user is None:
        cache_key = generate_courses_cache_key(category_id, search, limit, offset)
        cached_data = await cache_service.get(cache_key)
        if cached_data is not None:
            return cached_data

    # Получаем данные из БД
    result = await get_courses_from_db(category_id, search, limit, offset, db, current_user)

    # Для неавторизованных пользователей сохраняем в кэш
    if current_user is None:
        cache_key = generate_courses_cache_key(category_id, search, limit, offset)
        await cache_service.set(cache_key, result, ttl=300)

    return result


@router.post("/")
async def create_course(
        course: schemas.CourseCreate,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    if course.category_id:
        stmt = select(models.Category).where(models.Category.id == course.category_id)
        result = await db.execute(stmt)
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    video_url = convert_video_url(course.video_url, course.video_platform) if course.video_url else None

    db_course = models.Course(
        title=course.title,
        description=course.description,
        short_description=course.short_description,
        category_id=course.category_id,
        image_url=course.image_url,
        video_url=video_url,
        video_platform=course.video_platform,
        hashtags=course.hashtags,
        keywords=course.keywords,
        max_participants=course.max_participants,
        format_type=course.format_type,
        start_date=course.start_date,
        end_date=course.end_date,
        is_open_ended=course.is_open_ended,
        moodle_course_id=course.moodle_course_id,
        created_by=current_user.id
    )
    db.add(db_course)
    await db.commit()
    await db.refresh(db_course)

    for speaker in course.speakers:
        db_speaker = models.CourseSpeaker(
            course_id=db_course.id,
            full_name=speaker.full_name,
            bio=speaker.bio,
            photo_url=speaker.photo_url,
            position=speaker.position
        )
        db.add(db_speaker)

    await db.commit()

    # Очищаем кэш курсов и статистики
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete("admin_stats")

    return {"message": "Course created", "id": db_course.id}


@router.get("/{course_id}")
async def get_course(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    # Для неавторизованных пользователей используем кэш
    if current_user is None:
        cache_key = f"course_detail:{course_id}"
        cached_data = await cache_service.get(cache_key)
        if cached_data is not None:
            return cached_data

    # Получаем данные из БД
    course_data = await get_course_data_from_db(course_id, db)

    if course_data is None:
        raise HTTPException(status_code=404, detail="Course not found")

    # Для неавторизованных пользователей добавляем флаги в false
    if current_user is None:
        course_data.update({
            "is_favorite": False,
            "is_watch_later": False,
            "is_registered": False
        })
        # Сохраняем в кэш
        await cache_service.set(f"course_detail:{course_id}", course_data, ttl=300)
        return course_data

    # Для авторизованных пользователей проверяем статусы
    is_favorite = False
    is_watch_later = False
    is_registered = False

    fav_stmt = select(models.UserFavorite).where(
        and_(
            models.UserFavorite.user_id == current_user.id,
            models.UserFavorite.course_id == course_id
        )
    )
    fav_result = await db.execute(fav_stmt)
    is_favorite = fav_result.scalar_one_or_none() is not None

    wl_stmt = select(models.UserWatchLater).where(
        and_(
            models.UserWatchLater.user_id == current_user.id,
            models.UserWatchLater.course_id == course_id
        )
    )
    wl_result = await db.execute(wl_stmt)
    is_watch_later = wl_result.scalar_one_or_none() is not None

    reg_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    reg_result = await db.execute(reg_stmt)
    is_registered = reg_result.scalar_one_or_none() is not None

    course_data.update({
        "is_favorite": is_favorite,
        "is_watch_later": is_watch_later,
        "is_registered": is_registered
    })

    return course_data


@router.put("/{course_id}")
async def update_course(
        course_id: int,
        course: schemas.CourseUpdate,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    # Загружаем курс с явной загрузкой связей, чтобы избежать MissingGreenlet при commit/refresh
    stmt = select(models.Course).options(
        joinedload(models.Course.category),
        selectinload(models.Course.speakers)
    ).where(models.Course.id == course_id)
    result = await db.execute(stmt)
    db_course = result.unique().scalar_one_or_none()

    if not db_course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Обновляем основные поля
    for key, value in course.model_dump(exclude_unset=True).items():
        if key == "video_url" and value:
            platform = course.video_platform if hasattr(course, 'video_platform') else db_course.video_platform
            value = convert_video_url(value, platform or "youtube")
        setattr(db_course, key, value)

    # Обновление спикеров (если переданы)
    if course.speakers is not None:
        # Удаляем старых спикеров
        await db.execute(
            delete(models.CourseSpeaker).where(models.CourseSpeaker.course_id == course_id)
        )

        # Создаём новых спикеров
        for speaker_data in course.speakers:
            db_speaker = models.CourseSpeaker(
                course_id=course_id,
                full_name=speaker_data.full_name,
                bio=speaker_data.bio,
                photo_url=speaker_data.photo_url,
                position=speaker_data.position
            )
            db.add(db_speaker)

    await db.commit()

    # Очищаем кэш
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete(f"course_detail:{course_id}")
    await cache_service.delete("admin_stats")

    return {"message": "Course updated"}


@router.delete("/{course_id}")
async def delete_course(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_admin)
):
    stmt = select(models.Course).where(models.Course.id == course_id)
    result = await db.execute(stmt)
    course = result.scalar_one_or_none()

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    speakers_stmt = select(models.CourseSpeaker).where(models.CourseSpeaker.course_id == course_id)
    speakers_result = await db.execute(speakers_stmt)
    speakers = speakers_result.scalars().all()

    for speaker in speakers:
        if speaker.photo_url:
            delete_file_from_disk(speaker.photo_url)

    if course.image_url:
        delete_file_from_disk(course.image_url)

    await db.execute(models.CourseSpeaker.__table__.delete().where(models.CourseSpeaker.course_id == course_id))
    await db.execute(models.UserFavorite.__table__.delete().where(models.UserFavorite.course_id == course_id))
    await db.execute(models.UserWatchLater.__table__.delete().where(models.UserWatchLater.course_id == course_id))
    await db.execute(
        models.CourseRegistration.__table__.delete().where(models.CourseRegistration.course_id == course_id))
    await db.execute(models.UserProgress.__table__.delete().where(models.UserProgress.course_id == course_id))
    await db.execute(models.Certificate.__table__.delete().where(models.Certificate.course_id == course_id))

    await db.delete(course)
    await db.commit()

    # Очищаем кэш
    await cache_service.delete_pattern("courses_list*")
    await cache_service.delete(f"course_detail:{course_id}")
    await cache_service.delete("admin_stats")

    return {"message": "Course deleted successfully"}


@router.post("/{course_id}/favorite")
async def add_to_favorites(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing_stmt = select(models.UserFavorite).where(
        and_(
            models.UserFavorite.user_id == current_user.id,
            models.UserFavorite.course_id == course_id
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already in favorites")

    favorite = models.UserFavorite(user_id=current_user.id, course_id=course_id)
    db.add(favorite)
    await db.commit()
    return {"message": "Added to favorites"}


@router.delete("/{course_id}/favorite")
async def remove_from_favorites(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    stmt = select(models.UserFavorite).where(
        and_(
            models.UserFavorite.user_id == current_user.id,
            models.UserFavorite.course_id == course_id
        )
    )
    result = await db.execute(stmt)
    favorite = result.scalar_one_or_none()

    if not favorite:
        raise HTTPException(status_code=404, detail="Not in favorites")

    await db.delete(favorite)
    await db.commit()
    return {"message": "Removed from favorites"}


@router.post("/{course_id}/watch-later")
async def add_to_watch_later(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing_stmt = select(models.UserWatchLater).where(
        and_(
            models.UserWatchLater.user_id == current_user.id,
            models.UserWatchLater.course_id == course_id
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already in watch later")

    watch_later = models.UserWatchLater(user_id=current_user.id, course_id=course_id)
    db.add(watch_later)
    await db.commit()
    return {"message": "Added to watch later"}


@router.delete("/{course_id}/watch-later")
async def remove_from_watch_later(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    stmt = select(models.UserWatchLater).where(
        and_(
            models.UserWatchLater.user_id == current_user.id,
            models.UserWatchLater.course_id == course_id
        )
    )
    result = await db.execute(stmt)
    watch_later = result.scalar_one_or_none()

    if not watch_later:
        raise HTTPException(status_code=404, detail="Not in watch later")

    await db.delete(watch_later)
    await db.commit()
    return {"message": "Removed from watch later"}


@router.post("/{course_id}/register")
async def register_for_course(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if not course.is_active:
        raise HTTPException(status_code=400, detail="Course is not active")

    existing_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Already registered")

    if course.current_participants >= course.max_participants:
        raise HTTPException(status_code=400, detail="Course is full")

    user_stmt = select(models.User).options(
        selectinload(models.User.education),
        selectinload(models.User.work),
        selectinload(models.User.additional_info),
        selectinload(models.User.address)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    completion_details = user.get_profile_completion_details()
    if not completion_details["is_complete"]:
        missing_sections = []
        for section in completion_details["sections"]:
            if not section["is_complete"]:
                missing_sections.append({
                    "section": section["section"],
                    "label": section["label"],
                    "fields": section["fields"]
                })

        section_names = [s["label"] for s in missing_sections]
        message = f"Для записи на курс необходимо заполнить: {', '.join(section_names)}"

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "profile_incomplete",
                "message": message,
                "missing_sections": missing_sections,
                "redirect": "/profile"
            }
        )

    registration = models.CourseRegistration(
        user_id=current_user.id,
        course_id=course_id,
        is_paid=True
    )
    course.current_participants += 1
    db.add(registration)

    user_progress = models.UserProgress(
        user_id=current_user.id,
        course_id=course_id,
        progress_percent=0
    )
    db.add(user_progress)

    # ============================================================
    # ПОЛУЧАЕМ ЛОГИН И ПАРОЛЬ ДЛЯ MOODLE
    # ============================================================
    moodle_username = None
    moodle_password = None

    if course.moodle_course_id:
        try:
            moodle = MoodleService()

            # Проверяем, есть ли у пользователя аккаунт в Moodle
            moodle_user = moodle.get_user_by_email(current_user.email)

            if moodle_user:
                # Уже существует - получаем username
                moodle_username = moodle_user.get('username', current_user.email.split('@')[0])
                # Пароль генерируем новый (он будет обновлён при синхронизации)
                moodle_password = moodle.generate_password()
                # Сохраняем пароль в базе
                current_user.moodle_username = moodle_username
                current_user.moodle_password = moodle_password
            else:
                # Создаём нового пользователя в Moodle
                password = moodle.generate_password()
                moodle_user_id = moodle.create_user(
                    email=current_user.email,
                    full_name=current_user.full_name,
                    password=password
                )
                moodle_username = moodle.sanitize_username(current_user.email)
                moodle_password = password
                # Сохраняем в базе
                current_user.moodle_username = moodle_username
                current_user.moodle_password = moodle_password

            await db.flush()

        except Exception as e:
            print(f"Ошибка получения данных Moodle: {e}")
            # Не блокируем регистрацию, если не удалось получить данные

    # ============================================================
    # СОЗДАЁМ ЗАДАЧУ СИНХРОНИЗАЦИИ
    # ============================================================
    task_created = False
    task_id = None

    if course.moodle_course_id:
        try:
            sync_db = SessionLocal()
            try:
                sync_service = MoodleSyncService(sync_db)
                task = sync_service.create_sync_task(current_user.id, course_id)
                task_created = True
                task_id = task.id
            finally:
                sync_db.close()
        except Exception as e:
            task_created = False
            print(f"Ошибка создания задачи синхронизации: {e}")

    # ============================================================
    # СОЗДАЁМ УВЕДОМЛЕНИЕ ДЛЯ ПОЛЬЗОВАТЕЛЯ
    # ============================================================
    if moodle_username and moodle_password and course.moodle_course_id:
        notification_message = (
            f"✅ Вы записаны на курс «{course.title}».\n\n"
            f"🔑 Данные для входа в Moodle:\n"
            f"🌐 Ссылка: https://iro-lms.ru/\n"
            f"👤 Логин: {moodle_username}\n"
            f"🔐 Пароль: {moodle_password}\n\n"
            f"💡 Рекомендуем сменить пароль после первого входа.\n"
            f"📧 Пароль также отправлен на вашу почту."
        )
        create_notification(
            db,
            current_user.id,
            f"🎓 Доступ к курсу «{course.title}»",
            notification_message
        )
    else:
        notification_message = f"✅ Вы записаны на курс «{course.title}».\n\n"
        if course.moodle_course_id:
            notification_message += (
                "📌 Доступ к Moodle будет предоставлен в ближайшее время.\n"
                "Данные для входа появятся в личном кабинете."
            )
        else:
            notification_message += "📌 Курс не требует входа в Moodle."

        create_notification(
            db,
            current_user.id,
            f"🎓 Запись на курс «{course.title}»",
            notification_message
        )

    activity = models.UserActivityLog(
        user_id=current_user.id,
        action_type="course_register",
        course_id=course_id,
        extra_data=json.dumps({
            "course_title": course.title,
            "moodle_course_id": course.moodle_course_id,
            "sync_task_created": task_created,
            "sync_task_id": task_id,
            "moodle_username": moodle_username,
            "moodle_password": moodle_password
        })
    )
    db.add(activity)

    await db.commit()

    # Очищаем кэш курса
    await cache_service.delete(f"course_detail:{course_id}")
    await cache_service.delete_pattern("courses_list*")

    # ============================================================
    # ФОРМИРУЕМ ОТВЕТ С ДАННЫМИ ДЛЯ ВХОДА
    # ============================================================
    response = {
        "message": "Вы успешно записаны на курс!",
        "course_id": course_id,
        "course_title": course.title,
        "sync_task_created": task_created,
        "moodle_course_id": course.moodle_course_id,
        "has_moodle": bool(course.moodle_course_id)
    }

    if task_id:
        response["sync_task_id"] = task_id

    # Возвращаем логин и пароль, если есть
    if moodle_username and moodle_password and course.moodle_course_id:
        response["moodle_username"] = moodle_username
        response["moodle_password"] = moodle_password
        response["moodle_url"] = "https://iro-lms.ru/"
        response["moodle_credentials_shown"] = True
    else:
        response["moodle_credentials_shown"] = False

    if course.moodle_course_id and not task_created:
        response[
            "warning"] = "Запись выполнена, но возникла проблема с созданием задачи синхронизации. Пожалуйста, обратитесь в поддержку."

    return response


@router.get("/{course_id}/sync-status")
async def get_sync_status(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    reg_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    reg_result = await db.execute(reg_stmt)
    registration = reg_result.scalar_one_or_none()

    if not registration:
        raise HTTPException(status_code=403, detail="Вы не записаны на этот курс")

    if not course.moodle_course_id:
        return {
            "has_moodle": False,
            "status": "not_connected",
            "message": "Курс не привязан к Moodle"
        }

    sync_db = SessionLocal()
    try:
        sync_service = MoodleSyncService(sync_db)
        status = sync_service.get_task_status(current_user.id, course_id)
    finally:
        sync_db.close()

    if not status:
        return {
            "has_moodle": True,
            "status": "no_task",
            "moodle_course_id": course.moodle_course_id,
            "message": "Задача синхронизации не найдена. Возможно, синхронизация еще не запущена."
        }

    status_map = {
        "pending": "В очереди",
        "processing": "Выполняется",
        "completed": "Завершено",
        "failed": "Ошибка"
    }

    return {
        "has_moodle": True,
        "moodle_course_id": course.moodle_course_id,
        "task_id": status["id"],
        "status": status["status"],
        "status_display": status_map.get(status["status"], status["status"]),
        "attempts": status["attempts"],
        "max_attempts": status["max_attempts"],
        "last_error": status["last_error"],
        "created_at": status["created_at"],
        "processed_at": status["processed_at"],
        "next_retry_at": status["next_retry_at"],
        "moodle_user_id": status["moodle_user_id"]
    }


@router.get("/{course_id}/check-registration-eligibility")
async def check_registration_eligibility(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        return {"eligible": False, "reason": "course_not_found", "message": "Курс не найден"}

    user_stmt = select(models.User).options(
        selectinload(models.User.education),
        selectinload(models.User.work),
        selectinload(models.User.additional_info),
        selectinload(models.User.address)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        return {"eligible": False, "reason": "user_not_found", "message": "Пользователь не найден"}

    completion_details = user.get_profile_completion_details()

    if not completion_details["is_complete"]:
        missing_sections = []
        for section in completion_details["sections"]:
            if not section["is_complete"]:
                missing_sections.append({
                    "section": section["section"],
                    "label": section["label"],
                    "fields": section["fields"]
                })

        section_names = [s["label"] for s in missing_sections]
        message = f"Для записи на курс необходимо заполнить: {', '.join(section_names)}"

        return {
            "eligible": False,
            "reason": "profile_incomplete",
            "message": message,
            "missing_sections": missing_sections,
            "redirect": "/profile",
            "completion_details": completion_details
        }

    existing_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"eligible": False, "reason": "already_registered", "message": "Вы уже записаны на этот курс"}

    if course.current_participants >= course.max_participants:
        return {"eligible": False, "reason": "course_full", "message": "Курс полностью заполнен"}

    return {"eligible": True, "message": "Вы можете записаться на курс"}


@router.get("/{course_id}/moodle-link")
async def get_moodle_link(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    reg_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    reg_result = await db.execute(reg_stmt)
    registration = reg_result.scalar_one_or_none()

    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")

    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if not course.moodle_course_id:
        return {
            "has_moodle": False,
            "message": "This course is not connected to Moodle"
        }

    moodle = MoodleService()
    try:
        moodle_user_id = moodle.sync_user(
            email=current_user.email,
            full_name=current_user.full_name
        )

        is_enrolled = moodle.is_user_enrolled(moodle_user_id, course.moodle_course_id)

        if not is_enrolled:
            moodle.enroll_user_to_course(moodle_user_id, course.moodle_course_id)

        return {
            "has_moodle": True,
            "moodle_course_url": moodle.get_course_url(course.moodle_course_id),
            "moodle_course_id": course.moodle_course_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Moodle link: {str(e)}")


@router.get("/{course_id}/moodle-progress")
async def get_moodle_course_progress(
        course_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    reg_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    reg_result = await db.execute(reg_stmt)
    registration = reg_result.scalar_one_or_none()

    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")

    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if not course.moodle_course_id:
        return {
            "has_moodle": False,
            "message": "This course is not connected to Moodle"
        }

    moodle = MoodleService()

    try:
        moodle_user_id = moodle.sync_user(
            email=current_user.email,
            full_name=current_user.full_name
        )

        is_enrolled = moodle.is_user_enrolled(moodle_user_id, course.moodle_course_id)

        if not is_enrolled:
            moodle.enroll_user_to_course(moodle_user_id, course.moodle_course_id)

        progress = moodle.get_course_progress(moodle_user_id, course.moodle_course_id)

        activities = []
        for activity in progress.get('activities', []):
            activities.append({
                'id': activity.get('cmid'),
                'name': activity.get('name', 'Без названия'),
                'type': activity.get('type', 'unknown'),
                'completed': activity.get('completionstate', 0) > 0,
                'completionstate': activity.get('completionstate', 0),
                'timecompleted': activity.get('timecompleted'),
                'url': activity.get('url', '')
            })

        return {
            "has_moodle": True,
            "course_id": course_id,
            "moodle_course_id": course.moodle_course_id,
            "is_completed": progress.get('completed', False),
            "progress_percent": progress.get('progress_percent', 0),
            "timecompleted": progress.get('timecompleted'),
            "total_activities": progress.get('total_activities', 0),
            "completed_activities": progress.get('completed_activities', 0),
            "activities": activities
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Moodle progress: {str(e)}")


@router.get("/my/moodle-progress")
async def get_all_moodle_progress(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    reg_stmt = select(models.CourseRegistration).where(
        models.CourseRegistration.user_id == current_user.id
    )
    reg_result = await db.execute(reg_stmt)
    registrations = reg_result.scalars().all()

    moodle_courses = []
    for reg in registrations:
        course_stmt = select(models.Course).where(models.Course.id == reg.course_id)
        course_result = await db.execute(course_stmt)
        course = course_result.scalar_one_or_none()
        if course and course.moodle_course_id:
            moodle_courses.append({
                'course_id': course.id,
                'course_title': course.title,
                'moodle_course_id': course.moodle_course_id,
                'registered_at': reg.registered_at
            })

    if not moodle_courses:
        return {
            "has_moodle": False,
            "message": "No courses connected to Moodle",
            "courses": []
        }

    moodle = MoodleService()
    results = []

    try:
        moodle_user_id = moodle.sync_user(
            email=current_user.email,
            full_name=current_user.full_name
        )

        for course_info in moodle_courses:
            try:
                is_enrolled = moodle.is_user_enrolled(moodle_user_id, course_info['moodle_course_id'])

                if not is_enrolled:
                    moodle.enroll_user_to_course(moodle_user_id, course_info['moodle_course_id'])

                progress = moodle.get_course_progress(moodle_user_id, course_info['moodle_course_id'])

                results.append({
                    'course_id': course_info['course_id'],
                    'course_title': course_info['course_title'],
                    'moodle_course_id': course_info['moodle_course_id'],
                    'is_completed': progress.get('completed', False),
                    'progress_percent': progress.get('progress_percent', 0),
                    'total_activities': progress.get('total_activities', 0),
                    'completed_activities': progress.get('completed_activities', 0)
                })
            except Exception as e:
                results.append({
                    'course_id': course_info['course_id'],
                    'course_title': course_info['course_title'],
                    'moodle_course_id': course_info['moodle_course_id'],
                    'error': str(e)
                })

        return {
            "has_moodle": True,
            "user_id": current_user.id,
            "moodle_user_id": moodle_user_id,
            "courses": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Moodle progress: {str(e)}")


@router.post("/{course_id}/progress")
async def update_course_progress(
        course_id: int,
        progress: int = Query(..., ge=0, le=100),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    course_stmt = select(models.Course).where(models.Course.id == course_id)
    course_result = await db.execute(course_stmt)
    course = course_result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    reg_stmt = select(models.CourseRegistration).where(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    )
    reg_result = await db.execute(reg_stmt)
    registration = reg_result.scalar_one_or_none()

    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")

    progress_stmt = select(models.UserProgress).where(
        and_(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.course_id == course_id
        )
    )
    progress_result = await db.execute(progress_stmt)
    user_progress = progress_result.scalar_one_or_none()

    if not user_progress:
        user_progress = models.UserProgress(
            user_id=current_user.id,
            course_id=course_id,
            progress_percent=progress
        )
        db.add(user_progress)

        activity = models.UserActivityLog(
            user_id=current_user.id,
            action_type="course_start",
            course_id=course_id,
            extra_data=json.dumps({"course_title": course.title})
        )
        db.add(activity)
    else:
        user_progress.progress_percent = progress
        user_progress.last_activity = datetime.utcnow()

    if progress >= 100 and not user_progress.is_completed:
        user_progress.is_completed = True
        user_progress.completed_at = datetime.utcnow()
        registration.is_paid = True

        activity = models.UserActivityLog(
            user_id=current_user.id,
            action_type="course_complete",
            course_id=course_id,
            extra_data=json.dumps({"course_title": course.title})
        )
        db.add(activity)

        cert_number = f"CERT-{current_user.id}-{course_id}-{int(datetime.utcnow().timestamp())}"
        cert_hash = hashlib.md5(cert_number.encode()).hexdigest()[:16].upper()

        certificate = models.Certificate(
            user_id=current_user.id,
            course_id=course_id,
            certificate_number=cert_hash
        )
        db.add(certificate)

        from app.routers.achievements_router import check_and_award_achievements
        await check_and_award_achievements(current_user.id, db)

    await db.commit()
    return {"message": "Progress updated", "progress": progress, "is_completed": user_progress.is_completed}


@router.get("/my/progress")
async def get_my_progress(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.progress).selectinload(models.UserProgress.course)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result_items = []
    for p in user.progress:
        if p.course:
            result_items.append({
                "course_id": p.course_id,
                "course_title": p.course.title,
                "progress_percent": p.progress_percent,
                "is_completed": p.is_completed,
                "started_at": p.started_at,
                "completed_at": p.completed_at,
                "last_activity": p.last_activity
            })
    return result_items


@router.get("/my/achievements")
async def get_my_achievements(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.achievements)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    achievements = sorted(user.achievements, key=lambda a: a.earned_at, reverse=True)

    return [{
        "id": a.id,
        "achievement_id": a.achievement_id,
        "title": a.achievement_title,
        "description": a.achievement_description,
        "icon": a.achievement_icon,
        "level": a.achievement_level,
        "earned_at": a.earned_at
    } for a in achievements]


@router.get("/my/certificates")
async def get_my_certificates(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.certificates).selectinload(models.Certificate.course)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    certificates = sorted(user.certificates, key=lambda c: c.issue_date, reverse=True)

    return [{
        "id": c.id,
        "course_id": c.course_id,
        "course_title": c.course.title if c.course else "Курс",
        "certificate_number": c.certificate_number,
        "issue_date": c.issue_date,
        "pdf_url": c.pdf_url
    } for c in certificates]


@router.get("/my/activity")
async def get_my_activity(
        limit: int = Query(20, le=100),
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.activity_logs).selectinload(models.UserActivityLog.course)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    activities = sorted(user.activity_logs, key=lambda a: a.created_at, reverse=True)[:limit]

    return [{
        "id": a.id,
        "action_type": a.action_type,
        "course_id": a.course_id,
        "course_title": a.course.title if a.course else None,
        "extra_data": json.loads(a.extra_data) if a.extra_data else {},
        "created_at": a.created_at
    } for a in activities]


@router.get("/my/registrations")
async def get_my_registrations(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.registrations).selectinload(models.CourseRegistration.course),
        selectinload(models.User.progress)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    progress_map = {p.course_id: p for p in user.progress}

    result_items = []
    for r in user.registrations:
        course = r.course
        progress_percent = 0
        is_completed = False

        if course and course.id in progress_map:
            p = progress_map[course.id]
            progress_percent = p.progress_percent
            is_completed = p.is_completed

        result_items.append({
            "course_id": r.course_id,
            "course_title": course.title if course else "Unknown",
            "registered_at": r.registered_at,
            "progress": progress_percent,
            "is_completed": is_completed,
            "moodle_course_id": course.moodle_course_id if course else None,
            "moodle_username": current_user.moodle_username if current_user.moodle_username else None,
            "has_moodle_password": bool(current_user.moodle_password)
        })

    return result_items


@router.get("/my/favorites")
async def get_my_favorites(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.favorite_courses).selectinload(models.UserFavorite.course)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result_items = []
    for fav in user.favorite_courses:
        if fav.course:
            result_items.append({
                "id": fav.course.id,
                "title": fav.course.title,
                "short_description": fav.course.short_description,
                "image_url": fav.course.image_url,
                "description": fav.course.description,
                "moodle_course_id": fav.course.moodle_course_id
            })
    return result_items


@router.get("/my/watch-later")
async def get_my_watch_later(
        db: AsyncSession = Depends(get_async_db),
        current_user: models.User = Depends(auth.get_current_active_user)
):
    user_stmt = select(models.User).options(
        selectinload(models.User.watch_later).selectinload(models.UserWatchLater.course)
    ).where(models.User.id == current_user.id)
    user_result = await db.execute(user_stmt)
    user = user_result.unique().scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result_items = []
    for wl in user.watch_later:
        if wl.course:
            result_items.append({
                "id": wl.course.id,
                "title": wl.course.title,
                "short_description": wl.course.short_description,
                "image_url": wl.course.image_url,
                "description": wl.course.description,
                "moodle_course_id": wl.course.moodle_course_id
            })
    return result_items