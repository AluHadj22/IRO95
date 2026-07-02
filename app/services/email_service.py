# app/services/email_service.py
import smtplib
import logging
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from typing import Optional
from app.config import settings

# Настройка логирования
logger = logging.getLogger(__name__)


class EmailService:
    """Сервис для отправки email через SMTP"""
    
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS
    
    def _get_smtp_connection(self):
        """Устанавливает соединение с SMTP сервером"""
        try:
            if self.port == 465:
                # SSL (для Яндекс)
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
            else:
                # STARTTLS (для Яндекс тоже работает)
                server = smtplib.SMTP(self.host, self.port, timeout=30)
                if self.use_tls:
                    server.starttls()
            
            server.login(self.username, self.password)
            return server
        except Exception as e:
            logger.error(f"SMTP connection error: {str(e)}")
            raise Exception(f"Не удалось подключиться к SMTP серверу: {str(e)}")
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Отправляет email через SMTP
        
        Args:
            to_email: Кому отправляем
            subject: Тема письма
            html_content: HTML содержимое письма
            text_content: Текстовое содержимое (если не указано, генерируется из HTML)
        
        Returns:
            bool: True если отправлено успешно
        """
        if not to_email:
            logger.warning("Email не указан, пропускаем отправку")
            return False
        
        try:
            # Создаем письмо
            msg = MIMEMultipart('alternative')
            msg['Subject'] = Header(subject, 'utf-8').encode()
            msg['From'] = f"{Header(self.from_name, 'utf-8').encode()} <{self.from_email}>"
            msg['To'] = to_email
            
            # Текстовая версия (если не указана, генерируем из HTML)
            if not text_content:
                text_content = re.sub(r'<[^>]+>', '', html_content)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Добавляем части письма
            part_text = MIMEText(text_content, 'plain', 'utf-8')
            part_html = MIMEText(html_content, 'html', 'utf-8')
            
            msg.attach(part_text)
            msg.attach(part_html)
            
            # Отправляем
            server = self._get_smtp_connection()
            server.sendmail(self.from_email, [to_email], msg.as_string())
            server.quit()
            
            logger.info(f"Email successfully sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_welcome_email(
        self,
        to_email: str,
        full_name: str,
        moodle_username: str,
        moodle_password: str,
        moodle_url: str,
        moodle_course_name: Optional[str] = None
    ) -> bool:
        """
        Отправляет приветственное письмо с данными для входа в Moodle
        
        Args:
            to_email: Email получателя
            full_name: Полное имя пользователя
            moodle_username: Логин в Moodle
            moodle_password: Пароль в Moodle
            moodle_url: URL Moodle
            moodle_course_name: Название курса (опционально)
        """
        subject = "Доступ к платформе повышения квалификации ИРО ЧР"
        
        # Формируем текст письма
        if moodle_course_name:
            course_text = f"""
            <p><strong>Курс:</strong> {moodle_course_name}</p>
            """
        else:
            course_text = ""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0057A4; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 20px; background: #f9f9f9; border-radius: 0 0 8px 8px; }}
                .credentials {{ background: #eef2f7; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .credentials table {{ width: 100%; }}
                .credentials td {{ padding: 8px; }}
                .credentials .label {{ font-weight: bold; color: #0057A4; }}
                .button {{ display: inline-block; background: #0057A4; color: white; padding: 12px 30px; 
                         text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 15px; }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #888; text-align: center; }}
                .warning {{ color: #d97706; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📚 ИРО ЧР</h1>
                    <p>Платформа повышения квалификации</p>
                </div>
                <div class="content">
                    <h2>Здравствуйте, {full_name}!</h2>
                    
                    <p>Вы успешно записаны на курс повышения квалификации в системе дистанционного обучения 
                    <strong>«Институт развития образования Чеченской Республики»</strong>.</p>
                    
                    {course_text}
                    
                    <p><strong>Для доступа к учебным материалам используйте следующие данные:</strong></p>
                    
                    <div class="credentials">
                        <table>
                            <tr>
                                <td class="label">🌐 Ссылка на систему:</td>
                                <td><a href="{moodle_url}">{moodle_url}</a></td>
                            </tr>
                            <tr>
                                <td class="label">👤 Логин:</td>
                                <td><strong>{moodle_username}</strong></td>
                            </tr>
                            <tr>
                                <td class="label">🔑 Пароль:</td>
                                <td><strong>{moodle_password}</strong></td>
                            </tr>
                        </table>
                    </div>
                    
                    <p class="warning">
                        ⚠️ <strong>Важно!</strong> Пароль сгенерирован автоматически. 
                        Рекомендуем сменить его после первого входа в системе.
                    </p>
                    
                    <div style="text-align: center;">
                        <a href="{moodle_url}" class="button">🔗 Перейти в Moodle</a>
                    </div>
                    
                    <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                    
                    <p style="font-size: 14px; color: #555;">
                        <strong>Что делать, если у вас возникли вопросы?</strong><br>
                        Вы можете обратиться в службу поддержки ИРО ЧР.
                    </p>
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} ИРО ЧР - Институт развития образования Чеченской Республики</p>
                    <p>Это письмо сгенерировано автоматически, пожалуйста, не отвечайте на него.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Текстовая версия
        text_content = f"""
        Здравствуйте, {full_name}!
        
        Вы успешно записаны на курс повышения квалификации в системе дистанционного обучения
        «Институт развития образования Чеченской Республики».
        
        {f'Курс: {moodle_course_name}' if moodle_course_name else ''}
        
        Для доступа к учебным материалам используйте следующие данные:
        
        Ссылка на систему: {moodle_url}
        Логин: {moodle_username}
        Пароль: {moodle_password}
        
        ⚠️ Важно! Пароль сгенерирован автоматически.
        Рекомендуем сменить его после первого входа в системе.
        
        Что делать, если у вас возникли вопросы?
        Вы можете обратиться в службу поддержки ИРО ЧР.
        
        © {datetime.now().year} ИРО ЧР - Институт развития образования Чеченской Республики
        """
        
        return self.send_email(to_email, subject, html_content, text_content)
    
    def send_admin_notification(
        self,
        admin_email: str,
        user_name: str,
        user_email: str,
        moodle_course_name: str
    ) -> bool:
        """
        Отправляет уведомление администратору о новом пользователе
        
        Args:
            admin_email: Email администратора
            user_name: Имя пользователя
            user_email: Email пользователя
            moodle_course_name: Название курса
        """
        subject = f"🔔 Новый участник курса: {moodle_course_name}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
        </head>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #0057A4;">🆕 Новый участник зарегистрирован</h2>
            
            <p><strong>Курс:</strong> {moodle_course_name}</p>
            
            <div style="background: #eef2f7; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <table>
                    <tr><td><strong>ФИО:</strong></td><td>{user_name}</td></tr>
                    <tr><td><strong>Email:</strong></td><td>{user_email}</td></tr>
                </table>
            </div>
            
            <p>Пользователь успешно зарегистрирован на курс и имеет доступ к Moodle.</p>
            
            <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
            <p style="color: #888; font-size: 12px;">© {datetime.now().year} ИРО ЧР</p>
        </body>
        </html>
        """
        
        text_content = f"""
        Новый участник зарегистрирован
        
        Курс: {moodle_course_name}
        ФИО: {user_name}
        Email: {user_email}
        
        Пользователь успешно зарегистрирован на курс и имеет доступ к Moodle.
        
        © {datetime.now().year} ИРО ЧР
        """
        
        return self.send_email(admin_email, subject, html_content, text_content)


# Создаем глобальный экземпляр сервиса
email_service = EmailService()


def send_welcome_email(
    email: str,
    full_name: str,
    moodle_username: str,
    moodle_password: str,
    moodle_course_name: Optional[str] = None
) -> bool:
    """
    Упрощенная функция для отправки приветственного письма
    
    Используется в других модулях как shortcut.
    """
    return email_service.send_welcome_email(
        to_email=email,
        full_name=full_name,
        moodle_username=moodle_username,
        moodle_password=moodle_password,
        moodle_url=settings.MOODLE_URL,
        moodle_course_name=moodle_course_name
    )