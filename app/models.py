# app/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Enum, Float, JSON, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"


class ModuleType(str, enum.Enum):
    ONLINE = "online"      # Онлайн модуль (с заданиями)
    OFFLINE = "offline"    # Оффлайн модуль (отмечает учитель)


class AssignmentType(str, enum.Enum):
    TEXT = "text"          # Текстовый ответ
    FILE = "file"          # Ответ файлом
    CHOICE = "choice"      # Выбор варианта
    MULTIPLE = "multiple"  # Множественный выбор
    MATCHING = "matching"  # Соответствие
    ORDERING = "ordering"  # Упорядочивание


class LessonLectureType(str, enum.Enum):
    VIDEO = "video"        # Видео-лекция
    FILE = "file"          # Файл-лекция (PDF, DOC, PPT и т.д.)
    HYBRID = "hybrid"      # И видео, и файл


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
    
    favorite_courses = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="user", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    
    progress = relationship("UserProgress", back_populates="user", cascade="all, delete-orphan")
    achievements = relationship("UserAchievement", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="user", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="user", cascade="all, delete-orphan")
    
    # LMS связи - с указанием foreign_keys
    module_progress = relationship("UserModuleProgress", back_populates="user", cascade="all, delete-orphan", foreign_keys="UserModuleProgress.user_id")
    lesson_progress = relationship("UserLessonProgress", back_populates="user", cascade="all, delete-orphan", foreign_keys="UserLessonProgress.user_id")
    assignment_submissions = relationship("AssignmentSubmission", back_populates="user", cascade="all, delete-orphan", foreign_keys="AssignmentSubmission.user_id")
    assignment_attempts = relationship("AssignmentAttempt", back_populates="user", cascade="all, delete-orphan")


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
    price = Column(Float, default=0.0)
    max_participants = Column(Integer, default=100)
    current_participants = Column(Integer, default=0)
    format_type = Column(String(50), default="online")
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_open_ended = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== НОВОЕ ПОЛЕ ДЛЯ MOODLE ==========
    moodle_course_id = Column(Integer, nullable=True, index=True)  # ID курса в Moodle
    
    category = relationship("Category", back_populates="courses")
    speakers = relationship("CourseSpeaker", back_populates="course", cascade="all, delete-orphan")
    registrations = relationship("CourseRegistration", back_populates="course", cascade="all, delete-orphan")
    favorites = relationship("UserFavorite", back_populates="course", cascade="all, delete-orphan")
    watch_later = relationship("UserWatchLater", back_populates="course", cascade="all, delete-orphan")
    
    progress = relationship("UserProgress", back_populates="course", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="course", cascade="all, delete-orphan")
    certificates = relationship("Certificate", back_populates="course", cascade="all, delete-orphan")
    
    # LMS связи
    modules = relationship("CourseModule", back_populates="course", cascade="all, delete-orphan")


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


# ========== НОВЫЕ МОДЕЛИ ДЛЯ LMS ==========

class CourseModule(Base):
    """Модуль курса"""
    __tablename__ = "course_modules"
    
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    module_type = Column(Enum(ModuleType), default=ModuleType.ONLINE)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    course = relationship("Course", back_populates="modules")
    lessons = relationship("CourseLesson", back_populates="module", cascade="all, delete-orphan")
    user_progress = relationship("UserModuleProgress", back_populates="module", cascade="all, delete-orphan")


class CourseLesson(Base):
    """Урок/материал курса"""
    __tablename__ = "course_lessons"
    
    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    video_url = Column(String(500), nullable=True)
    order_index = Column(Integer, default=0)
    is_free = Column(Boolean, default=False)
    duration_minutes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== ПОЛЯ ДЛЯ ЛЕКЦИЙ ==========
    lecture_type = Column(Enum(LessonLectureType), server_default=LessonLectureType.VIDEO)
    lecture_file_url = Column(String(500), nullable=True)
    lecture_file_name = Column(String(500), nullable=True)
    lecture_file_type = Column(String(50), nullable=True)
    lecture_file_size = Column(Integer, default=0)
    has_lecture_file = Column(Boolean, default=False)
    
    # ========== ПОЛЯ ДЛЯ УПРАВЛЕНИЯ ==========
    allow_retake = Column(Boolean, default=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    is_published = Column(Boolean, default=True)
    
    module = relationship("CourseModule", back_populates="lessons")
    attachments = relationship("LessonAttachment", back_populates="lesson", cascade="all, delete-orphan")
    assignment = relationship("LessonAssignment", back_populates="lesson", uselist=False, cascade="all, delete-orphan")
    user_progress = relationship("UserLessonProgress", back_populates="lesson", cascade="all, delete-orphan")


class LessonAttachment(Base):
    """Прикреплённые файлы к уроку"""
    __tablename__ = "lesson_attachments"
    
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    file_type = Column(String(100), nullable=True)
    is_required = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    lesson = relationship("CourseLesson", back_populates="attachments")


class LessonAssignment(Base):
    """Задание к уроку"""
    __tablename__ = "lesson_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    assignment_type = Column(Enum(AssignmentType), default=AssignmentType.TEXT)
    max_score = Column(Integer, default=100)
    passing_score = Column(Integer, default=60)
    time_limit_minutes = Column(Integer, default=0)
    show_timer = Column(Boolean, default=True)
    max_attempts = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== ПОЛЯ ДЛЯ УПРАВЛЕНИЯ ==========
    deadline = Column(DateTime(timezone=True), nullable=True)
    allow_retake = Column(Boolean, default=True)
    retake_count = Column(Integer, default=3)
    auto_grade = Column(Boolean, default=False)
    
    lesson = relationship("CourseLesson", back_populates="assignment")
    questions = relationship("AssignmentQuestion", back_populates="assignment", cascade="all, delete-orphan")
    submissions = relationship("AssignmentSubmission", back_populates="assignment", cascade="all, delete-orphan")


class AssignmentQuestion(Base):
    """Вопросы в задании"""
    __tablename__ = "assignment_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("lesson_assignments.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(Text, nullable=False)
    question_image = Column(String(500), nullable=True)
    question_video = Column(String(500), nullable=True)
    question_type = Column(Enum(AssignmentType), default=AssignmentType.TEXT)
    options = Column(Text, nullable=True)
    correct_answer = Column(Text, nullable=True)
    points = Column(Integer, default=10)
    order_index = Column(Integer, default=0)
    is_required = Column(Boolean, default=True)
    
    # ========== НОВЫЕ ПОЛЯ ==========
    hint = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    
    assignment = relationship("LessonAssignment", back_populates="questions")
    answers = relationship("UserAnswer", back_populates="question", cascade="all, delete-orphan")


class UserModuleProgress(Base):
    """Прогресс пользователя по модулю"""
    __tablename__ = "user_module_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    module_id = Column(Integer, ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_by_teacher = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    teacher_comment = Column(Text, nullable=True)
    
    user = relationship("User", back_populates="module_progress", foreign_keys=[user_id])
    module = relationship("CourseModule", back_populates="user_progress")


class UserLessonProgress(Base):
    """Прогресс пользователя по уроку"""
    __tablename__ = "user_lesson_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lesson_id = Column(Integer, ForeignKey("course_lessons.id", ondelete="CASCADE"), nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_position = Column(Integer, default=0)
    video_watched_percent = Column(Integer, default=0)
    
    # ========== НОВЫЕ ПОЛЯ ==========
    lecture_file_downloaded = Column(Boolean, default=False)
    last_accessed = Column(DateTime(timezone=True), default=func.now())
    time_spent_seconds = Column(Integer, default=0)
    
    user = relationship("User", back_populates="lesson_progress", foreign_keys=[user_id])
    lesson = relationship("CourseLesson", back_populates="user_progress")


class AssignmentSubmission(Base):
    """Ответ пользователя на задание"""
    __tablename__ = "assignment_submissions"
    
    id = Column(Integer, primary_key=True, index=True)
    assignment_id = Column(Integer, ForeignKey("lesson_assignments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=True)
    is_passed = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    graded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    graded_at = Column(DateTime(timezone=True), nullable=True)
    teacher_comment = Column(Text, nullable=True)
    current_attempt = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    
    # ========== ПОЛЯ ДЛЯ ПЕРЕСДАЧИ ==========
    is_retake = Column(Boolean, default=False)
    retake_number = Column(Integer, default=0)
    previous_submission_id = Column(Integer, ForeignKey("assignment_submissions.id", ondelete="SET NULL"), nullable=True)
    time_spent_seconds = Column(Integer, default=0)
    is_auto_graded = Column(Boolean, default=False)
    auto_grade_score = Column(Integer, nullable=True)
    can_retake = Column(Boolean, default=True)
    
    assignment = relationship("LessonAssignment", back_populates="submissions")
    user = relationship("User", back_populates="assignment_submissions", foreign_keys=[user_id])
    answers = relationship("UserAnswer", back_populates="submission", cascade="all, delete-orphan")
    attempts = relationship("AssignmentAttempt", back_populates="submission", cascade="all, delete-orphan")
    
    previous_submission = relationship(
        "AssignmentSubmission", 
        remote_side=[id], 
        backref="next_submissions",
        foreign_keys=[previous_submission_id]
    )


class AssignmentAttempt(Base):
    """Попытки прохождения задания"""
    __tablename__ = "assignment_attempts"
    
    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, default=1)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Integer, nullable=True)
    is_passed = Column(Boolean, default=False)
    
    # ========== ПОЛЯ ДЛЯ ПЕРЕСДАЧИ ==========
    is_retake = Column(Boolean, default=False)
    time_spent_seconds = Column(Integer, default=0)
    
    submission = relationship("AssignmentSubmission", back_populates="attempts")
    user = relationship("User", back_populates="assignment_attempts", foreign_keys=[user_id])


class UserAnswer(Base):
    """Ответ пользователя на вопрос"""
    __tablename__ = "user_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    submission_id = Column(Integer, ForeignKey("assignment_submissions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("assignment_questions.id", ondelete="CASCADE"), nullable=False)
    answer_text = Column(Text, nullable=True)
    answer_file = Column(String(500), nullable=True)
    is_correct = Column(Boolean, nullable=True)
    points_earned = Column(Integer, default=0)
    attempt_id = Column(Integer, ForeignKey("assignment_attempts.id", ondelete="SET NULL"), nullable=True)
    
    # ========== НОВЫЕ ПОЛЯ ==========
    teacher_comment = Column(Text, nullable=True)
    auto_graded = Column(Boolean, default=False)
    
    submission = relationship("AssignmentSubmission", back_populates="answers")
    question = relationship("AssignmentQuestion", back_populates="answers")