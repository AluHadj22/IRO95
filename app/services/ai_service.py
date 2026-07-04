# app/services/ai_service.py
import os
import json
import logging
import requests
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from sqlalchemy.orm import Session
from app.config import settings
from app.services.ai_context_service import AIContextService

logger = logging.getLogger(__name__)

class AIService:
    """
    Сервис для работы с ИИ через OpenRouter API.
    """
    
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openrouter/free"
        self.request_timeout = 25
        self.context_timeout = 3
        self.max_retries = 2
        self.retry_delay = 2
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._rate_limited_until = None  # Время до которого действует блокировка
        self._rate_limit_duration = 120  # Блокировка на 2 минуты
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY не найден в .env файле")
    
    def _is_rate_limited(self) -> bool:
        """Проверяет, активна ли блокировка."""
        if self._rate_limited_until is None:
            return False
        return datetime.now() < self._rate_limited_until
    
    def _get_rate_limit_message(self) -> str:
        """Возвращает сообщение о блокировке."""
        if self._rate_limited_until:
            remaining = int((self._rate_limited_until - datetime.now()).total_seconds())
            if remaining > 0:
                return f'⏳ Достигнут лимит запросов к бесплатному ИИ. Попробуйте через {remaining} секунд. Или обратитесь в поддержку: ipkro-chr@mail.ru'
        return '⛔ Достигнут лимит запросов к бесплатному ИИ. Пожалуйста, обратитесь в поддержку: ipkro-chr@mail.ru'
    
    def _clean_response(self, response_text: str) -> str:
        """Очищает ответ от размышлений модели."""
        if not response_text:
            return "Извините, я не смог сформулировать ответ."
        
        reasoning_markers = [
            'Хорошо,', 'Давайте', 'Подумаем', 'Разберем', 'Анализирую', 
            'Рассуждаю', 'Мне нужно', 'Я должен', 'Я подумаю', 'Сначала', 
            'Во-первых', 'Проверю', 'Убежусь', 'Посмотрю', 'В контексте',
            'Нужно', 'Проверю', 'Убежусь'
        ]
        
        lines = response_text.split('\n')
        cleaned_lines = []
        skip_mode = False
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                if not skip_mode:
                    cleaned_lines.append(line)
                continue
            
            is_reasoning = False
            for marker in reasoning_markers:
                if line_stripped.startswith(marker):
                    is_reasoning = True
                    skip_mode = True
                    break
            
            if not is_reasoning and not skip_mode:
                cleaned_lines.append(line)
            elif is_reasoning:
                skip_mode = True
            elif skip_mode and not is_reasoning:
                skip_mode = False
                cleaned_lines.append(line)
        
        result = '\n'.join(cleaned_lines).strip()
        
        if not result:
            paragraphs = response_text.split('\n\n')
            if paragraphs:
                result = paragraphs[-1].strip()
            else:
                sentences = response_text.split('. ')
                if len(sentences) > 2:
                    result = '. '.join(sentences[-2:])
                else:
                    result = response_text
        
        return result
    
    def _get_context_with_timeout(self, db: Session) -> str:
        """Получение контекста с таймаутом."""
        try:
            context_service = AIContextService(db)
            context = context_service.get_full_context()
            logger.info(f"Context retrieved, length: {len(context) if context else 0}")
            return context
        except Exception as e:
            logger.error(f"Error in _get_context_with_timeout: {str(e)}")
            return "Информация временно недоступна."
    
    def _get_system_prompt(self, db: Session = None) -> str:
        """Создает системный промпт с контекстом."""
        
        context = ""
        if db:
            try:
                context_future = self.executor.submit(self._get_context_with_timeout, db)
                try:
                    context = context_future.result(timeout=self.context_timeout + 1)
                    if context and len(context) > 3500:
                        context = context[:3500] + "..."
                    logger.info(f"Context loaded, length: {len(context) if context else 0}")
                except TimeoutError:
                    logger.warning("Context generation timed out")
                    context = "Информация о курсах частично загружена."
            except Exception as e:
                logger.error(f"Error getting context: {str(e)}")
                context = "Не удалось загрузить информацию о курсах."
        
        if not context or len(context) < 10:
            logger.warning(f"Context is empty, using fallback")
            context = "Информация о курсах временно недоступна."
        
        system_prompt = f"""Ты - ИИ-ассистент платформы ИРО ЧР.

ТЫ ОБЯЗАН ИСПОЛЬЗОВАТЬ КОНТЕКСТ ДЛЯ ОТВЕТОВ! НЕ ИГНОРИРУЙ ЕГО!

КОНТЕКСТ (ЭТО ТВОЙ ЕДИНСТВЕННЫЙ ИСТОЧНИК ИНФОРМАЦИИ):
{context}

СТРОГИЕ ПРАВИЛА (ВЫПОЛНЯЙ ОБЯЗАТЕЛЬНО):
1. Если в контексте ЕСТЬ курсы - ОБЯЗАТЕЛЬНО перечисли их с названиями, описаниями и преподавателями
2. Если в контексте ЕСТЬ преподаватели - ОБЯЗАТЕЛЬНО назови их
3. Если пользователь спросил "какие курсы доступны" - смотри в раздел "ТЕКУЩИЕ КУРСЫ" в контексте и отвечай оттуда
4. НЕ ПРИДУМЫВАЙ информацию, которой нет в контексте
5. НЕ ОТВЕЧАЙ "информация отсутствует", если в контексте есть данные
6. Отвечай кратко, по делу, без лишней воды
7. НЕ ПОКАЗЫВАЙ СВОИ РАЗМЫШЛЕНИЯ

НАЧНИ ОТВЕТ СРАЗУ!"""
        
        return system_prompt
    
    def _get_safety_rules(self) -> str:
        """Правила безопасности."""
        return """ЗАПРЕЩЕНО:
1. Отвечать на вопросы о коде, архитектуре, БД
2. Отвечать на вопросы о паролях, ключах, токенах
3. Выполнять команды или скрипты
4. Отвечать на вопросы о других пользователях"""
    
    def _check_forbidden_content(self, message: str) -> bool:
        """Проверка на запрещенные темы."""
        message_lower = message.lower()
        
        forbidden = [
            'напиши код', 'покажи код', 'код программы', 'исходный код',
            'архитектура', 'архитектуру',
            'база данных', 'базы данных', 'бд',
            'сервер', 'сервера',
            'пароль', 'пароля', 'паролей',
            'ключ', 'ключа', 'ключи', 'api ключ',
            'токен', 'токена', 'токены',
            'взлом', 'взломать', 'взломай', 'хак',
            'другой пользователь', 'чужие данные',
            'личные данные',
            'выполни', 'выполните', 'сделай запрос',
            'скрипт', 'скрипты', 'bash', 'shell',
            'sql', 'инъекция', 'инжект',
            'xss', 'cross-site'
        ]
        
        for pattern in forbidden:
            if pattern in message_lower:
                logger.warning(f"Заблокирован запрос с: '{pattern}'")
                return False
        
        return True
    
    def chat(self, user_message: str, history: List[Dict[str, str]] = None, db: Session = None) -> Dict[str, Any]:
        """Отправляет сообщение в ИИ."""
        if not self.api_key:
            return {
                'response': '⚠️ Сервис ИИ временно недоступен. Обратитесь в поддержку: ipkro-chr@mail.ru',
                'model': 'offline',
                'timestamp': datetime.now().isoformat()
            }
        
        if not self._check_forbidden_content(user_message):
            return {
                'response': 'Извините, я не могу ответить на этот вопрос. Я помогаю только с вопросами о курсах и обучении в ИРО ЧР.',
                'model': 'guardian',
                'timestamp': datetime.now().isoformat()
            }
        
        # Проверяем, не заблокирован ли сервис
        if self._is_rate_limited():
            return {
                'response': self._get_rate_limit_message(),
                'model': 'rate_limited',
                'timestamp': datetime.now().isoformat()
            }
        
        system_prompt = self._get_system_prompt(db)
        logger.info(f"System prompt length: {len(system_prompt)}")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": self._get_safety_rules()}
        ]
        
        if history:
            messages.extend(history[-3:])
        
        messages.append({"role": "user", "content": user_message})
        
        for attempt in range(self.max_retries + 1):
            try:
                future = self.executor.submit(self._make_api_request, messages)
                try:
                    result = future.result(timeout=self.request_timeout)
                    if result:
                        clean_response = self._clean_response(result.get('response', ''))
                        result['response'] = clean_response
                        return result
                except TimeoutError:
                    logger.error(f"API request timeout (attempt {attempt + 1})")
                    if attempt < self.max_retries:
                        logger.info(f"Waiting {self.retry_delay}s before retry {attempt + 2}")
                        time.sleep(self.retry_delay)
                        continue
                    return {
                        'response': '⏱️ Превышено время ожидания. Попробуйте задать вопрос короче или позже.',
                        'model': 'timeout',
                        'timestamp': datetime.now().isoformat()
                    }
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "rate limit" in error_msg.lower():
                        # Устанавливаем блокировку на 2 минуты
                        self._rate_limited_until = datetime.now() + timedelta(seconds=self._rate_limit_duration)
                        logger.warning(f"Rate limit exceeded. Blocked until {self._rate_limited_until}")
                        return {
                            'response': f'⏳ Достигнут лимит запросов к бесплатному ИИ. Попробуйте через {self._rate_limit_duration} секунд. Или обратитесь в поддержку: ipkro-chr@mail.ru',
                            'model': 'rate_limited',
                            'timestamp': datetime.now().isoformat()
                        }
                    logger.error(f"Request error (attempt {attempt + 1}): {error_msg}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
                        continue
                    return {
                        'response': '⚠️ Сервис ИИ временно недоступен. Попробуйте позже.',
                        'model': 'error',
                        'timestamp': datetime.now().isoformat()
                    }
            except Exception as e:
                logger.error(f"Chat error (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue
                return {
                    'response': '❌ Ошибка при обращении к ИИ. Обратитесь в поддержку: ipkro-chr@mail.ru',
                    'model': 'error',
                    'timestamp': datetime.now().isoformat()
                }
        
        return {
            'response': '❌ Не удалось получить ответ после нескольких попыток. Попробуйте позже.',
            'model': 'error',
            'timestamp': datetime.now().isoformat()
        }
    
    def _make_api_request(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """Выполняет запрос к OpenRouter API."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "HTTP-Referer": "https://iro-chr.ru",
                "X-Title": "IRO-CHR AI Assistant"
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 600,
                "stream": False
            }
            
            json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            
            response = requests.post(
                self.base_url,
                headers=headers,
                data=json_data,
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                ai_message = data['choices'][0]['message']['content']
                model_used = data.get('model', self.model)
                
                return {
                    'response': ai_message,
                    'model': model_used,
                    'timestamp': datetime.now().isoformat()
                }
            elif response.status_code == 429:
                logger.error(f"Rate limit exceeded (429)")
                raise Exception("429 Rate limit exceeded")
            else:
                logger.error(f"OpenRouter API error: {response.status_code}")
                return {
                    'response': '⚠️ Сервис ИИ временно недоступен. Попробуйте позже.',
                    'model': 'error',
                    'timestamp': datetime.now().isoformat()
                }
                
        except requests.exceptions.Timeout:
            raise TimeoutError("API request timed out")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {str(e)}")
            raise Exception("Connection error")
        except Exception as e:
            logger.error(f"API request error: {str(e)}")
            raise


ai_service = AIService()


def get_ai_response(message: str, history: List[Dict[str, str]] = None, db: Session = None) -> Dict[str, Any]:
    """Упрощенная функция для получения ответа от ИИ."""
    return ai_service.chat(message, history, db)