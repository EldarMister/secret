"""
Главный модуль - обработчик WhatsApp webhook
Main Module for Business Assistant GO
Обновленная версия с ИИ (GPT-4.1-mini)
"""

from flask import request, jsonify
import json
import re
import logging
from datetime import datetime

import config
from db import get_db, User
from services import (
    send_whatsapp, send_whatsapp_buttons, send_whatsapp_image,
    send_telegram_group, send_telegram_private, send_telegram_photo, edit_telegram_message,
    speech_to_text, format_phone, format_currency
)
from nlu import parse_user_message, parse_confirmation

logger = logging.getLogger(__name__)


# =============================================================================
# VAGUE ADDRESS DETECTION & CANCELLATION
# =============================================================================

# Слова, которые ВСЕГДА означают неточный адрес (даже внутри фразы)
# "базардан уйго" -> "уйго" = strictly vague -> бот переспросит
STRICTLY_VAGUE = {
    "домой", "дома", "уйго", "үйгө", "уйдон", "үйдөн",
    "үйүмө", "уйума", "үйгө", "уйума", "үйүнө",
    "уйумо", "уйге", "үйгө"
}

# Слова, которые неточны ТОЛЬКО если весь адрес состоит только из них
# "дом" = vague, но "дом 5" = ok
MAYBE_VAGUE = {"дом", "уй", "үй", "квартира", "кв"}

# Слова отмены заказа (включая опечатки и варианты на кыргызском)
CANCEL_WORDS = {
    "отмена", "отменить", "отказ", "cancel", "стоп", "stop",
    "токтот", "баш тарт",
    "атмина", "атмин", "одмена", "кайтуу"
}
CANCEL_PREFIXES = ("отмен", "атмин", "атмина", "одмен", "артка", "кайт")

def _is_vague_address(address: str) -> bool:
    """Проверяет, является ли адрес слишком общим (дом, уйго, үйгө и т.д.)"""
    if not address:
        return True
    words = address.lower().strip().split()
    # Если ЛЮБОЕ слово — строго неточное (домой, уйго, үйгө) → всегда плохо
    for w in words:
        if w in STRICTLY_VAGUE:
            return True
    # Если ВЕСЬ адрес — это только "может быть неточный" (дом, уй) без конкретики
    if all(w in MAYBE_VAGUE for w in words):
        return True
    return False

def _is_cancellation(message: str) -> bool:
    """Проверяет, хочет ли пользователь отменить заказ"""
    msg_lower = message.lower().strip()
    if not msg_lower:
        return False

    # Эти слова используются в шагах подтверждения/выбора и не должны быть
    # глобальной отменой.
    if msg_lower in ('жок', 'нет', 'жо', 'жог'):
        return False

    # Точное совпадение
    if msg_lower in CANCEL_WORDS:
        return True

    # Если первое слово — отмена
    first_word = msg_lower.split()[0] if msg_lower else ""
    if first_word in CANCEL_WORDS:
        return True

    # По префиксу ловим формы вроде "отмен...", "кайт...", "артка..."
    if any(msg_lower.startswith(prefix) for prefix in CANCEL_PREFIXES):
        return True
    if any(first_word.startswith(prefix) for prefix in CANCEL_PREFIXES):
        return True

    return False


def _normalize_address(address: str) -> str:
    """Нормализовать адрес для сравнения."""
    if not address:
        return ""
    normalized = re.sub(r"\s+", " ", address.lower().strip())
    normalized = re.sub(r"[^\w\s\-а-яё]", "", normalized, flags=re.IGNORECASE)
    return normalized


def _addresses_equal(addr1: str, addr2: str) -> bool:
    """Проверка адресов на равенство после нормализации."""
    n1 = _normalize_address(addr1)
    n2 = _normalize_address(addr2)
    return bool(n1) and n1 == n2


def _is_concrete_order_details(text: str, service: str) -> bool:
    """
    True only for concrete dish/product lists.
    Intent-only phrases like "тамак керек", "кафе", "товарлар" return False.
    """
    if not text:
        return False

    raw = text.strip()
    if not raw:
        return False

    lowered = re.sub(r"\s+", " ", raw.lower()).strip()
    tokens = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", lowered)
    if not tokens:
        return False

    generic_intent_words = {
        "кафе", "еда", "тамак", "оокат", "меню", "мену", "миню", "мэню",
        "товар", "товары", "товарлар", "продукт", "продукты", "магазин", "дүкөн",
        "заказ", "керек", "нужно", "хочу"
    }
    if service == config.SERVICE_SHOP:
        generic_intent_words.update({"сатып", "алуу", "покупка", "покупки"})

    # Clear intent-only short phrases
    if len(tokens) <= 4 and all(t in generic_intent_words for t in tokens):
        return False
    if lowered in {"тамак керек", "оокат керек", "кафе", "товарлар", "товары", "магазин"}:
        return False

    # Strong concrete signals: numbers/quantities/list formatting
    if re.search(r"\b\d+\b", lowered):
        return True
    if re.search(r"\b(шт|кг|гр|г|л|мл|kg|gr|ml|x\d+)\b", lowered):
        return True
    if any(sep in raw for sep in [",", ";", "\n"]):
        return True
    if re.search(r"(^|\n)\s*[-*•]\s*", raw):
        return True

    meaningful = [t for t in tokens if t not in generic_intent_words]
    if len(meaningful) >= 2:
        return True
    if len(meaningful) == 1:
        return True

    return False


def _cancel_order_in_group(order_id: str, service_type: str, db, text: str) -> None:
    """Обновить сообщение в группе на 'заказ отменен' и убрать кнопки"""
    timer = db.get_latest_auction_timer(order_id, service_type)
    if not timer:
        return
    try:
        chat_id = timer.get('chat_id')
        message_id = int(timer.get('telegram_message_id'))
        if chat_id and message_id:
            edit_telegram_message(chat_id, message_id, text, buttons=[])
        db.mark_auction_processed(timer['id'])
    except Exception:
        logger.exception("Failed to edit group message for cancellation")


def handle_client_cancel(user: User, db) -> bool:
    """Отмена последнего активного заказа клиентом"""
    order = db.get_latest_active_order(user.phone)
    if not order:
        return False

    order_id = order.get('order_id')
    service_type = order.get('service_type')
    status = order.get('status')

    cancel_text = "❌ *ЗАКАЗ ОТМЕНЁН*\n\nКлиент отменил заказ."

    # Такси: отдельная логика комиссии и уведомления водителя
    if service_type == config.SERVICE_TAXI:
        if status in (config.ORDER_STATUS_PENDING, config.ORDER_STATUS_AUCTION, config.ORDER_STATUS_URGENT):
            db.update_order_status(order_id, config.ORDER_STATUS_CANCELLED)
            _cancel_order_in_group(order_id, config.SERVICE_TAXI, db, cancel_text)
        else:
            db.update_order_status(order_id, config.ORDER_STATUS_CANCELLED)
            # Уведомляем водителя и возвращаем комиссию
            driver_id = order.get('driver_id')
            commission = float(order.get('driver_commission') or config.TAXI_COMMISSION)
            if driver_id:
                if commission > 0:
                    db.update_driver_balance(driver_id, commission, reason=f"Client cancel taxi {order_id}")
                send_telegram_private(driver_id, "❌ Заказ отменён клиентом. Комиссия не списана.")

            # Обновляем сообщение в группе (если уже было «ЗАКАЗ ЗАБРАН»)
            _cancel_order_in_group(order_id, 'taxi_accepted', db, cancel_text)

        send_whatsapp(user.phone, "❌ Заказ отменён.")
        db.log_transaction("CLIENT_CANCEL_TAXI", user.phone, order_id)
        return True

    # Для остальных сервисов — просто отмена и редактирование сообщения в группе
    db.update_order_status(order_id, config.ORDER_STATUS_CANCELLED)
    _cancel_order_in_group(order_id, service_type, db, cancel_text)
    send_whatsapp(user.phone, "❌ Заказ отменён.")
    db.log_transaction("CLIENT_CANCEL_ORDER", user.phone, order_id)
    return True


# =============================================================================
# WHATSAPP WEBHOOK HANDLER
# =============================================================================

def handle_whatsapp():
    """Главная функция обработки сообщений от Клиента"""
    try:
        incoming_msg = ''
        sender_phone = ''
        media_url = ''
        media_type = ''
        button_response = ''
        
        # 1. Попытка парсинга как JSON (Green API)
        if request.is_json:
            data = request.get_json()
            
            # Проверяем тип вебхука Green API
            type_webhook = data.get('typeWebhook', '')
            
            # Обработка входящего сообщения
            if type_webhook in ['incomingMessageReceived', 'incomingCall']:
                sender_data = data.get('senderData', {})
                message_data = data.get('messageData', {})
                
                # Получаем телефон (убираем @c.us)
                sender = sender_data.get('sender', '')
                sender_phone = sender.replace('@c.us', '')
                
                # Текстовое сообщение
                if message_data.get('typeMessage') == 'textMessage':
                    incoming_msg = message_data.get('textMessageData', {}).get('textMessage', '')
                
                # Изображение
                elif message_data.get('typeMessage') == 'imageMessage':
                    media_url = message_data.get('fileMessageData', {}).get('downloadUrl', '')
                    media_type = message_data.get('fileMessageData', {}).get('mimeType', 'image/jpeg')
                    incoming_msg = message_data.get('fileMessageData', {}).get('caption', '')
                
                # Голосовое
                elif message_data.get('typeMessage') == 'audioMessage':
                    media_url = message_data.get('fileMessageData', {}).get('downloadUrl', '')
                    media_type = 'audio/ogg' 
                
                # Кнопки (ответ)
                elif message_data.get('typeMessage') == 'buttonsResponseMessage':
                    button_response = message_data.get('buttonsResponseMessageData', {}).get('selectedButtonId', '')
                    incoming_msg = button_response
                
            elif type_webhook == 'outgoingMessageStatus':
                return jsonify({"status": "ignored"}), 200
                
        # 2. Попытка парсинга как Form Data (Twilio)
        if not sender_phone:
            incoming_msg = request.values.get('Body', '').strip()
            sender_phone = request.values.get('From', '').replace('whatsapp:', '')
            media_url = request.values.get('MediaUrl0', '')
            media_type = request.values.get('MediaContentType0', '')
            button_response = request.values.get('ButtonResponse', '')

        if not sender_phone:
            return jsonify({"status": "ignored"}), 200

        logger.info(f"Received from {sender_phone}: {incoming_msg[:50]}...")
        
        db = get_db()
        
        # Получаем или создаем пользователя
        user = db.get_user(sender_phone)
        
        if not user:
            logger.error(f"Failed to get/create user: {sender_phone}")
            return jsonify({"status": "error"}), 500
        
        # Обработка голосового сообщения
        if media_type in ['audio/ogg', 'audio/aac'] and media_url:
            logger.info(f"Processing voice from {sender_phone}")
            incoming_msg = speech_to_text(media_url)
        
        # Обработка фото (сохраняем URL)
        if media_type and media_type.startswith('image/'):
            user.set_temp_data('media_url', media_url)
            user.set_temp_data('media_type', media_type)
        
        # Обработка кнопок (если есть)
        if button_response:
            return handle_button_response(user, button_response, db)
        
        # === ROUTING ===
        
        # Проверка на отмену (в любом состоянии),
        # кроме шага выбора цены такси: "Жок/Нет" там означает стандартный тариф.
        msg_lower = incoming_msg.lower().strip()
        is_taxi_price_decline = (
            user.current_state == config.STATE_TAXI_PRICE_CHOICE and
            msg_lower in ('жок', 'нет', 'no', '2', 'btn_taxi_standard')
        )
        if _is_cancellation(incoming_msg) and not is_taxi_price_decline:
            logger.info(f"User {sender_phone} cancelled order in state {user.current_state}")
            cancelled = handle_client_cancel(user, db)
            user.set_state(config.STATE_IDLE)
            user.clear_temp_data()
            if not cancelled:
                send_whatsapp(user.phone, config.ORDER_CANCELLED)
            return jsonify({"status": "ok"}), 200

        if user.current_state == config.STATE_TAXI_REORDER_CHOICE:
            return handle_taxi_reorder_choice(user, incoming_msg, db)
        
        if user.current_state == config.STATE_IDLE:
            return handle_idle_state(user, incoming_msg, db)
        
        # Подтверждение заказа (универсальное)
        elif user.current_state == config.STATE_CONFIRM_ORDER:
            return handle_confirm_order(user, incoming_msg, db)
        
        # Кафе
        elif user.current_state == config.STATE_CAFE_ORDER:
            return handle_cafe_order_details(user, incoming_msg, db)
        elif user.current_state == config.STATE_CAFE_ADDRESS:
            return handle_cafe_address(user, incoming_msg, db)
        
        # Магазин
        elif user.current_state == config.STATE_SHOP_LIST:
            return handle_shop_list(user, incoming_msg, db)
        
        # Аптека
        elif user.current_state == config.STATE_PHARMACY_WAIT_RX:
            return handle_pharmacy_request(user, incoming_msg, media_url, db)
        elif user.current_state == config.STATE_PHARMACY_ADDRESS:
            return handle_pharmacy_delivery_address(user, incoming_msg, db)
        
        # Такси
        elif user.current_state == config.STATE_TAXI_ROUTE:
            return handle_taxi_route(
                user,
                incoming_msg,
                db,
                is_voice_input=(media_type in ['audio/ogg', 'audio/aac'])
            )
        elif user.current_state == config.STATE_TAXI_PRICE_CHOICE:
            return handle_taxi_price_choice(user, incoming_msg, db)
        elif user.current_state == config.STATE_TAXI_CUSTOM_PRICE:
            return handle_taxi_custom_price(user, incoming_msg, db)
        
        # Веб-заказ меню
        elif user.current_state == config.STATE_WEB_ORDER_ADDRESS:
            return handle_web_order_address(user, incoming_msg, db)
        
        # Портер
        elif user.current_state == config.STATE_PORTER_CARGO_TYPE:
            return handle_porter_cargo_type(user, incoming_msg, db)
        elif user.current_state == config.STATE_PORTER_ROUTE:
            return handle_porter_route(user, incoming_msg, db)
        
        # Муравей
        elif user.current_state == config.STATE_ANT_ROUTE:
            return handle_ant_route(user, incoming_msg, db)
        
        # Неизвестное состояние
        else:
            user.set_state(config.STATE_IDLE)
            send_whatsapp(sender_phone, config.WELCOME_MESSAGE)
            return jsonify({"status": "ok"}), 200
            
    except Exception as e:
        logger.exception("Error handling WhatsApp webhook")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# IDLE STATE HANDLER (с ИИ)
# =============================================================================

def handle_idle_state(user: User, message: str, db) -> tuple:
    """Обработка состояния ожидания — ИИ определяет намерение"""
    msg_lower = message.lower()
    msg_trim = message.strip()
    first_token = msg_trim.split()[0] if msg_trim else ""
    first_token_digits = "".join(ch for ch in first_token if ch.isdigit())

    service_intent_by_number = {
        "1": "cafe",
        "2": "shop",
        "3": "pharmacy",
        "4": "taxi",
        "5": "porter",
        "6": "ant",
    }

    # Жёсткая проверка на «меню» / запрос еды, чтобы не путать с доставкой
    menu_keywords = ["меню", "мену", "мэню", "менью", "менйу", "миню", "менюу", "menu", "меню керек", "мага меню"]
    selected_intent = service_intent_by_number.get(msg_trim) or service_intent_by_number.get(first_token_digits)
    if selected_intent:
        nlu_result = {"intent": selected_intent, "from_address": None, "to_address": None, "order_details": None, "cargo_type": None}
    elif any(k in msg_lower for k in menu_keywords):
        nlu_result = {"intent": "cafe", "from_address": None, "to_address": None, "order_details": None, "cargo_type": None}
    else:
        # Используем ИИ для определения намерения
        nlu_result = parse_user_message(message)
    intent = nlu_result.get("intent", "unknown")
    
    logger.info(f"NLU intent for {user.phone}: {intent}")

    # === WEB ORDER CODE (W-xxxxx) ===
    # Проверка на код заказа с сайта
    if re.match(r'^W\d{5}$', message.strip(), re.IGNORECASE):
        code = message.strip().upper()
        order = db.get_web_order(code)
        
        if not order:
            send_whatsapp(sender_phone, "❌ Заказ с таким кодом не найден. Проверьте код.")
            return jsonify({"status": "ok"}), 200
            
        if order['status'] in ['CONFIRMED', 'COMPLETED', 'CANCELLED']:
             send_whatsapp(sender_phone, f"⚠️ Этот заказ уже обработан (Статус: {order['status']}).")
             return jsonify({"status": "ok"}), 200

        # Сохраняем контекст заказа
        user.set_temp_data('service_type', config.SERVICE_CAFE)
        user.set_temp_data('web_order_code', code)
        user.set_temp_data('cafe_id', order['cafe_id'])
        
        # Формируем детали заказа
        items = order['items_json']
        details_lines = [f"Кафе: {order['cafe_name']}"]
        for item in items:
            details_lines.append(f"- {item['name']} x{item['count']}")
        details_lines.append(f"\nИтого: {int(order['total_price'])} сом")
        
        order_details = "\n".join(details_lines)
        user.set_temp_data('cafe_order_details', order_details)
        
        # Переходим к вводу адреса
        user.set_state(config.STATE_WEB_ORDER_ADDRESS)
        send_whatsapp(user.phone, "📍 Введите адрес доставки (или отправьте геолокацию):")
        return jsonify({"status": "ok"}), 200
    
    # === ТАКСИ ===
    if intent == "taxi":
        from_addr = nlu_result.get("from_address")
        to_addr = nlu_result.get("to_address")
        
        if from_addr and to_addr:
            # ИИ извлёк оба адреса — спрашиваем про цену
            user.set_temp_data('service_type', config.SERVICE_TAXI)
            user.set_temp_data('taxi_from', from_addr)
            user.set_temp_data('taxi_to', to_addr)
            user.set_temp_data('taxi_route', f"{from_addr} — {to_addr}")
            user.set_state(config.STATE_TAXI_PRICE_CHOICE)
            _send_taxi_price_choice(user.phone, from_addr, to_addr)
        else:
            # Адреса не указаны — спрашиваем
            user.set_temp_data('taxi_from', '')
            user.set_temp_data('taxi_to', '')
            user.set_state(config.STATE_TAXI_ROUTE)
            send_whatsapp(user.phone, config.TAXI_PROMPT)
        
        return jsonify({"status": "ok"}), 200
    
    # === КАФЕ ===
    elif intent == "cafe":
        order_details_raw = nlu_result.get("order_details")
        order_details = order_details_raw if _is_concrete_order_details(order_details_raw, config.SERVICE_CAFE) else None
        
        if order_details:
            # ИИ извлёк детали заказа — спрашиваем адрес
            user.set_temp_data('cafe_order_details', order_details)
            user.set_state(config.STATE_CAFE_ADDRESS)
            send_whatsapp(user.phone, config.CAFE_ADDRESS_PROMPT)
        else:
            # Предлагаем меню или ручной ввод
            menu_msg = f"🍔 *Меню заказа / Тамак заказ кылуу*\n\nПерейдите по ссылке, чтобы выбрать блюда:\n{config.MENU_LINK}\n\nИли напишите список блюд вручную ниже.\nЖе тамактардын тизмесин төмөндө жазыңыз."
            send_whatsapp(user.phone, menu_msg)
            user.set_state(config.STATE_CAFE_ORDER)
        
        return jsonify({"status": "ok"}), 200
    
    # === МАГАЗИН ===
    elif intent == "shop":
        order_details_raw = nlu_result.get("order_details")
        order_details = order_details_raw if _is_concrete_order_details(order_details_raw, config.SERVICE_SHOP) else None
        
        if order_details:
            # ИИ извлёк список — к подтверждению
            user.set_temp_data('service_type', config.SERVICE_SHOP)
            user.set_temp_data('shop_list', order_details)
            user.set_state(config.STATE_CONFIRM_ORDER)
            
            confirm_msg = config.CONFIRM_SHOP.format(order_details=order_details)
            send_whatsapp(user.phone, confirm_msg)
        else:
            user.set_state(config.STATE_SHOP_LIST)
            send_whatsapp(user.phone, config.SHOP_PROMPT)
        
        return jsonify({"status": "ok"}), 200
    
    # === АПТЕКА ===
    elif intent == "pharmacy":
        order_details = nlu_result.get("order_details")
        
        if order_details:
            # ИИ извлёк название лекарства — к подтверждению
            user.set_temp_data('service_type', config.SERVICE_PHARMACY)
            user.set_temp_data('pharmacy_request', order_details)
            user.set_state(config.STATE_CONFIRM_ORDER)
            
            confirm_msg = config.CONFIRM_PHARMACY.format(order_details=order_details)
            send_whatsapp(user.phone, confirm_msg)
        else:
            user.set_state(config.STATE_PHARMACY_WAIT_RX)
            send_whatsapp(user.phone, config.PHARMACY_PROMPT)
        
        return jsonify({"status": "ok"}), 200
    
    # === ПОРТЕР ===
    elif intent == "porter":
        cargo_type = nlu_result.get("cargo_type")
        from_addr = nlu_result.get("from_address")
        to_addr = nlu_result.get("to_address")
        
        if cargo_type and from_addr and to_addr:
            # Всё есть — к подтверждению
            user.set_temp_data('service_type', config.SERVICE_PORTER)
            user.set_temp_data('porter_cargo_type', cargo_type)
            user.set_temp_data('porter_from', from_addr)
            user.set_temp_data('porter_to', to_addr)
            user.set_temp_data('porter_route', f"{from_addr} — {to_addr}")
            user.set_state(config.STATE_CONFIRM_ORDER)
            
            confirm_msg = config.CONFIRM_PORTER.format(
                cargo_type=config.CARGO_TYPES.get(cargo_type, cargo_type),
                from_address=from_addr,
                to_address=to_addr
            )
            send_whatsapp(user.phone, confirm_msg)
        elif cargo_type:
            # Есть тип груза, нет маршрута
            user.set_temp_data('porter_cargo_type', cargo_type)
            user.set_state(config.STATE_PORTER_ROUTE)
            send_whatsapp(user.phone, config.PORTER_ROUTE_PROMPT)
        else:
            user.set_state(config.STATE_PORTER_CARGO_TYPE)
            send_whatsapp(user.phone, config.PORTER_CARGO_PROMPT)
        
        return jsonify({"status": "ok"}), 200
    
    # === МУРАВЕЙ ===
    elif intent == "ant":
        order_details = nlu_result.get("order_details")
        from_addr = nlu_result.get("from_address")
        to_addr = nlu_result.get("to_address")
        
        if order_details and from_addr and to_addr:
            # Всё есть — к подтверждению
            user.set_temp_data('service_type', config.SERVICE_ANT)
            user.set_temp_data('ant_details', order_details)
            user.set_temp_data('ant_from', from_addr)
            user.set_temp_data('ant_to', to_addr)
            user.set_temp_data('ant_route', f"{from_addr} — {to_addr}")
            user.set_state(config.STATE_CONFIRM_ORDER)
            
            confirm_msg = config.CONFIRM_ANT.format(
                order_details=order_details,
                from_address=from_addr,
                to_address=to_addr
            )
            send_whatsapp(user.phone, confirm_msg)
        else:
            user.set_state(config.STATE_ANT_ROUTE)
            if order_details:
                user.set_temp_data('ant_details', order_details)
            send_whatsapp(user.phone, config.ANT_PROMPT)
        
        return jsonify({"status": "ok"}), 200
    
    # === ПРИВЕТСТВИЕ или НЕИЗВЕСТНОЕ ===
    else:
        send_whatsapp(user.phone, config.WELCOME_MESSAGE)
        return jsonify({"status": "ok"}), 200


# =============================================================================
# UNIVERSAL CONFIRM ORDER HANDLER
# =============================================================================

def handle_confirm_order(user: User, message: str, db) -> tuple:
    """Универсальная обработка подтверждения заказа (с ИИ)"""
    
    # ИИ определяет: подтвердил, отменил, или исправляет
    confirmation = parse_confirmation(message)
    
    service_type = user.get_temp_data('service_type', '')
    
    # Если пользователь исправляет данные
    if confirmation.get("is_correction"):
        return _handle_correction(user, confirmation, service_type)
    
    # Если подтвердил
    if confirmation.get("confirmed"):
        if service_type == config.SERVICE_TAXI:
            return _submit_taxi_order(user, db)
        elif service_type == config.SERVICE_CAFE:
            return _submit_cafe_order(user, db)
        elif service_type == config.SERVICE_SHOP:
            return _submit_shop_order(user, db)
        elif service_type == config.SERVICE_PHARMACY:
            return _submit_pharmacy_order(user, db)
        elif service_type == config.SERVICE_PORTER:
            return _submit_porter_order(user, db)
        elif service_type == config.SERVICE_ANT:
            return _submit_ant_order(user, db)
        else:
            # Неизвестный тип — сбрасываем
            user.set_state(config.STATE_IDLE)
            user.clear_temp_data()
            send_whatsapp(user.phone, config.WELCOME_MESSAGE)
            return jsonify({"status": "ok"}), 200
    
    # Если отменил
    else:
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        send_whatsapp(user.phone, config.ORDER_CANCELLED)
        return jsonify({"status": "ok"}), 200


def _handle_correction(user: User, confirmation: dict, service_type: str) -> tuple:
    """Обработка исправления данных пользователем"""
    
    if service_type == config.SERVICE_TAXI:
        if confirmation.get("corrected_from"):
            user.set_temp_data('taxi_from', confirmation["corrected_from"])
        if confirmation.get("corrected_to"):
            user.set_temp_data('taxi_to', confirmation["corrected_to"])
        
        from_addr = user.get_temp_data('taxi_from', '')
        to_addr = user.get_temp_data('taxi_to', '')
        user.set_temp_data('taxi_route', f"{from_addr} — {to_addr}")
        
        confirm_msg = config.CONFIRM_TAXI.format(
            from_address=from_addr,
            to_address=to_addr
        )
        send_whatsapp(user.phone, confirm_msg)
    
    elif service_type == config.SERVICE_CAFE:
        if confirmation.get("corrected_details"):
            user.set_temp_data('cafe_order_details', confirmation["corrected_details"])
        if confirmation.get("corrected_to"):
            user.set_temp_data('cafe_address', confirmation["corrected_to"])
        
        order_details = user.get_temp_data('cafe_order_details', '')
        address = user.get_temp_data('cafe_address', '')
        
        confirm_msg = config.CONFIRM_CAFE.format(
            order_details=order_details,
            address=address
        )
        send_whatsapp(user.phone, confirm_msg)
    
    elif service_type == config.SERVICE_SHOP:
        if confirmation.get("corrected_details"):
            user.set_temp_data('shop_list', confirmation["corrected_details"])
        
        order_details = user.get_temp_data('shop_list', '')
        confirm_msg = config.CONFIRM_SHOP.format(order_details=order_details)
        send_whatsapp(user.phone, confirm_msg)
    
    elif service_type == config.SERVICE_PHARMACY:
        if confirmation.get("corrected_details"):
            user.set_temp_data('pharmacy_request', confirmation["corrected_details"])
        
        order_details = user.get_temp_data('pharmacy_request', '')
        confirm_msg = config.CONFIRM_PHARMACY.format(order_details=order_details)
        send_whatsapp(user.phone, confirm_msg)
    
    elif service_type == config.SERVICE_PORTER:
        if confirmation.get("corrected_from"):
            user.set_temp_data('porter_from', confirmation["corrected_from"])
        if confirmation.get("corrected_to"):
            user.set_temp_data('porter_to', confirmation["corrected_to"])
        
        from_addr = user.get_temp_data('porter_from', '')
        to_addr = user.get_temp_data('porter_to', '')
        cargo_type = user.get_temp_data('porter_cargo_type', 'other')
        user.set_temp_data('porter_route', f"{from_addr} — {to_addr}")
        
        confirm_msg = config.CONFIRM_PORTER.format(
            cargo_type=config.CARGO_TYPES.get(cargo_type, cargo_type),
            from_address=from_addr,
            to_address=to_addr
        )
        send_whatsapp(user.phone, confirm_msg)
    
    elif service_type == config.SERVICE_ANT:
        if confirmation.get("corrected_details"):
            user.set_temp_data('ant_details', confirmation["corrected_details"])
        if confirmation.get("corrected_from"):
            user.set_temp_data('ant_from', confirmation["corrected_from"])
        if confirmation.get("corrected_to"):
            user.set_temp_data('ant_to', confirmation["corrected_to"])
        
        order_details = user.get_temp_data('ant_details', '')
        from_addr = user.get_temp_data('ant_from', '')
        to_addr = user.get_temp_data('ant_to', '')
        user.set_temp_data('ant_route', f"{from_addr} — {to_addr}")
        
        confirm_msg = config.CONFIRM_ANT.format(
            order_details=order_details,
            from_address=from_addr,
            to_address=to_addr
        )
        send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# ORDER SUBMISSION FUNCTIONS
# =============================================================================

def _submit_taxi_order(user: User, db) -> tuple:
    """Отправка заказа такси"""
    route = user.get_temp_data('taxi_route', '')
    custom_price = user.get_temp_data('taxi_custom_price', None)
    
    # Если клиент предложил свою цену, сохраняем её в price_total
    price_value = float(custom_price) if custom_price else 0
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_TAXI,
        details=route,
        price=price_value
    )
    
    # Определяем комиссию для отображения
    if custom_price and float(custom_price) < config.TAXI_CUSTOM_PRICE_THRESHOLD:
        commission_info = f"💰 Комиссия: {config.TAXI_CUSTOM_PRICE_COMMISSION} сом"
    else:
        commission_info = f"💰 Комиссия: {config.TAXI_COMMISSION} сом"
    
    # Цена в Telegram-сообщении
    if custom_price:
        price_display = f"{int(float(custom_price))} сом (цена клиента)"
    else:
        price_display = f"{config.TAXI_PRICE_RANGE} сом (договорная)"
    
    telegram_msg = config.TAXI_ORDER_TELEGRAM.format(
        route=route,
        price=price_display,
        commission_info=commission_info,
        phone=user.phone
    )
    
    buttons = [{
        "text": "🚖 Взять заказ",
        "callback": f"taxi_take_{order_id}"
    }]
    
    result = send_telegram_group(config.GROUP_TAXI_ID, telegram_msg, buttons)
    
    if result:
        db.create_auction_timer(
            order_id=order_id,
            service_type=config.SERVICE_TAXI,
            telegram_message_id=str(result.get('message_id')),
            chat_id=config.GROUP_TAXI_ID,
            timeout_seconds=config.TAXI_RESPONSE_TIMEOUT
        )
    
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    
    send_whatsapp(user.phone, config.TAXI_PRICE_INFO)
    
    db.log_transaction("TAXI_ORDER_CREATED", user.phone, order_id)
    
    return jsonify({"status": "ok", "order_id": order_id}), 200


def _submit_cafe_order(user: User, db) -> tuple:
    """Отправка заказа в кафе"""
    order_details = user.get_temp_data('cafe_order_details', '')
    address = user.get_temp_data('cafe_address', '')
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_CAFE,
        details=order_details,
        address=address,
        payment_method=config.PAYMENT_CASH  # По умолчанию наличные
    )
    
    commission_info = f"💰 Комиссия: {config.CAFE_COMMISSION_PERCENT}%"
    
    telegram_msg = config.CAFE_ORDER_TELEGRAM.format(
        order_id=order_id,
        order_details=order_details[:200],
        address=address,
        payment=config.PAYMENT_METHODS.get(config.PAYMENT_CASH, config.PAYMENT_CASH),
        phone=user.phone
    ) + f"\n\n{commission_info}"
    
    buttons = [
        {"text": "✅ Принять (2 мин)", "callback": f"cafe_accept_{order_id}"},
        {"text": "❌ Отказать", "callback": f"cafe_decline_{order_id}"}
    ]
    
    result = send_telegram_group(config.GROUP_CAFE_ID, telegram_msg, buttons)
    
    if result:
        db.create_auction_timer(
            order_id=order_id,
            service_type=config.SERVICE_CAFE,
            telegram_message_id=str(result.get('message_id')),
            chat_id=config.GROUP_CAFE_ID,
            timeout_seconds=config.CAFE_AUCTION_TIMEOUT
        )
    
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    
    send_whatsapp(user.phone, config.CAFE_ORDER_SENT)
    
    db.log_transaction("CAFE_ORDER_CREATED", user.phone, order_id, details=order_details[:100])
    
    return jsonify({"status": "ok", "order_id": order_id}), 200


def _submit_shop_order(user: User, db) -> tuple:
    """Отправка заказа в магазин"""
    shop_list = user.get_temp_data('shop_list', '')
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_SHOP,
        details=shop_list
    )
    
    shopper = db.get_shopper()
    
    if shopper:
        msg = f"""🛒 *НОВЫЙ ЗАКАЗ (Магазин)*

📋 *Список:*
{shop_list}

📞 *Клиент:* {user.phone}
💰 *Ваш заработок:* {config.SHOPPER_SERVICE_FEE} сом

Выберите действие:"""
        
        buttons = [
            {"text": "🛒 Взять в работу", "callback": f"shop_take_{order_id}"}
        ]
        
        send_telegram_private(shopper['telegram_id'], msg, buttons)
        send_whatsapp(user.phone, config.ORDER_SENT_GENERIC)
        
        db.log_transaction("SHOP_ORDER_CREATED", user.phone, order_id)
    else:
        send_whatsapp(user.phone, "❌ Закупщик временно недоступен. Попробуйте позже.")
    
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    
    return jsonify({"status": "ok"}), 200


def _submit_pharmacy_order(user: User, db) -> tuple:
    """Отправка заказа в аптеку"""
    request_text = user.get_temp_data('pharmacy_request', '')
    media_url = user.get_temp_data('pharmacy_media_url', '')
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_PHARMACY,
        details=request_text
    )
    
    telegram_msg = config.PHARMACY_ORDER_TELEGRAM.format(
        request=request_text[:200],
        phone=user.phone
    )
    
    if media_url:
        send_telegram_photo(config.GROUP_PHARMACY_ID, media_url, telegram_msg)
    else:
        buttons = [{
            "text": "💊 У нас есть (указать цену)",
            "callback": f"pharm_bid_{order_id}"
        }]
        send_telegram_group(config.GROUP_PHARMACY_ID, telegram_msg, buttons)
    
    user.set_state(config.STATE_PHARMACY_WAIT_PRICE)
    user.set_temp_data('pharmacy_order_id', order_id)
    
    send_whatsapp(user.phone, config.PHARMACY_SEARCHING)
    
    db.log_transaction("PHARMACY_ORDER_CREATED", user.phone, order_id)
    
    return jsonify({"status": "ok"}), 200


def _submit_porter_order(user: User, db) -> tuple:
    """Отправка заказа портера"""
    route = user.get_temp_data('porter_route', '')
    cargo_type = user.get_temp_data('porter_cargo_type', 'other')
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_PORTER,
        details=route,
        cargo_type=cargo_type
    )
    
    telegram_msg = config.PORTER_ORDER_TELEGRAM.format(
        cargo_type=config.CARGO_TYPES.get(cargo_type, cargo_type),
        route=route,
        phone=user.phone
    )
    
    buttons = [{
        "text": "🚛 Взять груз",
        "callback": f"porter_take_{order_id}"
    }]
    
    send_telegram_group(config.GROUP_PORTER_ID, telegram_msg, buttons)
    
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    
    send_whatsapp(user.phone, config.ORDER_SENT_GENERIC)
    
    db.log_transaction("PORTER_ORDER_CREATED", user.phone, order_id)
    
    return jsonify({"status": "ok"}), 200


def _submit_ant_order(user: User, db) -> tuple:
    """Отправка заказа муравья"""
    route = user.get_temp_data('ant_route', '')
    details = user.get_temp_data('ant_details', '')
    
    order_id = db.create_order(
        client_phone=user.phone,
        service_type=config.SERVICE_ANT,
        details=f"{details} | {route}"
    )
    
    telegram_msg = config.ANT_ORDER_TELEGRAM.format(
        details=details,
        route=route,
        phone=user.phone
    )
    
    buttons = [{
        "text": "🐜 Взять заказ",
        "callback": f"ant_take_{order_id}"
    }]
    
    send_telegram_group(config.GROUP_ANT_ID, telegram_msg, buttons)
    
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    
    send_whatsapp(user.phone, config.ORDER_SENT_GENERIC)
    
    db.log_transaction("ANT_ORDER_CREATED", user.phone, order_id)
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# CAFE FLOW (упрощённый — без оплаты)
# =============================================================================

def handle_cafe_order_details(user: User, message: str, db) -> tuple:
    """Обработка деталей заказа кафе"""
    user.set_temp_data('cafe_order_details', message)
    user.set_state(config.STATE_CAFE_ADDRESS)
    send_whatsapp(user.phone, config.CAFE_ADDRESS_PROMPT)
    return jsonify({"status": "ok"}), 200


def handle_cafe_address(user: User, message: str, db) -> tuple:
    """Обработка адреса доставки — переход к подтверждению"""
    # Проверка на слишком общий адрес
    if _is_vague_address(message):
        send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
        return jsonify({"status": "ok"}), 200
    
    user.set_temp_data('cafe_address', message)
    user.set_temp_data('service_type', config.SERVICE_CAFE)
    
    order_details = user.get_temp_data('cafe_order_details', '')
    
    # Переход к подтверждению (без вопроса об оплате)
    user.set_state(config.STATE_CONFIRM_ORDER)
    confirm_msg = config.CONFIRM_CAFE.format(
        order_details=order_details,
        address=message
    )
    send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


def handle_web_order_address(user: User, message: str, db) -> tuple:
    """Обработка адреса для веб-заказа"""
    # Validation if needed
    if len(message) < 3:
         send_whatsapp(user.phone, "Пожалуйста, введите корректный адрес:")
         return jsonify({"status": "ok"}), 200
         
    user.set_temp_data('cafe_address', message)
    
    # Update web order status/info
    code = user.get_temp_data('web_order_code')
    if code:
        db.update_web_order_status(code, 'ADDRESS_SET', client_phone=user.phone, address=message)
    
    # Proceed to confirmation
    details = user.get_temp_data('cafe_order_details', '')
    
    user.set_state(config.STATE_CONFIRM_ORDER)
    confirm_msg = config.CONFIRM_CAFE.format(
        order_details=details,
        address=message
    )
    send_whatsapp(user.phone, confirm_msg)
    return jsonify({"status": "ok"}), 200


# =============================================================================
# SHOP FLOW (упрощённый)
# =============================================================================

def handle_shop_list(user: User, message: str, db) -> tuple:
    """Обработка списка покупок — переход к подтверждению"""
    user.set_temp_data('shop_list', message)
    user.set_temp_data('service_type', config.SERVICE_SHOP)
    
    user.set_state(config.STATE_CONFIRM_ORDER)
    confirm_msg = config.CONFIRM_SHOP.format(order_details=message)
    send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# PHARMACY FLOW
# =============================================================================

def handle_pharmacy_request(user: User, message: str, media_url: str, db) -> tuple:
    """Обработка запроса в аптеку — переход к подтверждению"""
    request_text = message if message else "(фото рецепта)"
    user.set_temp_data('pharmacy_request', request_text)
    user.set_temp_data('service_type', config.SERVICE_PHARMACY)
    
    if media_url:
        user.set_temp_data('pharmacy_media_url', media_url)
    
    user.set_state(config.STATE_CONFIRM_ORDER)
    confirm_msg = config.CONFIRM_PHARMACY.format(order_details=request_text)
    send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


def handle_pharmacy_delivery_address(user: User, message: str, db) -> tuple:
    """Получили адрес клиента после цены аптеки: сразу оформляем доставку."""
    address = (message or "").strip()
    if not address:
        send_whatsapp(user.phone, "📍 Введите адрес доставки.")
        return jsonify({"status": "ok"}), 200

    if _is_vague_address(address):
        send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
        return jsonify({"status": "ok"}), 200

    order_id = user.get_temp_data('pharmacy_order_id')
    pharmacy_id = user.get_temp_data('pharmacy_selected_pharmacy_id')
    pharmacy_name = user.get_temp_data('pharmacy_selected_pharmacy_name', 'Аптека')
    drug_price = float(user.get_temp_data('pharmacy_selected_price', 0) or 0)

    if not order_id or not pharmacy_id or drug_price <= 0:
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        send_whatsapp(user.phone, "❌ Ошибка данных заказа. Начните заново.")
        return jsonify({"status": "ok"}), 200

    order = db.get_order(order_id)
    if not order:
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        send_whatsapp(user.phone, "❌ Заказ не найден. Начните заново.")
        return jsonify({"status": "ok"}), 200

    total_price = drug_price + config.PHARMACY_DELIVERY_FEE + config.TAXI_PHARMACY_COMMISSION

    # Записываем адрес, итоговую цену и переводим в готовность к доставке
    db.update_order_status(
        order_id,
        config.ORDER_STATUS_READY,
        provider_id=pharmacy_id,
        price=total_price,
        address=address
    )

    taxi_msg = f"""💊 *ЗАКАЗ АПТЕКА (ДОСТАВКА)*

🏥 *Забрать из:* {pharmacy_name}
📋 *Лекарство:* {order.get('details', '')}
💵 *Цена лекарства:* {int(drug_price)} сом
💰 *С клиента взять:* {int(total_price)} сом
📍 *Куда доставить:* {address}
📞 *Клиент:* {user.phone}"""

    buttons = [{
        "text": "🚖 Взять доставку",
        "callback": f"delivery_take_{order_id}"
    }]
    send_telegram_group(config.GROUP_TAXI_ID, taxi_msg, buttons)

    send_telegram_private(
        str(pharmacy_id),
        f"✅ Клиент оформил заказ #{order_id}.\nПодготовьте медикаменты — скоро приедет таксист."
    )

    send_whatsapp(
        user.phone,
        f"✅ Заказ оформлен.\n🚖 Ищем курьера для доставки из аптеки.\n💰 К оплате: {int(total_price)} сом."
    )

    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    db.log_transaction("PHARMACY_ADDRESS_CONFIRMED", user.phone, order_id, amount=total_price)

    return jsonify({"status": "ok"}), 200


# =============================================================================
# TAXI FLOW
# =============================================================================

def handle_taxi_reorder_choice(user: User, message: str, db) -> tuple:
    """Обработка ответа клиента после отмены водителем: повторить заказ или начать новый."""
    msg_lower = (message or "").lower().strip()

    yes_words = {"да", "ооба", "yes", "1", "btn_taxi_reorder_yes"}
    no_words = {"нет", "жок", "no", "2", "btn_taxi_reorder_no"}

    if msg_lower in yes_words:
        route = (user.get_temp_data('taxi_reorder_route', '') or '').strip()
        if not route:
            user.clear_temp_data()
            user.set_temp_data('service_type', config.SERVICE_TAXI)
            user.set_temp_data('taxi_from', '')
            user.set_temp_data('taxi_to', '')
            user.set_state(config.STATE_TAXI_ROUTE)
            send_whatsapp(user.phone, config.TAXI_PROMPT)
            return jsonify({"status": "ok"}), 200

        raw_price = user.get_temp_data('taxi_reorder_price', 0)
        try:
            price = float(raw_price or 0)
        except (TypeError, ValueError):
            price = 0

        user.set_temp_data('service_type', config.SERVICE_TAXI)
        user.set_temp_data('taxi_route', route)
        user.set_temp_data('taxi_custom_price', price if price > 0 else None)

        # Для совместимости с остальным flow заполняем откуда/куда если маршрут разделён.
        parts = [p.strip() for p in re.split(r"\s*[—-]\s*", route, maxsplit=1) if p.strip()]
        if len(parts) == 2:
            user.set_temp_data('taxi_from', parts[0])
            user.set_temp_data('taxi_to', parts[1])

        return _submit_taxi_order(user, db)

    if msg_lower in no_words:
        user.clear_temp_data()
        user.set_temp_data('service_type', config.SERVICE_TAXI)
        user.set_temp_data('taxi_from', '')
        user.set_temp_data('taxi_to', '')
        user.set_state(config.STATE_TAXI_ROUTE)
        send_whatsapp(user.phone, config.TAXI_PROMPT)
        return jsonify({"status": "ok"}), 200

    send_whatsapp(
        user.phone,
        "🚖 Повторить тот же заказ?\n"
        "Ооба болсо *Да*, жаңы маршрут болсо *Нет/Жок* деп жазыңыз."
    )
    return jsonify({"status": "ok"}), 200


def _send_taxi_price_choice(phone: str, from_address: str, to_address: str) -> bool:
    """Отправить выбор цены для такси с кнопками и fallback на текст."""
    price_choice_msg = config.TAXI_PRICE_CHOICE_PROMPT.format(
        from_address=from_address,
        to_address=to_address
    )
    buttons = [
        {"text": "✅ Да / Ооба", "id": "btn_taxi_custom"},
        {"text": "❌ Нет / Жок", "id": "btn_taxi_standard"},
    ]
    if send_whatsapp_buttons(phone, price_choice_msg, buttons):
        return True
    return send_whatsapp(phone, price_choice_msg)


def handle_taxi_route(user: User, message: str, db, is_voice_input: bool = False) -> tuple:
    """Обработка маршрута такси: собираем откуда/куда до полной информации."""
    msg = message.strip()
    if not msg:
        send_whatsapp(user.phone, config.TAXI_PROMPT)
        return jsonify({"status": "ok"}), 200

    nlu_result = parse_user_message(msg)
    parsed_from = (nlu_result.get("from_address") or "").strip()
    parsed_to = (nlu_result.get("to_address") or "").strip()

    # Fallback: если пользователь написал маршрут через дефис
    if not parsed_from and not parsed_to:
        dash_split = re.split(r"\s*[—-]\s*", msg, maxsplit=1)
        if len(dash_split) == 2 and dash_split[0].strip() and dash_split[1].strip():
            parsed_from = dash_split[0].strip()
            parsed_to = dash_split[1].strip()

    current_from = (user.get_temp_data('taxi_from', '') or "").strip()
    current_to = (user.get_temp_data('taxi_to', '') or "").strip()

    def _ask_for_to():
        send_whatsapp(
            user.phone,
            "📍 *Куда ехать? / Кайда барабыз?*\n\n"
            "Напишите конечный адрес (куда поедем).\n"
            "Акыркы даректи жазыңыз (кайда барабыз)."
        )

    def _ask_for_from():
        send_whatsapp(
            user.phone,
            "📍 *Откуда ехать? / Кайдан барабыз?*\n\n"
            "Напишите адрес подачи (где вас забрать).\n"
            "Баштапкы даректи жазыңыз (кайдан алабыз)."
        )

    def _go_to_price_choice(from_address: str, to_address: str):
        user.set_temp_data('service_type', config.SERVICE_TAXI)
        user.set_temp_data('taxi_from', from_address)
        user.set_temp_data('taxi_to', to_address)
        user.set_temp_data('taxi_route', f"{from_address} — {to_address}")
        user.set_state(config.STATE_TAXI_PRICE_CHOICE)
        _send_taxi_price_choice(user.phone, from_address, to_address)
        return jsonify({"status": "ok"}), 200

    # Если сразу извлекли оба адреса
    if parsed_from and parsed_to:
        if _is_vague_address(parsed_from) or _is_vague_address(parsed_to):
            send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
            return jsonify({"status": "ok"}), 200
        if _addresses_equal(parsed_from, parsed_to):
            send_whatsapp(
                user.phone,
                "⚠️ Адрес *откуда* и *куда* получился одинаковым.\n"
                "Напишите маршрут точнее: *Откуда* и *Куда* отдельно."
            )
            return jsonify({"status": "ok"}), 200
        return _go_to_price_choice(parsed_from, parsed_to)

    # Для текстового ввода не уточняем адреса, как просил пользователь:
    # сразу переходим к выбору цены (старый быстрый сценарий).
    if not is_voice_input:
        fast_from = parsed_from or msg
        fast_to = parsed_to or msg
        return _go_to_price_choice(fast_from, fast_to)

    # Для голосового ввода — пошаговый сбор недостающего адреса
    if not current_from and not current_to:
        single_addr = parsed_from or parsed_to or msg
        if _is_vague_address(single_addr):
            send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
            return jsonify({"status": "ok"}), 200

        # Если ИИ нашёл только "куда", то сначала просим "откуда"
        if parsed_to and not parsed_from:
            user.set_temp_data('service_type', config.SERVICE_TAXI)
            user.set_temp_data('taxi_to', single_addr)
            _ask_for_from()
            return jsonify({"status": "ok"}), 200

        user.set_temp_data('service_type', config.SERVICE_TAXI)
        user.set_temp_data('taxi_from', single_addr)
        _ask_for_to()
        return jsonify({"status": "ok"}), 200

    if current_from and not current_to:
        to_addr = parsed_to or parsed_from or msg
        if _is_vague_address(to_addr):
            send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
            return jsonify({"status": "ok"}), 200
        if _addresses_equal(current_from, to_addr):
            send_whatsapp(
                user.phone,
                "⚠️ Адрес назначения совпадает с адресом подачи.\n"
                "Напишите другой адрес *КУДА*."
            )
            return jsonify({"status": "ok"}), 200
        return _go_to_price_choice(current_from, to_addr)

    if current_to and not current_from:
        from_addr = parsed_from or parsed_to or msg
        if _is_vague_address(from_addr):
            send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
            return jsonify({"status": "ok"}), 200
        if _addresses_equal(from_addr, current_to):
            send_whatsapp(
                user.phone,
                "⚠️ Адрес подачи совпадает с адресом назначения.\n"
                "Напишите другой адрес *ОТКУДА*."
            )
            return jsonify({"status": "ok"}), 200
        return _go_to_price_choice(from_addr, current_to)

    if _addresses_equal(current_from, current_to):
        send_whatsapp(
            user.phone,
            "⚠️ Адреса сейчас одинаковые. Напишите маршрут заново: *Откуда* и *Куда*."
        )
        return jsonify({"status": "ok"}), 200

    return _go_to_price_choice(current_from, current_to)


def handle_taxi_price_choice(user: User, message: str, db) -> tuple:
    """Обработка выбора: предложить свою цену или нет"""
    msg_lower = message.lower().strip()
    
    from_addr = user.get_temp_data('taxi_from', '')
    to_addr = user.get_temp_data('taxi_to', '')
    
    # Если клиент сразу прислал число, воспринимаем как предложенную цену
    numbers = re.findall(r'\d+', message)
    if numbers and msg_lower not in ('1', '2'):
        price = int(numbers[0])
        if price < config.TAXI_CUSTOM_PRICE_MIN:
            send_whatsapp(user.phone, config.TAXI_CUSTOM_PRICE_TOO_LOW)
            return jsonify({"status": "ok"}), 200

        user.set_temp_data('taxi_custom_price', price)
        # Сразу создаем заказ без лишнего шага подтверждения
        return _submit_taxi_order(user, db)

    # Клиент хочет предложить свою цену (кнопкой/словом)
    if msg_lower in ('btn_taxi_custom', 'да', 'yes', 'ооба', 'ообо', '1'):
        user.set_state(config.STATE_TAXI_CUSTOM_PRICE)
        send_whatsapp(user.phone, config.TAXI_CUSTOM_PRICE_PROMPT)
        return jsonify({"status": "ok"}), 200
    
    # Клиент отказался — сразу стандартный тариф
    if msg_lower in ('btn_taxi_standard', 'нет', 'no', 'жок', '2'):
        user.set_temp_data('taxi_custom_price', None)
        return _submit_taxi_order(user, db)
    
    # Непонятный ответ — переспрашиваем
    _send_taxi_price_choice(user.phone, from_addr, to_addr)
    return jsonify({"status": "ok"}), 200


def handle_taxi_custom_price(user: User, message: str, db) -> tuple:
    """Обработка ввода своей цены клиентом"""
    # Извлекаем число из сообщения
    import re
    numbers = re.findall(r'\d+', message)
    
    if not numbers:
        send_whatsapp(user.phone, config.TAXI_CUSTOM_PRICE_PROMPT)
        return jsonify({"status": "ok"}), 200
    
    price = int(numbers[0])
    
    if price < config.TAXI_CUSTOM_PRICE_MIN:
        send_whatsapp(user.phone, config.TAXI_CUSTOM_PRICE_TOO_LOW)
        return jsonify({"status": "ok"}), 200
    
    # Сохраняем цену и сразу отправляем заказ в поиск водителя
    user.set_temp_data('taxi_custom_price', price)
    return _submit_taxi_order(user, db)


# =============================================================================
# PORTER FLOW
# =============================================================================

def handle_porter_cargo_type(user: User, message: str, db) -> tuple:
    """Обработка типа груза — ИИ определяет"""
    nlu_result = parse_user_message(message)
    
    cargo_type = nlu_result.get("cargo_type")
    if not cargo_type:
        msg_lower = message.lower()
        if any(word in msg_lower for word in ["1", "мебель", "furniture"]):
            cargo_type = "furniture"
        elif any(word in msg_lower for word in ["2", "мусор", "trash", "таштанды"]):
            cargo_type = "trash"
        elif any(word in msg_lower for word in ["3", "строй", "construction", "курулуш"]):
            cargo_type = "construction"
        elif any(word in msg_lower for word in ["4", "скот", "животные", "livestock", "мал"]):
            cargo_type = "livestock"
        else:
            cargo_type = "other"
    
    user.set_temp_data('porter_cargo_type', cargo_type)
    user.set_state(config.STATE_PORTER_ROUTE)
    
    send_whatsapp(user.phone, config.PORTER_ROUTE_PROMPT)
    
    return jsonify({"status": "ok"}), 200


def handle_porter_route(user: User, message: str, db) -> tuple:
    """Обработка маршрута портер — переход к подтверждению"""
    nlu_result = parse_user_message(message)
    
    from_addr = nlu_result.get("from_address") or message
    to_addr = nlu_result.get("to_address") or message
    cargo_type = user.get_temp_data('porter_cargo_type', 'other')
    
    # Проверка на слишком общий адрес
    if _is_vague_address(from_addr) or _is_vague_address(to_addr):
        send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
        return jsonify({"status": "ok"}), 200
    
    user.set_temp_data('service_type', config.SERVICE_PORTER)
    user.set_temp_data('porter_from', from_addr)
    user.set_temp_data('porter_to', to_addr)
    user.set_temp_data('porter_route', f"{from_addr} — {to_addr}")
    user.set_state(config.STATE_CONFIRM_ORDER)
    
    confirm_msg = config.CONFIRM_PORTER.format(
        cargo_type=config.CARGO_TYPES.get(cargo_type, cargo_type),
        from_address=from_addr,
        to_address=to_addr
    )
    send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# ANT (МУРАВЕЙ) FLOW
# =============================================================================

def handle_ant_route(user: User, message: str, db) -> tuple:
    """Обработка сообщения муравей — ИИ извлекает детали и маршрут"""
    nlu_result = parse_user_message(message)
    
    order_details = nlu_result.get("order_details") or user.get_temp_data('ant_details', '') or message
    from_addr = nlu_result.get("from_address") or message
    to_addr = nlu_result.get("to_address") or message
    
    # Проверка на слишком общий адрес
    if _is_vague_address(from_addr) or _is_vague_address(to_addr):
        user.set_temp_data('ant_details', order_details)
        send_whatsapp(user.phone, config.VAGUE_ADDRESS_PROMPT)
        return jsonify({"status": "ok"}), 200
    
    user.set_temp_data('service_type', config.SERVICE_ANT)
    user.set_temp_data('ant_details', order_details)
    user.set_temp_data('ant_from', from_addr)
    user.set_temp_data('ant_to', to_addr)
    user.set_temp_data('ant_route', f"{from_addr} — {to_addr}")
    user.set_state(config.STATE_CONFIRM_ORDER)
    
    confirm_msg = config.CONFIRM_ANT.format(
        order_details=order_details,
        from_address=from_addr,
        to_address=to_addr
    )
    send_whatsapp(user.phone, confirm_msg)
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# BUTTON RESPONSE HANDLER
# =============================================================================

def handle_button_response(user: User, button_response: str, db) -> tuple:
    """Обработка нажатия кнопок в WhatsApp"""
    from client_confirm_handler import handle_pharmacy_client_confirm
    
    try:
        # Такси: выбор цены
        if user.current_state == config.STATE_TAXI_PRICE_CHOICE:
            return handle_taxi_price_choice(user, button_response, db)
        
        # Аптека: подтверждение
        if user.current_state == config.STATE_PHARMACY_CONFIRM:
            return handle_pharmacy_client_confirm(user, button_response, db)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling button response")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# HEALTH CHECK
# =============================================================================

def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "ramadan_mode": config.IS_RAMADAN,
        "ai_enabled": True
    }), 200
