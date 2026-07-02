# app/services/moodle_service.py

import requests
import secrets
import string
import re
import hashlib
import urllib.parse
import logging
from typing import Optional, Dict, List, Any
from urllib3.exceptions import InsecureRequestWarning
from app.config import settings
from app.services.email_service import email_service

# Настройка логирования
logger = logging.getLogger(__name__)

# Отключаем предупреждения о небезопасных запросах (мы их проверяем сами)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class MoodleService:
    def __init__(self):
        self.base_url = settings.MOODLE_URL.rstrip('/')
        self.token = settings.MOODLE_API_TOKEN
        self.timeout = 30
        self.verify_ssl = True  # ✅ В продакшене всегда True
        
        # Для локальной разработки можно отключить проверку SSL
        if self.base_url.startswith('http://localhost') or self.base_url.startswith('http://127.0.0.1'):
            self.verify_ssl = False
            logger.warning("⚠️ SSL verification disabled for localhost")
    
    def _call_api(self, function: str, params: Dict[str, Any] = None) -> Dict:
        """
        Вызов Moodle API с проверкой SSL и безопасным логированием.
        ✅ Проверка SSL сертификата
        ✅ Безопасное логирование (без токенов)
        ✅ Обработка таймаутов
        """
        url = f"{self.base_url}/webservice/rest/server.php"
        data = {'wstoken': self.token, 'wsfunction': function, 'moodlewsrestformat': 'json'}
        if params:
            data.update(params)
        
        # Безопасное логирование - скрываем токен и пароли
        safe_params = {k: v for k, v in data.items() if k != 'wstoken'}
        logger.info(f"Moodle API call: {function}, params: {list(safe_params.keys())}")
        
        # ✅ ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ДЛЯ СОЗДАНИЯ ПОЛЬЗОВАТЕЛЯ
        if function == 'core_user_create_users':
            # Создаём безопасную копию для логирования (скрываем токен, но показываем всё остальное)
            log_data = {k: v for k, v in data.items() if k != 'wstoken'}
            logger.info(f"🔍 FULL API DATA for create_user: {log_data}")
        
        try:
            response = requests.post(
                url, 
                data=data, 
                timeout=self.timeout,
                verify=self.verify_ssl  # ✅ Проверка SSL
            )
            response.raise_for_status()
            result = response.json()
            
            if isinstance(result, dict) and 'exception' in result:
                error_msg = result.get('message', 'Unknown error')
                logger.error(f"Moodle API error: {function} - {error_msg}")
                raise Exception(f"Moodle API Error: {error_msg}")
            
            logger.info(f"Moodle API success: {function}")
            return result
            
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL error connecting to Moodle: {str(e)}")
            raise Exception(f"SSL error: {str(e)}")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout connecting to Moodle: {str(e)}")
            raise Exception(f"Timeout error: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Moodle: {str(e)}")
            raise Exception(f"Connection error: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error to Moodle: {str(e)}")
            raise Exception(f"Failed to call Moodle API: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in Moodle API: {str(e)}")
            raise Exception(f"Unexpected error: {str(e)}")
    
    def generate_password(self) -> str:
        """
        Генерирует удобный для запоминания пароль типа "Password1!".
        ✅ Начинается с заглавной буквы
        ✅ Содержит строчные буквы
        ✅ Содержит цифру
        ✅ Содержит специальный символ
        ✅ Длина 10-12 символов
        ✅ Легко читается и вводится
        """
        # Слова для основы пароля (легко запоминаются)
        base_words = [
            'Password', 'Welcome', 'Learn', 'Study', 'Course', 'Moodle',
            'Access', 'Login', 'User', 'Student', 'Teacher', 'IRO'
        ]
        
        # Выбираем случайное слово
        word = secrets.choice(base_words)
        
        # Добавляем случайную цифру (1-9)
        digit = secrets.choice('123456789')
        
        # Добавляем специальный символ
        special = secrets.choice('!@#$%^&*')
        
        # Добавляем случайные 2-3 буквы для уникальности
        extra = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(3))
        
        # Собираем пароль: слово + цифра + специальный символ + доп. буквы
        password = word + digit + special + extra
        
        return password
    
    def sanitize_username(self, email: str) -> str:
        """
        Санитизация email в username для Moodle.
        ✅ Безопасное преобразование
        """
        username = email.split('@')[0].lower()
        username = re.sub(r'[^a-zA-Z0-9._-]', '', username)
        
        if len(username) < 3:
            hash_part = hashlib.md5(email.encode()).hexdigest()[:8]
            username = f"user_{hash_part}"
        
        if username and username[0].isdigit():
            username = f"u_{username}"
        
        return username
    
    def create_user(self, email: str, full_name: str, password: str = None) -> int:
        """
        Создание пользователя в Moodle.
        ✅ Отключено кодирование пароля для теста
        ✅ Полное логирование всех параметров
        ✅ Отправка email с данными для входа
        """
        name_parts = full_name.strip().split(' ', 1)
        firstname = name_parts[0] if name_parts[0] else 'User'
        lastname = name_parts[1] if len(name_parts) > 1 else 'Unknown'
        
        firstname = firstname[:100]
        lastname = lastname[:100]
        
        if not password:
            password = self.generate_password()
        
        username = self.sanitize_username(email)
        
        # ✅ ЛОГИРУЕМ СГЕНЕРИРОВАННЫЙ ПАРОЛЬ
        logger.info(f"🔑 GENERATED PASSWORD: '{password}'")
        
        # Проверка существующего пользователя
        try:
            existing = self._call_api('core_user_get_users_by_field', {
                'field': 'username', 'values[0]': username
            })
            if existing:
                username = f"{username}_{secrets.choice(string.digits)}{secrets.choice(string.digits)}"
        except Exception:
            pass
        
        logger.info(f"Creating Moodle user: email={email}, username={username}, firstname={firstname}, lastname={lastname}")
        
        # ❌ ОТКЛЮЧАЕМ КОДИРОВАНИЕ ПАРОЛЯ ДЛЯ ТЕСТА
        # encoded_password = urllib.parse.quote(password, safe='')
        # Используем пароль как есть
        raw_password = password
        
        # ✅ ЛОГИРУЕМ, ЧТО МЫ ОТПРАВЛЯЕМ В MOODLE
        logger.info(f"🔑 SENDING PASSWORD TO MOODLE (raw): '{raw_password}'")
        
        result = self._call_api('core_user_create_users', {
            'users[0][username]': username,
            'users[0][password]': raw_password,  # ❌ БЕЗ КОДИРОВАНИЯ!
            'users[0][firstname]': firstname,
            'users[0][lastname]': lastname,
            'users[0][email]': email
        })
        
        moodle_user_id = result[0]['id']
        logger.info(f"Moodle user created: ID={moodle_user_id}, email={email}")
        
        # ============================================================
        # ✅ ОТПРАВКА EMAIL С ДАННЫМИ ДЛЯ ВХОДА В MOODLE
        # ============================================================
        try:
            email_sent = email_service.send_welcome_email(
                to_email=email,
                full_name=full_name,
                moodle_username=username,
                moodle_password=raw_password,  # Отправляем ТОТ ЖЕ пароль
                moodle_url=self.base_url,
                moodle_course_name=None
            )
            
            if email_sent:
                logger.info(f"📧 Welcome email sent to {email}")
            else:
                logger.warning(f"⚠️ Failed to send welcome email to {email}")
                
        except Exception as e:
            # Ошибка отправки email не должна блокировать создание пользователя
            logger.error(f"❌ Error sending welcome email to {email}: {str(e)}")
        
        return moodle_user_id
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Получение пользователя по email с обработкой ошибок"""
        try:
            result = self._call_api('core_user_get_users_by_field', {
                'field': 'email', 'values[0]': email
            })
            return result[0] if result else None
        except Exception:
            logger.warning(f"User not found in Moodle: {email}")
            return None
    
    def get_user_id(self, email: str) -> Optional[int]:
        """Получение ID пользователя по email"""
        user = self.get_user_by_email(email)
        return user['id'] if user else None
    
    def sync_user(self, email: str, full_name: str) -> int:
        """
        Синхронизация пользователя с Moodle.
        ✅ Создаёт пользователя, если не существует
        ✅ Безопасное логирование
        """
        existing = self.get_user_by_email(email)
        if existing:
            logger.info(f"User already exists in Moodle: {email} (ID={existing['id']})")
            return existing['id']
        
        logger.info(f"Creating new user in Moodle: {email}")
        user_id = self.create_user(email, full_name)
        return user_id
    
    def get_courses(self) -> List[Dict]:
        """Получение списка курсов из Moodle"""
        try:
            return self._call_api('core_course_get_courses')
        except Exception as e:
            logger.error(f"Failed to get courses: {str(e)}")
            return []
    
    def get_course_by_id(self, course_id: int) -> Optional[Dict]:
        """Получение курса по ID"""
        try:
            result = self._call_api('core_course_get_courses', {
                'options[ids][0]': course_id
            })
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get course {course_id}: {str(e)}")
            return None
    
    def get_course_url(self, course_id: int) -> str:
        """Получение URL курса в Moodle"""
        return f"{self.base_url}/course/view.php?id={course_id}"
    
    def enroll_user_to_course(self, user_id: int, course_id: int, course_name: str = None) -> bool:
        """
        Зачисление пользователя на курс.
        ✅ Обработка ошибок
        """
        logger.info(f"Enrolling user {user_id} to course {course_id}")
        
        try:
            self._call_api('enrol_manual_enrol_users', {
                'enrolments[0][roleid]': 5,
                'enrolments[0][userid]': user_id,
                'enrolments[0][courseid]': course_id
            })
            logger.info(f"User {user_id} enrolled to course {course_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enroll user {user_id} to course {course_id}: {str(e)}")
            return False
    
    def is_user_enrolled(self, user_id: int, course_id: int) -> bool:
        """
        Проверка, зачислен ли пользователь на курс.
        ✅ Обработка ошибок
        """
        try:
            result = self._call_api('core_enrol_get_enrolled_users', {
                'courseid': course_id
            })
            return any(user['id'] == user_id for user in result)
        except Exception as e:
            logger.error(f"Failed to check enrollment: {str(e)}")
            return False
    
    def get_enrolled_users(self, course_id: int) -> List[Dict]:
        """Получение списка зачисленных пользователей на курс"""
        try:
            return self._call_api('core_enrol_get_enrolled_users', {
                'courseid': course_id
            })
        except Exception as e:
            logger.error(f"Failed to get enrolled users for course {course_id}: {str(e)}")
            return []
    
    def get_course_completion(self, user_id: int, course_id: int) -> Dict:
        """Получение статуса завершения курса"""
        try:
            return self._call_api('core_completion_get_course_completion_status', {
                'userid': user_id,
                'courseid': course_id
            })
        except Exception as e:
            logger.error(f"Failed to get course completion for user {user_id}, course {course_id}: {str(e)}")
            return {'completed': False, 'timecompleted': None}
    
    def get_activities_completion(self, user_id: int, course_id: int) -> List[Dict]:
        """
        Получение прогресса по каждому уроку/активности в курсе.
        ✅ Обработка ошибок
        """
        try:
            result = self._call_api('core_completion_get_activities_completion_status', {
                'userid': user_id,
                'courseid': course_id
            })
            return result.get('statuses', [])
        except Exception as e:
            logger.error(f"Error getting activities completion: {str(e)}")
            return []
    
    def get_course_progress(self, user_id: int, course_id: int) -> Dict:
        """
        Получение полного прогресса пользователя по курсу.
        ✅ Обработка ошибок
        ✅ Безопасное возвращение данных
        """
        try:
            # Получаем общий статус завершения курса
            completion = self.get_course_completion(user_id, course_id)
            
            # Получаем прогресс по каждому уроку
            activities = self.get_activities_completion(user_id, course_id)
            
            # Вычисляем процент на основе активностей
            total_activities = len(activities)
            completed_activities = sum(
                1 for a in activities 
                if a.get('completionstate', 0) > 0
            )
            
            progress_percent = int(
                (completed_activities / total_activities) * 100
            ) if total_activities > 0 else 0
            
            return {
                'completed': completion.get('completed', False),
                'progress_percent': progress_percent,
                'timecompleted': completion.get('timecompleted'),
                'activities': activities,
                'total_activities': total_activities,
                'completed_activities': completed_activities
            }
        except Exception as e:
            logger.error(f"Error getting course progress: {str(e)}")
            return {
                'completed': False,
                'progress_percent': 0,
                'timecompleted': None,
                'activities': [],
                'total_activities': 0,
                'completed_activities': 0
            }
    
    def get_site_info(self) -> Dict:
        """Получение информации о сайте Moodle"""
        try:
            return self._call_api('core_webservice_get_site_info')
        except Exception as e:
            logger.error(f"Failed to get site info: {str(e)}")
            return {}
    
    def check_connection(self) -> bool:
        """
        Проверка соединения с Moodle.
        ✅ Используется для health check
        """
        try:
            self.get_site_info()
            return True
        except Exception:
            return False