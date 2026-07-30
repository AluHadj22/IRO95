# scripts/test_load.py

import requests
import random
import time
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# ============================================================
# НАСТРОЙКИ
# ============================================================

BASE_URL = "http://localhost:8000"
COURSE_ID = 17
NUM_USERS = 10
MAX_WORKERS = 1  # ✅ УМЕНЬШЕНО ДО 1 (последовательные запросы)
DELAY_BETWEEN_REQUESTS = 1.5  # ✅ УВЕЛИЧЕНО ДО 1.5 СЕКУНД
DELAY_AFTER_LOGIN = 0.5  # ✅ Задержка после логина
DELAY_AFTER_REGISTER = 1.0  # ✅ Задержка после регистрации

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def random_phone():
    return f"+7{random.randint(900, 999)}{random.randint(1000000, 9999999)}"

def random_snils():
    return f"{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(10, 99)}"

def random_inn():
    return ''.join(str(random.randint(0, 9)) for _ in range(12))

def random_passport():
    return {
        "series": f"{random.randint(10, 99)}{random.randint(10, 99)}",
        "number": ''.join(str(random.randint(0, 9)) for _ in range(6)),
        "issued_by": random.choice(["ОВД г. Грозный", "УФМС по ЧР", "МВД по ЧР"]),
        "issued_date": (datetime.now() - timedelta(days=random.randint(365*2, 365*10))).strftime("%Y-%m-%d")
    }

def random_subjects():
    all_subjects = ["Математика", "Русский язык", "Литература", "Информатика",
                    "Физика", "Химия", "Биология", "История", "Обществознание",
                    "География", "Английский язык", "Физкультура", "Технология"]
    count = random.randint(1, 3)
    return random.sample(all_subjects, count)

def random_education():
    levels = ["Высшее", "Среднее профессиональное", "Среднее общее (студент)"]
    return {
        "level": random.choice(levels),
        "series": f"АБ{random.randint(10, 99)}",
        "number": ''.join(str(random.randint(0, 9)) for _ in range(6)),
        "qualification": random.choice(["Педагог", "Учитель", "Преподаватель", "Воспитатель"]),
        "issue_date": (datetime.now() - timedelta(days=random.randint(365*3, 365*15))).strftime("%Y-%m-%d")
    }

# ============================================================
# ОСНОВНЫЕ ФУНКЦИИ
# ============================================================

def register_user(i):
    """Регистрирует одного пользователя"""
    email = f"load.test.{i+1}_{random.randint(1000, 9999)}@example.com"
    
    user_data = {
        "email": email,
        "full_name": f"Тестовый Пользователь {i+1}",
        "password": "Test123!",
        "position": random.choice(["Учитель", "Завуч", "Директор", None]),
        "phone": random_phone(),
        "organization": f"Школа №{random.randint(1, 50)} г. Грозный",
        "position_type": random.choice(["Учитель", "Завуч", "Директор", "Иное"]),
        "position_custom": None
    }
    
    if user_data["position_type"] == "Иное":
        user_data["position_custom"] = random.choice(["Специалист", "Методист", "Руководитель"])
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json=user_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "email": email,
                "user_id": result.get("user_id"),
                "full_name": user_data["full_name"],
                "password": "Test123!"
            }
        elif response.status_code == 429:
            return {
                "success": False,
                "email": email,
                "error": "Слишком много запросов (429). Увеличьте задержки."
            }
        else:
            return {
                "success": False,
                "email": email,
                "error": f"{response.status_code} - {response.text}"
            }
            
    except Exception as e:
        return {"success": False, "email": email, "error": str(e)}


def fill_profile(user_id, email, token):
    """Заполняет профиль пользователя"""
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # 1. ЛИЧНЫЕ ДАННЫЕ
        personal_data = {
            "last_name": f"Тестов",
            "first_name": f"Пользователь",
            "middle_name": f"Тестович",
            "gender": random.choice(["male", "female"]),
            "birth_date": (datetime.now() - timedelta(days=random.randint(25*365, 50*365))).strftime("%Y-%m-%d"),
            "citizenship": "Россия",
            "region": "Чеченская Республика",
            "municipality": random.choice(["Грозный", "Аргун", "Гудермес", "Шали", "Урус-Мартан"]),
            "phone_raw": random_phone().replace("+7", ""),
            "consent_to_personal_data": True
        }
        
        response = requests.put(
            f"{BASE_URL}/api/profile/personal-data",
            json=personal_data,
            headers=headers,
            timeout=30
        )
        if response.status_code != 200:
            return False, f"Ошибка личных данных: {response.status_code}"
        
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 2. ОБРАЗОВАНИЕ
        edu = random_education()
        education_data = {
            "education_level": edu["level"],
            "document_series": edu["series"],
            "document_number": edu["number"],
            "qualification": edu["qualification"],
            "issue_date": edu["issue_date"],
            "is_main": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/profile/education",
            json=education_data,
            headers=headers,
            timeout=30
        )
        if response.status_code != 200:
            return False, f"Ошибка образования: {response.status_code}"
        
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 3. МЕСТО РАБОТЫ
        work_data = {
            "organization": f"Школа №{random.randint(1, 50)} г. Грозный",
            "organization_inn": random_inn()[:10],
            "work_experience_years": random.randint(1, 20),
            "teaching_experience_years": random.randint(1, 15),
            "organization_type": random.choice(["Образовательная", "Дошкольная", "Средняя"]),
            "position": random.choice(["Учитель", "Преподаватель", "Воспитатель"]),
            "activity_type": random.choice([
                "Управленческие кадры",
                "Педагогические работники",
                "Специалисты системы ДПO",
                "Органы управления образованием"
            ]),
            "subjects": random_subjects(),
            "is_urban": True,
            "is_current": True,
            "work_start_date": (datetime.now() - timedelta(days=random.randint(365, 365*10))).strftime("%Y-%m-%d")
        }
        
        response = requests.post(
            f"{BASE_URL}/api/profile/work",
            json=work_data,
            headers=headers,
            timeout=30
        )
        if response.status_code != 200:
            return False, f"Ошибка места работы: {response.status_code}"
        
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 4. ДОКУМЕНТЫ
        passport = random_passport()
        additional_data = {
            "snils": random_snils(),
            "passport_series": passport["series"],
            "passport_number": passport["number"],
            "passport_issued_by": passport["issued_by"],
            "passport_issued_date": passport["issued_date"],
            "passport_department_code": f"{random.randint(100, 999)}-{random.randint(100, 999)}",
            "inn": random_inn(),
            "data_confirmed": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/profile/additional-info",
            json=additional_data,
            headers=headers,
            timeout=30
        )
        if response.status_code != 200:
            return False, f"Ошибка документов: {response.status_code}"
        
        return True, "Профиль заполнен полностью"
        
    except Exception as e:
        return False, str(e)


def get_user_token(email, password):
    """Получает токен пользователя"""
    try:
        time.sleep(DELAY_AFTER_LOGIN)
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            data={
                "username": email,
                "password": password
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json().get("access_token"), None
        elif response.status_code == 429:
            return None, "Слишком много запросов (429). Подожди."
        else:
            return None, f"Ошибка входа: {response.status_code}"
            
    except Exception as e:
        return None, str(e)


def enroll_to_course(user_id, email, password, course_id):
    """Записывает пользователя на курс"""
    try:
        # 1. Получаем токен
        token, error = get_user_token(email, password)
        if error:
            return False, error
        
        if not token:
            return False, "Не удалось получить токен"
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Проверяем профиль
        check_response = requests.get(
            f"{BASE_URL}/api/profile/check-complete",
            headers=headers,
            timeout=30
        )
        
        if check_response.status_code == 200:
            check_result = check_response.json()
            if not check_result.get("is_complete"):
                return False, f"Профиль не заполнен: {check_result.get('message')}"
        
        # 3. Записываемся на курс
        enroll_response = requests.post(
            f"{BASE_URL}/api/courses/{course_id}/register",
            headers=headers,
            timeout=30
        )
        
        if enroll_response.status_code == 200:
            return True, "Записан на курс"
        else:
            return False, f"Ошибка записи: {enroll_response.status_code}"
            
    except Exception as e:
        return False, str(e)


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def run_load_test(num_users=10, course_id=16):
    print("=" * 60)
    print(f"🚀 НАГРУЗОЧНЫЙ ТЕСТ")
    print(f"   Пользователей: {num_users}")
    print(f"   Курс ID: {course_id}")
    print(f"   Параллельных запросов: {MAX_WORKERS}")
    print(f"   Задержка между запросами: {DELAY_BETWEEN_REQUESTS} сек")
    print(f"   Задержка после логина: {DELAY_AFTER_LOGIN} сек")
    print("=" * 60)
    
    # ШАГ 1: Регистрация
    print("\n👤 ШАГ 1: Регистрация пользователей...")
    print("-" * 50)
    
    registered_users = []
    
    # ✅ Регистрируем ПОСЛЕДОВАТЕЛЬНО (не параллельно)
    for i in range(num_users):
        result = register_user(i)
        if result["success"]:
            registered_users.append(result)
            print(f"  ✅ {result['email']} - зарегистрирован (ID: {result['user_id']})")
        else:
            print(f"  ❌ {result['email']} - ОШИБКА: {result.get('error', 'Unknown')}")
        
        # ✅ Ждем после каждой регистрации
        time.sleep(DELAY_AFTER_REGISTER)
    
    print(f"\n📊 Зарегистрировано: {len(registered_users)}/{num_users}")
    
    if not registered_users:
        print("\n❌ Нет зарегистрированных пользователей. Тест остановлен.")
        return
    
    # ШАГ 2: Заполнение профилей
    print("\n📝 ШАГ 2: Заполнение профилей...")
    print("-" * 50)
    
    filled_users = []
    
    for user in registered_users:
        # Получаем токен
        token, error = get_user_token(user["email"], user["password"])
        if error:
            print(f"  ❌ {user['email']} - ошибка токена: {error}")
            continue
        
        if not token:
            print(f"  ❌ {user['email']} - не удалось получить токен")
            continue
        
        print(f"  ✅ {user['email']} - получен токен")
        user["token"] = token
        
        # Заполняем профиль
        success, message = fill_profile(
            user["user_id"],
            user["email"],
            user["token"]
        )
        
        if success:
            filled_users.append(user)
            print(f"  ✅ {user['email']} - профиль заполнен")
        else:
            print(f"  ❌ {user['email']} - ошибка: {message}")
        
        # ✅ Дополнительная задержка после заполнения профиля
        time.sleep(DELAY_BETWEEN_REQUESTS * 2)
    
    print(f"\n📊 Заполнено профилей: {len(filled_users)}/{len(registered_users)}")
    
    if not filled_users:
        print("\n❌ Нет пользователей с заполненным профилем.")
        return
    
    # ШАГ 3: Запись на курс
    print("\n📚 ШАГ 3: Запись на курс...")
    print("-" * 50)
    
    enrolled = []
    failed = []
    
    for user in filled_users:
        success, message = enroll_to_course(
            user["user_id"],
            user["email"],
            user["password"],
            course_id
        )
        
        if success:
            enrolled.append(user)
            print(f"  ✅ {user['email']} - {message}")
        else:
            failed.append(user)
            print(f"  ❌ {user['email']} - {message}")
        
        # ✅ Дополнительная задержка после каждой записи
        time.sleep(DELAY_BETWEEN_REQUESTS * 2)
    
    # ИТОГИ
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ")
    print("=" * 60)
    print(f"  👤 Зарегистрировано:     {len(registered_users)}/{num_users}")
    print(f"  📝 Заполнено профилей:   {len(filled_users)}/{len(registered_users)}")
    print(f"  📚 Записано на курс:     {len(enrolled)}/{len(filled_users)}")
    print(f"  ❌ Ошибок:               {len(failed)}")
    print(f"  ✅ УСПЕШНО:              {len(enrolled)}/{num_users}")
    print("=" * 60)
    
    return {
        "total": num_users,
        "registered": len(registered_users),
        "filled": len(filled_users),
        "enrolled": len(enrolled),
        "failed": len(failed)
    }


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    import sys
    
    num_users = 10
    course_id = 16
    
    if len(sys.argv) > 1:
        try:
            num_users = int(sys.argv[1])
        except ValueError:
            pass
    
    if len(sys.argv) > 2:
        try:
            course_id = int(sys.argv[2])
        except ValueError:
            pass
    
    run_load_test(num_users=num_users, course_id=course_id)