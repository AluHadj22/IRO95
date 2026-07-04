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
            <div style="background: rgba(201, 161, 59, 0.08); padding: 12px 16px; border-radius: 10px; border-left: 4px solid #c9a13b; margin: 12px 0;">
                <span style="font-weight: 600; color: #1a1a2e;">📖 Курс:</span>
                <span style="color: #64748b;">{moodle_course_name}</span>
            </div>
            """
        else:
            course_text = ""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                /* ===== ОСНОВНЫЕ СТИЛИ ===== */
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    color: #1a1a2e;
                    line-height: 1.6;
                    background: #f8fafc;
                    margin: 0;
                    padding: 0;
                }}
                
                .email-wrapper {{
                    max-width: 620px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #f8fafc;
                }}
                
                .email-container {{
                    background: #ffffff;
                    border-radius: 20px;
                    overflow: hidden;
                    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
                    border: 1px solid #e2e8f0;
                }}
                
                /* ===== ШАПКА ===== */
                .email-header {{
                    background: linear-gradient(135deg, #0a0a18 0%, #1a1a2e 60%, #0f0f1a 100%);
                    padding: 32px 36px 28px;
                    text-align: center;
                    border-bottom: 3px solid rgba(201, 161, 59, 0.3);
                    position: relative;
                }}
                
                .email-header::after {{
                    content: '';
                    position: absolute;
                    bottom: -1px;
                    left: 0;
                    right: 0;
                    height: 3px;
                    background: linear-gradient(90deg, transparent, #c9a13b, #b8860b, #c9a13b, transparent);
                }}
                
                .email-header .logo {{
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 14px;
                    margin-bottom: 8px;
                }}
                
                .email-header .logo img {{
                    height: 52px;
                    width: auto;
                    border-radius: 12px;
                    box-shadow: 0 2px 12px rgba(201, 161, 59, 0.2);
                }}
                
                .email-header .logo-text {{
                    display: flex;
                    flex-direction: column;
                    text-align: left;
                }}
                
                .email-header .logo-text .title {{
                    font-size: 1.2rem;
                    font-weight: 800;
                    color: #ffffff;
                    letter-spacing: -0.3px;
                }}
                
                .email-header .logo-text .title .gold {{
                    color: #c9a13b;
                }}
                
                .email-header .logo-text .subtitle {{
                    font-size: 0.65rem;
                    color: rgba(255, 255, 255, 0.5);
                    font-weight: 400;
                    letter-spacing: 0.3px;
                }}
                
                .email-header .badge {{
                    display: inline-block;
                    background: rgba(201, 161, 59, 0.15);
                    color: #f9d976;
                    padding: 4px 18px;
                    border-radius: 20px;
                    font-size: 0.7rem;
                    font-weight: 500;
                    border: 1px solid rgba(201, 161, 59, 0.15);
                    margin-top: 8px;
                    letter-spacing: 0.3px;
                }}
                
                /* ===== ТЕЛО ===== */
                .email-body {{
                    padding: 32px 36px 28px;
                }}
                
                .email-body .greeting {{
                    font-size: 1.4rem;
                    font-weight: 700;
                    color: #1a1a2e;
                    margin-bottom: 6px;
                }}
                
                .email-body .greeting-sub {{
                    font-size: 1rem;
                    color: #64748b;
                    margin-bottom: 20px;
                }}
                
                .email-body .divider {{
                    border: none;
                    border-top: 2px solid #f1f5f9;
                    margin: 20px 0;
                }}
                
                /* ===== КАРТОЧКА С ДАННЫМИ ===== */
                .credentials-card {{
                    background: #f8fafc;
                    border-radius: 16px;
                    padding: 20px 24px;
                    margin: 16px 0;
                    border: 1px solid #e2e8f0;
                    transition: all 0.3s ease;
                }}
                
                .credentials-card .card-title {{
                    font-size: 0.85rem;
                    font-weight: 600;
                    color: #1a1a2e;
                    margin-bottom: 12px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                
                .credentials-card .card-title i {{
                    color: #c9a13b;
                }}
                
                .credentials-table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                
                .credentials-table tr {{
                    border-bottom: 1px solid rgba(226, 232, 240, 0.3);
                }}
                
                .credentials-table tr:last-child {{
                    border-bottom: none;
                }}
                
                .credentials-table td {{
                    padding: 10px 8px;
                    font-size: 0.9rem;
                }}
                
                .credentials-table .label {{
                    font-weight: 600;
                    color: #1a1a2e;
                    width: 130px;
                    white-space: nowrap;
                }}
                
                .credentials-table .label i {{
                    color: #c9a13b;
                    margin-right: 6px;
                    width: 18px;
                }}
                
                .credentials-table .value {{
                    color: #1a1a2e;
                    font-weight: 500;
                    word-break: break-all;
                }}
                
                .credentials-table .value.url {{
                    color: #c9a13b;
                    text-decoration: none;
                }}
                
                .credentials-table .value.url:hover {{
                    text-decoration: underline;
                }}
                
                .credentials-table .value .password-box {{
                    background: #ffffff;
                    padding: 2px 12px;
                    border-radius: 6px;
                    border: 1px dashed #c9a13b;
                    font-family: 'Courier New', monospace;
                    letter-spacing: 0.5px;
                    display: inline-block;
                }}
                
                /* ===== ИНСТРУКЦИЯ (РАСКРЫВАЮЩАЯСЯ) ===== */
                .instruction-wrapper {{
                    margin: 16px 0 8px;
                    border-radius: 12px;
                    border: 1px solid #e2e8f0;
                    overflow: hidden;
                    background: #ffffff;
                }}
                
                .instruction-toggle {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    width: 100%;
                    padding: 14px 20px;
                    background: #f8fafc;
                    border: none;
                    cursor: pointer;
                    font-size: 0.9rem;
                    font-weight: 600;
                    color: #1a1a2e;
                    transition: all 0.3s ease;
                    font-family: 'Inter', sans-serif;
                    text-align: left;
                }}
                
                .instruction-toggle:hover {{
                    background: #f1f5f9;
                }}
                
                .instruction-toggle .toggle-icon {{
                    color: #c9a13b;
                    font-size: 1.2rem;
                    transition: transform 0.3s ease;
                    font-weight: 700;
                }}
                
                .instruction-toggle .toggle-icon.open {{
                    transform: rotate(180deg);
                }}
                
                .instruction-content {{
                    display: none;
                    padding: 20px 24px;
                    background: #ffffff;
                    border-top: 1px solid #e2e8f0;
                }}
                
                .instruction-content.show {{
                    display: block;
                }}
                
                .instruction-content .step {{
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    padding: 6px 0;
                    color: #1a1a2e;
                    font-size: 0.88rem;
                }}
                
                .instruction-content .step .num {{
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    min-width: 24px;
                    height: 24px;
                    background: rgba(201, 161, 59, 0.12);
                    color: #c9a13b;
                    border-radius: 50%;
                    font-size: 0.7rem;
                    font-weight: 700;
                    flex-shrink: 0;
                    margin-top: 1px;
                }}
                
                .instruction-content .step .text {{
                    flex: 1;
                }}
                
                .instruction-content .step .text strong {{
                    color: #c9a13b;
                }}
                
                .instruction-content .step .text .highlight {{
                    background: rgba(201, 161, 59, 0.08);
                    padding: 1px 8px;
                    border-radius: 4px;
                    font-weight: 500;
                }}
                
                .instruction-content .step .text .moodle-link {{
                    color: #c9a13b;
                    font-weight: 600;
                    text-decoration: none;
                }}
                
                .instruction-content .step .text .moodle-link:hover {{
                    text-decoration: underline;
                }}
                
                .instruction-content .divider-light {{
                    border: none;
                    border-top: 1px solid #f1f5f9;
                    margin: 12px 0;
                }}
                
                /* ===== КНОПКА ===== */
                .btn-wrapper {{
                    text-align: center;
                    margin: 24px 0 8px;
                }}
                
                .btn-primary {{
                    display: inline-block;
                    background: linear-gradient(135deg, #c9a13b 0%, #b8860b 50%, #8b6914 100%);
                    color: #ffffff !important;
                    padding: 12px 36px;
                    border-radius: 12px;
                    text-decoration: none;
                    font-weight: 600;
                    font-size: 0.95rem;
                    transition: all 0.3s ease;
                    border: none;
                    cursor: pointer;
                    box-shadow: 0 4px 16px rgba(201, 161, 59, 0.25);
                }}
                
                .btn-primary:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 8px 24px rgba(201, 161, 59, 0.35);
                    color: #ffffff !important;
                }}
                
                /* ===== WARNING ===== */
                .warning-box {{
                    background: rgba(245, 158, 11, 0.06);
                    border-left: 4px solid #f59e0b;
                    padding: 12px 16px;
                    border-radius: 8px;
                    margin: 16px 0;
                    font-size: 0.85rem;
                    color: #92400e;
                }}
                
                .warning-box strong {{
                    color: #78350f;
                }}
                
                /* ===== ФУТЕР ===== */
                .email-footer {{
                    padding: 20px 36px 24px;
                    border-top: 1px solid #f1f5f9;
                    text-align: center;
                }}
                
                .email-footer .support {{
                    font-size: 0.85rem;
                    color: #64748b;
                    margin-bottom: 8px;
                }}
                
                .email-footer .support a {{
                    color: #c9a13b;
                    text-decoration: none;
                    font-weight: 500;
                }}
                
                .email-footer .support a:hover {{
                    text-decoration: underline;
                }}
                
                .email-footer .copyright {{
                    font-size: 0.7rem;
                    color: #94a3b8;
                    margin-top: 8px;
                }}
                
                .email-footer .copyright .gold-text {{
                    color: #c9a13b;
                }}
                
                /* ===== АДАПТИВ ===== */
                @media (max-width: 480px) {{
                    .email-wrapper {{
                        padding: 10px;
                    }}
                    .email-header {{
                        padding: 24px 20px 20px;
                    }}
                    .email-header .logo img {{
                        height: 40px;
                    }}
                    .email-header .logo-text .title {{
                        font-size: 1rem;
                    }}
                    .email-body {{
                        padding: 24px 20px 20px;
                    }}
                    .email-body .greeting {{
                        font-size: 1.2rem;
                    }}
                    .credentials-card {{
                        padding: 16px;
                    }}
                    .credentials-table td {{
                        padding: 8px 4px;
                        font-size: 0.82rem;
                    }}
                    .credentials-table .label {{
                        width: 90px;
                        font-size: 0.8rem;
                    }}
                    .email-footer {{
                        padding: 16px 20px 20px;
                    }}
                    .btn-primary {{
                        padding: 10px 24px;
                        font-size: 0.85rem;
                    }}
                    .instruction-content {{
                        padding: 16px;
                    }}
                    .instruction-content .step {{
                        font-size: 0.82rem;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="email-wrapper">
                <div class="email-container">
                    
                    <!-- ===== ШАПКА ===== -->
                    <div class="email-header">
                        <div class="logo">
                            <img src="https://govzalla.ru/wp-content/uploads/2023/05/logo-min-1.png" alt="ИРО ЧР">
                            <div class="logo-text">
                                <span class="title">ГБУ ДПО <span class="gold">«ИРО ЧР»</span></span>
                                <span class="subtitle">Институт развития образования Чеченской Республики</span>
                            </div>
                        </div>
                        <div class="badge">✦ Система дистанционного обучения</div>
                    </div>
                    
                    <!-- ===== ТЕЛО ===== -->
                    <div class="email-body">
                        
                        <div class="greeting">Здравствуйте, {full_name}!</div>
                        <div class="greeting-sub">Вы успешно записаны на курс повышения квалификации.</div>
                        
                        {course_text}
                        
                        <hr class="divider">
                        
                        <!-- Данные для входа -->
                        <div class="credentials-card">
                            <div class="card-title">
                                <i>🔐</i> Данные для входа в систему
                            </div>
                            <table class="credentials-table">
                                <tr>
                                    <td class="label"><i>🌐</i> Ссылка:</td>
                                    <td class="value">
                                        <a href="{moodle_url}" class="value url" target="_blank">{moodle_url}</a>
                                    </td>
                                </tr>
                                <tr>
                                    <td class="label"><i>👤</i> Логин:</td>
                                    <td class="value"><strong>{moodle_username}</strong></td>
                                </tr>
                                <tr>
                                    <td class="label"><i>🔑</i> Пароль:</td>
                                    <td class="value">
                                        <span class="password-box">{moodle_password}</span>
                                    </td>
                                </tr>
                            </table>
                        </div>
                        
                        <!-- ИНСТРУКЦИЯ (раскрывающаяся) -->
                        <div class="instruction-wrapper">
                            <button class="instruction-toggle" onclick="toggleInstruction(this)" type="button">
                                <span>📖 Как войти в систему Moodle и начать обучение?</span>
                                <span class="toggle-icon">▾</span>
                            </button>
                            <div class="instruction-content" id="instructionContent">
                                <div class="step">
                                    <span class="num">1</span>
                                    <span class="text">
                                        Перейдите по ссылке <strong class="highlight">«{moodle_url}»</strong> 
                                        (или используйте кнопку ниже)
                                    </span>
                                </div>
                                <div class="step">
                                    <span class="num">2</span>
                                    <span class="text">
                                        На странице входа введите ваш <strong>логин</strong> и <strong>пароль</strong>, 
                                        указанные выше в карточке с данными.
                                    </span>
                                </div>
                                <div class="step">
                                    <span class="num">3</span>
                                    <span class="text">
                                        После успешного входа вы попадёте в <strong>личный кабинет</strong>, 
                                        где будет отображаться ваш курс.
                                    </span>
                                </div>
                                <div class="step">
                                    <span class="num">4</span>
                                    <span class="text">
                                        Нажмите на название курса, чтобы перейти к <strong>учебным материалам</strong> 
                                        и начать обучение.
                                    </span>
                                </div>
                                <hr class="divider-light">
                                <div style="font-size: 0.82rem; color: #64748b; padding: 4px 0;">
                                    <i>💡</i> <strong>Важно:</strong> Рекомендуем сменить пароль после первого входа 
                                    для безопасности вашего аккаунта.
                                </div>
                            </div>
                        </div>
                        
                        <!-- Кнопка перехода -->
                        <div class="btn-wrapper">
                            <a href="{moodle_url}" class="btn-primary" target="_blank">
                                🚀 Перейти в Moodle
                            </a>
                        </div>
                        
                        <!-- Предупреждение -->
                        <div class="warning-box">
                            <strong>⚠️ Важно!</strong> Пароль сгенерирован автоматически. 
                            Рекомендуем сменить его после первого входа в системе.
                        </div>
                        
                        <hr class="divider" style="margin-top: 20px;">
                        
                        <div style="font-size: 0.85rem; color: #64748b;">
                            <strong>❓ Что делать, если возникли вопросы?</strong><br>
                            Вы можете обратиться в службу поддержки ИРО ЧР по электронной почте:
                            <a href="mailto:ipkro-chr@mail.ru" style="color: #c9a13b; text-decoration: none; font-weight: 500;">ipkro-chr@mail.ru</a>
                        </div>
                    </div>
                    
                    <!-- ===== ФУТЕР ===== -->
                    <div class="email-footer">
                        <div class="support">
                            <i>📧</i> По всем вопросам пишите:
                            <a href="mailto:ipkro-chr@mail.ru">ipkro-chr@mail.ru</a>
                        </div>
                        <div class="copyright">
                            © {datetime.now().year} <span class="gold-text">ИРО ЧР</span> — Институт развития образования Чеченской Республики
                            <br>
                            <span style="font-size: 0.65rem; opacity: 0.6;">Это письмо сгенерировано автоматически, пожалуйста, не отвечайте на него.</span>
                        </div>
                    </div>
                    
                </div>
            </div>
            
            <script>
                // Небольшой скрипт для раскрытия инструкции (работает в большинстве почтовых клиентов)
                function toggleInstruction(btn) {{
                    var content = btn.nextElementSibling;
                    var icon = btn.querySelector('.toggle-icon');
                    if (content.classList.contains('show')) {{
                        content.classList.remove('show');
                        if (icon) icon.classList.remove('open');
                    }} else {{
                        content.classList.add('show');
                        if (icon) icon.classList.add('open');
                    }}
                }}
            </script>
            
            <!-- Для почтовых клиентов, которые не поддерживают JavaScript -->
            <noscript>
                <style>
                    .instruction-content {{
                        display: block !important;
                        border-top: 1px solid #e2e8f0;
                    }}
                    .instruction-toggle .toggle-icon {{
                        display: none;
                    }}
                </style>
            </noscript>
        </body>
        </html>
        """
        
        # Текстовая версия (для почтовых клиентов без HTML)
        text_content = f"""
        ========================================
        ГБУ ДПО «ИРО ЧР» - Институт развития образования Чеченской Республики
        Система дистанционного обучения
        ========================================

        Здравствуйте, {full_name}!

        Вы успешно записаны на курс повышения квалификации.
        
        {f'Курс: {moodle_course_name}' if moodle_course_name else ''}

        ----------------------------------------------------
        ДАННЫЕ ДЛЯ ВХОДА В СИСТЕМУ MOODLE
        ----------------------------------------------------
        Ссылка: {moodle_url}
        Логин: {moodle_username}
        Пароль: {moodle_password}
        ----------------------------------------------------

        ИНСТРУКЦИЯ ПО ВХОДУ:
        1. Перейдите по ссылке {moodle_url}
        2. Введите ваш логин и пароль (указаны выше)
        3. После входа вы попадёте в личный кабинет с вашим курсом
        4. Нажмите на название курса, чтобы начать обучение

        ⚠️ ВАЖНО! Пароль сгенерирован автоматически.
        Рекомендуем сменить его после первого входа.

        ----------------------------------------------------
        По всем вопросам пишите: ipkro-chr@mail.ru
        ----------------------------------------------------

        © {datetime.now().year} ИРО ЧР - Институт развития образования Чеченской Республики
        Это письмо сгенерировано автоматически, пожалуйста, не отвечайте на него.
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
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    color: #1a1a2e;
                    line-height: 1.6;
                    background: #f8fafc;
                    margin: 0;
                    padding: 0;
                }}
                .email-wrapper {{
                    max-width: 560px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .email-container {{
                    background: #ffffff;
                    border-radius: 16px;
                    overflow: hidden;
                    border: 1px solid #e2e8f0;
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04);
                }}
                .header {{
                    background: linear-gradient(135deg, #0a0a18 0%, #1a1a2e 60%, #0f0f1a 100%);
                    padding: 24px 28px;
                    border-bottom: 3px solid rgba(201, 161, 59, 0.3);
                }}
                .header h2 {{
                    color: #ffffff;
                    margin: 0;
                    font-weight: 700;
                    font-size: 1.2rem;
                }}
                .header .gold {{
                    color: #c9a13b;
                }}
                .body {{
                    padding: 24px 28px;
                }}
                .user-card {{
                    background: #f8fafc;
                    border-radius: 12px;
                    padding: 16px 20px;
                    border: 1px solid #e2e8f0;
                    margin: 12px 0;
                }}
                .user-card table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                .user-card td {{
                    padding: 6px 8px;
                    font-size: 0.9rem;
                }}
                .user-card .label {{
                    font-weight: 600;
                    color: #1a1a2e;
                    width: 80px;
                }}
                .user-card .label i {{
                    color: #c9a13b;
                    margin-right: 6px;
                }}
                .badge-success {{
                    display: inline-block;
                    background: #d1fae5;
                    color: #059669;
                    padding: 2px 12px;
                    border-radius: 12px;
                    font-size: 0.75rem;
                    font-weight: 500;
                }}
                .footer {{
                    padding: 16px 28px;
                    border-top: 1px solid #f1f5f9;
                    text-align: center;
                    font-size: 0.7rem;
                    color: #94a3b8;
                }}
                .footer .gold-text {{
                    color: #c9a13b;
                }}
            </style>
        </head>
        <body>
            <div class="email-wrapper">
                <div class="email-container">
                    <div class="header">
                        <h2>🆕 Новый участник <span class="gold">зарегистрирован</span></h2>
                    </div>
                    <div class="body">
                        <p><strong>Курс:</strong> {moodle_course_name}</p>
                        
                        <div class="user-card">
                            <table>
                                <tr>
                                    <td class="label"><i>👤</i> ФИО:</td>
                                    <td><strong>{user_name}</strong></td>
                                </tr>
                                <tr>
                                    <td class="label"><i>📧</i> Email:</td>
                                    <td><a href="mailto:{user_email}" style="color: #c9a13b; text-decoration: none;">{user_email}</a></td>
                                </tr>
                            </table>
                        </div>
                        
                        <p>
                            <span class="badge-success">✅ Успешно зарегистрирован</span>
                            <span style="margin-left: 8px; font-size: 0.85rem; color: #64748b;">
                                Пользователь имеет доступ к Moodle
                            </span>
                        </p>
                    </div>
                    <div class="footer">
                        © {datetime.now().year} <span class="gold-text">ИРО ЧР</span> — Институт развития образования Чеченской Республики
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        ========================================
        НОВЫЙ УЧАСТНИК ЗАРЕГИСТРИРОВАН
        ========================================

        Курс: {moodle_course_name}

        ----------------------------------------------------
        ФИО: {user_name}
        Email: {user_email}
        ----------------------------------------------------

        Статус: Успешно зарегистрирован
        Пользователь имеет доступ к Moodle.

        ========================================
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