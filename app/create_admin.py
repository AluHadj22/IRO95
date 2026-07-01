# app/create_admin.py
from app.database import SessionLocal, engine, Base
from app.models import User, UserRole
from app.auth import get_password_hash
from app.config import settings
import os
import sys

def create_admin():
    """
    Создаёт администратора, если его нет.
    ✅ Пароль берётся из .env (ADMIN_INIT_PASSWORD)
    ✅ Если пароль не задан - запрашивает ввод
    ✅ Проверка, что скрипт не запущен в продакшене случайно
    """
    
    # === ЗАЩИТА ОТ СЛУЧАЙНОГО ЗАПУСКА В ПРОДАКШЕНЕ ===
    if not settings.DEBUG:
        print("⚠️  ВНИМАНИЕ! Вы пытаетесь запустить create_admin.py в ПРОДАКШЕНЕ!")
        response = input("Это может создать дублирующего админа. Продолжить? (y/N): ")
        if response.lower() != 'y':
            print("❌ Отменено.")
            sys.exit(0)
    
    print("Проверка наличия таблиц...")
    Base.metadata.create_all(bind=engine)
    print("✅ Таблицы проверены/созданы")
    
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли уже администратор
        admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
        
        if admin:
            print(f"⚠️  Администратор уже существует: {admin.email}")
            print("   Если забыли пароль, удалите админа вручную и запустите скрипт заново.")
            return
        
        # === ПОЛУЧАЕМ ПАРОЛЬ ИЗ .env ИЛИ ЗАПРАШИВАЕМ ===
        admin_password = os.getenv("ADMIN_INIT_PASSWORD")
        
        if not admin_password:
            print("\n🔑 Пароль для администратора не задан в .env (ADMIN_INIT_PASSWORD)")
            print("   Рекомендуется задать его в .env, но можно ввести сейчас.")
            import getpass
            admin_password = getpass.getpass("Введите пароль для администратора (мин. 8 символов): ")
            
            if len(admin_password) < 8:
                print("❌ Пароль слишком короткий (минимум 8 символов).")
                return
            
            confirm_password = getpass.getpass("Повторите пароль: ")
            if admin_password != confirm_password:
                print("❌ Пароли не совпадают.")
                return
        
        # Проверяем длину пароля из .env
        if len(admin_password) < 8:
            print(f"❌ Пароль из .env слишком короткий (минимум 8 символов). Текущая длина: {len(admin_password)}")
            return
        
        # === СОЗДАЁМ АДМИНИСТРАТОРА ===
        admin = User(
            email=os.getenv("ADMIN_INIT_EMAIL", "admin@iro.ru"),
            full_name=os.getenv("ADMIN_INIT_NAME", "Администратор ИРО"),
            hashed_password=get_password_hash(admin_password),
            role=UserRole.ADMIN,
            is_active=True,
            is_blocked=False
        )
        
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print("\n✅ Администратор успешно создан!")
        print(f"   Email: {admin.email}")
        print(f"   Пароль: {'***' if admin_password else 'установлен'}")
        print(f"   🔑 Код для регистрации админа: {settings.ADMIN_SECRET_CODE}")
        
        # === ПРЕДУПРЕЖДЕНИЕ О БЕЗОПАСНОСТИ ===
        if admin_password == "admin123" or admin_password == "password":
            print("\n⚠️  ВНИМАНИЕ! Используется слабый пароль!")
            print("   Смените пароль в .env (ADMIN_INIT_PASSWORD) и удалите админа, затем создайте заново.")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()