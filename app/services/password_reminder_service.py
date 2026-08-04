# app/services/password_reminder_service.py

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app import models
from app.services.moodle_service import MoodleService
from app.services.email_service import email_service
from app.config import settings

logger = logging.getLogger(__name__)


class PasswordReminderService:
    """
    Сервис для отправки напоминаний о паролях пользователям,
    у которых уже был аккаунт в Moodle до регистрации на платформе.
    """
    
    DEFAULT_PASSWORD = "Password1!"
    
    def __init__(self, db: Session):
        self.db = db
        self.moodle = MoodleService()
    
    def get_users_with_existing_moodle_account(self) -> List[models.User]:
        """
        Получает пользователей, у которых был аккаунт в Moodle до регистрации
        и которым еще не отправляли пароль.
        """
        users = self.db.query(models.User).filter(
            and_(
                models.User.moodle_account_existed_before == True,
                models.User.moodle_password_sent == False,
                models.User.is_blocked == False,
                models.User.is_active == True
            )
        ).all()
        
        return users
    
    def get_all_moodle_users_with_pagination(
        self, 
        page: int = 1, 
        per_page: int = 20,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получает список ВСЕХ пользователей, у которых есть аккаунт в Moodle
        (независимо от того, отправлен ли им пароль), с пагинацией.
        
        Args:
            page: Номер страницы (начиная с 1)
            per_page: Количество записей на странице
            search: Поиск по email или ФИО
        
        Returns:
            dict: {
                "total": общее количество,
                "page": текущая страница,
                "per_page": записей на странице,
                "total_pages": всего страниц,
                "users": список пользователей с дополнительной информацией
            }
        """
        # Базовый запрос - все пользователи с аккаунтом в Moodle
        query = self.db.query(models.User).filter(
            and_(
                models.User.moodle_account_existed_before == True,
                models.User.is_blocked == False,
                models.User.is_active == True
            )
        )
        
        # Поиск по email или ФИО
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    models.User.email.ilike(search_term),
                    models.User.full_name.ilike(search_term),
                    models.User.last_name.ilike(search_term),
                    models.User.first_name.ilike(search_term)
                )
            )
        
        # Общее количество
        total = query.count()
        
        # Пагинация
        offset = (page - 1) * per_page
        users = query.order_by(models.User.id).offset(offset).limit(per_page).all()
        
        # Формируем результат с дополнительной информацией
        result_users = []
        for user in users:
            # Получаем username из Moodle
            moodle_user = self.moodle.get_user_by_email(user.email)
            username = moodle_user.get('username', user.email.split('@')[0]) if moodle_user else user.email.split('@')[0]
            
            result_users.append({
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "username": username,
                "password_sent": user.moodle_password_sent,
                "registered_at": user.created_at.isoformat() if user.created_at else None
            })
        
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "users": result_users
        }
    
    def _update_moodle_password(self, user: models.User) -> bool:
        """
        Обновляет пароль пользователя в Moodle на DEFAULT_PASSWORD.
        
        Args:
            user: Объект пользователя
        
        Returns:
            bool: True если пароль обновлен успешно
        """
        print(f"\n{'='*60}")
        print(f"🔐 _update_moodle_password: Начало для {user.email}")
        print(f"{'='*60}")
        
        try:
            logger.info(f"🔐 Начинаем обновление пароля для {user.email}")
            
            # Получаем пользователя из Moodle
            print(f"📡 1. Вызов moodle.get_user_by_email('{user.email}')...")
            moodle_user = self.moodle.get_user_by_email(user.email)
            
            if not moodle_user:
                print(f"❌ 2. Пользователь {user.email} НЕ НАЙДЕН в Moodle")
                logger.error(f"❌ Пользователь {user.email} не найден в Moodle")
                return False
            
            moodle_user_id = moodle_user.get('id')
            username = moodle_user.get('username')
            
            print(f"✅ 2. Найден пользователь в Moodle:")
            print(f"   - ID: {moodle_user_id}")
            print(f"   - username: {username}")
            logger.info(f"✅ Найден пользователь в Moodle: ID={moodle_user_id}, username={username}")
            
            if not moodle_user_id:
                print(f"❌ 3. Не удалось получить ID пользователя {user.email} в Moodle")
                logger.error(f"❌ Не удалось получить ID пользователя {user.email} в Moodle")
                return False
            
            # Обновляем пароль через Moodle API
            print(f"🔄 3. Вызов moodle._call_api('core_user_update_users')...")
            print(f"   - user_id: {moodle_user_id}")
            print(f"   - new_password: {self.DEFAULT_PASSWORD}")
            logger.info(f"🔄 Отправляем запрос на обновление пароля для user_id={moodle_user_id}")
            
            result = self.moodle._call_api('core_user_update_users', {
                'users[0][id]': moodle_user_id,
                'users[0][password]': self.DEFAULT_PASSWORD
            })
            
            print(f"✅ 4. API вернул результат: {result}")
            print(f"✅ Пароль для пользователя {user.email} (ID: {moodle_user_id}) обновлен на {self.DEFAULT_PASSWORD}")
            print(f"{'='*60}\n")
            
            logger.info(f"✅ API вернул результат: {result}")
            logger.info(f"✅ Пароль для пользователя {user.email} (ID: {moodle_user_id}) обновлен на {self.DEFAULT_PASSWORD}")
            return True
            
        except Exception as e:
            print(f"❌ ОШИБКА в _update_moodle_password: {str(e)}")
            logger.error(f"❌ Ошибка при обновлении пароля для {user.email}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            logger.error(traceback.format_exc())
            print(f"{'='*60}\n")
            return False
    
    def send_password_reminder(self, user: models.User) -> bool:
        """
        Обновляет пароль пользователя в Moodle и отправляет письмо с логином и паролем.
        
        Returns:
            bool: True если пароль обновлен и письмо отправлено успешно
        """
        print(f"\n{'='*60}")
        print(f"📧 send_password_reminder: Начало для {user.email} (ID: {user.id})")
        print(f"{'='*60}")
        
        try:
            logger.info(f"📧 Начинаем отправку напоминания для {user.email}")
            
            # 1. Проверяем, существует ли пользователь в Moodle
            print(f"📡 1. Проверка существования пользователя в Moodle...")
            moodle_user = self.moodle.get_user_by_email(user.email)
            
            if not moodle_user:
                print(f"❌ Пользователь {user.email} не найден в Moodle")
                logger.warning(f"❌ Пользователь {user.email} не найден в Moodle")
                return False
            
            moodle_user_id = moodle_user.get('id')
            username = moodle_user.get('username', user.email.split('@')[0])
            
            print(f"✅ Найден пользователь в Moodle:")
            print(f"   - ID: {moodle_user_id}")
            print(f"   - username: {username}")
            logger.info(f"👤 Пользователь в Moodle: ID={moodle_user_id}, username={username}")
            
            if not moodle_user_id:
                print(f"❌ Не удалось получить ID пользователя {user.email} в Moodle")
                logger.warning(f"❌ Не удалось получить ID пользователя {user.email} в Moodle")
                return False
            
            # 2. Обновляем пароль в Moodle
            print(f"\n🔄 Шаг 2: Обновление пароля в Moodle...")
            password_updated = self._update_moodle_password(user)
            
            if not password_updated:
                print(f"❌ Шаг 2: НЕ УДАЛОСЬ обновить пароль для {user.email}")
                logger.error(f"❌ Не удалось обновить пароль для {user.email}")
                return False
            
            print(f"✅ Шаг 2: Пароль обновлен успешно!")
            logger.info(f"✅ Шаг 1 завершен: Пароль обновлен")
            
            # 3. Отправляем письмо
            print(f"\n📧 Шаг 3: Отправка письма на {user.email}...")
            logger.info(f"📧 Шаг 2: Отправка письма на {user.email}...")
            
            subject = "Ваши данные для входа в Moodle"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: 'Inter', sans-serif; color: #1a1a2e; line-height: 1.6; background: #f8fafc; margin: 0; padding: 0; }}
                    .email-wrapper {{ max-width: 560px; margin: 0 auto; padding: 20px; }}
                    .email-container {{ background: #ffffff; border-radius: 16px; overflow: hidden; border: 1px solid #e2e8f0; }}
                    .header {{ background: linear-gradient(135deg, #0a0a18 0%, #1a1a2e 100%); padding: 24px 28px; text-align: center; border-bottom: 3px solid rgba(201, 161, 59, 0.3); }}
                    .header h2 {{ color: #ffffff; margin: 0; font-weight: 700; font-size: 1.2rem; }}
                    .header .gold {{ color: #c9a13b; }}
                    .header .logo-img {{ height: 48px; margin-bottom: 12px; }}
                    .body {{ padding: 28px 32px; }}
                    .greeting {{ font-size: 1.2rem; font-weight: 700; color: #1a1a2e; margin-bottom: 4px; }}
                    .greeting-sub {{ color: #64748b; font-size: 0.95rem; margin-bottom: 16px; }}
                    .alert-box {{ background: rgba(245, 158, 11, 0.06); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; margin: 12px 0 16px; font-size: 0.85rem; color: #92400e; }}
                    .credentials-card {{ background: #f8fafc; border-radius: 12px; padding: 16px 20px; border: 1px solid #e2e8f0; margin: 12px 0; }}
                    .credentials-card table {{ width: 100%; border-collapse: collapse; }}
                    .credentials-card td {{ padding: 8px; font-size: 0.9rem; }}
                    .credentials-card .label {{ font-weight: 600; color: #1a1a2e; width: 80px; }}
                    .credentials-card .label i {{ color: #c9a13b; margin-right: 6px; }}
                    .password-box {{ background: #ffffff; padding: 2px 12px; border-radius: 6px; border: 1px dashed #c9a13b; font-family: monospace; letter-spacing: 0.5px; display: inline-block; }}
                    .btn-wrapper {{ text-align: center; margin: 24px 0 16px; }}
                    .btn-primary {{ display: inline-block; background: linear-gradient(135deg, #c9a13b 0%, #b8860b 100%); color: #ffffff !important; padding: 12px 36px; border-radius: 10px; text-decoration: none; font-weight: 600; font-size: 0.95rem; box-shadow: 0 4px 16px rgba(201, 161, 59, 0.25); }}
                    .btn-primary:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(201, 161, 59, 0.35); color: #ffffff !important; }}
                    .footer {{ padding: 16px 28px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 0.7rem; color: #94a3b8; }}
                    .footer .gold-text {{ color: #c9a13b; }}
                    .warning-text {{ font-size: 0.8rem; color: #94a3b8; text-align: center; margin-top: 8px; }}
                    @media (max-width: 480px) {{ .body {{ padding: 20px 16px; }} .btn-primary {{ display: block; width: 100%; text-align: center; }} }}
                </style>
            </head>
            <body>
                <div class="email-wrapper">
                    <div class="email-container">
                        <div class="header">
                            <img src="https://govzalla.ru/wp-content/uploads/2023/05/logo-min-1.png" alt="ИРО ЧР" class="logo-img">
                            <h2>ГБУ ДПО <span class="gold">«ИРО ЧР»</span></h2>
                        </div>
                        
                        <div class="body">
                            <div class="greeting">Здравствуйте, {user.full_name}!</div>
                            <div class="greeting-sub">Ваши данные для входа в систему Moodle.</div>
                            
                            <div class="alert-box">
                                <strong>🔑 Важно!</strong> Ваш пароль был установлен по умолчанию: <strong>Password1!</strong>
                                <br>Рекомендуем сменить его после первого входа.
                            </div>
                            
                            <div class="credentials-card">
                                <table>
                                    <tr>
                                        <td class="label"><i>🌐</i> Ссылка:</td>
                                        <td><a href="{settings.MOODLE_URL}" target="_blank" style="color: #c9a13b; text-decoration: none;">{settings.MOODLE_URL}</a></td>
                                    </tr>
                                    <tr>
                                        <td class="label"><i>👤</i> Логин:</td>
                                        <td><strong>{username}</strong></td>
                                    </tr>
                                    <tr>
                                        <td class="label"><i>🔑</i> Пароль:</td>
                                        <td><span class="password-box">Password1!</span></td>
                                    </tr>
                                </table>
                            </div>
                            
                            <div class="btn-wrapper">
                                <a href="{settings.MOODLE_URL}" class="btn-primary" target="_blank">
                                    🚀 Перейти в Moodle
                                </a>
                            </div>
                            
                            <div class="warning-text">
                                <i>💡</i> Если вы не можете войти, обратитесь в поддержку: ipkro-chr@mail.ru
                            </div>
                        </div>
                        
                        <div class="footer">
                            © 2026 <span class="gold-text">ИРО ЧР</span> — Институт развития образования Чеченской Республики
                            <br><span style="font-size: 0.65rem; opacity: 0.6;">Это письмо сгенерировано автоматически, пожалуйста, не отвечайте на него.</span>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""
            ========================================
            ГБУ ДПО «ИРО ЧР» - Институт развития образования Чеченской Республики
            ========================================
            
            Здравствуйте, {user.full_name}!
            
            Ваши данные для входа в систему Moodle:
            
            Ссылка: {settings.MOODLE_URL}
            Логин: {username}
            Пароль: Password1!
            
            ⚠️ ВАЖНО! Пароль установлен по умолчанию.
            Рекомендуем сменить его после первого входа.
            
            ========================================
            © 2026 ИРО ЧР - Институт развития образования Чеченской Республики
            """
            
            success = email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            if success:
                user.moodle_password_sent = True
                self.db.commit()
                print(f"✅ Шаг 3: Письмо УСПЕШНО отправлено на {user.email}")
                print(f"✅ Полный цикл для {user.email} завершен успешно!")
                print(f"{'='*60}\n")
                logger.info(f"✅ Письмо успешно отправлено пользователю {user.email}")
                logger.info(f"✅ Полный цикл для {user.email} завершен успешно!")
                return True
            else:
                print(f"❌ Шаг 3: НЕ УДАЛОСЬ отправить письмо на {user.email}")
                print(f"{'='*60}\n")
                logger.error(f"❌ Не удалось отправить письмо пользователю {user.email}")
                return False
                
        except Exception as e:
            print(f"❌ ОШИБКА в send_password_reminder: {str(e)}")
            logger.error(f"❌ Ошибка при отправке письма пользователю {user.email}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            logger.error(traceback.format_exc())
            print(f"{'='*60}\n")
            return False
    
    def send_password_reminders_to_all(self) -> Dict[str, Any]:
        """
        Отправляет напоминания о паролях всем пользователям,
        у которых был аккаунт в Moodle до регистрации.
        
        Returns:
            dict: Результат операции
        """
        print(f"\n{'='*60}")
        print(f"🚀 send_password_reminders_to_all: ЗАПУСК")
        print(f"{'='*60}")
        
        logger.info("🚀 Запуск массовой отправки напоминаний о паролях")
        
        users = self.get_users_with_existing_moodle_account()
        
        if not users:
            print(f"ℹ️ Нет пользователей, которым нужно отправить пароль")
            logger.info("ℹ️ Нет пользователей, которым нужно отправить пароль")
            return {
                "success": True,
                "total": 0,
                "sent": 0,
                "failed": 0,
                "message": "Нет пользователей, которым нужно отправить пароль"
            }
        
        print(f"📊 Найдено {len(users)} пользователей для отправки")
        logger.info(f"📊 Найдено {len(users)} пользователей для отправки")
        
        sent = 0
        failed = 0
        
        for user in users:
            print(f"\n--- Обработка пользователя {user.email} ({user.id}) ---")
            logger.info(f"--- Обработка пользователя {user.email} ({user.id}) ---")
            if self.send_password_reminder(user):
                sent += 1
            else:
                failed += 1
        
        result_message = f"Отправлено {sent} писем, ошибок: {failed}"
        print(f"\n✅ Массовая отправка завершена: {result_message}")
        print(f"{'='*60}\n")
        logger.info(f"✅ Массовая отправка завершена: {result_message}")
        
        return {
            "success": True,
            "total": len(users),
            "sent": sent,
            "failed": failed,
            "message": result_message
        }
    
    def send_password_reminders_to_selected(self, user_ids: List[int]) -> Dict[str, Any]:
        """
        Отправляет напоминания о паролях выбранным пользователям.
        
        Args:
            user_ids: Список ID пользователей
        
        Returns:
            dict: Результат операции
        """
        print(f"\n{'='*60}")
        print(f"🚀 send_password_reminders_to_selected: ЗАПУСК")
        print(f"📋 user_ids: {user_ids}")
        print(f"{'='*60}")
        
        logger.info(f"🚀 Запуск выборочной отправки напоминаний для {len(user_ids)} пользователей")
        
        if not user_ids:
            print(f"⚠️ Не выбрано ни одного пользователя")
            logger.warning("⚠️ Не выбрано ни одного пользователя")
            return {
                "success": False,
                "total": 0,
                "sent": 0,
                "failed": 0,
                "message": "Не выбрано ни одного пользователя"
            }
        
        print(f"📡 Запрос к БД для пользователей с ID: {user_ids}")
        users = self.db.query(models.User).filter(
            and_(
                models.User.id.in_(user_ids),
                models.User.moodle_account_existed_before == True,
                models.User.is_blocked == False,
                models.User.is_active == True
            )
        ).all()
        
        print(f"👤 Найдено в БД: {len(users)} пользователей")
        
        if not users:
            print(f"⚠️ Выбранные пользователи не найдены или не имеют аккаунта в Moodle")
            logger.warning("⚠️ Выбранные пользователи не найдены или не имеют аккаунта в Moodle")
            return {
                "success": False,
                "total": 0,
                "sent": 0,
                "failed": 0,
                "message": "Выбранные пользователи не найдены или не имеют аккаунта в Moodle"
            }
        
        logger.info(f"📊 Найдено {len(users)} пользователей для отправки (из {len(user_ids)} запрошенных)")
        
        sent = 0
        failed = 0
        failed_users = []
        
        for user in users:
            print(f"\n--- Обработка пользователя {user.email} (ID: {user.id}) ---")
            logger.info(f"--- Обработка пользователя {user.email} ({user.id}) ---")
            if self.send_password_reminder(user):
                sent += 1
            else:
                failed += 1
                failed_users.append(user.email)
        
        result_message = f"Отправлено {sent} писем, ошибок: {failed}"
        if failed_users:
            result_message += f". Не удалось отправить: {', '.join(failed_users)}"
        
        print(f"\n✅ Выборочная отправка завершена: {result_message}")
        print(f"{'='*60}\n")
        logger.info(f"✅ Выборочная отправка завершена: {result_message}")
        
        return {
            "success": True,
            "total": len(users),
            "sent": sent,
            "failed": failed,
            "failed_users": failed_users,
            "message": result_message
        }