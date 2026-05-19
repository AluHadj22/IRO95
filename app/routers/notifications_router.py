from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models, auth
from app.database import get_db

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("/")
def get_notifications(db: Session = Depends(get_db),
                      current_user: models.User = Depends(auth.get_current_active_user)):
    notifications = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id
    ).order_by(models.Notification.created_at.desc()).all()
    
    return [{"id": n.id, "title": n.title, "message": n.message, "is_read": n.is_read, "created_at": n.created_at}
            for n in notifications]

@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db),
              current_user: models.User = Depends(auth.get_current_active_user)):
    notification = db.query(models.Notification).filter(
        and_(models.Notification.id == notification_id, models.Notification.user_id == current_user.id)
    ).first()
    
    if not notification:
        raise HTTPException(status_code=404, detail="Not found")
    
    notification.is_read = True
    db.commit()
    return {"message": "Marked as read"}

@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_active_user)):
    db.query(models.Notification).filter(
        and_(models.Notification.user_id == current_user.id, models.Notification.is_read == False)
    ).update({"is_read": True})
    db.commit()
    return {"message": "All marked as read"}