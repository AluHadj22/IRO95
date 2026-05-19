from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app import models, schemas, auth
from app.database import get_db
from typing import Optional

router = APIRouter(prefix="/api/courses", tags=["Courses"])

@router.get("/")
def get_courses(
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user)
):
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
    
    courses = query.order_by(models.Course.created_at.desc()).all()
    
    user_favorites = set()
    user_watch_later = set()
    
    if current_user:
        favorites = db.query(models.UserFavorite).filter(models.UserFavorite.user_id == current_user.id).all()
        user_favorites = {fav.course_id for fav in favorites}
        
        watch_later = db.query(models.UserWatchLater).filter(models.UserWatchLater.user_id == current_user.id).all()
        user_watch_later = {wl.course_id for wl in watch_later}
    
    result = []
    for c in courses:
        result.append({
            "id": c.id, "title": c.title, "short_description": c.short_description,
            "description": c.description, "price": c.price, "image_url": c.image_url,
            "video_url": c.video_url, "hashtags": c.hashtags, "keywords": c.keywords,
            "current_participants": c.current_participants, "max_participants": c.max_participants,
            "category_name": c.category.name if c.category else None,
            "category_id": c.category_id,
            "is_favorite": c.id in user_favorites, "is_watch_later": c.id in user_watch_later,
            "start_date": c.start_date, "end_date": c.end_date,
            "speakers": [{"id": s.id, "full_name": s.full_name, "bio": s.bio, 
                          "photo_url": s.photo_url, "position": s.position} for s in c.speakers]
        })
    return result

@router.post("/")
def create_course(
    course: schemas.CourseCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_admin)
):
    # Проверяем существование категории
    if course.category_id:
        category = db.query(models.Category).filter(models.Category.id == course.category_id).first()
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
    
    # Создаем курс
    db_course = models.Course(
        title=course.title,
        description=course.description,
        short_description=course.short_description,
        category_id=course.category_id,
        image_url=course.image_url,  # URL загруженного изображения
        video_url=course.video_url,
        hashtags=course.hashtags,
        keywords=course.keywords,
        price=course.price,
        max_participants=course.max_participants,
        start_date=course.start_date,
        end_date=course.end_date,
        created_by=current_user.id
    )
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    
    # Добавляем спикеров с их фото
    for speaker in course.speakers:
        db_speaker = models.CourseSpeaker(
            course_id=db_course.id,
            full_name=speaker.full_name,
            bio=speaker.bio,
            photo_url=speaker.photo_url,  # URL загруженного фото спикера
            position=speaker.position
        )
        db.add(db_speaker)
    
    db.commit()
    return {"message": "Course created", "id": db_course.id}

@router.get("/{course_id}")
def get_course(course_id: int, db: Session = Depends(get_db),
               current_user: Optional[models.User] = Depends(auth.get_current_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    is_favorite = False
    is_watch_later = False
    
    if current_user:
        fav = db.query(models.UserFavorite).filter(
            and_(models.UserFavorite.user_id == current_user.id, models.UserFavorite.course_id == course_id)
        ).first()
        is_favorite = fav is not None
        
        wl = db.query(models.UserWatchLater).filter(
            and_(models.UserWatchLater.user_id == current_user.id, models.UserWatchLater.course_id == course_id)
        ).first()
        is_watch_later = wl is not None
    
    return {
        "id": course.id, "title": course.title, "description": course.description,
        "short_description": course.short_description, "price": course.price,
        "image_url": course.image_url, "video_url": course.video_url,
        "hashtags": course.hashtags, "keywords": course.keywords,
        "current_participants": course.current_participants, "max_participants": course.max_participants,
        "category_id": course.category_id, "category_name": course.category.name if course.category else None,
        "start_date": course.start_date, "end_date": course.end_date, "is_active": course.is_active,
        "is_favorite": is_favorite, "is_watch_later": is_watch_later,
        "speakers": [{"id": s.id, "full_name": s.full_name, "bio": s.bio, 
                      "photo_url": s.photo_url, "position": s.position} for s in course.speakers]
    }

@router.put("/{course_id}")
def update_course(course_id: int, course: schemas.CourseUpdate, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_admin)):
    db_course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not db_course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    for key, value in course.model_dump(exclude_unset=True).items():
        setattr(db_course, key, value)
    
    db.commit()
    return {"message": "Course updated"}

@router.delete("/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_admin)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Удаляем связанных спикеров
    db.query(models.CourseSpeaker).filter(models.CourseSpeaker.course_id == course_id).delete()
    
    # Удаляем из избранного
    db.query(models.UserFavorite).filter(models.UserFavorite.course_id == course_id).delete()
    
    # Удаляем из "посмотреть позже"
    db.query(models.UserWatchLater).filter(models.UserWatchLater.course_id == course_id).delete()
    
    # Удаляем регистрации
    db.query(models.CourseRegistration).filter(models.CourseRegistration.course_id == course_id).delete()
    
    # Удаляем сам курс
    db.delete(course)
    db.commit()
    return {"message": "Course deleted successfully"}

@router.post("/{course_id}/favorite")
def add_to_favorites(course_id: int, db: Session = Depends(get_db),
                     current_user: models.User = Depends(auth.get_current_active_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.UserFavorite).filter(
        and_(models.UserFavorite.user_id == current_user.id, models.UserFavorite.course_id == course_id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already in favorites")
    
    favorite = models.UserFavorite(user_id=current_user.id, course_id=course_id)
    db.add(favorite)
    db.commit()
    return {"message": "Added to favorites"}

@router.delete("/{course_id}/favorite")
def remove_from_favorites(course_id: int, db: Session = Depends(get_db),
                          current_user: models.User = Depends(auth.get_current_active_user)):
    favorite = db.query(models.UserFavorite).filter(
        and_(models.UserFavorite.user_id == current_user.id, models.UserFavorite.course_id == course_id)
    ).first()
    if not favorite:
        raise HTTPException(status_code=404, detail="Not in favorites")
    
    db.delete(favorite)
    db.commit()
    return {"message": "Removed from favorites"}

@router.post("/{course_id}/watch-later")
def add_to_watch_later(course_id: int, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_active_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.UserWatchLater).filter(
        and_(models.UserWatchLater.user_id == current_user.id, models.UserWatchLater.course_id == course_id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already in watch later")
    
    watch_later = models.UserWatchLater(user_id=current_user.id, course_id=course_id)
    db.add(watch_later)
    db.commit()
    return {"message": "Added to watch later"}

@router.delete("/{course_id}/watch-later")
def remove_from_watch_later(course_id: int, db: Session = Depends(get_db),
                            current_user: models.User = Depends(auth.get_current_active_user)):
    watch_later = db.query(models.UserWatchLater).filter(
        and_(models.UserWatchLater.user_id == current_user.id, models.UserWatchLater.course_id == course_id)
    ).first()
    if not watch_later:
        raise HTTPException(status_code=404, detail="Not in watch later")
    
    db.delete(watch_later)
    db.commit()
    return {"message": "Removed from watch later"}

@router.post("/{course_id}/register")
def register_for_course(course_id: int, db: Session = Depends(get_db),
                        current_user: models.User = Depends(auth.get_current_active_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.CourseRegistration).filter(
        and_(models.CourseRegistration.user_id == current_user.id, models.CourseRegistration.course_id == course_id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already registered")
    
    if course.current_participants >= course.max_participants:
        raise HTTPException(status_code=400, detail="Course is full")
    
    if course.price > 0:
        raise HTTPException(status_code=402, detail="Payment required")
    
    registration = models.CourseRegistration(user_id=current_user.id, course_id=course_id, is_paid=True)
    course.current_participants += 1
    db.add(registration)
    db.commit()
    return {"message": "Successfully registered"}

@router.post("/{course_id}/pay")
def pay_for_course(course_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_active_user)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    existing = db.query(models.CourseRegistration).filter(
        and_(models.CourseRegistration.user_id == current_user.id, models.CourseRegistration.course_id == course_id)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already registered")
    
    if course.current_participants >= course.max_participants:
        raise HTTPException(status_code=400, detail="Course is full")
    
    registration = models.CourseRegistration(user_id=current_user.id, course_id=course_id, is_paid=True)
    course.current_participants += 1
    db.add(registration)
    db.commit()
    
    return {"success": True, "message": f"Оплата {course.price} руб. прошла успешно!", "payment_id": f"PAY_{course_id}_{current_user.id}"}

@router.get("/my/favorites")
def get_my_favorites(db: Session = Depends(get_db),
                     current_user: models.User = Depends(auth.get_current_active_user)):
    favorites = db.query(models.UserFavorite).filter(models.UserFavorite.user_id == current_user.id).all()
    
    result = []
    for fav in favorites:
        if fav.course:
            result.append({
                "id": fav.course.id, "title": fav.course.title,
                "short_description": fav.course.short_description,
                "price": fav.course.price, "image_url": fav.course.image_url
            })
    return result

@router.get("/my/watch-later")
def get_my_watch_later(db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_active_user)):
    watch_later = db.query(models.UserWatchLater).filter(models.UserWatchLater.user_id == current_user.id).all()
    
    result = []
    for wl in watch_later:
        if wl.course:
            result.append({
                "id": wl.course.id, "title": wl.course.title,
                "short_description": wl.course.short_description,
                "price": wl.course.price, "image_url": wl.course.image_url
            })
    return result

@router.get("/my/registrations")
def get_my_registrations(db: Session = Depends(get_db),
                         current_user: models.User = Depends(auth.get_current_active_user)):
    registrations = db.query(models.CourseRegistration).filter(
        models.CourseRegistration.user_id == current_user.id
    ).all()
    
    return [{
        "course_id": r.course_id, "course_title": r.course.title if r.course else "Unknown",
        "price": r.course.price if r.course else 0, "is_paid": r.is_paid,
        "registered_at": r.registered_at
    } for r in registrations]