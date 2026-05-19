from app.database import SessionLocal
from app.models import User, UserRole
from app.auth import get_password_hash

def create_admin():
    db = SessionLocal()
    
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if not admin:
        admin = User(
            email="admin@iro.ru",
            full_name="Администратор ИРО",
            hashed_password=get_password_hash("admin123"),
            role=UserRole.ADMIN,
            is_active=True,
            is_blocked=False
        )
        db.add(admin)
        db.commit()
        print("✅ Админ создан: admin@iro.ru / admin123")
        print("🔑 Код для регистрации админа: adminIRO3377")
    else:
        print("⚠️ Админ уже существует")
    
    db.close()

if __name__ == "__main__":
    create_admin()