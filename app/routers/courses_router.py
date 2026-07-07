# app/routers/courses_router.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from app import models, schemas, auth
from app.database import get_db
from app.services.moodle_service import MoodleService
from app.dependencies import require_complete_profile
from typing import Optional
import json
from datetime import datetime

router = APIRouter(prefix="/api/courses", tags=["Courses"])


def convert_video_url(url: str, platform: str = "youtube") -> str:
    """Преобразует URL видео в embed формат для разных платформ"""
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


# ========== ПОЛУЧЕНИЕ СПИСКА КУРСОВ (С ИСПРАВЛЕНИЕМ N+1) ==========

@router.get("/")
def get_courses(
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    """
    Получение списка курсов с пагинацией и оптимизированными запросами.
    Использует joinedload для предотвращения N+1 запросов.
    """
    query = db.query(models.Course).filter(models.Course.is_active == True)
    
    if category_id:
        query = query.filter(models.Course.category_id == category_id)
    
    if search:
        query = query.filter(
            or_(
                models.Course.title.ilike(f"%{search}%"),
                models.Course.description.ilike(f"%{search}%"),
                models.Course.hashtags.ilike(f"%{search}%")
            )
        )
    
    # Оптимизация: загружаем связанные данные одним запросом
    query = query.options(
        joinedload(models.Course.category),
        joinedload(models.Course.speakers)
    )
    
    total = query.count()
    courses = query.order_by(models.Course.created_at.desc()).offset(offset).limit(limit).all()
    
    user_favorites = set()
    user_watch_later = set()
    
    if current_user:
        favorites = db.query(models.UserFavorite).filter(
            models.UserFavorite.user_id == current_user.id
        ).all()
        user_favorites = {fav.course_id for fav in favorites}
        
        watch_later = db.query(models.UserWatchLater).filter(
            models.UserWatchLater.user_id == current_user.id
        ).all()
        user_watch_later = {wl.course_id for wl in watch_later}
    
    result = []
    for c in courses:
        result.append({
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
        "items": result
    }


@router.post("/")
def create_course(
    course: schemas.CourseCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    if course.category_id:
        category = db.query(models.Category).filter(
            models.Category.id == course.category_id
        ).first()
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
    db.commit()
    db.refresh(db_course)
    
    for speaker in course.speakers:
        db_speaker = models.CourseSpeaker(
            course_id=db_course.id,
            full_name=speaker.full_name,
            bio=speaker.bio,
            photo_url=speaker.photo_url,
            position=speaker.position
        )
        db.add(db_speaker)
    
    db.commit()
    return {"message": "Course created", "id": db_course.id}


@router.get("/{course_id}")
def get_course(
    course_id: int, 
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user_optional)
):
    """Получение одного курса с оптимизированной загрузкой связей"""
    course = db.query(models.Course).options(
        joinedload(models.Course.category),
        joinedload(models.Course.speakers)
    ).filter(models.Course.id == course_id).first()
    
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    is_favorite = False
    is_watch_later = False
    
    if current_user:
        fav = db.query(models.UserFavorite).filter(
            and_(
                models.UserFavorite.user_id == current_user.id,
                models.UserFavorite.course_id == course_id
            )
        ).first()
        is_favorite = fav is not None
        
        wl = db.query(models.UserWatchLater).filter(
            and_(
                models.UserWatchLater.user_id == current_user.id,
                models.UserWatchLater.course_id == course_id
            )
        ).first()
        is_watch_later = wl is not None
    
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
        "is_favorite": is_favorite,
        "is_watch_later": is_watch_later,
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


@router.put("/{course_id}")
def update_course(
    course_id: int,
    course: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    db_course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    for key, value in course.model_dump(exclude_unset=True).items():
        if key == "video_url" and value:
            platform = course.video_platform if hasattr(course, 'video_platform') else db_course.video_platform
            value = convert_video_url(value, platform or "youtube")
        setattr(db_course, key, value)
    
    db.commit()
    return {"message": "Course updated"}


@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
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


@router.post("/{course_id}/favorite")
def add_to_favorites(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.UserFavorite).filter(
        and_(
            models.UserFavorite.user_id == current_user.id,
            models.UserFavorite.course_id == course_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already in favorites")
    
    favorite = models.UserFavorite(user_id=current_user.id, course_id=course_id)
    db.add(favorite)
    db.commit()
    return {"message": "Added to favorites"}


@router.delete("/{course_id}/favorite")
def remove_from_favorites(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    favorite = db.query(models.UserFavorite).filter(
        and_(
            models.UserFavorite.user_id == current_user.id,
            models.UserFavorite.course_id == course_id
        )
    ).first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Not in favorites")
    
    db.delete(favorite)
    db.commit()
    return {"message": "Removed from favorites"}


@router.post("/{course_id}/watch-later")
def add_to_watch_later(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.UserWatchLater).filter(
        and_(
            models.UserWatchLater.user_id == current_user.id,
            models.UserWatchLater.course_id == course_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already in watch later")
    
    watch_later = models.UserWatchLater(user_id=current_user.id, course_id=course_id)
    db.add(watch_later)
    db.commit()
    return {"message": "Added to watch later"}


@router.delete("/{course_id}/watch-later")
def remove_from_watch_later(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    watch_later = db.query(models.UserWatchLater).filter(
        and_(
            models.UserWatchLater.user_id == current_user.id,
            models.UserWatchLater.course_id == course_id
        )
    ).first()
    if not watch_later:
        raise HTTPException(status_code=404, detail="Not in watch later")
    
    db.delete(watch_later)
    db.commit()
    return {"message": "Removed from watch later"}


# ========== РЕГИСТРАЦИЯ НА КУРС ==========

@router.post("/{course_id}/register")
def register_for_course(
    course_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_complete_profile)
):
    """Запись на курс с синхронизацией с Moodle"""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    if not course.is_active:
        raise HTTPException(status_code=400, detail="Course is not active")
    
    existing = db.query(models.CourseRegistration).filter(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already registered")
    
    if course.current_participants >= course.max_participants:
        raise HTTPException(status_code=400, detail="Course is full")
    
    moodle_enrolled = False
    moodle_course_url = None
    moodle_user_id = None
    moodle_error = None
    
    if course.moodle_course_id:
        moodle = MoodleService()
        try:
            moodle_user_id = moodle.sync_user(
                email=current_user.email,
                full_name=current_user.full_name
            )
            
            is_enrolled = moodle.is_user_enrolled(moodle_user_id, course.moodle_course_id)
            
            if not is_enrolled:
                moodle.enroll_user_to_course(moodle_user_id, course.moodle_course_id)
            
            moodle_enrolled = True
            moodle_course_url = moodle.get_course_url(course.moodle_course_id)
            
        except Exception as e:
            moodle_error = str(e)
            print(f"Moodle sync error: {e}")
    
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
    
    activity = models.UserActivityLog(
        user_id=current_user.id,
        action_type="course_register",
        course_id=course_id,
        extra_data=json.dumps({
            "course_title": course.title,
            "moodle_enrolled": moodle_enrolled,
            "moodle_course_id": course.moodle_course_id,
            "moodle_error": moodle_error
        })
    )
    db.add(activity)
    
    db.commit()
    
    response = {
        "message": "Successfully registered",
        "course_id": course_id,
        "course_title": course.title,
        "moodle_enrolled": moodle_enrolled
    }
    
    if moodle_course_url:
        response["moodle_course_url"] = moodle_course_url
        response["message"] = "Successfully registered! You can now access the course in Moodle."
    elif moodle_error:
        response["moodle_error"] = moodle_error
        response["message"] = "Registered in the system, but Moodle sync failed. Please contact support."
    
    return response


@router.get("/{course_id}/check-registration-eligibility")
def check_registration_eligibility(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Проверяет, может ли пользователь записаться на курс"""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        return {"eligible": False, "reason": "course_not_found", "message": "Курс не найден"}
    
    completion_details = current_user.get_profile_completion_details()
    
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
    
    existing = db.query(models.CourseRegistration).filter(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    ).first()
    if existing:
        return {"eligible": False, "reason": "already_registered", "message": "Вы уже записаны на этот курс"}
    
    if course.current_participants >= course.max_participants:
        return {"eligible": False, "reason": "course_full", "message": "Курс полностью заполнен"}
    
    return {"eligible": True, "message": "Вы можете записаться на курс"}


@router.get("/{course_id}/moodle-link")
def get_moodle_link(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить ссылку на курс в Moodle"""
    registration = db.query(models.CourseRegistration).filter(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    ).first()
    
    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")
    
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
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
def get_moodle_course_progress(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить прогресс пользователя по курсу из Moodle"""
    registration = db.query(models.CourseRegistration).filter(
        and_(
            models.CourseRegistration.user_id == current_user.id,
            models.CourseRegistration.course_id == course_id
        )
    ).first()
    
    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")
    
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
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
def get_all_moodle_progress(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить прогресс по всем курсам пользователя в Moodle"""
    registrations = db.query(models.CourseRegistration).filter(
        models.CourseRegistration.user_id == current_user.id
    ).all()
    
    moodle_courses = []
    course_ids = []
    for reg in registrations:
        course = db.query(models.Course).filter(models.Course.id == reg.course_id).first()
        if course and course.moodle_course_id:
            moodle_courses.append({
                'course_id': course.id,
                'course_title': course.title,
                'moodle_course_id': course.moodle_course_id,
                'registered_at': reg.registered_at
            })
            course_ids.append(course.id)
    
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


# ========== ПРОГРЕСС И СТАТИСТИКА ==========

@router.post("/{course_id}/progress")
def update_course_progress(
    course_id: int,
    progress: int = Query(..., ge=0, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Обновление прогресса по курсу"""
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    registration = db.query(models.CourseRegistration).filter(
        and_(
            models.CourseRegistration.user_id == current_user.id, 
            models.CourseRegistration.course_id == course_id
        )
    ).first()
    
    if not registration:
        raise HTTPException(status_code=403, detail="You are not registered for this course")
    
    user_progress = db.query(models.UserProgress).filter(
        and_(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.course_id == course_id
        )
    ).first()
    
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
        
        import hashlib
        import time
        cert_number = f"CERT-{current_user.id}-{course_id}-{int(time.time())}"
        cert_hash = hashlib.md5(cert_number.encode()).hexdigest()[:16].upper()
        
        certificate = models.Certificate(
            user_id=current_user.id,
            course_id=course_id,
            certificate_number=cert_hash
        )
        db.add(certificate)
        
        from app.routers.achievements_router import check_and_award_achievements
        check_and_award_achievements(current_user.id, db)
    
    db.commit()
    return {"message": "Progress updated", "progress": progress, "is_completed": user_progress.is_completed}


@router.get("/my/progress")
def get_my_progress(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    progress = db.query(models.UserProgress).filter(
        models.UserProgress.user_id == current_user.id
    ).all()
    
    result = []
    for p in progress:
        if p.course:
            result.append({
                "course_id": p.course_id,
                "course_title": p.course.title,
                "progress_percent": p.progress_percent,
                "is_completed": p.is_completed,
                "started_at": p.started_at,
                "completed_at": p.completed_at,
                "last_activity": p.last_activity
            })
    return result


@router.get("/my/stats")
def get_my_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    registrations = db.query(models.CourseRegistration).filter(
        models.CourseRegistration.user_id == current_user.id
    ).all()
    registered_courses = [r.course_id for r in registrations]
    
    completed_progress = db.query(models.UserProgress).filter(
        and_(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.is_completed == True
        )
    ).count()
    
    in_progress = db.query(models.UserProgress).filter(
        and_(
            models.UserProgress.user_id == current_user.id,
            models.UserProgress.is_completed == False,
            models.UserProgress.progress_percent > 0
        )
    ).count()
    
    achievements_count = db.query(models.UserAchievement).filter(
        models.UserAchievement.user_id == current_user.id
    ).count()
    
    total_hours = completed_progress * 36
    
    favorites_count = db.query(models.UserFavorite).filter(
        models.UserFavorite.user_id == current_user.id
    ).count()
    
    watch_later_count = db.query(models.UserWatchLater).filter(
        models.UserWatchLater.user_id == current_user.id
    ).count()
    
    return {
        "total_courses": len(registered_courses),
        "completed_courses": completed_progress,
        "in_progress_courses": in_progress,
        "achievements_count": achievements_count,
        "total_hours": total_hours,
        "favorites_count": favorites_count,
        "watch_later_count": watch_later_count
    }


@router.get("/my/achievements")
def get_my_achievements(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    achievements = db.query(models.UserAchievement).filter(
        models.UserAchievement.user_id == current_user.id
    ).order_by(models.UserAchievement.earned_at.desc()).all()
    
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
def get_my_certificates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    certificates = db.query(models.Certificate).filter(
        models.Certificate.user_id == current_user.id
    ).order_by(models.Certificate.issue_date.desc()).all()
    
    return [{
        "id": c.id,
        "course_id": c.course_id,
        "course_title": c.course.title if c.course else "Курс",
        "certificate_number": c.certificate_number,
        "issue_date": c.issue_date,
        "pdf_url": c.pdf_url
    } for c in certificates]


@router.get("/my/activity")
def get_my_activity(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    activities = db.query(models.UserActivityLog).filter(
        models.UserActivityLog.user_id == current_user.id
    ).order_by(models.UserActivityLog.created_at.desc()).limit(limit).all()
    
    return [{
        "id": a.id,
        "action_type": a.action_type,
        "course_id": a.course_id,
        "course_title": a.course.title if a.course else None,
        "extra_data": json.loads(a.extra_data) if a.extra_data else {},
        "created_at": a.created_at
    } for a in activities]


@router.get("/my/registrations")
def get_my_registrations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Получить мои регистрации на курсы с прогрессом"""
    registrations = db.query(models.CourseRegistration).filter(
        models.CourseRegistration.user_id == current_user.id
    ).all()
    
    result = []
    for r in registrations:
        course = r.course
        progress_percent = 0
        is_completed = False
        
        user_progress = db.query(models.UserProgress).filter(
            and_(
                models.UserProgress.user_id == current_user.id,
                models.UserProgress.course_id == course.id
            )
        ).first()
        
        if user_progress:
            progress_percent = user_progress.progress_percent
            is_completed = user_progress.is_completed
        
        result.append({
            "course_id": r.course_id,
            "course_title": course.title if course else "Unknown",
            "registered_at": r.registered_at,
            "progress": progress_percent,
            "is_completed": is_completed,
            "moodle_course_id": course.moodle_course_id if course else None
        })
    
    return result


@router.get("/my/favorites")
def get_my_favorites(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    favorites = db.query(models.UserFavorite).filter(
        models.UserFavorite.user_id == current_user.id
    ).all()
    
    result = []
    for fav in favorites:
        if fav.course:
            result.append({
                "id": fav.course.id,
                "title": fav.course.title,
                "short_description": fav.course.short_description,
                "image_url": fav.course.image_url,
                "description": fav.course.description,
                "moodle_course_id": fav.course.moodle_course_id
            })
    return result


@router.get("/my/watch-later")
def get_my_watch_later(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    watch_later = db.query(models.UserWatchLater).filter(
        models.UserWatchLater.user_id == current_user.id
    ).all()
    
    result = []
    for wl in watch_later:
        if wl.course:
            result.append({
                "id": wl.course.id,
                "title": wl.course.title,
                "short_description": wl.course.short_description,
                "image_url": wl.course.image_url,
                "description": wl.course.description,
                "moodle_course_id": wl.course.moodle_course_id
            })
    return result