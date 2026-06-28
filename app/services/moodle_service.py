# app/services/moodle_service.py

import requests
import secrets
import string
import re
import hashlib
import urllib.parse
from typing import Optional, Dict, List, Any
from app.config import settings


class MoodleService:
    def __init__(self):
        self.base_url = settings.MOODLE_URL.rstrip('/')
        self.token = settings.MOODLE_API_TOKEN
    
    def _call_api(self, function: str, params: Dict[str, Any] = None) -> Dict:
        url = f"{self.base_url}/webservice/rest/server.php"
        data = {'wstoken': self.token, 'wsfunction': function, 'moodlewsrestformat': 'json'}
        if params:
            data.update(params)
        
        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and 'exception' in result:
                raise Exception(f"Moodle API Error: {result.get('message', 'Unknown error')}")
            return result
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to call Moodle API: {str(e)}")
    
    def generate_password(self) -> str:
        """
        Генерирует пароль, соответствующий требованиям Moodle:
        - минимум 8 символов
        - хотя бы 1 цифра
        - хотя бы 1 заглавная буква
        - хотя бы 1 строчная буква
        - хотя бы 1 специальный символ
        """
        upper = secrets.choice(string.ascii_uppercase)
        lower = secrets.choice(string.ascii_lowercase)
        digit = secrets.choice(string.digits)
        special = secrets.choice("!@#$%^&*")
        rest = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
        
        password = list(upper + lower + digit + special + rest)
        secrets.SystemRandom().shuffle(password)
        return ''.join(password)
    
    def sanitize_username(self, email: str) -> str:
        username = email.split('@')[0].lower()
        username = re.sub(r'[^a-zA-Z0-9._-]', '', username)
        if len(username) < 3:
            hash_part = hashlib.md5(email.encode()).hexdigest()[:8]
            username = f"user_{hash_part}"
        if username[0].isdigit():
            username = f"u_{username}"
        return username
    
    def create_user(self, email: str, full_name: str, password: str = None) -> int:
        name_parts = full_name.strip().split(' ', 1)
        firstname = name_parts[0] if name_parts[0] else 'User'
        lastname = name_parts[1] if len(name_parts) > 1 else 'Unknown'
        
        firstname = firstname[:100]
        lastname = lastname[:100]
        
        if not password:
            password = self.generate_password()
        
        username = self.sanitize_username(email)
        
        try:
            existing = self._call_api('core_user_get_users_by_field', {
                'field': 'username', 'values[0]': username
            })
            if existing:
                username = f"{username}_{secrets.choice(string.digits)}{secrets.choice(string.digits)}"
        except Exception:
            pass
        
        encoded_password = urllib.parse.quote(password, safe='')
        
        print(f"\n📝 ПАРАМЕТРЫ ДЛЯ MOODLE API:")
        print(f"   username: '{username}'")
        print(f"   password: '{password}' (закодирован: {encoded_password})")
        print(f"   firstname: '{firstname}'")
        print(f"   lastname: '{lastname}'")
        print(f"   email: '{email}'")
        print("=" * 40)
        
        result = self._call_api('core_user_create_users', {
            'users[0][username]': username,
            'users[0][password]': encoded_password,
            'users[0][firstname]': firstname,
            'users[0][lastname]': lastname,
            'users[0][email]': email
        })
        
        print(f"✅ Moodle user created: ID={result[0]['id']}")
        return result[0]['id']
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        try:
            result = self._call_api('core_user_get_users_by_field', {
                'field': 'email', 'values[0]': email
            })
            return result[0] if result else None
        except Exception:
            return None
    
    def get_user_id(self, email: str) -> Optional[int]:
        user = self.get_user_by_email(email)
        return user['id'] if user else None
    
    def sync_user(self, email: str, full_name: str) -> int:
        existing = self.get_user_by_email(email)
        if existing:
            print(f"✅ User already exists in Moodle: {email} (ID={existing['id']})")
            return existing['id']
        
        print(f"🔄 Creating new user in Moodle: {email}")
        password = self.generate_password()
        user_id = self.create_user(email, full_name, password)
        return user_id
    
    def get_courses(self) -> List[Dict]:
        return self._call_api('core_course_get_courses')
    
    def get_course_by_id(self, course_id: int) -> Optional[Dict]:
        try:
            result = self._call_api('core_course_get_courses', {
                'options[ids][0]': course_id
            })
            return result[0] if result else None
        except Exception:
            return None
    
    def get_course_url(self, course_id: int) -> str:
        return f"{self.base_url}/course/view.php?id={course_id}"
    
    def enroll_user_to_course(self, user_id: int, course_id: int) -> bool:
        print(f"📚 Enrolling user {user_id} to course {course_id}")
        self._call_api('enrol_manual_enrol_users', {
            'enrolments[0][roleid]': 5,
            'enrolments[0][userid]': user_id,
            'enrolments[0][courseid]': course_id
        })
        print(f"✅ User {user_id} enrolled to course {course_id}")
        return True
    
    def is_user_enrolled(self, user_id: int, course_id: int) -> bool:
        try:
            result = self._call_api('core_enrol_get_enrolled_users', {
                'courseid': course_id
            })
            return any(user['id'] == user_id for user in result)
        except Exception:
            return False
    
    def get_enrolled_users(self, course_id: int) -> List[Dict]:
        return self._call_api('core_enrol_get_enrolled_users', {
            'courseid': course_id
        })
    
    def get_course_completion(self, user_id: int, course_id: int) -> Dict:
        return self._call_api('core_completion_get_course_completion_status', {
            'userid': user_id,
            'courseid': course_id
        })
    
    def get_activities_completion(self, user_id: int, course_id: int) -> List[Dict]:
        """
        Получает прогресс по каждому уроку/активности в курсе.
        
        Args:
            user_id: ID пользователя в Moodle
            course_id: ID курса в Moodle
            
        Returns:
            List[Dict]: Список активностей с прогрессом
        """
        try:
            result = self._call_api('core_completion_get_activities_completion_status', {
                'userid': user_id,
                'courseid': course_id
            })
            return result.get('statuses', [])
        except Exception as e:
            print(f"Error getting activities completion: {e}")
            return []
    
    def get_course_progress(self, user_id: int, course_id: int) -> Dict:
        """
        Получает полный прогресс пользователя по курсу.
        
        Args:
            user_id: ID пользователя в Moodle
            course_id: ID курса в Moodle
            
        Returns:
            Dict: {
                'completed': bool,
                'progress_percent': int,
                'timecompleted': Optional[int],
                'activities': List[Dict]
            }
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
            print(f"Error getting course progress: {e}")
            return {
                'completed': False,
                'progress_percent': 0,
                'timecompleted': None,
                'activities': [],
                'total_activities': 0,
                'completed_activities': 0
            }
    
    def get_site_info(self) -> Dict:
        return self._call_api('core_webservice_get_site_info')