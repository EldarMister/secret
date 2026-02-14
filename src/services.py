"""
Вспомогательные сервисы
Services Module for Business Assistant GO
Обновленная версия согласно ТЗ v2.0
"""

import json
import requests
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlencode

import config


# =============================================================================
# WHATSAPP SERVICES (GREEN API + Twilio)
# =============================================================================

def send_whatsapp(phone: str, message: str) -> bool:
    """Отправить сообщение в WhatsApp"""
    if config.WHATSAPP_PROVIDER == "twilio":
        return _send_whatsapp_twilio(phone, message)
    else:
        return _send_whatsapp_green(phone, message)


def _send_whatsapp_green(phone: str, message: str) -> bool:
    """Отправить сообщение через GREEN API"""
    try:
        url = f"{config.GREEN_API_URL}/sendMessage/{config.GREEN_API_TOKEN}"
        
        phone_clean = _clean_phone(phone)
        
        payload = {
            "chatId": f"{phone_clean}@c.us",
            "message": message
        }
        
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"[GREEN API] Message sent to {phone}")
            return True
        else:
            print(f"[GREEN API] Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"[GREEN API] Exception: {e}")
        return False


def _send_whatsapp_twilio(phone: str, message: str) -> bool:
    """Отправить сообщение через Twilio"""
    try:
        from twilio.rest import Client
        
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        
        phone_clean = _clean_phone(phone)
        if not phone_clean.startswith('+'):
            phone_clean = '+' + phone_clean
        
        message = client.messages.create(
            from_=f"whatsapp:{config.TWILIO_PHONE_NUMBER}",
            body=message,
            to=f"whatsapp:{phone_clean}"
        )
        
        print(f"[Twilio] Message sent to {phone}, SID: {message.sid}")
        return True
        
    except Exception as e:
        print(f"[Twilio] Exception: {e}")
        return False


def send_whatsapp_buttons(phone: str, message: str, buttons: List[Dict]) -> bool:
    """Отправить интерактивное сообщение с кнопками в WhatsApp"""
    try:
        if config.WHATSAPP_PROVIDER == "twilio":
            return _send_whatsapp_buttons_twilio(phone, message, buttons)
        else:
            return _send_whatsapp_buttons_green(phone, message, buttons)
    except Exception as e:
        print(f"Error sending WhatsApp buttons: {e}")
        return False


def _send_whatsapp_buttons_green(phone: str, message: str, buttons: List[Dict]) -> bool:
    """Отправить кнопки через GREEN API"""
    try:
        url = f"{config.GREEN_API_URL}/sendTemplateButtons/{config.GREEN_API_TOKEN}"
        
        phone_clean = _clean_phone(phone)
        
        template_buttons = []
        for idx, btn in enumerate(buttons):
            template_buttons.append({
                "index": idx,
                "urlButton": None,
                "callButton": None,
                "quickReplyButton": {
                    "displayText": btn["text"],
                    "id": btn.get("id", f"btn_{idx}")
                }
            })
        
        payload = {
            "chatId": f"{phone_clean}@c.us",
            "message": message,
            "templateButtons": template_buttons
        }
        
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        return response.status_code == 200
        
    except Exception as e:
        print(f"[GREEN API Buttons] Exception: {e}")
        return False


def _send_whatsapp_buttons_twilio(phone: str, message: str, buttons: List[Dict]) -> bool:
    """Отправить кнопки через Twilio (используем список с номерами)"""
    try:
        # Twilio не поддерживает нативные кнопки, отправляем как текст с нумерацией
        button_text = "\n\n"
        for idx, btn in enumerate(buttons, 1):
            button_text += f"{idx}. {btn['text']}\n"
        
        full_message = message + button_text + "\nОтветьте номером варианта."
        
        return _send_whatsapp_twilio(phone, full_message)
        
    except Exception as e:
        print(f"[Twilio Buttons] Exception: {e}")
        return False


def send_whatsapp_image(phone: str, image_url: str, caption: str = "") -> bool:
    """Отправить изображение в WhatsApp"""
    try:
        if config.WHATSAPP_PROVIDER == "twilio":
            return _send_whatsapp_image_twilio(phone, image_url, caption)
        else:
            return _send_whatsapp_image_green(phone, image_url, caption)
    except Exception as e:
        print(f"Error sending WhatsApp image: {e}")
        return False


def _send_whatsapp_image_green(phone: str, image_url: str, caption: str = "") -> bool:
    """Отправить изображение через GREEN API"""
    try:
        url = f"{config.GREEN_API_URL}/sendFileByUrl/{config.GREEN_API_TOKEN}"
        
        phone_clean = _clean_phone(phone)
        
        payload = {
            "chatId": f"{phone_clean}@c.us",
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        }
        
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        return response.status_code == 200
        
    except Exception as e:
        print(f"[GREEN API Image] Exception: {e}")
        return False


def _send_whatsapp_image_twilio(phone: str, image_url: str, caption: str = "") -> bool:
    """Отправить изображение через Twilio"""
    try:
        from twilio.rest import Client
        
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        
        phone_clean = _clean_phone(phone)
        if not phone_clean.startswith('+'):
            phone_clean = '+' + phone_clean
        
        message = client.messages.create(
            from_=f"whatsapp:{config.TWILIO_PHONE_NUMBER}",
            body=caption,
            media_url=[image_url],
            to=f"whatsapp:{phone_clean}"
        )
        
        return True
        
    except Exception as e:
        print(f"[Twilio Image] Exception: {e}")
        return False


def send_whatsapp_location(phone: str, latitude: float, longitude: float, 
                           name: str = "", address: str = "") -> bool:
    """Отправить геолокацию в WhatsApp"""
    try:
        if config.WHATSAPP_PROVIDER == "green":
            url = f"{config.GREEN_API_URL}/sendLocation/{config.GREEN_API_TOKEN}"
            
            phone_clean = _clean_phone(phone)
            
            payload = {
                "chatId": f"{phone_clean}@c.us",
                "latitude": latitude,
                "longitude": longitude,
                "name": name,
                "address": address
            }
            
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            return response.status_code == 200
        else:
            # Twilio не поддерживает отправку локации напрямую
            location_url = f"https://maps.google.com/?q={latitude},{longitude}"
            return send_whatsapp(phone, f"📍 Локация: {location_url}")
            
    except Exception as e:
        print(f"Error sending location: {e}")
        return False


# =============================================================================
# TELEGRAM SERVICES
# =============================================================================

def send_telegram_message(chat_id: str, message: str, 
                          buttons: Optional[List[Dict]] = None,
                          parse_mode: str = "Markdown") -> Optional[Dict]:
    """Отправить сообщение в Telegram"""
    try:
        url = f"{config.TELEGRAM_API_URL}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        
        if buttons:
            inline_keyboard = []
            for btn in buttons:
                inline_keyboard.append([{
                    "text": btn["text"],
                    "callback_data": btn["callback"]
                }])
            
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json().get("result")
        else:
            print(f"Telegram error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception sending Telegram message: {e}")
        return None


def send_telegram_group(chat_id: str, message: str, 
                        buttons: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Отправить сообщение в Telegram группу"""
    return send_telegram_message(chat_id, message, buttons)


def send_telegram_private(telegram_id: str, message: str, 
                          buttons: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Отправить личное сообщение в Telegram"""
    return send_telegram_message(telegram_id, message, buttons)


def send_telegram_photo(chat_id: str, photo_url: str, caption: str = "",
                        buttons: Optional[List[Dict]] = None) -> Optional[Dict]:
    """Отправить фото в Telegram"""
    try:
        url = f"{config.TELEGRAM_API_URL}/sendPhoto"
        
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        
        if buttons:
            inline_keyboard = []
            for btn in buttons:
                inline_keyboard.append([{
                    "text": btn["text"],
                    "callback_data": btn["callback"]
                }])
            
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json().get("result")
        else:
            print(f"Telegram photo error: {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception sending Telegram photo: {e}")
        return None


def edit_telegram_message(chat_id: str, message_id: int, 
                          new_text: str, buttons: Optional[List[Dict]] = None) -> bool:
    """Редактировать сообщение в Telegram"""
    try:
        url = f"{config.TELEGRAM_API_URL}/editMessageText"
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "Markdown"
        }
        
        if buttons is not None:
            inline_keyboard = []
            for btn in buttons:
                inline_keyboard.append([{
                    "text": btn["text"],
                    "callback_data": btn["callback"]
                }])
            
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200
        
    except Exception as e:
        print(f"Exception editing Telegram message: {e}")
        return False


def delete_telegram_message(chat_id: str, message_id: int) -> bool:
    """Удалить сообщение в Telegram"""
    try:
        url = f"{config.TELEGRAM_API_URL}/deleteMessage"
        
        payload = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        response = requests.post(url, json=payload, timeout=30)
        return response.status_code == 200
        
    except Exception as e:
        print(f"Exception deleting Telegram message: {e}")
        return False


def send_telegram_broadcast(user_ids: List[str], message: str) -> Dict[str, bool]:
    """Рассылка сообщения нескольким пользователям"""
    results = {}
    for user_id in user_ids:
        result = send_telegram_private(user_id, message)
        results[user_id] = result is not None
    return results


# =============================================================================
# SPEECH-TO-TEXT SERVICES
# =============================================================================

def speech_to_text(audio_url: str) -> str:
    """Преобразовать голосовое сообщение в текст"""
    try:
        if not config.OPENAI_API_KEY:
            return "[Распознавание голоса недоступно - нет API ключа]"
        
        # Скачиваем аудио файл
        audio_response = requests.get(audio_url, timeout=30)
        
        if audio_response.status_code != 200:
            return "[Ошибка загрузки аудио]"
        
        return _transcribe_with_whisper(audio_response.content)
            
    except Exception as e:
        print(f"Exception in speech_to_text: {e}")
        return "[Ошибка распознавания голоса]"


def _transcribe_with_whisper(audio_content: bytes) -> str:
    """Транскрибировать аудио с помощью OpenAI Whisper"""
    try:
        url = "https://api.openai.com/v1/audio/transcriptions"
        
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}"
        }
        
        files = {
            'file': ('audio.ogg', audio_content, 'audio/ogg'),
            'model': (None, 'whisper-1')
        }
        
        response = requests.post(url, headers=headers, files=files, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            return result.get("text", "")
        else:
            print(f"Whisper API error: {response.text}")
            return "[Ошибка распознавания]"
            
    except Exception as e:
        print(f"Exception in Whisper transcription: {e}")
        return "[Ошибка распознавания]"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _clean_phone(phone: str) -> str:
    """Очистить номер телефона"""
    phone = phone.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # Если номер начинается с whatsapp:, убираем
    if "whatsapp:" in phone:
        phone = phone.replace("whatsapp:", "")
    
    return phone


def format_phone(phone: str) -> str:
    """Форматировать номер телефона для отображения"""
    phone = _clean_phone(phone)
    
    if len(phone) == 10:
        return f"+996 ({phone[:3]}) {phone[3:6]}-{phone[6:8]}-{phone[8:]}"
    elif len(phone) == 12 and phone.startswith("996"):
        return f"+{phone[:3]} ({phone[3:6]}) {phone[6:9]}-{phone[9:11]}-{phone[11:]}"
    
    return phone


def calculate_taxi_price(route: str) -> str:
    """Рассчитать примерную цену такси"""
    route_lower = route.lower()
    
    base_price = 100
    
    if any(word in route_lower for word in ["центр", "рынок", "базар", "center", "bazaar"]):
        return f"{base_price}-{base_price + 20}"
    elif any(word in route_lower for word in ["микрорайон", "мкр", "жилмассив", "microdistrict"]):
        return f"{base_price + 30}-{base_price + 50}"
    elif any(word in route_lower for word in ["за город", "село", "деревня", "village", "outskirts"]):
        return f"{base_price + 100}-{base_price + 200}"
    
    return f"{base_price}-{base_price + 50}"


def escape_markdown(text: str) -> str:
    """Экранировать специальные символы Markdown"""
    if not text:
        return ""
    
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def format_currency(amount: float) -> str:
    """Форматировать сумму валюты"""
    return f"{amount:,.0f}".replace(",", " ")


def truncate_text(text: str, max_length: int = 200) -> str:
    """Обрезать текст до указанной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def detect_language(text: str) -> str:
    """Определить язык текста (ru/kg)"""
    # Простая эвристика - проверяем на кыргызские символы
    kyrgyz_chars = set('ңөү')
    
    for char in text.lower():
        if char in kyrgyz_chars:
            return 'kg'
    
    return 'ru'
