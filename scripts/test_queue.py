# scripts/test_queue.py
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import User, Course, MoodleSyncTask, MoodleSyncStatus
from app.services.moodle_sync_service import MoodleSyncService
from app.scheduler import start_scheduler, stop_scheduler, get_scheduler_status


def print_separator():
    print("=" * 60)


def print_header(text):
    print_separator()
    print(f"  {text}")
    print_separator()


def get_test_user(db):
    user = db.query(User).first()
    if not user:
        print("❌ Нет пользователей в БД. Создайте хотя бы одного пользователя.")
        return None
    print(f"✅ Найден пользователь: {user.full_name} (ID: {user.id})")
    return user


def get_test_course(db):
    course = db.query(Course).filter(Course.moodle_course_id.isnot(None)).first()
    if not course:
        course = db.query(Course).first()
        if not course:
            print("❌ Нет курсов в БД. Создайте хотя бы один курс.")
            return None
        print(f"⚠️ Курс не привязан к Moodle (ID: {course.id})")
        return course
    print(f"✅ Найден курс: {course.title} (ID: {course.id}, Moodle ID: {course.moodle_course_id})")
    return course


def create_test_task(db, user_id, course_id):
    print_header("СОЗДАНИЕ ТЕСТОВОЙ ЗАДАЧИ")
    
    service = MoodleSyncService(db)
    
    existing_task = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.user_id == user_id,
        MoodleSyncTask.course_id == course_id,
        MoodleSyncTask.status.in_([MoodleSyncStatus.PENDING, MoodleSyncStatus.PROCESSING])
    ).first()
    
    if existing_task:
        print(f"⚠️ Задача уже существует (ID: {existing_task.id}, статус: {existing_task.status.value})")
        return existing_task
    
    task = service.create_sync_task(user_id, course_id)
    print(f"✅ Создана задача ID: {task.id}")
    print(f"   Пользователь ID: {task.user_id}")
    print(f"   Курс ID: {task.course_id}")
    print(f"   Статус: {task.status.value}")
    print(f"   Попыток: {task.attempts}")
    return task


def check_tasks_in_queue(db):
    print_header("ПРОВЕРКА ЗАДАЧ В ОЧЕРЕДИ")
    
    pending = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.status == MoodleSyncStatus.PENDING
    ).count()
    
    processing = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.status == MoodleSyncStatus.PROCESSING
    ).count()
    
    completed = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.status == MoodleSyncStatus.COMPLETED
    ).count()
    
    failed = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.status == MoodleSyncStatus.FAILED
    ).count()
    
    total = db.query(MoodleSyncTask).count()
    
    print(f"📊 Статистика задач:")
    print(f"   Всего: {total}")
    print(f"   В ожидании (pending): {pending}")
    print(f"   В обработке (processing): {processing}")
    print(f"   Завершено (completed): {completed}")
    print(f"   Ошибка (failed): {failed}")
    
    if pending > 0:
        tasks = db.query(MoodleSyncTask).filter(
            MoodleSyncTask.status == MoodleSyncStatus.PENDING
        ).limit(5).all()
        print(f"\n   Последние задачи в очереди:")
        for t in tasks:
            print(f"      ID: {t.id}, попыток: {t.attempts}, создана: {t.created_at.strftime('%H:%M:%S')}")
    
    if completed > 0:
        tasks = db.query(MoodleSyncTask).filter(
            MoodleSyncTask.status == MoodleSyncStatus.COMPLETED
        ).limit(5).all()
        print(f"\n   Последние завершенные задачи:")
        for t in tasks:
            moodle_id = t.moodle_user_id or "N/A"
            print(f"      ID: {t.id}, Moodle user: {moodle_id}, обработана: {t.processed_at.strftime('%H:%M:%S') if t.processed_at else 'N/A'}")
    
    if failed > 0:
        tasks = db.query(MoodleSyncTask).filter(
            MoodleSyncTask.status == MoodleSyncStatus.FAILED
        ).limit(5).all()
        print(f"\n   Последние задачи с ошибкой:")
        for t in tasks:
            print(f"      ID: {t.id}, попыток: {t.attempts}, ошибка: {t.last_error[:50] if t.last_error else 'N/A'}...")
    
    return total, pending, processing, completed, failed


def show_task_details(db, task_id):
    print_header(f"ДЕТАЛИ ЗАДАЧИ #{task_id}")
    
    task = db.query(MoodleSyncTask).filter(MoodleSyncTask.id == task_id).first()
    if not task:
        print("❌ Задача не найдена")
        return
    
    print(f"ID: {task.id}")
    print(f"Пользователь ID: {task.user_id}")
    print(f"Курс ID: {task.course_id}")
    print(f"Статус: {task.status.value}")
    print(f"Попыток: {task.attempts}/{task.max_attempts}")
    print(f"Создана: {task.created_at}")
    print(f"Обновлена: {task.updated_at}")
    print(f"Обработана: {task.processed_at}")
    print(f"Следующая попытка: {task.next_retry_at}")
    print(f"Последняя ошибка: {task.last_error or 'Нет'}")
    print(f"Moodle user ID: {task.moodle_user_id or 'Нет'}")


def run_manual_processing(db):
    print_header("РУЧНАЯ ОБРАБОТКА ОЧЕРЕДИ")
    
    service = MoodleSyncService(db)
    processed = service.process_queue()
    print(f"✅ Обработано задач: {processed}")


def wait_for_processing(db, task_id, max_wait=60, check_interval=3):
    print_header(f"ОЖИДАНИЕ ОБРАБОТКИ ЗАДАЧИ #{task_id}")
    print(f"Максимальное время ожидания: {max_wait} секунд")
    
    elapsed = 0
    while elapsed < max_wait:
        task = db.query(MoodleSyncTask).filter(MoodleSyncTask.id == task_id).first()
        if not task:
            print("❌ Задача не найдена")
            return False
        
        status = task.status.value
        print(f"   [{elapsed}s] Статус: {status}")
        
        if status == MoodleSyncStatus.COMPLETED:
            print("✅ Задача успешно выполнена!")
            show_task_details(db, task_id)
            return True
        elif status == MoodleSyncStatus.FAILED:
            print(f"❌ Задача завершилась с ошибкой:")
            print(f"   {task.last_error}")
            show_task_details(db, task_id)
            return False
        
        time.sleep(check_interval)
        elapsed += check_interval
        db.refresh(task)
    
    print(f"⏰ Время ожидания истекло. Текущий статус: {task.status.value}")
    return False


def cleanup_tasks(db):
    print_header("ОЧИСТКА ТЕСТОВЫХ ЗАДАЧ")
    
    tasks = db.query(MoodleSyncTask).filter(
        MoodleSyncTask.status.in_([MoodleSyncStatus.PENDING, MoodleSyncStatus.PROCESSING])
    ).all()
    
    if not tasks:
        print("Нет задач для очистки")
        return
    
    for task in tasks:
        print(f"Удаление задачи #{task.id} (статус: {task.status.value})")
        db.delete(task)
    
    db.commit()
    print(f"✅ Удалено задач: {len(tasks)}")


def main():
    print_header("ТЕСТИРОВАНИЕ ОЧЕРЕДИ СИНХРОНИЗАЦИИ")
    
    db = SessionLocal()
    
    try:
        user = get_test_user(db)
        if not user:
            return
        
        course = get_test_course(db)
        if not course:
            return
        
        print(f"\n📋 Будет создана задача для:")
        print(f"   Пользователь: {user.full_name} (ID: {user.id})")
        print(f"   Курс: {course.title} (ID: {course.id})")
        
        if not course.moodle_course_id:
            print("\n⚠️ ВНИМАНИЕ: Курс не привязан к Moodle!")
            print("   Задача будет создана, но синхронизация завершится с ошибкой.")
            print("   Это нормально для тестирования очереди.")
        
        check_tasks_in_queue(db)
        
        print("\n")
        choice = input("Создать тестовую задачу? (y/n): ")
        if choice.lower() == 'y':
            task = create_test_task(db, user.id, course.id)
        else:
            task = None
        
        if task:
            print("\n")
            choice = input("Запустить ручную обработку очереди? (y/n): ")
            if choice.lower() == 'y':
                run_manual_processing(db)
            else:
                print("\n⚠️ Планировщик должен запуститься автоматически при старте приложения.")
                print("   Если планировщик запущен, задача будет обработана в течение 3 секунд.")
            
            choice = input("\nОжидать обработку задачи автоматически? (y/n): ")
            if choice.lower() == 'y':
                wait_for_processing(db, task.id)
        
        check_tasks_in_queue(db)
        
        if task:
            choice = input("\nПоказать детали задачи? (y/n): ")
            if choice.lower() == 'y':
                show_task_details(db, task.id)
            
            choice = input("\nОчистить тестовые задачи? (y/n): ")
            if choice.lower() == 'y':
                cleanup_tasks(db)
        
        print_header("ЗАВЕРШЕНО")
        print("✅ Тестирование завершено!")
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()