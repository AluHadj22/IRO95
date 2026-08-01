# scripts/test_email.py
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import User, Course
from app.services.email_service import email_service
from app.config import settings


def print_separator():
    print("=" * 60)


def print_header(text):
    print_separator()
    print(f"  {text}")
    print_separator()


def test_send_welcome_email():
    print_header("ТЕСТ ОТПРАВКИ WELCOME EMAIL")
    
    db = SessionLocal()
    
    try:
        user = db.query(User).filter(User.email.like("%@example.com")).first()
        if not user:
            user = db.query(User).first()
            if not user:
                print("❌ Нет пользователей в БД. Сначала создайте хотя бы одного.")
                return
        
        course = db.query(Course).first()
        if not course:
            print("❌ Нет курсов в БД. Создайте хотя бы один курс.")
            return
        
        print(f"📧 Отправка тестового письма:")
        print(f"   Получатель: {user.email}")
        print(f"   Имя: {user.full_name}")
        print(f"   Курс: {course.title}")
        print(f"   SMTP Host: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
        
        result = email_service.send_welcome_email(
            to_email=user.email,
            full_name=user.full_name,
            moodle_username=user.email,
            moodle_password="TestPassword123!",
            moodle_url=settings.MOODLE_URL or "https://iro-lms.ru",
            moodle_course_name=course.title
        )
        
        if result:
            print("✅ Письмо отправлено успешно!")
            print(f"\n📬 Проверьте письмо в MailHog:")
            print(f"   🌐 http://localhost:8025")
        else:
            print("❌ Ошибка отправки письма")
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def test_send_password_reset():
    print_header("ТЕСТ СБРОСА ПАРОЛЯ")
    
    db = SessionLocal()
    
    try:
        user = db.query(User).first()
        if not user:
            print("❌ Нет пользователей")
            return
        
        reset_link = f"{settings.BASE_URL}/reset-password?token=test_token_12345"
        
        print(f"📧 Отправка письма для сброса пароля:")
        print(f"   Получатель: {user.email}")
        
        result = email_service.send_password_reset_email(
            to_email=user.email,
            full_name=user.full_name,
            reset_link=reset_link
        )
        
        if result:
            print("✅ Письмо для сброса пароля отправлено!")
            print(f"\n📬 Проверьте письмо в MailHog:")
            print(f"   🌐 http://localhost:8025")
        else:
            print("❌ Ошибка отправки")
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


def test_admin_notification():
    print_header("ТЕСТ УВЕДОМЛЕНИЯ АДМИНИСТРАТОРУ")
    
    db = SessionLocal()
    
    try:
        user = db.query(User).first()
        if not user:
            print("❌ Нет пользователей")
            return
        
        course = db.query(Course).first()
        if not course:
            print("❌ Нет курсов")
            return
        
        admin_email = "admin@test.local"
        
        print(f"📧 Отправка уведомления администратору:")
        print(f"   Админ: {admin_email}")
        print(f"   Пользователь: {user.full_name}")
        print(f"   Курс: {course.title}")
        
        result = email_service.send_admin_notification(
            admin_email=admin_email,
            user_name=user.full_name,
            user_email=user.email,
            moodle_course_name=course.title
        )
        
        if result:
            print("✅ Уведомление администратору отправлено!")
            print(f"\n📬 Проверьте письмо в MailHog:")
            print(f"   🌐 http://localhost:8025")
        else:
            print("❌ Ошибка отправки")
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


def test_bulk_emails(count=5):
    print_header(f"МАССОВАЯ ОТПРАВКА ({count} писем)")
    
    db = SessionLocal()
    
    try:
        users = db.query(User).limit(count).all()
        course = db.query(Course).first()
        
        if not users:
            print("❌ Нет пользователей")
            return
        
        if not course:
            print("❌ Нет курсов")
            return
        
        print(f"📧 Отправка {len(users)} писем...")
        
        success_count = 0
        for i, user in enumerate(users, 1):
            try:
                result = email_service.send_welcome_email(
                    to_email=user.email,
                    full_name=user.full_name,
                    moodle_username=user.email,
                    moodle_password="TestPassword123!",
                    moodle_url=settings.MOODLE_URL or "https://iro-lms.ru",
                    moodle_course_name=course.title
                )
                
                if result:
                    success_count += 1
                    print(f"  {i}. ✅ {user.email}")
                else:
                    print(f"  {i}. ❌ {user.email}")
                    
                time.sleep(0.2)
                
            except Exception as e:
                print(f"  {i}. ❌ {user.email}: {str(e)}")
        
        print(f"\n📊 Итог: {success_count}/{len(users)} писем отправлено")
        if success_count > 0:
            print(f"\n📬 Проверьте письма в MailHog:")
            print(f"   🌐 http://localhost:8025")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
    finally:
        db.close()


def test_send_to_all_users():
    """
    Отправка welcome email ВСЕМ пользователям в БД.
    """
    print_header("ОТПРАВКА WELCOME EMAIL ВСЕМ ПОЛЬЗОВАТЕЛЯМ")
    
    db = SessionLocal()
    
    try:
        users = db.query(User).all()
        
        if not users:
            print("❌ Нет пользователей в БД")
            return
        
        course = db.query(Course).first()
        if not course:
            print("❌ Нет курсов в БД")
            return
        
        print(f"📊 Найдено пользователей: {len(users)}")
        print(f"📚 Курс: {course.title}")
        
        confirm = input(f"\nОтправить письма {len(users)} пользователям? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ Отменено")
            return
        
        print(f"\n📧 Отправка {len(users)} писем...")
        print("-" * 60)
        
        success_count = 0
        fail_count = 0
        start_time = time.time()
        
        for i, user in enumerate(users, 1):
            try:
                result = email_service.send_welcome_email(
                    to_email=user.email,
                    full_name=user.full_name,
                    moodle_username=user.email,
                    moodle_password="TestPassword123!",
                    moodle_url=settings.MOODLE_URL or "https://iro-lms.ru",
                    moodle_course_name=course.title
                )
                
                if result:
                    success_count += 1
                    print(f"  {i}. ✅ {user.email}")
                else:
                    fail_count += 1
                    print(f"  {i}. ❌ {user.email}")
                    
                # Небольшая задержка, чтобы не перегружать SMTP
                time.sleep(0.1)
                
            except Exception as e:
                fail_count += 1
                print(f"  {i}. ❌ {user.email}: {str(e)}")
        
        elapsed = time.time() - start_time
        
        print("-" * 60)
        print(f"\n📊 ИТОГИ:")
        print(f"   ✅ Успешно: {success_count}")
        print(f"   ❌ Ошибок: {fail_count}")
        print(f"   ⏱️  Время: {elapsed:.2f} сек")
        print(f"   📬 Всего: {len(users)}")
        
        if success_count > 0:
            print(f"\n📬 Проверьте письма в MailHog:")
            print(f"   🌐 http://localhost:8025")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def main():
    print_header("ТЕСТИРОВАНИЕ EMAIL УВЕДОМЛЕНИЙ")
    
    print(f"📧 SMTP Настройки:")
    print(f"   Host: {settings.SMTP_HOST}")
    print(f"   Port: {settings.SMTP_PORT}")
    print(f"   TLS: {settings.SMTP_USE_TLS}")
    print(f"   From: {settings.SMTP_FROM_EMAIL}")
    print()
    
    print("Выберите тест:")
    print("1. Отправить welcome email одному пользователю")
    print("2. Отправить письмо для сброса пароля")
    print("3. Отправить уведомление администратору")
    print("4. Массовая отправка (5 писем)")
    print("5. Отправить ВСЕМ пользователям")
    print("6. ВСЕ ТЕСТЫ")
    
    choice = input("\nВаш выбор (1-6): ").strip()
    
    if choice == "1":
        test_send_welcome_email()
    elif choice == "2":
        test_send_password_reset()
    elif choice == "3":
        test_admin_notification()
    elif choice == "4":
        count = input("Сколько писем отправить? (по умолчанию 5): ").strip()
        try:
            count = int(count) if count else 5
        except:
            count = 5
        test_bulk_emails(count)
    elif choice == "5":
        test_send_to_all_users()
    elif choice == "6":
        test_send_welcome_email()
        print("\n")
        test_send_password_reset()
        print("\n")
        test_admin_notification()
        print("\n")
        test_bulk_emails(5)
        print("\n")
        test_send_to_all_users()
    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()