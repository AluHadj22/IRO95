# app/services/ai_context_service.py
from sqlalchemy.orm import Session
from app import models
from typing import List, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AIContextService:
    """
    Сервис для подготовки контекстной информации об ИРО ЧР для ИИ-ассистента.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def _get_static_info(self) -> str:
        """
        Возвращает статическую информацию об институте и платформе.
        """
        return """
        ИНФОРМАЦИЯ ОБ ИНСТИТУТЕ:
        Полное наименование: Государственное бюджетное учреждение дополнительного профессионального образования «Институт развития образования Чеченской Республики»
        Сокращённое наименование: ГБУ ДПО «ИРО ЧР»
        Учредитель: Министерство образования и науки Чеченской Республики (Министр — Дааев Хож-Бауди Буарович)

        РУКОВОДСТВО:
        • Ректор: Эльмурзаева Ганга Бекхановна
        • Проректор по научно-методической работе: Ялакаева Индира Анатольевна
        • Проректор по инновационной и проектной деятельности: Болатбиева Анжелика Наврадиевна

        ОСНОВНЫЕ НАПРАВЛЕНИЯ ДЕЯТЕЛЬНОСТИ:
        • Реализация дополнительных профессиональных программ повышения квалификации
        • Реализация дополнительных профессиональных программ профессиональной переподготовки
        • Научно-исследовательская и научно-методическая работа
        • Научно-методическое сопровождение региональных инновационных площадок

        ФОРМЫ ОБУЧЕНИЯ:
        • Очно-заочная форма с применением электронного обучения и дистанционных технологий
        • Обучение на русском языке

        КОНТАКТЫ ИНСТИТУТА:
        • Официальный сайт: https://govzalla.ru/
        • Система дистанционного обучения (Moodle): https://iro-lms.ru/
        • Email: ipkro-chr@mail.ru
        • Телефон: 8 (8712) 21-22-24
        • Адрес: г. Грозный, ул. Лермонтова, 2
        • Режим работы: Пн-пт 9:00-18:00 (педагогический персонал: 9:00-17:00), обед 13:00-14:00, Сб-вс выходной

        КОНТАКТЫ УЧРЕДИТЕЛЯ (Минобрнауки ЧР):
        • Адрес: г. Грозный, ул. им. М.Д. Миллионщикова, 67 "а"
        • Телефон: +7 (8712) 22-27-42
        • Email: moin.chr@mail.ru
        • Сайт: mon95.ru

        КАК НАЙТИ КУРС НА ПЛАТФОРМЕ:
        1. Перейдите в раздел «Курсы» в верхней навигационной панели
        2. Используйте поиск по названию или ключевым словам
        3. Отфильтруйте курсы по категории
        4. Нажмите на карточку курса для просмотра программы и записи

        КАК НАЧАТЬ ОБУЧЕНИЕ ПОСЛЕ ЗАПИСИ:
        1. Перейдите в раздел «Кабинет» в верхней навигационной панели
        2. В личном кабинете откройте вкладку «Мои курсы»
        3. Найдите запись о курсе и нажмите «Перейти в Moodle»
        4. Войдите в Moodle с данными, отправленными на вашу электронную почту
        5. После входа вы попадёте на страницу курса

        ПОЧЕМУ НЕЛЬЗЯ ЗАПИСАТЬСЯ НА КУРС (ТОЛЬКО ЭТИ ПРИЧИНЫ):
        • Наиболее частая причина - НЕЗАПОЛНЕННЫЙ ПРОФИЛЬ
        • Перед записью необходимо заполнить раздел «Мои данные» в личном кабинете
        • Укажите: Фамилию, Имя, Отчество, Пол, Дату рождения, Гражданство, Субъект РФ, Муниципалитет, Телефон
        • Также необходимо заполнить: Образование (с загрузкой диплома), Место работы, СНИЛС (с загрузкой), Паспорт (с загрузкой), ИНН (с загрузкой)
        • После заполнения всех данных и подтверждения - попробуйте записаться снова
        • Других причин для отказа в записи нет - все курсы бесплатные
        • Если профиль полностью заполнен, но запись не проходит - обратитесь в поддержку

        КАК ОТОЗВАТЬ СОГЛАСИЕ НА ОБРАБОТКУ ДАННЫХ:
        • Направьте письменное заявление на email: ipkro-chr@mail.ru
        • Укажите ФИО и контактные данные для идентификации
        • Сотрудники рассмотрят обращение в установленном порядке

        ВАЖНО О ПЛАТФОРМЕ:
        • Платформа записи НЕ является местом проведения обучения
        • Обучение проходит в системе дистанционного обучения (Moodle) по ссылке: https://iro-lms.ru/
        • После записи на курс вы автоматически получаете доступ к Moodle
        • Все курсы на платформе БЕСПЛАТНЫЕ, никаких платежей не требуется
        """
    
    def get_courses_context(self, limit: int = 5) -> str:
        """
        Получает информацию о курсах для контекста.
        """
        try:
            courses = self.db.query(
                models.Course.id,
                models.Course.title,
                models.Course.short_description,
                models.Course.description,
                models.Course.format_type,
                models.Course.start_date,
                models.Course.end_date,
                models.Course.current_participants,
                models.Course.max_participants,
                models.Course.is_active,
                models.Course.category_id,
                models.Course.moodle_course_id
            ).filter(
                models.Course.is_active == True
            ).order_by(
                models.Course.created_at.desc()
            ).limit(limit).all()
            
            if not courses:
                return "Активных курсов нет."
            
            result = []
            for course in courses:
                category_name = "Без категории"
                if course.category_id:
                    try:
                        category = self.db.query(models.Category.name).filter(
                            models.Category.id == course.category_id,
                            models.Category.is_active == True
                        ).first()
                        if category:
                            category_name = category[0]
                    except:
                        pass
                
                speakers = self.db.query(
                    models.CourseSpeaker.full_name
                ).filter(
                    models.CourseSpeaker.course_id == course.id
                ).limit(3).all()
                
                speakers_text = ""
                if speakers:
                    speaker_names = [s[0] for s in speakers]
                    speakers_text = f" (преподает: {', '.join(speaker_names)})"
                
                start_date = course.start_date.strftime("%d.%m.%Y") if course.start_date else "скоро"
                end_date = course.end_date.strftime("%d.%m.%Y") if course.end_date else "по набору"
                
                description = course.short_description or course.description or "Нет описания"
                if len(description) > 80:
                    description = description[:80] + "..."
                
                places_status = ""
                if course.current_participants >= course.max_participants:
                    places_status = " (мест нет)"
                elif course.max_participants - course.current_participants <= 3:
                    places_status = f" (осталось {course.max_participants - course.current_participants} мест)"
                
                result.append(
                    f"• {course.title}{speakers_text}\n"
                    f"  {description}\n"
                    f"  {course.format_type or 'онлайн'}, {start_date} - {end_date}, {course.current_participants}/{course.max_participants}{places_status}"
                )
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Error getting courses context: {str(e)}")
            return "Информация о курсах временно недоступна."
    
    def get_teachers_context(self, limit: int = 5) -> str:
        """Получает информацию о преподавателях/спикерах."""
        try:
            speakers = self.db.query(
                models.CourseSpeaker.full_name,
                models.CourseSpeaker.position,
                models.CourseSpeaker.course_id
            ).join(
                models.Course
            ).filter(
                models.Course.is_active == True
            ).limit(limit * 2).all()
            
            if not speakers:
                return "На данный момент на платформе нет назначенных преподавателей."
            
            speaker_dict = {}
            for s in speakers:
                if s.full_name not in speaker_dict:
                    speaker_dict[s.full_name] = {
                        'name': s.full_name,
                        'position': s.position or 'Преподаватель',
                        'courses': []
                    }
                if s.course_id:
                    try:
                        course_title = self.db.query(models.Course.title).filter(
                            models.Course.id == s.course_id
                        ).first()
                        if course_title and course_title[0] not in speaker_dict[s.full_name]['courses']:
                            speaker_dict[s.full_name]['courses'].append(course_title[0][:40])
                    except:
                        pass
            
            result = []
            for name, data in list(speaker_dict.items())[:limit]:
                courses_text = ", ".join(data['courses'][:3])
                result.append(f"• {name} - {data['position']} (преподает: {courses_text})")
            
            return "\n".join(result) if result else "На данный момент на платформе нет назначенных преподавателей."
            
        except Exception as e:
            logger.error(f"Error getting teachers context: {str(e)}")
            return "Информация о преподавателях временно недоступна."
    
    def get_full_context(self) -> str:
        """
        Получает полный контекст для ИИ (статика + курсы + преподаватели).
        """
        try:
            context_parts = []
            
            # Статическая информация об институте и платформе
            context_parts.append("=== ИНФОРМАЦИЯ ОБ ИРО ЧР И ПЛАТФОРМЕ ===")
            context_parts.append(self._get_static_info())
            
            # Получаем курсы
            courses = self.get_courses_context(limit=5)
            if courses and "Активных курсов нет" not in courses:
                context_parts.append("\n=== ТЕКУЩИЕ КУРСЫ ===")
                context_parts.append(courses)
            
            # Получаем преподавателей
            teachers = self.get_teachers_context(limit=5)
            if teachers and "нет назначенных преподавателей" not in teachers:
                context_parts.append("\n=== ПРЕПОДАВАТЕЛИ ===")
                context_parts.append(teachers)
            
            # Если нет курсов
            if courses and "Активных курсов нет" in courses:
                context_parts.append("\nНа данный момент активных курсов нет. Следите за обновлениями на платформе.")
            
            full_context = "\n".join(context_parts)
            logger.info(f"Full context generated, length: {len(full_context)}")
            
            # Обрезаем если слишком длинный
            if len(full_context) > 4000:
                full_context = full_context[:4000] + "..."
            
            return full_context
            
        except Exception as e:
            logger.error(f"Error getting full context: {str(e)}")
            return "Информация о платформе временно недоступна. Пожалуйста, обратитесь в поддержку."