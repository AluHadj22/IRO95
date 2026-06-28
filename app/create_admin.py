# app/create_admin.py
from app.database import SessionLocal, engine, Base
from app.models import User, UserRole
from app.auth import get_password_hash
import os

def create_admin():
    # Создаём таблицы, если их нет
    print("Проверка наличия таблиц...")
    Base.metadata.create_all(bind=engine)
    print("✅ Таблицы проверены/созданы")
    
    db = SessionLocal()
    
    try:
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
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin()