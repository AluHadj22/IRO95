# app/scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from sqlalchemy import create_engine
from app.config import settings
from app.database import SessionLocal
from app.services.moodle_sync_service import MoodleSyncService

logger = logging.getLogger(__name__)

scheduler = None
_job_id = "moodle_sync_job"


def get_scheduler():
    """
    Создает и настраивает экземпляр планировщика.
    """
    global scheduler

    if scheduler is not None:
        return scheduler

    logger.info("Инициализация планировщика APScheduler")

    engine = create_engine(settings.DATABASE_URL)

    jobstores = {
        'default': SQLAlchemyJobStore(engine=engine, tablename='apscheduler_jobs')
    }

    executors = {
        'default': ThreadPoolExecutor(max_workers=5)
    }

    job_defaults = {
        'coalesce': True,
        'max_instances': 1,
        'misfire_grace_time': 10
    }

    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone='UTC'
    )

    scheduler.add_listener(
        _job_listener,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
    )

    logger.info("Планировщик APScheduler настроен")

    return scheduler


def _job_listener(event):
    """
    Слушатель событий планировщика.
    """
    if event.exception:
        logger.error(f"Ошибка выполнения задачи {event.job_id}: {event.exception}")
    else:
        logger.debug(f"Задача {event.job_id} выполнена успешно")


def _process_queue():
    """
    Задача, которая выполняется по расписанию.
    Обрабатывает очередь синхронизации.
    """
    db = None
    try:
        logger.debug("Запуск обработки очереди синхронизации")

        db = SessionLocal()
        service = MoodleSyncService(db)
        processed = service.process_queue()

        if processed > 0:
            logger.info(f"Обработано {processed} задач синхронизации")

    except Exception as e:
        logger.error(f"Ошибка при обработке очереди: {str(e)}")
    finally:
        if db:
            db.close()


def start_scheduler():
    """
    Запуск планировщика.
    """
    global scheduler

    if scheduler is None:
        scheduler = get_scheduler()

    if scheduler.running:
        logger.warning("Планировщик уже запущен")
        return

    try:
        existing_job = scheduler.get_job(_job_id)
        if existing_job:
            scheduler.remove_job(_job_id)
            logger.info(f"Существующая задача {_job_id} удалена")

        scheduler.add_job(
            _process_queue,
            trigger=IntervalTrigger(seconds=3),
            id=_job_id,
            replace_existing=True,
            name="Синхронизация с Moodle"
        )

        scheduler.start()
        logger.info("Планировщик APScheduler запущен (интервал: 3 секунды)")

    except Exception as e:
        logger.error(f"Ошибка запуска планировщика: {str(e)}")
        raise


def stop_scheduler():
    """
    Остановка планировщика.
    """
    global scheduler

    if scheduler is None:
        logger.warning("Планировщик не инициализирован")
        return

    if not scheduler.running:
        logger.warning("Планировщик уже остановлен")
        return

    try:
        scheduler.shutdown(wait=True)
        logger.info("Планировщик APScheduler остановлен")

    except Exception as e:
        logger.error(f"Ошибка остановки планировщика: {str(e)}")
        raise


def is_scheduler_running() -> bool:
    """
    Проверяет, запущен ли планировщик.
    """
    if scheduler is None:
        return False
    return scheduler.running


def get_scheduler_status() -> dict:
    """
    Возвращает статус планировщика.
    """
    if scheduler is None:
        return {"running": False, "initialized": False}

    return {
        "running": scheduler.running,
        "initialized": True,
        "pending_jobs": len(scheduler.get_jobs()) if scheduler.running else 0,
        "job_ids": [job.id for job in scheduler.get_jobs()] if scheduler.running else []
    }