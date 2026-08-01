# app/services/moodle_sync_service.py
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.models import User, Course, MoodleSyncTask, MoodleSyncStatus, UserActivityLog
from app.services.moodle_service import MoodleService
from app.services.email_service import email_service
from app.config import settings

logger = logging.getLogger(__name__)


class MoodleSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.moodle = MoodleService()
        self.batch_size = 10
        self.rate_limit_delay = 0.1

    def process_queue(self) -> int:
        """
        Основной метод обработки очереди.
        Возвращает количество обработанных задач.
        """
        processed_count = 0
        tasks = self._get_pending_tasks()

        if not tasks:
            logger.debug("Нет задач в очереди для обработки")
            return 0

        logger.info(f"Найдено {len(tasks)} задач для обработки")

        for task in tasks:
            try:
                self._process_task(task)
                processed_count += 1
            except Exception as e:
                logger.error(f"Критическая ошибка при обработке задачи {task.id}: {str(e)}")
                self.db.rollback()

        return processed_count

    def _get_pending_tasks(self, limit: int = 10) -> List[MoodleSyncTask]:
        """
        Получение задач из очереди.
        """
        now = datetime.utcnow()

        query = self.db.query(MoodleSyncTask).filter(
            MoodleSyncTask.status == MoodleSyncStatus.PENDING,
            or_(
                MoodleSyncTask.next_retry_at.is_(None),
                MoodleSyncTask.next_retry_at <= now
            )
        ).order_by(
            MoodleSyncTask.created_at.asc()
        ).limit(limit)

        return query.all()

    def _process_task(self, task: MoodleSyncTask):
        """
        Обработка одной задачи.
        """
        logger.info(f"Начало обработки задачи {task.id} (попытка {task.attempts + 1})")

        task.status = MoodleSyncStatus.PROCESSING
        self.db.commit()

        try:
            user = self.db.query(User).filter(User.id == task.user_id).first()
            course = self.db.query(Course).filter(Course.id == task.course_id).first()

            if not user:
                raise ValueError(f"Пользователь с ID {task.user_id} не найден")

            if not course:
                raise ValueError(f"Курс с ID {task.course_id} не найден")

            if not course.moodle_course_id:
                raise ValueError(f"Курс {course.id} не привязан к Moodle")

            moodle_user_id = self._sync_user_to_moodle(user)

            moodle_enrolled = self._enroll_user_to_moodle(user, course, moodle_user_id)

            task.moodle_user_id = moodle_user_id
            task.status = MoodleSyncStatus.COMPLETED
            task.processed_at = datetime.utcnow()
            task.last_error = None
            task.next_retry_at = None

            self.db.commit()

            self._log_activity(user, course, True)

            logger.info(f"Задача {task.id} успешно завершена")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка при обработке задачи {task.id}: {error_msg}")

            task.attempts += 1

            if task.can_retry():
                delay = task.get_retry_delay()
                task.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                task.status = MoodleSyncStatus.PENDING
                task.last_error = error_msg

                logger.warning(
                    f"Задача {task.id} будет повторена через {delay} сек "
                    f"(попытка {task.attempts}/{task.max_attempts})"
                )
            else:
                task.status = MoodleSyncStatus.FAILED
                task.last_error = error_msg
                task.next_retry_at = None

                self._notify_admin(user, course, error_msg)
                self._log_activity(user, course, False, error_msg)

                logger.error(f"Задача {task.id} окончательно провалена после {task.attempts} попыток")

            self.db.commit()

    def _sync_user_to_moodle(self, user: User) -> int:
        """
        Синхронизация пользователя с Moodle.
        """
        logger.info(f"Синхронизация пользователя {user.email} с Moodle")

        try:
            moodle_user_id = self.moodle.sync_user(
                email=user.email,
                full_name=user.full_name
            )
            logger.info(f"Пользователь {user.email} синхронизирован, Moodle ID: {moodle_user_id}")
            return moodle_user_id
        except Exception as e:
            logger.error(f"Ошибка синхронизации пользователя {user.email}: {str(e)}")
            raise

    def _enroll_user_to_moodle(self, user: User, course: Course, moodle_user_id: int) -> bool:
        """
        Зачисление пользователя на курс в Moodle.
        """
        logger.info(f"Зачисление пользователя {user.email} на курс {course.id} (Moodle ID: {course.moodle_course_id})")

        try:
            is_enrolled = self.moodle.is_user_enrolled(moodle_user_id, course.moodle_course_id)

            if is_enrolled:
                logger.info(f"Пользователь {user.email} уже зачислен на курс {course.moodle_course_id}")
                return True

            result = self.moodle.enroll_user_to_course(
                user_id=moodle_user_id,
                course_id=course.moodle_course_id
            )

            if result:
                logger.info(f"Пользователь {user.email} успешно зачислен на курс {course.moodle_course_id}")
                return True
            else:
                raise Exception("Moodle API вернул ошибку при зачислении")

        except Exception as e:
            logger.error(f"Ошибка зачисления пользователя {user.email} на курс {course.moodle_course_id}: {str(e)}")
            raise

    def _notify_admin(self, user: User, course: Course, error: str):
        """
        Уведомление администратора об ошибке.
        """
        try:
            admin_email = getattr(settings, 'ADMIN_EMAIL', None)

            if not admin_email:
                logger.warning("ADMIN_EMAIL не задан в настройках, уведомление не отправлено")
                return

            logger.info(f"Отправка уведомления администратору {admin_email} об ошибке")

            subject = f"Ошибка синхронизации: {user.email} -> {course.title}"

            html_content = f"""
            <h2>Ошибка синхронизации с Moodle</h2>
            <p><strong>Пользователь:</strong> {user.full_name} ({user.email})</p>
            <p><strong>Курс:</strong> {course.title} (ID: {course.id})</p>
            <p><strong>Moodle курс ID:</strong> {course.moodle_course_id}</p>
            <p><strong>Ошибка:</strong> {error}</p>
            <p><strong>Время:</strong> {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')}</p>
            <hr>
            <p>Необходимо проверить соединение с Moodle и повторить синхронизацию вручную.</p>
            """

            email_service.send_email(
                to_email=admin_email,
                subject=subject,
                html_content=html_content
            )

            logger.info(f"Уведомление администратору отправлено")

        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору: {str(e)}")

    def _log_activity(self, user: User, course: Course, success: bool, error: str = None):
        """
        Логирование активности в системе.
        """
        try:
            extra_data = {
                "course_id": course.id,
                "course_title": course.title,
                "moodle_course_id": course.moodle_course_id,
                "success": success
            }

            if error:
                extra_data["error"] = error

            activity = UserActivityLog(
                user_id=user.id,
                action_type="moodle_sync" if success else "moodle_sync_failed",
                course_id=course.id,
                extra_data=json.dumps(extra_data)
            )

            self.db.add(activity)
            self.db.commit()

            logger.info(f"Активность залогирована для пользователя {user.id}")

        except Exception as e:
            logger.error(f"Ошибка логирования активности: {str(e)}")
            self.db.rollback()

    def get_task_status(self, user_id: int, course_id: int) -> Optional[dict]:
        """
        Получение статуса синхронизации для пользователя и курса.
        """
        task = self.db.query(MoodleSyncTask).filter(
            MoodleSyncTask.user_id == user_id,
            MoodleSyncTask.course_id == course_id
        ).order_by(
            MoodleSyncTask.created_at.desc()
        ).first()

        if not task:
            return None

        return {
            "id": task.id,
            "status": task.status.value,
            "attempts": task.attempts,
            "max_attempts": task.max_attempts,
            "last_error": task.last_error,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "processed_at": task.processed_at.isoformat() if task.processed_at else None,
            "next_retry_at": task.next_retry_at.isoformat() if task.next_retry_at else None,
            "moodle_user_id": task.moodle_user_id
        }

    def create_sync_task(self, user_id: int, course_id: int) -> MoodleSyncTask:
        """
        Создание задачи синхронизации.
        """
        existing_task = self.db.query(MoodleSyncTask).filter(
            MoodleSyncTask.user_id == user_id,
            MoodleSyncTask.course_id == course_id,
            MoodleSyncTask.status.in_([MoodleSyncStatus.PENDING, MoodleSyncStatus.PROCESSING])
        ).first()

        if existing_task:
            logger.info(f"Задача уже существует для пользователя {user_id} и курса {course_id}")
            return existing_task

        task = MoodleSyncTask(
            user_id=user_id,
            course_id=course_id,
            status=MoodleSyncStatus.PENDING,
            attempts=0,
            max_attempts=5
        )

        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        logger.info(f"Создана задача синхронизации {task.id} для пользователя {user_id} и курса {course_id}")

        return task