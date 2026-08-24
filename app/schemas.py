# app/schemas.py
from pydantic import BaseModel, EmailStr, Field, validator, field_validator
from datetime import datetime, date
from typing import Optional, List, Any, Union
from enum import Enum
import re


class UserRole(str, Enum):
    """Технические роли пользователей в системе (определяют права доступа)"""
    TEACHER = "teacher"
    ADMIN = "admin"


# ДОЛЖНОСТИ (ПОЗИЦИИ) 

POSITION_TYPES = [
    "Учитель",
    "Завуч",
    "Директор",
    "Иное"
]


# АУТЕНТИФИКАЦИЯ 

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    organization: Optional[str] = Field(None, max_length=500)
    password: str = Field(..., min_length=8, description="Пароль должен содержать минимум 8 символов")
    admin_code: Optional[str] = None
    position_type: Optional[str] = Field(None, description="Тип должности: Учитель, Завуч, Директор, Иное")
    position_custom: Optional[str] = Field(None, max_length=255, description="Своя должность, если выбрано 'Иное'")

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Проверка силы пароля"""
        if len(v) < 8:
            raise ValueError('Пароль должен содержать минимум 8 символов')

        if not re.search(r'\d', v):
            raise ValueError('Пароль должен содержать хотя бы одну цифру')

        if not re.search(r'[A-ZА-Я]', v):
            raise ValueError('Пароль должен содержать хотя бы одну заглавную букву')

        if not re.search(r'[a-zа-я]', v):
            raise ValueError('Пароль должен содержать хотя бы одну строчную букву')

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Пароль должен содержать хотя бы один специальный символ (!@#$%^&*() etc.)')

        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            cleaned = re.sub(r'[^\d+]', '', v)
            if not re.match(r'^\+?\d{10,15}$', cleaned):
                raise ValueError('Неверный формат телефона. Используйте +7XXXXXXXXXX')
        return v

    @field_validator('position_type')
    @classmethod
    def validate_position_type(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in POSITION_TYPES:
            raise ValueError(f"Недопустимый тип должности. Допустимые значения: {', '.join(POSITION_TYPES)}")
        return v

    @field_validator('position_custom')
    @classmethod
    def validate_position_custom(cls, v: Optional[str], info) -> Optional[str]:
        if info.data.get('position_type') == 'Иное' and not v:
            raise ValueError('Пожалуйста, укажите вашу должность')
        return v


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    position: Optional[str]
    phone: Optional[str]
    organization: Optional[str]
    role: str
    is_blocked: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# АДМИНСКОЕ ОБНОВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ

class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    organization: Optional[str] = Field(None, max_length=500)
    is_blocked: Optional[bool] = None

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            cleaned = re.sub(r'[^\d+]', '', v)
            if not re.match(r'^\+?\d{10,15}$', cleaned):
                raise ValueError('Неверный формат телефона')
        return v


#  УПРАВЛЕНИЕ РОЛЯМИ

class UserRoleUpdate(BaseModel):
    """
    Схема для изменения роли пользователя администратором.
    Используется в эндпоинте PUT /api/admin/users/{user_id}/role
    """
    role: UserRole

    class Config:
        use_enum_values = True


#  КАТЕГОРИИ

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    courses_count: int = 0

    class Config:
        from_attributes = True


#  СПИКЕРЫ

class SpeakerCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    bio: Optional[str] = Field(None, max_length=1000)
    photo_url: Optional[str] = Field(None, max_length=500)
    position: Optional[str] = Field(None, max_length=255)


class SpeakerResponse(BaseModel):
    id: int
    full_name: str
    bio: Optional[str]
    photo_url: Optional[str]
    position: Optional[str]

    class Config:
        from_attributes = True


#    КУРСЫ

class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    image_url: Optional[str] = Field(None, max_length=500)
    video_url: Optional[str] = Field(None, max_length=500)
    video_platform: str = "youtube"
    hashtags: Optional[str] = Field(None, max_length=500)
    keywords: Optional[str] = Field(None, max_length=500)
    max_participants: int = Field(100, ge=1, le=1000)
    format_type: str = "online"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: bool = False
    moodle_course_id: Optional[int] = None
    speakers: List[SpeakerCreate] = []

    @field_validator('end_date')
    @classmethod
    def validate_dates(cls, v: Optional[datetime], info) -> Optional[datetime]:
        if v and info.data.get('start_date'):
            if v < info.data['start_date']:
                raise ValueError('Дата окончания не может быть раньше даты начала')
        return v


class CourseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=200)
    category_id: Optional[int] = None
    image_url: Optional[str] = Field(None, max_length=500)
    video_url: Optional[str] = Field(None, max_length=500)
    video_platform: Optional[str] = None
    hashtags: Optional[str] = Field(None, max_length=500)
    keywords: Optional[str] = Field(None, max_length=500)
    max_participants: Optional[int] = Field(None, ge=1, le=1000)
    format_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_open_ended: Optional[bool] = None
    is_active: Optional[bool] = None
    moodle_course_id: Optional[int] = None
    speakers: Optional[List[SpeakerCreate]] = None  # <-- ДОБАВЛЕНО

    @field_validator('end_date')
    @classmethod
    def validate_dates(cls, v: Optional[datetime], info) -> Optional[datetime]:
        if v and info.data.get('start_date'):
            if v < info.data['start_date']:
                raise ValueError('Дата окончания не может быть раньше даты начала')
        return v


class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    short_description: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]
    image_url: Optional[str]
    video_url: Optional[str]
    video_platform: Optional[str] = "youtube"
    hashtags: Optional[str]
    keywords: Optional[str]
    max_participants: int
    current_participants: int
    format_type: str = "online"
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    is_open_ended: bool = False
    is_active: bool
    moodle_course_id: Optional[int] = None
    speakers: List[SpeakerResponse] = []
    is_favorite: bool = False
    is_watch_later: bool = False

    class Config:
        from_attributes = True


#    УВЕДОМЛЕНИЯ

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


#    ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ

#    Личные данные

class PersonalDataUpdate(BaseModel):
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    middle_name: Optional[str] = Field(None, max_length=100)
    gender: Optional[str] = Field(None, pattern="^(male|female)$")
    birth_date: Optional[date] = None
    citizenship: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=200)
    municipality: Optional[str] = Field(None, max_length=200)
    phone_raw: Optional[str] = Field(None, max_length=20)
    consent_to_personal_data: Optional[bool] = None

    @field_validator('phone_raw')
    @classmethod
    def validate_phone_raw(cls, v: Optional[str]) -> Optional[str]:
        if v:
            cleaned = re.sub(r'\D', '', v)
            if len(cleaned) != 10:
                raise ValueError('Телефон должен содержать ровно 10 цифр (без +7)')
            return cleaned
        return v


class PersonalDataResponse(BaseModel):
    last_name: Optional[str]
    first_name: Optional[str]
    middle_name: Optional[str]
    gender: Optional[str]
    birth_date: Optional[date]
    citizenship: Optional[str]
    region: Optional[str]
    municipality: Optional[str]
    phone_raw: Optional[str]
    consent_to_personal_data: bool

    class Config:
        from_attributes = True


#    Образование

EDUCATION_LEVELS = [
    "Высшее",
    "Среднее профессиональное",
    "Среднее общее (студент)"
]


class EducationCreate(BaseModel):
    education_level: Optional[str] = Field(None, max_length=100)
    document_series: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=50)
    qualification: Optional[str] = Field(None, max_length=500)
    document_number: Optional[str] = Field(None, max_length=50)
    issue_date: Optional[date] = None
    academic_degree: Optional[str] = Field(None, max_length=50)
    academic_title: Optional[str] = Field(None, max_length=50)
    diploma_last_name: Optional[str] = Field(None, max_length=100)
    diploma_first_name: Optional[str] = Field(None, max_length=100)
    diploma_middle_name: Optional[str] = Field(None, max_length=100)
    is_main: bool = False

    @validator('education_level')
    def validate_education_level(cls, v):
        if v and v not in EDUCATION_LEVELS:
            raise ValueError(f"Недопустимый уровень образования. Допустимые значения: {', '.join(EDUCATION_LEVELS)}")
        return v


class EducationUpdate(BaseModel):
    education_level: Optional[str] = Field(None, max_length=100)
    document_series: Optional[str] = Field(None, max_length=50)
    registration_number: Optional[str] = Field(None, max_length=50)
    qualification: Optional[str] = Field(None, max_length=500)
    document_number: Optional[str] = Field(None, max_length=50)
    issue_date: Optional[date] = None
    academic_degree: Optional[str] = Field(None, max_length=50)
    academic_title: Optional[str] = Field(None, max_length=50)
    diploma_last_name: Optional[str] = Field(None, max_length=100)
    diploma_first_name: Optional[str] = Field(None, max_length=100)
    diploma_middle_name: Optional[str] = Field(None, max_length=100)
    is_main: Optional[bool] = None

    @validator('education_level')
    def validate_education_level(cls, v):
        if v and v not in EDUCATION_LEVELS:
            raise ValueError(f"Недопустимый уровень образования. Допустимые значения: {', '.join(EDUCATION_LEVELS)}")
        return v


class EducationResponse(BaseModel):
    id: int
    user_id: int
    education_level: Optional[str]
    document_series: Optional[str]
    registration_number: Optional[str]
    qualification: Optional[str]
    document_number: Optional[str]
    issue_date: Optional[date]
    academic_degree: Optional[str]
    academic_title: Optional[str]
    diploma_last_name: Optional[str]
    diploma_first_name: Optional[str]
    diploma_middle_name: Optional[str]
    is_main: bool
    diploma_file_url: Optional[str]
    diploma_file_name: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


#    Работа

ACTIVITY_TYPES = [
    "Управленческие кадры",
    "Педагогические работники",
    "Специалисты системы ДПO",
    "Органы управления образованием"
]


class WorkCreate(BaseModel):
    organization: Optional[str] = Field(None, max_length=500)
    organization_inn: Optional[str] = Field(None, max_length=50)
    work_experience_years: Optional[int] = Field(None, ge=0, le=60)
    teaching_experience_years: Optional[int] = Field(None, ge=0, le=60)
    organization_type: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)
    activity_type: str = Field(..., max_length=200, min_length=1, description="Вид деятельности (обязательно)")
    civil_service_status: Optional[str] = Field(None, max_length=100)
    subjects: List[str] = Field(..., min_length=1, description="Предметы (обязательно, минимум 1)")
    is_urban: bool = False
    is_rural: bool = False
    is_shnor: bool = False
    is_current: bool = True
    work_start_date: Optional[date] = None
    work_end_date: Optional[date] = None

    @validator('activity_type')
    def validate_activity_type(cls, v):
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"Недопустимый вид деятельности. Допустимые значения: {', '.join(ACTIVITY_TYPES)}")
        return v

    @validator('work_end_date')
    def validate_work_dates(cls, v, values):
        if v and values.get('work_start_date'):
            if v < values['work_start_date']:
                raise ValueError('Дата окончания не может быть раньше даты начала')
        return v


class WorkUpdate(BaseModel):
    organization: Optional[str] = Field(None, max_length=500)
    organization_inn: Optional[str] = Field(None, max_length=50)
    work_experience_years: Optional[int] = Field(None, ge=0, le=60)
    teaching_experience_years: Optional[int] = Field(None, ge=0, le=60)
    organization_type: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)
    activity_type: Optional[str] = Field(None, max_length=200)
    civil_service_status: Optional[str] = Field(None, max_length=100)
    subjects: Optional[List[str]] = None
    is_urban: Optional[bool] = None
    is_rural: Optional[bool] = None
    is_shnor: Optional[bool] = None
    is_current: Optional[bool] = None
    work_start_date: Optional[date] = None
    work_end_date: Optional[date] = None

    @validator('activity_type')
    def validate_activity_type(cls, v):
        if v and v not in ACTIVITY_TYPES:
            raise ValueError(f"Недопустимый вид деятельности. Допустимые значения: {', '.join(ACTIVITY_TYPES)}")
        return v


class WorkResponse(BaseModel):
    id: int
    user_id: int
    organization: Optional[str]
    organization_inn: Optional[str]
    work_experience_years: Optional[int]
    teaching_experience_years: Optional[int]
    organization_type: Optional[str]
    position: Optional[str]
    activity_type: Optional[str]
    civil_service_status: Optional[str]
    subjects: Optional[List[str]]
    is_urban: bool
    is_rural: bool
    is_shnor: bool
    is_current: bool
    work_start_date: Optional[date]
    work_end_date: Optional[date]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


#    Почтовый адрес

class AddressCreate(BaseModel):
    postal_index: Optional[str] = Field(None, max_length=10)
    region: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=200)
    street: Optional[str] = Field(None, max_length=300)
    house: Optional[str] = Field(None, max_length=50)
    building: Optional[str] = Field(None, max_length=50)
    structure: Optional[str] = Field(None, max_length=50)
    apartment: Optional[str] = Field(None, max_length=50)
    is_main: bool = True

    @field_validator('postal_index')
    @classmethod
    def validate_postal_index(cls, v: Optional[str]) -> Optional[str]:
        if v:
            if not re.match(r'^\d{5,6}$', v):
                raise ValueError('Индекс должен содержать 5 или 6 цифр')
        return v


class AddressUpdate(BaseModel):
    postal_index: Optional[str] = Field(None, max_length=10)
    region: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=200)
    street: Optional[str] = Field(None, max_length=300)
    house: Optional[str] = Field(None, max_length=50)
    building: Optional[str] = Field(None, max_length=50)
    structure: Optional[str] = Field(None, max_length=50)
    apartment: Optional[str] = Field(None, max_length=50)
    is_main: Optional[bool] = None


class AddressResponse(BaseModel):
    id: int
    user_id: int
    postal_index: Optional[str]
    region: Optional[str]
    city: Optional[str]
    street: Optional[str]
    house: Optional[str]
    building: Optional[str]
    structure: Optional[str]
    apartment: Optional[str]
    is_main: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


#    ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ

class AdditionalInfoUpdate(BaseModel):
    """Обновление дополнительной информации (только СНИЛС и подтверждение)"""
    snils: Optional[str] = Field(None, max_length=20)
    data_confirmed: Optional[bool] = None

    @field_validator('snils')
    @classmethod
    def validate_snils(cls, v: Optional[str]) -> Optional[str]:
        """
        УПРОЩЁННАЯ ВАЛИДАЦИЯ СНИЛС
        Принимает: 12345678901, 123-456-789-01, 123-456-789 01
        Возвращает: 123-456-789 01
        """
        if not v:
            return v

        # Убираем все пробелы, дефисы и другие разделители
        cleaned = re.sub(r'[\s\-]', '', v)

        # Проверяем, что только цифры и длина 11
        if not re.match(r'^\d{11}$', cleaned):
            raise ValueError('СНИЛС должен содержать 11 цифр')

        # Форматируем красиво: XXX-XXX-XXX XX
        formatted = f"{cleaned[:3]}-{cleaned[3:6]}-{cleaned[6:9]} {cleaned[9:11]}"
        return formatted


class AdditionalInfoResponse(BaseModel):
    """Ответ с дополнительной информацией (только СНИЛС и свидетельство о браке)"""
    id: int
    user_id: int
    snils: Optional[str]
    snils_file_url: Optional[str]
    snils_file_name: Optional[str]
    marriage_certificate_file_url: Optional[str]
    marriage_certificate_file_name: Optional[str]
    data_confirmed: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


#    Полный профиль

class FullProfileResponse(BaseModel):
    user: UserResponse
    personal_data: PersonalDataResponse
    education: List[EducationResponse] = []
    work: List[WorkResponse] = []
    address: Optional[AddressResponse] = None
    additional_info: Optional[AdditionalInfoResponse] = None
    is_profile_complete: bool

    class Config:
        from_attributes = True


#    Загрузка файлов   

class FileUploadResponse(BaseModel):
    url: str
    filename: str
    file_size: int
    file_type: str
    message: str


#    ПРОВЕРКА ПРОФИЛЯ    

class ProfileCompleteCheck(BaseModel):
    is_complete: bool
    missing_fields: List[str] = []
    message: str
    sections: Optional[List[dict]] = None
    total_sections: Optional[int] = None
    completed_sections: Optional[int] = None