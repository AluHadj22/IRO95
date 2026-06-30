# app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Enum, Float, JSON, Table, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    position = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    organization = Column(String(500), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.TEACHER)
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== НОВЫЕ ПОЛЯ ДЛЯ ПРОФИЛЯ ==========
    # Личные данные
    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)  # male/female
    birth_date = Column(Date, nullable=True)
    citizenship = Column(String(100), nullable=True)
    region = Column(String(200), nullable=True)  # Субъект РФ
    municipality = Column(String(200), nullable=True)
    phone_raw = Column(String(20), nullable=True)  # телефон в формате +7XXXXXXXXXX
    consent_to_personal_data = Column(Boolean, default=False)
    
    # Связи с новыми таблицами
    education = relationship("UserEducation", back_populates="user", cascade="all, delete-orphan")
    work = relationship("UserWork", back_populates="user", cascade="all, delete-orphan")
    address = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan", uselist=False)
    additional_info = relationship("UserAdditionalInfo", back_populates="user", cascade="all, delete-orphan", uselist=False)
    
    # ========== СУЩЕСТВУЮЩИЕ СВЯЗИ ==========
    favorite_courses = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="user", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    
    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="user", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="user", cascade="all, delete-orphan")
    
    # ========== МЕТОДЫ ПРОВЕРКИ ПРОФИЛЯ ==========
    
    def is_personal_data_complete(self) -> bool:
        """Проверяет, заполнены ли все обязательные поля личных данных"""
        required_fields = [
            self.last_name, self.first_name, self.middle_name,
            self.gender, self.birth_date, self.citizenship,
            self.region, self.municipality, self.phone_raw,
            self.consent_to_personal_data
        ]
        return all(required_fields)
    
    def has_education(self) -> bool:
        """Проверяет, есть ли хотя бы одна запись об образовании"""
        return len(self.education) > 0
    
    def has_education_with_diploma(self) -> bool:
        """Проверяет, есть ли запись об образовании с загруженным дипломом"""
        for edu in self.education:
            if edu.diploma_file_url:
                return True
        return False
    
    def has_work(self) -> bool:
        """Проверяет, есть ли хотя бы одна запись о работе"""
        return len(self.work) > 0
    
    def has_work_with_subjects(self) -> bool:
        """Проверяет, есть ли запись о работе с заполненными предметами"""
        import json
        for work in self.work:
            if work.subjects:
                try:
                    subjects = json.loads(work.subjects)
                    if subjects and len(subjects) > 0:
                        return True
                except:
                    pass
        return False
    
    def has_snils(self) -> bool:
        """Проверяет, заполнен ли СНИЛС"""
        return self.additional_info is not None and bool(self.additional_info.snils)
    
    def has_snils_file(self) -> bool:
        """Проверяет, загружен ли файл СНИЛС"""
        return self.additional_info is not None and bool(self.additional_info.snils_file_url)
    
    def has_passport_file(self) -> bool:
        """Проверяет, загружен ли файл паспорта"""
        return self.additional_info is not None and bool(self.additional_info.passport_file_url)
    
    def has_inn_file(self) -> bool:
        """Проверяет, загружен ли файл ИНН"""
        return self.additional_info is not None and bool(self.additional_info.inn_file_url)
    
    def has_data_confirmed(self) -> bool:
        """Проверяет, подтверждены ли данные"""
        return self.additional_info is not None and self.additional_info.data_confirmed
    
    def is_profile_complete(self) -> bool:
        """
        ОСНОВНАЯ ПРОВЕРКА: заполнен ли профиль полностью для записи на курсы.
        Проверяет:
        1. Личные данные (все обязательные поля)
        2. Образование (хотя бы одна запись)
        3. Диплом (загружен файл)
        4. Работа (хотя бы одна запись с предметами)
        5. СНИЛС (номер и файл)
        6. Паспорт (файл)
        7. ИНН (файл)
        8. Подтверждение данных
        """
        return (
            self.is_personal_data_complete() and
            self.has_education() and
            self.has_education_with_diploma() and
            self.has_work() and
            self.has_work_with_subjects() and
            self.has_snils() and
            self.has_snils_file() and
            self.has_passport_file() and
            self.has_inn_file() and
            self.has_data_confirmed()
        )
    
    def get_profile_completion_details(self) -> dict:
        """
        Возвращает детальную информацию о заполненности профиля.
        Используется для отображения пользователю списка незаполненных разделов.
        """
        missing_sections = []
        
        # Проверка личных данных
        if not self.is_personal_data_complete():
            missing_fields = []
            if not self.last_name: missing_fields.append("Фамилия")
            if not self.first_name: missing_fields.append("Имя")
            if not self.middle_name: missing_fields.append("Отчество")
            if not self.gender: missing_fields.append("Пол")
            if not self.birth_date: missing_fields.append("Дата рождения")
            if not self.citizenship: missing_fields.append("Гражданство")
            if not self.region: missing_fields.append("Субъект РФ")
            if not self.municipality: missing_fields.append("Муниципалитет")
            if not self.phone_raw: missing_fields.append("Телефон")
            if not self.consent_to_personal_data: missing_fields.append("Согласие на обработку данных")
            missing_sections.append({
                "section": "personal_data",
                "label": "Личные данные",
                "fields": missing_fields,
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "personal_data",
                "label": "Личные данные",
                "fields": [],
                "is_complete": True
            })
        
        # Проверка образования
        if not self.has_education():
            missing_sections.append({
                "section": "education",
                "label": "Образование",
                "fields": ["Добавьте запись об образовании"],
                "is_complete": False
            })
        elif not self.has_education_with_diploma():
            missing_sections.append({
                "section": "education",
                "label": "Образование",
                "fields": ["Загрузите копию диплома"],
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "education",
                "label": "Образование",
                "fields": [],
                "is_complete": True
            })
        
        # Проверка работы
        if not self.has_work():
            missing_sections.append({
                "section": "work",
                "label": "Место работы",
                "fields": ["Добавьте место работы"],
                "is_complete": False
            })
        elif not self.has_work_with_subjects():
            missing_sections.append({
                "section": "work",
                "label": "Место работы",
                "fields": ["Заполните предметы в месте работы"],
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "work",
                "label": "Место работы",
                "fields": [],
                "is_complete": True
            })
        
        # Проверка документов
        doc_fields = []
        if not self.has_snils():
            doc_fields.append("Заполните номер СНИЛС")
        if not self.has_snils_file():
            doc_fields.append("Загрузите файл СНИЛС")
        if not self.has_passport_file():
            doc_fields.append("Загрузите копию паспорта")
        if not self.has_inn_file():
            doc_fields.append("Загрузите копию ИНН")
        
        if doc_fields:
            missing_sections.append({
                "section": "documents",
                "label": "Документы",
                "fields": doc_fields,
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "documents",
                "label": "Документы",
                "fields": [],
                "is_complete": True
            })
        
        # Проверка подтверждения данных
        if not self.has_data_confirmed():
            missing_sections.append({
                "section": "confirmation",
                "label": "Подтверждение данных",
                "fields": ["Подтвердите все данные в разделе Документы"],
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "confirmation",
                "label": "Подтверждение данных",
                "fields": [],
                "is_complete": True
            })
        
        all_complete = all(section["is_complete"] for section in missing_sections)
        
        return {
            "is_complete": all_complete,
            "sections": missing_sections,
            "total_sections": len(missing_sections),
            "completed_sections": sum(1 for s in missing_sections if s["is_complete"])
        }


class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="📁")
    color = Column(String(20), default="#667eea")
    order_index = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    courses = relationship("Course", back_populates="category", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    short_description = Column(String(200), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    image_url = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    video_platform = Column(String(50), default="youtube")
    hashtags = Column(String(500), nullable=True)
    keywords = Column(String(500), nullable=True)
    max_participants = Column(Integer, default=100)
    current_participants = Column(Integer, default=0)
    format_type = Column(String(50), default="online")
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_open_ended = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== ПОЛЕ ДЛЯ MOODLE ==========
    moodle_course_id = Column(Integer, nullable=True, index=True)  # ID курса в Moodle
    
    category = relationship("Category", back_populates="courses")
    speakers = relationship("CourseSpeaker", back_populates="course", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="course", cascade="all, delete-orphan")
    favorites = relationship("UserFavorite", back_populates="course", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="course", cascade="all, delete-orphan")
    
    progress = relationship("UserProgress", back_populates="course", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="course", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="course", cascade="all, delete-orphan")


class CourseSpeaker(Base):
    __tablename__ = "course_speakers"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(255), nullable=False)
    bio = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)
    position = Column(String(255), nullable=True)
    
    course = relationship("Course", back_populates="speakers")


class UserFavorite(Base):
    __tablename__ = "user_favorites"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="favorite_courses")
    course = relationship("Course", back_populates="favorites")


class UserWatchLater(Base):
    __tablename__ = "user_watch_later"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="watch_later")
    course = relationship("Course", back_populates="watch_later")


class CourseRegistration(Base):
    __tablename__ = "course_registrations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    is_paid = Column(Boolean, default=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="registrations")
    course = relationship("Course", back_populates="registrations")


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="notifications")


class UserProgress(Base):
    """Прогресс пользователя по курсу (общий)"""
    __tablename__ = "user_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    progress_percent = Column(Integer, default=0)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    is_completed = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="progress", foreign_keys=[user_id])
    course = relationship("Course", back_populates="progress", foreign_keys=[course_id])


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_id = Column(String(100), nullable=False)
    achievement_title = Column(String(255), nullable=False)
    achievement_description = Column(String(500), nullable=False)
    achievement_icon = Column(String(100), nullable=False)
    achievement_level = Column(String(50), default="bronze")
    earned_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="achievements", foreign_keys=[user_id])


class UserActivityLog(Base):
    __tablename__ = "user_activity_log"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(String(100), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    extra_data = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="activity_logs", foreign_keys=[user_id])
    course = relationship("Course", back_populates="activity_logs", foreign_keys=[course_id])


class Certificate(Base):
    __tablename__ = "certificates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    certificate_number = Column(String(100), unique=True, nullable=False)
    issue_date = Column(DateTime(timezone=True), server_default=func.now())
    pdf_url = Column(String(500), nullable=True)
    
    user = relationship("User", back_populates="certificates", foreign_keys=[user_id])
    course = relationship("Course", back_populates="certificates", foreign_keys=[course_id])


# ========== НОВЫЕ МОДЕЛИ ДЛЯ ПРОФИЛЯ ПОЛЬЗОВАТЕЛЯ ==========

class UserEducation(Base):
    """Образование пользователя"""
    __tablename__ = "user_education"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Уровень образования (выплывающий список)
    education_level = Column(String(100), nullable=True)  # СПО; Бакалавриат; Специалитет; Магистратура; Начальное общее; Основное общее; Среднее общее
    
    # Данные документа об образовании
    document_series = Column(String(50), nullable=True)  # Серия документа
    registration_number = Column(String(50), nullable=True)  # Регистрационный номер
    qualification = Column(String(500), nullable=True)  # Квалификация по диплому
    document_number = Column(String(50), nullable=True)  # Номер документа
    issue_date = Column(Date, nullable=True)  # Дата выдачи
    
    # Ученая степень / звание
    academic_degree = Column(String(50), nullable=True)  # Нет степени; Кандидат наук; Доктор наук
    academic_title = Column(String(50), nullable=True)  # Нет звания; Доцент; Профессор
    
    # Если ФИО в дипломе отличается
    diploma_last_name = Column(String(100), nullable=True)
    diploma_first_name = Column(String(100), nullable=True)
    diploma_middle_name = Column(String(100), nullable=True)
    
    # Флаг основного образования
    is_main = Column(Boolean, default=False)
    
    # Файл с копией диплома
    diploma_file_url = Column(String(500), nullable=True)
    diploma_file_name = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="education")


class UserWork(Base):
    """Место работы пользователя"""
    __tablename__ = "user_work"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Место работы (поиск по ИНН или названию)
    organization = Column(String(500), nullable=True)  # полное название организации
    organization_inn = Column(String(50), nullable=True)  # ИНН организации
    
    # Стаж
    work_experience_years = Column(Integer, nullable=True)  # Стаж в должности (лет)
    teaching_experience_years = Column(Integer, nullable=True)  # Педагогический стаж (лет)
    
    # Тип организации (выплывающий список)
    organization_type = Column(String(200), nullable=True)  # 1-10 типы
    
    # Должность (зависит от типа организации)
    position = Column(String(200), nullable=True)
    
    # Дополнительные поля
    activity_type = Column(String(200), nullable=True)  # Вид деятельности (необязательно)
    civil_service_status = Column(String(100), nullable=True)  # Статус госслужащего
    
    # Предметы (выплывающий список, множественный выбор) - храним как JSON строку
    subjects = Column(Text, nullable=True)  # JSON строка с массивом предметов
    
    # Чекбоксы
    is_urban = Column(Boolean, default=False)  # городская
    is_rural = Column(Boolean, default=False)  # сельская
    is_shnor = Column(Boolean, default=False)  # ШНОР
    
    # Текущее место работы
    is_current = Column(Boolean, default=True)
    work_start_date = Column(Date, nullable=True)
    work_end_date = Column(Date, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="work")


class UserAddress(Base):
    """Почтовый адрес пользователя"""
    __tablename__ = "user_address"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    postal_index = Column(String(10), nullable=True)  # Индекс
    region = Column(String(200), nullable=True)  # Регион/область
    city = Column(String(200), nullable=True)  # Населенный пункт
    street = Column(String(300), nullable=True)  # Улица
    house = Column(String(50), nullable=True)  # Номер дома
    building = Column(String(50), nullable=True)  # Корпус (необязательно)
    structure = Column(String(50), nullable=True)  # Строение (необязательно)
    apartment = Column(String(50), nullable=True)  # Квартира (необязательно)
    
    is_main = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="address")


class UserAdditionalInfo(Base):
    """Дополнительная информация о пользователе"""
    __tablename__ = "user_additional_info"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # СНИЛС (формат: XXX-XXX-XXX XX)
    snils = Column(String(20), nullable=True)
    snils_file_url = Column(String(500), nullable=True)
    snils_file_name = Column(String(500), nullable=True)
    
    # Паспортные данные
    passport_series = Column(String(10), nullable=True)
    passport_number = Column(String(20), nullable=True)
    passport_issued_by = Column(String(500), nullable=True)
    passport_issued_date = Column(Date, nullable=True)
    passport_department_code = Column(String(20), nullable=True)
    passport_file_url = Column(String(500), nullable=True)
    passport_file_name = Column(String(500), nullable=True)
    
    # ИНН
    inn = Column(String(20), nullable=True)
    inn_file_url = Column(String(500), nullable=True)
    inn_file_name = Column(String(500), nullable=True)
    
    # Свидетельство о браке (если была смена ФИО)
    marriage_certificate_file_url = Column(String(500), nullable=True)
    marriage_certificate_file_name = Column(String(500), nullable=True)
    
    # Подтверждение данных
    data_confirmed = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="additional_info")