from sqlalchemy.orm import Session
from app import models

def create_notification(db: Session, user_id: int, title: str, message: str):
    notification = models.Notification(user_id=user_id, title=title, message=message)
    db.add(notification)
    db.commit()
    return notification

def notify_new_course(db: Session, course: models.Course):
    users = db.query(models.User).filter(models.User.role == models.UserRole.TEACHER).all()
    
    for user in users:
        create_notification(db, user.id, f"Новый курс: {course.title}",
                           f"Добавлен новый курс '{course.title}' в категории {course.category.name if course.category else 'Общая'}")