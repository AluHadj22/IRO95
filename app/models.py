# app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Enum, Float, JSON, Table, Date, \
    Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
import json


class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class MoodleSyncStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    position = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    organization = Column(String(500), nullable=True)
    hashed_password = Column(String(300), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.TEACHER)
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    last_name = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    gender = Column(String(10), nullable=True)
    birth_date = Column(Date, nullable=True)
    citizenship = Column(String(100), nullable=True)
    region = Column(String(200), nullable=True)
    municipality = Column(String(200), nullable=True)
    phone_raw = Column(String(20), nullable=True)
    consent_to_personal_data = Column(Boolean, default=False)
    consent_given_at = Column(DateTime(timezone=True), nullable=True)

    moodle_account_existed_before = Column(Boolean, default=False)
    moodle_password_sent = Column(Boolean, default=False)
    moodle_password = Column(String(255), nullable=True)  # Храним последний сгенерированный пароль для Moodle
    moodle_username = Column(String(255), nullable=True)  # Храним логин в Moodle

    education = relationship("UserEducation", back_populates="user", cascade="all, delete-orphan")
    work = relationship("UserWork", back_populates="user", cascade="all, delete-orphan")
    address = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan", uselist=False)
    additional_info = relationship("UserAdditionalInfo", back_populates="user", cascade="all, delete-orphan",
                                   uselist=False)

    favorite_courses = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="user", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="user", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="user", cascade="all, delete-orphan")

    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    moodle_sync_tasks = relationship("MoodleSyncTask", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_user_email', 'email'),
        Index('idx_user_role', 'role'),
        Index('idx_user_is_blocked', 'is_blocked'),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_teacher(self) -> bool:
        return self.role == UserRole.TEACHER

    def get_role_display(self) -> str:
        role_names = {
            UserRole.TEACHER: "Преподаватель",
            UserRole.ADMIN: "Администратор"
        }
        return role_names.get(self.role, "Неизвестно")

    def get_position_display(self) -> str:
        return self.position or "Не указана"

    def is_personal_data_complete(self) -> bool:
        required_fields = [
            self.last_name, self.first_name, self.middle_name,
            self.gender, self.birth_date, self.citizenship,
            self.region, self.municipality, self.phone_raw,
            self.consent_to_personal_data
        ]
        return all(field is not None and field != "" for field in required_fields)

    def has_education(self) -> bool:
        return self.education is not None and len(self.education) > 0

    def has_education_with_diploma(self) -> bool:
        if not self.education:
            return False
        for edu in self.education:
            if edu.diploma_file_url:
                return True
        return False

    def has_work(self) -> bool:
        return self.work is not None and len(self.work) > 0

    def has_work_with_subjects(self) -> bool:
        if not self.work:
            return False
        for work in self.work:
            if work.subjects:
                try:
                    subjects = json.loads(work.subjects)
                    if subjects and len(subjects) > 0:
                        return True
                except (json.JSONDecodeError, TypeError):
                    pass
        return False

    def has_snils(self) -> bool:
        return self.additional_info is not None and bool(self.additional_info.snils)

    def has_snils_file(self) -> bool:
        return self.additional_info is not None and bool(self.additional_info.snils_file_url)

    def has_marriage_certificate_file(self) -> bool:
        return self.additional_info is not None and bool(self.additional_info.marriage_certificate_file_url)

    def has_data_confirmed(self) -> bool:
        return self.additional_info is not None and self.additional_info.data_confirmed

    def is_profile_complete(self) -> bool:
        return (
                self.is_personal_data_complete() and
                self.has_education() and
                self.has_education_with_diploma() and
                self.has_work() and
                self.has_snils() and
                self.has_snils_file() and
                self.has_data_confirmed()
        )

    def get_profile_completion_details(self) -> dict:
        missing_sections = []

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

        if not self.has_education():
            missing_sections.append({
                "section": "education",
                "label": "Образование",
                "fields": ["Добавьте запись об образовании"],
                "is_complete": False
            })
        elif not self.has_education_with_diploma():
            missing_sections.append({
                "section": "education_diploma",
                "label": "Диплом об образовании",
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

        if not self.has_work():
            missing_sections.append({
                "section": "work",
                "label": "Место работы",
                "fields": ["Добавьте место работы"],
                "is_complete": False
            })
        else:
            missing_sections.append({
                "section": "work",
                "label": "Место работы",
                "fields": [],
                "is_complete": True
            })

        doc_fields = []
        if not self.has_snils():
            doc_fields.append("Заполните номер СНИЛС")
        if not self.has_snils_file():
            doc_fields.append("Загрузите копию СНИЛС")

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

    moodle_course_id = Column(Integer, nullable=True, index=True)

    __table_args__ = (
        Index('idx_course_category_id', 'category_id'),
        Index('idx_course_is_active', 'is_active'),
        Index('idx_course_moodle_id', 'moodle_course_id'),
    )

    category = relationship("Category", back_populates="courses")
    speakers = relationship("CourseSpeaker", back_populates="course", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="course", cascade="all, delete-orphan")
    favorites = relationship("UserFavorite", back_populates="course", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="course", cascade="all, delete-orphan")

    progress = relationship("UserProgress", back_populates="course", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="course", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="course", cascade="all, delete-orphan")

    moodle_sync_tasks = relationship("MoodleSyncTask", back_populates="course", cascade="all, delete-orphan")


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


class UserEducation(Base):
    __tablename__ = "user_education"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    education_level = Column(String(100), nullable=True)
    document_series = Column(String(50), nullable=True)
    registration_number = Column(String(50), nullable=True)
    qualification = Column(String(500), nullable=True)
    document_number = Column(String(50), nullable=True)
    issue_date = Column(Date, nullable=True)
    academic_degree = Column(String(50), nullable=True)
    academic_title = Column(String(50), nullable=True)
    diploma_last_name = Column(String(100), nullable=True)
    diploma_first_name = Column(String(100), nullable=True)
    diploma_middle_name = Column(String(100), nullable=True)
    is_main = Column(Boolean, default=False)
    diploma_file_url = Column(String(500), nullable=True)
    diploma_file_name = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="education")


class UserWork(Base):
    __tablename__ = "user_work"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    organization = Column(String(500), nullable=True)
    organization_inn = Column(String(50), nullable=True)
    work_experience_years = Column(Integer, nullable=True)
    teaching_experience_years = Column(Integer, nullable=True)
    organization_type = Column(String(200), nullable=True)
    position = Column(String(200), nullable=True)
    activity_type = Column(String(200), nullable=True)
    civil_service_status = Column(String(100), nullable=True)
    subjects = Column(Text, nullable=True)
    is_urban = Column(Boolean, default=False)
    is_rural = Column(Boolean, default=False)
    is_shnor = Column(Boolean, default=False)
    is_current = Column(Boolean, default=True)
    work_start_date = Column(Date, nullable=True)
    work_end_date = Column(Date, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="work")


class UserAddress(Base):
    __tablename__ = "user_address"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    postal_index = Column(String(10), nullable=True)
    region = Column(String(200), nullable=True)
    city = Column(String(200), nullable=True)
    street = Column(String(300), nullable=True)
    house = Column(String(50), nullable=True)
    building = Column(String(50), nullable=True)
    structure = Column(String(50), nullable=True)
    apartment = Column(String(50), nullable=True)
    is_main = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="address")


class UserAdditionalInfo(Base):
    __tablename__ = "user_additional_info"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    snils = Column(String(255), nullable=True)
    snils_file_url = Column(String(500), nullable=True)
    snils_file_name = Column(String(500), nullable=True)

    marriage_certificate_file_url = Column(String(500), nullable=True)
    marriage_certificate_file_name = Column(String(500), nullable=True)

    data_confirmed = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="additional_info")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)

    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_reset_token', 'token'),
        Index('idx_reset_user_id', 'user_id'),
        Index('idx_reset_expires_at', 'expires_at'),
    )


class MoodleSyncTask(Base):
    __tablename__ = "moodle_sync_tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(MoodleSyncStatus), default=MoodleSyncStatus.PENDING, nullable=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    last_error = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)

    moodle_user_id = Column(Integer, nullable=True)
    moodle_enrollment_id = Column(Integer, nullable=True)

    user = relationship("User", back_populates="moodle_sync_tasks")
    course = relationship("Course", back_populates="moodle_sync_tasks")

    __table_args__ = (
        Index('idx_sync_status', 'status'),
        Index('idx_sync_user_course', 'user_id', 'course_id'),
        Index('idx_sync_next_retry', 'next_retry_at'),
        Index('idx_sync_created_at', 'created_at'),
    )

    def get_retry_delay(self) -> int:
        delays = [30, 60, 120, 300, 600]
        if self.attempts < len(delays):
            return delays[self.attempts]
        return 600

    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

    def increment_attempts(self):
        self.attempts += 1
        if self.can_retry():
            delay = self.get_retry_delay()
            self.next_retry_at = func.now() + delay
        else:
            self.status = MoodleSyncStatus.FAILED
            self.next_retry_at = None