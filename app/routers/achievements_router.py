from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app import models, auth
from app.database import get_db
import json

router = APIRouter(prefix="/api/achievements", tags=["Achievements"])

# Список всех достижений
ACHIEVEMENTS = {
    "first_course": {
        "title": "Первый шаг",
        "description": "Завершён первый курс",
        "icon": "bi-stars",
        "level": "bronze",
        "requirement": 1,
        "type": "courses_completed"
    },
    "five_courses": {
        "title": "Эрудит",
        "description": "Завершено 5 курсов",
        "icon": "bi-book-half",
        "level": "silver",
        "requirement": 5,
        "type": "courses_completed"
    },
    "ten_courses": {
        "title": "Профессионал",
        "description": "Завершено 10 курсов",
        "icon": "bi-award",
        "level": "gold",
        "requirement": 10,
        "type": "courses_completed"
    },
    "twenty_courses": {
        "title": "Эксперт",
        "description": "Завершено 20 курсов",
        "icon": "bi-trophy",
        "level": "gold",
        "requirement": 20,
        "type": "courses_completed"
    },
    "fifty_hours": {
        "title": "Усердный ученик",
        "description": "50 часов обучения",
        "icon": "bi-clock-fill",
        "level": "bronze",
        "requirement": 50,
        "type": "hours"
    },
    "hundred_hours": {
        "title": "Мастер",
        "description": "100 часов обучения",
        "icon": "bi-hourglass-split",
        "level": "silver",
        "requirement": 100,
        "type": "hours"
    },
    "two_hundred_hours": {
        "title": "Легенда",
        "description": "200 часов обучения",
        "icon": "bi-infinity",
        "level": "gold",
        "requirement": 200,
        "type": "hours"
    },
    "favorite_three": {
        "title": "Коллекционер",
        "description": "3 курса в избранном",
        "icon": "bi-heart-fill",
        "level": "bronze",
        "requirement": 3,
        "type": "favorites"
    },
    "favorite_ten": {
        "title": "Меломан",
        "description": "10 курсов в избранном",
        "icon": "bi-hearts",
        "level": "silver",
        "requirement": 10,
        "type": "favorites"
    }
}

def check_and_award_achievements(user_id: int, db: Session):
    """Проверка и выдача достижений"""
    from sqlalchemy import func
    
    # Получаем статистику пользователя
    completed_courses = db.query(models.UserProgress).filter(
        models.UserProgress.user_id == user_id,
        models.UserProgress.is_completed == True
    ).count()
    
    total_hours = completed_courses * 36  # Примерное значение
    
    favorites_count = db.query(models.UserFavorite).filter(
        models.UserFavorite.user_id == user_id
    ).count()
    
    # Получаем уже выданные достижения
    earned_ids = [a.achievement_id for a in db.query(models.UserAchievement).filter(
        models.UserAchievement.user_id == user_id
    ).all()]
    
    new_achievements = []
    
    for ach_id, ach_data in ACHIEVEMENTS.items():
        if ach_id in earned_ids:
            continue
        
        earned = False
        if ach_data["type"] == "courses_completed":
            if completed_courses >= ach_data["requirement"]:
                earned = True
        elif ach_data["type"] == "hours":
            if total_hours >= ach_data["requirement"]:
                earned = True
        elif ach_data["type"] == "favorites":
            if favorites_count >= ach_data["requirement"]:
                earned = True
        
        if earned:
            achievement = models.UserAchievement(
                user_id=user_id,
                achievement_id=ach_id,
                achievement_title=ach_data["title"],
                achievement_description=ach_data["description"],
                achievement_icon=ach_data["icon"],
                achievement_level=ach_data["level"]
            )
            db.add(achievement)
            new_achievements.append(achievement)
    
    if new_achievements:
        db.commit()
    
    return new_achievements

@router.post("/check")
def check_achievements(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    """Принудительная проверка достижений"""
    new_achievements = check_and_award_achievements(current_user.id, db)
    return {
        "message": f"Получено {len(new_achievements)} новых достижений",
        "new_achievements": [{
            "title": a.achievement_title,
            "description": a.achievement_description
        } for a in new_achievements]
    }