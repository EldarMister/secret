"""
Обработчик callback-запросов от Telegram
Telegram Handler Module for Business Assistant GO
Обновленная версия согласно ТЗ v2.0
"""

from flask import request, jsonify
import json
import logging
from datetime import datetime

import config
from db import get_db
from services import (
    send_whatsapp, send_telegram_private, send_telegram_group,
    edit_telegram_message, delete_telegram_message, format_phone
)

logger = logging.getLogger(__name__)


# =============================================================================
# TELEGRAM WEBHOOK HANDLER
# =============================================================================

def handle_telegram_webhook():
    """Главная функция обработки запросов от Telegram"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        # Обработка callback_query (нажатие кнопок)
        if 'callback_query' in data:
            return handle_callback_query(data['callback_query'])
        
        # Обработка обычных сообщений
        if 'message' in data:
            return handle_telegram_message(data['message'])
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling Telegram webhook")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_callback_query(callback_query: dict) -> tuple:
    """Обработка нажатия кнопок в Telegram"""
    try:
        data = callback_query.get('data', '')
        user_id = str(callback_query['from']['id'])
        user_name = callback_query['from'].get('first_name', 'Unknown')
        message_id = callback_query['message']['message_id']
        chat_id = str(callback_query['message']['chat']['id'])
        
        logger.info(f"Callback from {user_name} ({user_id}): {data}")
        
        db = get_db()
        
        # === КАФЕ ===
        if data.startswith("cafe_accept_"):
            return handle_cafe_accept(data, user_id, user_name, chat_id, message_id, db)
        elif data.startswith("cafe_ready_"):
            return handle_cafe_ready_time(data, user_id, user_name, db)
        
        # === АПТЕКА ===
        elif data.startswith("pharm_bid_"):
            return handle_pharmacy_bid(data, user_id, user_name, chat_id, db)
        elif data.startswith("pharm_price_"):
            return handle_pharmacy_price_submit(data, user_id, user_name, db)
        
        # === ТАКСИ ===
        elif data.startswith("taxi_take_"):
            return handle_taxi_take(data, user_id, user_name, chat_id, message_id, db)
        elif data.startswith("taxi_arrived_"):
            return handle_taxi_arrived(data, user_id, user_name, db)
        elif data.startswith("taxi_cancel_"):
            return handle_taxi_cancel(data, user_id, user_name, db)
        elif data.startswith("taxi_finish_"):
            return handle_taxi_finish(data, user_id, user_name, db)
        
        # === ПОРТЕР ===
        elif data.startswith("porter_take_"):
            return handle_porter_take(data, user_id, user_name, chat_id, message_id, db)
        
        # === МАГАЗИН ===
        elif data.startswith("shop_take_"):
            return handle_shop_take(data, user_id, user_name, db)
        elif data.startswith("shop_self_delivery_"):
            return handle_shop_self_delivery(data, user_id, db)
        elif data.startswith("shop_call_taxi_"):
            return handle_shop_call_taxi(data, user_id, chat_id, message_id, db)
        
        # === ДОСТАВКА ЕДЫ ===
        elif data.startswith("delivery_take_"):
            return handle_delivery_take(data, user_id, user_name, chat_id, message_id, db)
        
        # === АДМИН ===
        elif data.startswith("admin_"):
            return handle_admin_callback(data, user_id, db)
        
        # === РЕГИСТРАЦИЯ ВОДИТЕЛЕЙ ===
        elif data.startswith("dreg_"):
            return handle_driver_reg_callback(data, user_id, user_name, db)
        
        # === КОМАНДЫ ЧЕРЕЗ КНОПКИ ===
        elif data.startswith("cmd_"):
            return _handle_cmd_button(data, user_id, db)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling callback query")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# CAFE HANDLERS
# =============================================================================

def handle_cafe_accept(data: str, user_id: str, user_name: str,
                       chat_id: str, message_id: int, db) -> tuple:
    """Обработка принятия заказа кафе"""
    try:
        order_id = data.split("_")[2]
        
        # Проверяем, не занят ли заказ
        if db.is_order_taken(order_id):
            send_telegram_private(user_id, "❌ Заказ уже забрали другие!")
            return jsonify({"status": "ok"}), 200
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        
        # Обновляем статус
        db.update_order_status(order_id, config.ORDER_STATUS_ACCEPTED, provider_id=user_id)
        
        # Запрашиваем время готовности
        time_buttons = []
        for minutes in config.CAFE_READY_TIMES:
            time_buttons.append({
                "text": f"⏱ {minutes} мин",
                "callback": f"cafe_ready_{order_id}_{minutes}"
            })
        
        msg = f"""✅ *Заказ #{order_id} принят!*

Укажите время готовности:"""
        
        send_telegram_private(user_id, msg, time_buttons)
        
        # Обновляем сообщение в группе
        updated_text = f"""🍔 *ЗАКАЗ #{order_id} - ПРИНЯТ* ✅

🏠 *Кафе:* {user_name}
⏱ Ожидаем время готовности...

📞 Клиент: {order.get('client_phone', 'N/A')}"""
        
        edit_telegram_message(chat_id, message_id, updated_text)
        
        # Уведомляем клиента
        client_msg = f"""✅ *Заказ #{order_id}*

🏠 *Кафе:* {user_name}
⏱ Ожидаем подтверждение времени готовности..."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        db.log_transaction("CAFE_ORDER_ACCEPTED", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling cafe accept")
        send_telegram_private(user_id, "❌ Ошибка при принятии заказа.")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_cafe_ready_time(data: str, user_id: str, user_name: str, db) -> tuple:
    """Обработка времени готовности кафе"""
    try:
        parts = data.split("_")
        order_id = parts[2]
        ready_time = int(parts[3])
        
        # Обновляем заказ
        db.update_order_status(order_id, config.ORDER_STATUS_READY, ready_time=ready_time)
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            return jsonify({"status": "error"}), 404
        
        # Рассчитываем комиссию (5% всегда, без скидок)
        order_amount = order.get('price_total', 0) or 1000  # Если цена не указана, берем минимум
        commission_added, new_debt = db.update_cafe_debt(user_id, order_amount)
        commission_info = f"💰 Комиссия ({config.CAFE_COMMISSION_PERCENT}%) добавлена в долг"
        
        # Отправляем заявку в группу такси
        taxi_msg = f"""📦 *ДОСТАВКА ЕДЫ*

🏠 *Забрать из:* {user_name}
📋 *Заказ:* #{order_id}
⏱ *Готово через:* {ready_time} мин
📍 *Куда:* {order.get('address', 'Уточнить')}
💳 *Оплата:* {config.PAYMENT_METHODS.get(order.get('payment_method'), 'Наличные')}

📞 *Клиент:* {order.get('client_phone', '')}

{commission_info}"""
        
        buttons = [{
            "text": "🚖 Взять доставку",
            "callback": f"delivery_take_{order_id}"
        }]
        
        send_telegram_group(config.GROUP_TAXI_ID, taxi_msg, buttons)
        
        # Уведомляем клиента
        client_msg = f"""✅ *Заказ #{order_id}*

🏠 *Кафе:* {user_name}
⏱ *Готово через:* {ready_time} минут
🚖 Ищем курьера для доставки...

💳 Оплата: {config.PAYMENT_METHODS.get(order.get('payment_method'), 'Наличные')}"""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        # Уведомляем кафе
        send_telegram_private(user_id, f"✅ Заказ #{order_id} передан на доставку. {commission_info}")
        
        db.log_transaction("CAFE_READY_TIME_SET", user_id, order_id, details=f"Ready in {ready_time} min")
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling cafe ready time")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# PHARMACY HANDLERS
# =============================================================================

def handle_pharmacy_bid(data: str, user_id: str, user_name: str,
                        chat_id: str, db) -> tuple:
    """Обработка отклика аптеки - запрос цены"""
    try:
        order_id = data.split("_")[2]
        
        # Запрашиваем цену у аптеки через ЛС
        msg = f"""💊 *УКАЖИТЕ ЦЕНУ*

Заказ: #{order_id}

Ответьте на это сообщение указав цену (только цифра):

Пример: *450*"""
        
        send_telegram_private(user_id, msg)
        
        # Сохраняем контекст
        db.set_user_temp_data(user_id, 'pending_pharmacy_order', order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling pharmacy bid")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_pharmacy_price_submit(data: str, user_id: str, user_name: str, db) -> tuple:
    """Обработка отправки цены аптекой"""
    try:
        parts = data.split("_")
        order_id = parts[2]
        price = float(parts[3])
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            return jsonify({"status": "error"}), 404
        
        # Сохраняем предложение
        db.add_pharmacy_bid(order_id, user_id, price)
        
        # Итоговая цена для клиента: лекарство + доставка + комиссия таксиста
        total = price + config.PHARMACY_DELIVERY_FEE + config.TAXI_PHARMACY_COMMISSION
        
        # Спрашиваем клиента (WhatsApp)
        client_msg = f"""💊 *Найдено в аптеке!*

🏥 *Аптека:* {user_name}
💵 *Цена лекарства:* {price} сом
🚚 *Доставка:* {config.PHARMACY_DELIVERY_FEE} сом
💼 *Комиссия:* {config.TAXI_PHARMACY_COMMISSION} сом
💰 *ИТОГО:* {total} сом

Берем?"""
        
        buttons = [
            {"text": "✅ Да", "id": f"pharm_yes_{order_id}_{user_id}"},
            {"text": "❌ Нет", "id": f"pharm_no_{order_id}"}
        ]
        
        send_whatsapp_buttons(order.get('client_phone', ''), client_msg, buttons)
        
        # Уведомляем аптеку
        send_telegram_private(user_id, f"✅ Предложение отправлено клиенту. Ждем подтверждения.")
        
        db.log_transaction("PHARMACY_PRICE_SUBMITTED", user_id, order_id, amount=price)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling pharmacy price submit")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# TAXI HANDLERS
# =============================================================================

def handle_taxi_take(data: str, user_id: str, user_name: str,
                     chat_id: str, message_id: int, db) -> tuple:
    """Обработка взятия заказа таксистом"""
    try:
        order_id = data.split("_")[2]
        
        # Проверяем, не занят ли заказ
        if db.is_order_taken(order_id):
            send_telegram_private(user_id, "❌ Заказ уже забрали другие!")
            return jsonify({"status": "ok"}), 200
        
        # Получаем информацию о водителе
        driver = db.get_driver(user_id)
        
        if not driver:
            send_telegram_private(
                user_id,
                "❌ Вы не зарегистрированы!\n\nДля регистрации напишите боту /register в личные сообщения."
            )
            return jsonify({"status": "ok"}), 200
        
        # Получаем заказ (нужен для определения комиссии)
        order = db.get_order(order_id)
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        if order.get('status') == config.ORDER_STATUS_CANCELLED:
            send_telegram_private(user_id, "❌ Заказ уже отменён клиентом.")
            return jsonify({"status": "ok"}), 200
        
        # Определяем комиссию: если клиент предложил цену < 70 → 5 сом, иначе 10 сом
        custom_price = float(order.get('price_total', 0))
        if custom_price > 0 and custom_price < config.TAXI_CUSTOM_PRICE_THRESHOLD:
            commission = config.TAXI_CUSTOM_PRICE_COMMISSION  # 5 сом
        else:
            commission = config.TAXI_COMMISSION  # 10 сом
        
        # Проверяем баланс — минимум 10 сом
        balance = float(driver.get('balance', 0))
        if balance < config.MIN_DRIVER_BALANCE:
            send_telegram_private(
                user_id,
                f"❌ *Недостаточно средств!*\n\n"
                f"💰 Ваш баланс: *{balance} сом*\n"
                f"⚠️ Минимальный баланс для приёма заказов: *{config.MIN_DRIVER_BALANCE} сом*\n\n"
                f"📌 Пополните баланс и попробуйте снова."
            )
            return jsonify({"status": "ok"}), 200
        
        now = datetime.now()
        # Обновляем статус заказа
        db.update_order_status(
            order_id,
            config.ORDER_STATUS_IN_DELIVERY,
            driver_id=user_id,
            driver_assigned_at=now,
            driver_commission=commission
        )
        
        # Списываем комиссию
        success, new_balance = db.update_driver_balance(
            user_id, 
            -commission,
            reason=f"Taxi order {order_id}"
        )
        commission_msg = f"\n💰 Списано комиссии: {commission} сом\n💳 Новый баланс: {new_balance} сом"
        
        # Сообщаем клиенту
        driver_msg = f"""✅ *Машина найдена и выехала!*

🚘 *Автомобиль:* {driver.get('car_model', 'Не указана')}
🔢 *Номер:* {driver.get('plate', 'Не указан')}
👤 *Водитель:* {driver.get('name', user_name)}
📞 *Телефон:* {driver.get('phone', 'Не указан')}

⏱ Ожидайте прибытия."""
        
        send_whatsapp(order.get('client_phone', ''), driver_msg)
        
        # Сообщаем водителю с кнопкой "Приехал"
        driver_private_msg = f"""🚖 *Заказ ваш!*

📞 *Клиент:* {order.get('client_phone', '')}
🛣 *Маршрут:* {order.get('details', '')}

💰 Не забудьте взять оплату по прибытию.{commission_msg}

✅ Удачной поездки!"""
        
        arrived_button = [
            {"text": "📍 Я приехал", "callback": f"taxi_arrived_{order_id}"},
            {"text": "❌ Отмена", "callback": f"taxi_cancel_{order_id}"}
        ]
        
        send_telegram_private(user_id, driver_private_msg, arrived_button)
        
        # Обновляем сообщение в группе
        updated_text = f"""🚖 *ЗАКАЗ ЗАБРАН* ✅

👤 Водитель: *{user_name}*
📞 Клиент: {order.get('client_phone', '')}

⏱ Заказ в работе."""
        
        edit_telegram_message(chat_id, message_id, updated_text)
        
        # Таймер на удаление сообщения "ЗАКАЗ ЗАБРАН" через 30 мин
        db.create_auction_timer(
            order_id=order_id,
            service_type='taxi_accepted',
            telegram_message_id=str(message_id),
            chat_id=chat_id,
            timeout_seconds=config.TAXI_ACCEPTED_TIMEOUT
        )
        
        db.log_transaction("TAXI_ORDER_TAKEN", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling taxi take")
        send_telegram_private(user_id, "❌ Ошибка при взятии заказа.")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_taxi_arrived(data: str, user_id: str, user_name: str, db) -> tuple:
    """Обработка кнопки 'Приехал' — уведомление клиенту"""
    try:
        order_id = data.split("_")[2]
        
        # Получаем заказ
        order = db.get_order(order_id)
        
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        
        # Получаем данные водителя
        driver = db.get_driver(user_id)
        car_info = ""
        if driver:
            car_info = f"\n🚘 *{driver.get('car_model', '')}* | {driver.get('plate', '')}"
        
        # Отправляем клиенту в WhatsApp
        client_msg = f"""📍 *Водитель приехал и ожидает вас!*
{car_info}
👤 *Водитель:* {driver.get('name', user_name) if driver else user_name}
📞 *Телефон:* {driver.get('phone', 'Не указан') if driver else 'Не указан'}

🚶 Пожалуйста, выходите."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        # Подтверждаем водителю
        send_telegram_private(
            user_id,
            "✅ *Клиент уведомлён!*\n\n📍 Ожидайте клиента.",
            [
                {"text": "✅ Завершить поездку", "callback": f"taxi_finish_{order_id}"},
                {"text": "❌ Отменить", "callback": f"taxi_cancel_{order_id}"}
            ]
        )
        
        db.log_transaction("TAXI_DRIVER_ARRIVED", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling taxi arrived")
        send_telegram_private(user_id, "❌ Ошибка.")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_taxi_finish(data: str, user_id: str, user_name: str, db) -> tuple:
    """Завершение поездки водителем"""
    try:
        order_id = data.split("_")[2]
        order = db.get_order(order_id)
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        if order.get('driver_id') and str(order.get('driver_id')) != str(user_id):
            send_telegram_private(user_id, "❌ Этот заказ закреплён за другим водителем.")
            return jsonify({"status": "ok"}), 200

        db.update_order_status(
            order_id,
            config.ORDER_STATUS_COMPLETED,
            completed_at=datetime.now()
        )

        send_telegram_private(user_id, "✅ Поездка завершена. Спасибо!")

        # Уведомление клиента
        send_whatsapp(order.get('client_phone', ''), "✅ Ваша поездка завершена. Спасибо, что выбрали нас!")

        db.log_transaction("TAXI_TRIP_FINISHED", user_id, order_id)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("Error finishing taxi trip")
        send_telegram_private(user_id, "❌ Ошибка завершения.")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_taxi_cancel(data: str, user_id: str, user_name: str, db) -> tuple:
    """Отмена заказа водителем с таймером комиссии"""
    try:
        order_id = data.split("_")[2]
        order = db.get_order(order_id)
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        if order.get('driver_id') and str(order.get('driver_id')) != str(user_id):
            send_telegram_private(user_id, "❌ Этот заказ закреплён за другим водителем.")
            return jsonify({"status": "ok"}), 200

        commission = float(order.get('driver_commission') or config.TAXI_COMMISSION)
        assigned_at = order.get('driver_assigned_at')
        refund = False
        if assigned_at:
            delta = datetime.now() - assigned_at
            refund = delta.total_seconds() <= 30
        # Если нет метки времени, считаем что комиссия удержана

        if refund and commission > 0:
            db.update_driver_balance(user_id, commission, reason=f"Refund taxi {order_id}")

        db.update_order_status(order_id, config.ORDER_STATUS_CANCELLED, driver_id=None)

        driver_msg = "❌ Заказ отменён."
        if refund:
            driver_msg += f"\n💰 Комиссия не списана."
        else:
            driver_msg += f"\n💰 Комиссия остаётся удержанной."
        send_telegram_private(user_id, driver_msg)

        # Уведомление клиента
        client_msg = ("❌ Ваш заказ отменён.\n"
                      "Хотите вызвать такси на тот же адрес и цену или отказаться?\n"
                      "Ответьте в чат: Да / Нет.")
        client_phone = order.get('client_phone', '')
        if client_phone:
            client_user = db.get_user(client_phone)
            if client_user:
                client_user.set_state(config.STATE_TAXI_REORDER_CHOICE)
                client_user.set_temp_data('service_type', config.SERVICE_TAXI)
                client_user.set_temp_data('taxi_reorder_route', order.get('details', '') or '')
                client_user.set_temp_data('taxi_reorder_price', float(order.get('price_total') or 0))

        send_whatsapp(client_phone, client_msg)

        db.log_transaction("TAXI_DRIVER_CANCEL", user_id, order_id, amount=(-commission if refund else None))

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("Error cancelling taxi trip")
        send_telegram_private(user_id, "❌ Ошибка отмены.")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# PORTER HANDLERS
# =============================================================================

def handle_porter_take(data: str, user_id: str, user_name: str,
                       chat_id: str, message_id: int, db) -> tuple:
    """Обработка взятия заказа портером"""
    try:
        order_id = data.split("_")[2]
        
        # Проверяем, не занят ли заказ
        if db.is_order_taken(order_id):
            send_telegram_private(user_id, "❌ Заказ уже забрали другие!")
            return jsonify({"status": "ok"}), 200
        
        # Получаем информацию о водителе
        driver = db.get_driver(user_id)
        
        if not driver:
            db.add_driver(user_id, user_name, driver_type='porter')
            driver = db.get_driver(user_id)
        
        # Обновляем статус
        db.update_order_status(order_id, config.ORDER_STATUS_IN_DELIVERY, driver_id=user_id)
        
        # Списываем комиссию
        commission = config.PORTER_COMMISSION
        success, new_balance = db.update_driver_balance(
            user_id,
            -commission,
            reason=f"Porter order {order_id}"
        )
        
        # Получаем заказ
        order = db.get_order(order_id)
        
        # Сообщаем клиенту
        client_msg = f"""✅ *Водитель найден!*

🚛 *Транспорт:* {driver.get('car_model', 'Портер/Муравей')}
👤 *Водитель:* {driver.get('name', user_name)}
📞 *Телефон:* {driver.get('phone', 'Не указан')}
🔢 *Номер:* {driver.get('plate', 'Не указан')}

💰 Цена: *Договорная*

Скоро позвонит для уточнения."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        # Сообщаем водителю
        driver_msg = f"""🚛 *ЗАКАЗ ВАШ!*

📞 *Клиент:* {order.get('client_phone', '')}
📦 *Тип груза:* {config.CARGO_TYPES.get(order.get('cargo_type'), 'Другое')}
🛣 *Маршрут:* {order.get('details', '')}

💰 Цена: *Договорная*
💰 Комиссия: {commission} сом

Свяжитесь с клиентом для уточнения деталей."""
        
        send_telegram_private(user_id, driver_msg)
        
        # Обновляем сообщение в группе
        updated_text = f"""🚛 *ГРУЗ ЗАБРАН* ✅

👤 Водитель: *{user_name}*
📞 Клиент: {order.get('client_phone', '')}

⏱ Заказ в работе."""
        
        edit_telegram_message(chat_id, message_id, updated_text)
        
        db.log_transaction("PORTER_ORDER_TAKEN", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling porter take")
        send_telegram_private(user_id, "❌ Ошибка при взятии заказа.")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# SHOP HANDLERS
# =============================================================================

def handle_shop_take(data: str, user_id: str, user_name: str, db) -> tuple:
    """Обработка взятия заказа закупщиком"""
    try:
        order_id = data.split("_")[2]
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            send_telegram_private(user_id, "❌ Заказ не найден.")
            return jsonify({"status": "ok"}), 200
        
        # Списываем комиссию 10 сом с закупщика
        commission = config.SHOPPER_COMMISSION
        success, new_balance = db.update_driver_balance(
            user_id,
            -commission,
            reason=f"Shop order {order_id}"
        )
        
        if not success:
            send_telegram_private(user_id, f"❌ Недостаточно средств на балансе. Нужно: {commission} сом")
            return jsonify({"status": "ok"}), 200
        
        # Обновляем статус
        db.update_order_status(order_id, config.ORDER_STATUS_ACCEPTED, provider_id=user_id)
        
        # Предлагаем варианты доставки
        msg = f"""🛒 *ЗАКАЗ ВЗЯТ*

📋 *Список:*
{order.get('details', '')}

📞 *Клиент:* {order.get('client_phone', '')}

Выберите способ доставки:"""
        
        buttons = [
            {"text": "🚶 Доставлю сам", "callback": f"shop_self_delivery_{order_id}"},
            {"text": "🚖 Вызвать такси", "callback": f"shop_call_taxi_{order_id}"}
        ]
        
        send_telegram_private(user_id, msg, buttons)
        
        db.log_transaction("SHOP_ORDER_TAKEN", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling shop take")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_shop_self_delivery(data: str, user_id: str, db) -> tuple:
    """Закупщик доставляет сам"""
    try:
        order_id = data.split("_")[3]
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            return jsonify({"status": "error"}), 404
        
        # Уведомляем клиента
        client_msg = f"""✅ *Закупщик назначен!*

👤 *Курьер:* Закупщик
📞 Скоро свяжется для уточнения.

💰 Услуга: *{config.SHOPPER_SERVICE_FEE} сом*
📦 Товары: по чеку

Курьер доставит самостоятельно."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        # Уведомляем закупщика
        send_telegram_private(
            user_id,
            f"✅ Клиент уведомлен.\n💰 Ваш заработок: {config.SHOPPER_SERVICE_FEE} сом"
        )
        
        db.log_transaction("SHOP_SELF_DELIVERY", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling shop self delivery")
        return jsonify({"status": "error", "message": str(e)}), 500


def handle_shop_call_taxi(data: str, user_id: str, chat_id: str, message_id: int, db) -> tuple:
    """Закупщик вызывает такси для доставки"""
    try:
        order_id = data.split("_")[3]
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            return jsonify({"status": "error"}), 404
        
        # Отправляем заявку в группу такси
        taxi_msg = f"""🛒 *ДОСТАВКА ИЗ МАГАЗИНА*

📋 *Заказ:* #{order_id}
📦 *Забрать у:* Закупщика
📍 *Куда:* {order.get('client_phone', '')}
💰 *С клиента:* Чек + {config.SHOPPER_SERVICE_FEE} сом
💰 *Таксисту:* Чек + {config.TAXI_SHOP_DELIVERY_FEE} сом

📞 *Закупщик:* {user_id}"""
        
        buttons = [{
            "text": "🚖 Взять доставку",
            "callback": f"delivery_take_{order_id}"
        }]
        
        send_telegram_group(config.GROUP_TAXI_ID, taxi_msg, buttons)
        
        # Уведомляем закупщика
        send_telegram_private(
            user_id,
            f"✅ Заявка на такси отправлена.\n💰 Ваш заработок: {config.SHOPPER_TAXI_DELIVERY_FEE} сом"
        )
        
        # Уведомляем клиента
        client_msg = f"""✅ *Закупщик назначен!*

👤 *Курьер:* Закупщик
🚖 *Доставка:* Через такси

💰 Услуга: *{config.SHOPPER_SERVICE_FEE} сом*
📦 Товары: по чеку

Ищем такси для доставки..."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        db.log_transaction("SHOP_TAXI_CALLED", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling shop call taxi")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# DELIVERY HANDLERS
# =============================================================================

def handle_delivery_take(data: str, user_id: str, user_name: str,
                         chat_id: str, message_id: int, db) -> tuple:
    """Обработка взятия доставки еды/лекарств/магазина"""
    try:
        order_id = data.split("_")[2]
        
        # Проверяем, не занят ли заказ
        if db.is_order_taken(order_id):
            send_telegram_private(user_id, "❌ Заказ уже забрали другие!")
            return jsonify({"status": "ok"}), 200
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            return jsonify({"status": "error"}), 404
        
        # Определяем тип доставки и комиссию
        service_type = order.get('service_type')
        commission = 0
        commission_msg = ""
        
        if service_type == config.SERVICE_SHOP:
            # Доставка из магазина - 10 сом с таксиста
            commission = config.TAXI_SHOP_COMMISSION
        elif service_type == config.SERVICE_PHARMACY:
            # Доставка аптеки - 10 сом с таксиста
            commission = config.TAXI_PHARMACY_COMMISSION
        
        # Списываем комиссию если есть
        if commission > 0:
            success, new_balance = db.update_driver_balance(
                user_id,
                -commission,
                reason=f"Delivery {service_type} order {order_id}"
            )
            if success:
                commission_msg = f"\n💰 Списано комиссии: {commission} сом"
            else:
                send_telegram_private(user_id, f"❌ Недостаточно средств. Нужно: {commission} сом")
                return jsonify({"status": "ok"}), 200
        
        # Получаем информацию о водителе
        driver = db.get_driver(user_id)
        if not driver:
            db.add_driver(user_id, user_name)
            driver = db.get_driver(user_id)
        
        # Обновляем статус
        db.update_order_status(order_id, config.ORDER_STATUS_IN_DELIVERY, driver_id=user_id)
        
        # Сообщаем клиенту
        client_msg = f"""✅ *Курьер найден!*

🚖 *Водитель:* {driver.get('name', user_name)}
📞 *Телефон:* {driver.get('phone', 'Не указан')}
🔢 *Номер:* {driver.get('plate', 'Не указан')}

⏱ Ожидайте доставку."""
        
        send_whatsapp(order.get('client_phone', ''), client_msg)
        
        # Сообщаем водителю
        driver_msg = f"""📦 *ДОСТАВКА ВАША!*

📋 *Заказ:* #{order_id}
📞 *Клиент:* {order.get('client_phone', '')}
📍 *Адрес:* {order.get('address', 'Уточнить')}

💰 Не забудьте взять оплату.{commission_msg}"""
        
        send_telegram_private(user_id, driver_msg)
        
        # Обновляем сообщение в группе
        updated_text = f"""📦 *ДОСТАВКА ЗАБРАТА* ✅

👤 Водитель: *{user_name}*
📞 Клиент: {order.get('client_phone', '')}

⏱ Доставка в процессе."""
        
        edit_telegram_message(chat_id, message_id, updated_text)
        
        db.log_transaction("DELIVERY_TAKEN", user_id, order_id)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling delivery take")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# ADMIN HANDLERS
# =============================================================================

def handle_admin_callback(data: str, user_id: str, db) -> tuple:
    """Обработка админских команд"""
    try:
        # Проверяем, является ли пользователь админом
        if user_id not in config.ADMIN_TELEGRAM_IDS:
            send_telegram_private(user_id, "❌ У вас нет прав администратора.")
            return jsonify({"status": "ok"}), 200
        
        action = data.split("_")[1]
        
        if action == "stats":
            # Показываем статистику
            stats = db.get_daily_stats()
            msg = f"""📊 *Статистика за сегодня*

📦 Всего заказов: {stats.get('total_orders', 0)}
✅ Выполнено: {stats.get('completed', 0)}
❌ Отменено: {stats.get('cancelled', 0)}
💰 Выручка: {stats.get('total_revenue', 0)} сом
💼 Комиссия: {stats.get('total_commission', 0)} сом"""
            
            send_telegram_private(user_id, msg)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling admin callback")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# ОБРАБОТКА КНОПОК МЕНЮ (cmd_*)
# =============================================================================

def _handle_cmd_button(data: str, user_id: str, db) -> tuple:
    """Обработка нажатий кнопок главного меню"""
    try:
        cmd = data.replace("cmd_", "")
        
        if cmd == "register":
            return _handle_register_command(user_id, '/register', db)
        elif cmd == "balance":
            return _handle_balance_command(user_id, db)
        elif cmd == "profile":
            return _handle_profile_command(user_id, db)
        elif cmd == "stats":
            return _handle_stats_command(user_id, db)
        elif cmd == "help":
            send_telegram_private(user_id, config.DRIVER_HELP_MSG)
            return jsonify({"status": "ok"}), 200
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling cmd button")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# TELEGRAM MESSAGE HANDLER (команды + регистрация водителей)
# =============================================================================

def handle_telegram_message(message: dict) -> tuple:
    """Обработка сообщений от Telegram (личные сообщения боту)"""
    try:
        chat_type = message['chat'].get('type', 'private')
        
        # Обрабатываем только личные сообщения (не групповые)
        if chat_type != 'private':
            return jsonify({"status": "ok"}), 200
        
        text = message.get('text', '').strip()
        user_id = str(message['from']['id'])
        user_name = message['from'].get('first_name', 'Unknown')
        
        if not text:
            return jsonify({"status": "ok"}), 200
        
        db = get_db()
        
        logger.info(f"Telegram DM from {user_name} ({user_id}): {text}")
        
        # =====================================================================
        # ОБРАБОТКА КОМАНД
        # =====================================================================
        
        text_lower = text.lower().strip()
        
        # /start — Приветствие
        if text_lower in ('/start', 'start', 'привет', 'здравствуйте'):
            send_telegram_private(user_id, config.DRIVER_WELCOME, config.DRIVER_WELCOME_BUTTONS)
            db.clear_telegram_session(user_id)
            return jsonify({"status": "ok"}), 200
        
        # /help — Помощь
        if text_lower in ('/help', 'help', 'помощь'):
            send_telegram_private(user_id, config.DRIVER_HELP_MSG)
            return jsonify({"status": "ok"}), 200
        
        # /register — Начать регистрацию
        if text_lower in ('/register', 'register', 'регистрация', '/update', 'update'):
            return _handle_register_command(user_id, text_lower, db)
        
        # /balance — Проверить баланс
        if text_lower in ('/balance', 'balance', 'баланс'):
            return _handle_balance_command(user_id, db)
        
        # /profile — Мой профиль
        if text_lower in ('/profile', 'profile', 'профиль'):
            return _handle_profile_command(user_id, db)
        
        # /stats — Моя статистика
        if text_lower in ('/stats', 'stats', 'статистика'):
            return _handle_stats_command(user_id, db)
        
        # /cancel — Отмена текущего действия
        if text_lower in ('/cancel', 'cancel', 'отмена'):
            db.clear_telegram_session(user_id)
            send_telegram_private(user_id, "❌ Действие отменено.")
            send_telegram_private(user_id, config.DRIVER_WELCOME, config.DRIVER_WELCOME_BUTTONS)
            return jsonify({"status": "ok"}), 200
        
        # =====================================================================
        # ОБРАБОТКА СОСТОЯНИЙ РЕГИСТРАЦИИ
        # =====================================================================
        
        session = db.get_telegram_session(user_id)
        
        if session:
            state = session.get('state', 'IDLE')
            
            if state == config.STATE_DRIVER_REG_TYPE:
                return _handle_reg_type(user_id, text, db)
            
            elif state == config.STATE_DRIVER_REG_NAME:
                return _handle_reg_name(user_id, text, db)
            
            elif state == config.STATE_DRIVER_REG_PHONE:
                return _handle_reg_phone(user_id, text, db)
            
            elif state == config.STATE_DRIVER_REG_CAR:
                return _handle_reg_car(user_id, text, db)
            
            elif state == config.STATE_DRIVER_REG_PLATE:
                return _handle_reg_plate(user_id, text, db)
            
            elif state == config.STATE_DRIVER_REG_CONFIRM:
                return _handle_reg_confirm(user_id, text, db)
        
        # =====================================================================
        # ВВОД ЦЕНЫ АПТЕКОЙ (старая логика)
        # =====================================================================
        
        if text.isdigit():
            price = int(text)
            msg = f"""💊 *Цена указана:* {price} сом

Ожидаем подтверждения клиента..."""
            send_telegram_private(user_id, msg)
            return jsonify({"status": "ok"}), 200
        
        # Неизвестное сообщение — показать меню
        send_telegram_private(user_id, config.DRIVER_WELCOME, config.DRIVER_WELCOME_BUTTONS)
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling telegram message")
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# КОМАНДЫ ВОДИТЕЛЯ
# =============================================================================

def _handle_register_command(user_id: str, command: str, db) -> tuple:
    """Обработка команды /register или /update"""
    
    is_update = command in ('/update', 'update')
    
    # Проверяем, зарегистрирован ли уже
    driver = db.get_driver(user_id)
    
    if driver and not is_update:
        # Уже зарегистрирован — показываем данные
        driver_type_key = driver.get('driver_type', 'taxi')
        type_emoji = config.DRIVER_TYPES.get(driver_type_key, '🚖 Такси').split(' ')[0]
        
        msg = config.DRIVER_REG_ALREADY.format(
            type_emoji=type_emoji,
            driver_type=config.DRIVER_TYPES.get(driver_type_key, driver_type_key),
            name=driver.get('name', 'Не указано'),
            phone=driver.get('phone', 'Не указан'),
            car_model=driver.get('car_model', 'Не указано'),
            plate=driver.get('plate', 'Не указан'),
            balance=driver.get('balance', 0)
        )
        send_telegram_private(user_id, msg)
        return jsonify({"status": "ok"}), 200
    
    # Начинаем регистрацию/обновление
    db.create_telegram_session(user_id)
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_TYPE)
    
    # Отправляем с кнопками
    buttons = [
        {"text": "🚖 Такси", "callback": "dreg_type_taxi"},
        {"text": "🚛 Портер", "callback": "dreg_type_porter"},
        {"text": "🐜 Муравей", "callback": "dreg_type_ant"}
    ]
    
    send_telegram_private(user_id, config.DRIVER_REG_TYPE_PROMPT, buttons)
    return jsonify({"status": "ok"}), 200


def _handle_balance_command(user_id: str, db) -> tuple:
    """Обработка команды /balance"""
    
    driver = db.get_driver(user_id)
    
    if not driver:
        send_telegram_private(user_id, config.DRIVER_NOT_REGISTERED)
        return jsonify({"status": "ok"}), 200
    
    balance = float(driver.get('balance', 0))
    
    if balance >= 100:
        status = "✅ Баланс достаточный для приёма заказов."
    elif balance >= 0:
        status = "⚠️ Баланс низкий. Рекомендуем пополнить."
    else:
        status = "🔴 Баланс отрицательный! Пополните для продолжения работы."
    
    msg = config.DRIVER_BALANCE_MSG.format(
        balance=balance,
        status=status
    )
    send_telegram_private(user_id, msg)
    return jsonify({"status": "ok"}), 200


def _handle_profile_command(user_id: str, db) -> tuple:
    """Обработка команды /profile"""
    
    driver = db.get_driver(user_id)
    
    if not driver:
        send_telegram_private(user_id, config.DRIVER_NOT_REGISTERED)
        return jsonify({"status": "ok"}), 200
    
    driver_type_key = driver.get('driver_type', 'taxi')
    type_emoji = config.DRIVER_TYPES.get(driver_type_key, '🚖 Такси').split(' ')[0]
    
    created_at = driver.get('created_at', '')
    if hasattr(created_at, 'strftime'):
        created_at = created_at.strftime('%d.%m.%Y')
    
    msg = config.DRIVER_PROFILE_MSG.format(
        type_emoji=type_emoji,
        driver_type=config.DRIVER_TYPES.get(driver_type_key, driver_type_key),
        name=driver.get('name', 'Не указано'),
        phone=driver.get('phone', 'Не указан'),
        car_model=driver.get('car_model', 'Не указано'),
        plate=driver.get('plate', 'Не указан'),
        balance=driver.get('balance', 0),
        created_at=created_at
    )
    send_telegram_private(user_id, msg)
    return jsonify({"status": "ok"}), 200


def _handle_stats_command(user_id: str, db) -> tuple:
    """Обработка команды /stats"""
    
    driver = db.get_driver(user_id)
    
    if not driver:
        send_telegram_private(user_id, config.DRIVER_NOT_REGISTERED)
        return jsonify({"status": "ok"}), 200
    
    stats = db.get_driver_order_stats(user_id)
    balance = float(driver.get('balance', 0))
    
    msg = f"""📊 *Моя статистика*

📦 Всего заказов: {stats.get('total_orders', 0)}
✅ Выполнено: {stats.get('completed', 0)}
❌ Отменено: {stats.get('cancelled', 0)}
📅 Сегодня: {stats.get('today', 0)}

💰 Текущий баланс: {balance} сом"""
    
    send_telegram_private(user_id, msg)
    return jsonify({"status": "ok"}), 200


# =============================================================================
# РЕГИСТРАЦИЯ ВОДИТЕЛЯ — ПОШАГОВЫЙ FLOW
# =============================================================================

def _handle_reg_type(user_id: str, text: str, db) -> tuple:
    """Шаг 1: Выбор типа водителя"""
    text_lower = text.lower().strip()
    
    driver_type = None
    
    if text_lower in ('1', 'такси', 'taxi', '🚖'):
        driver_type = 'taxi'
    elif text_lower in ('2', 'портер', 'porter', 'грузовик', '🚛'):
        driver_type = 'porter'
    elif text_lower in ('3', 'муравей', 'ant', 'дамас', '🐜'):
        driver_type = 'ant'
    
    if not driver_type:
        send_telegram_private(
            user_id, 
            "⚠️ Выберите тип: *1* (Такси), *2* (Портер) или *3* (Муравей)"
        )
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_data(user_id, 'driver_type', driver_type)
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_NAME)
    
    send_telegram_private(user_id, config.DRIVER_REG_NAME_PROMPT)
    return jsonify({"status": "ok"}), 200


def _handle_reg_name(user_id: str, text: str, db) -> tuple:
    """Шаг 2: Ввод ФИО"""
    
    if len(text) < 2:
        send_telegram_private(user_id, "⚠️ Имя слишком короткое. Введите ваше ФИО.")
        return jsonify({"status": "ok"}), 200
    
    if len(text) > 100:
        send_telegram_private(user_id, "⚠️ Имя слишком длинное. Максимум 100 символов.")
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_data(user_id, 'name', text)
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_PHONE)
    
    send_telegram_private(user_id, config.DRIVER_REG_PHONE_PROMPT)
    return jsonify({"status": "ok"}), 200


def _handle_reg_phone(user_id: str, text: str, db) -> tuple:
    """Шаг 3: Ввод телефона"""
    
    # Очищаем номер
    phone = text.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
    
    if len(phone) < 9 or not phone.isdigit():
        send_telegram_private(
            user_id, 
            "⚠️ Неверный формат номера.\n\nВведите номер цифрами, например: *0555123456*"
        )
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_data(user_id, 'phone', phone)
    
    # Выбираем подсказку в зависимости от типа
    driver_type = db.get_telegram_session_data(user_id, 'driver_type', 'taxi')
    
    if driver_type == 'ant':
        # Муравьи регистрируются БЕЗ марки авто и госномера
        db.set_telegram_session_data(user_id, 'car_model', 'Муравей')
        db.set_telegram_session_data(user_id, 'plate', '—')
        db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_CONFIRM)
        
        # Собираем данные для подтверждения
        session = db.get_telegram_session(user_id)
        temp_data = session.get('temp_data', {})
        
        msg = config.DRIVER_REG_CONFIRM_TEMPLATE_ANT.format(
            type_emoji='🐜',
            driver_type=config.DRIVER_TYPES.get('ant', 'Муравей'),
            name=temp_data.get('name', ''),
            phone=phone
        )
        
        buttons = [
            {"text": "✅ Да, всё верно", "callback": "dreg_confirm_yes"},
            {"text": "❌ Нет, начать заново", "callback": "dreg_confirm_no"}
        ]
        
        send_telegram_private(user_id, msg, buttons)
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_CAR)
    
    if driver_type == 'porter':
        prompt = config.DRIVER_REG_CAR_PROMPT_PORTER
    else:
        prompt = config.DRIVER_REG_CAR_PROMPT_TAXI
    
    send_telegram_private(user_id, prompt)
    return jsonify({"status": "ok"}), 200


def _handle_reg_car(user_id: str, text: str, db) -> tuple:
    """Шаг 4: Ввод марки авто"""
    
    if len(text) < 2:
        send_telegram_private(user_id, "⚠️ Введите марку и модель вашего транспорта.")
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_data(user_id, 'car_model', text)
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_PLATE)
    
    send_telegram_private(user_id, config.DRIVER_REG_PLATE_PROMPT)
    return jsonify({"status": "ok"}), 200


def _handle_reg_plate(user_id: str, text: str, db) -> tuple:
    """Шаг 5: Ввод госномера"""
    
    if len(text) < 3:
        send_telegram_private(user_id, "⚠️ Введите государственный номер вашего транспорта.")
        return jsonify({"status": "ok"}), 200
    
    db.set_telegram_session_data(user_id, 'plate', text.upper())
    db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_CONFIRM)
    
    # Собираем все данные для подтверждения
    session = db.get_telegram_session(user_id)
    temp_data = session.get('temp_data', {})
    
    driver_type_key = temp_data.get('driver_type', 'taxi')
    type_emoji = config.DRIVER_TYPES.get(driver_type_key, '🚖 Такси').split(' ')[0]
    
    msg = config.DRIVER_REG_CONFIRM_TEMPLATE.format(
        type_emoji=type_emoji,
        driver_type=config.DRIVER_TYPES.get(driver_type_key, driver_type_key),
        name=temp_data.get('name', ''),
        phone=temp_data.get('phone', ''),
        car_model=temp_data.get('car_model', ''),
        plate=text.upper()
    )
    
    buttons = [
        {"text": "✅ Да, всё верно", "callback": "dreg_confirm_yes"},
        {"text": "❌ Нет, начать заново", "callback": "dreg_confirm_no"}
    ]
    
    send_telegram_private(user_id, msg, buttons)
    return jsonify({"status": "ok"}), 200


def _handle_reg_confirm(user_id: str, text: str, db) -> tuple:
    """Шаг 6: Подтверждение регистрации"""
    text_lower = text.lower().strip()
    
    if text_lower in ('да', 'yes', 'ооба', 'верно', 'ок', 'ok', '✅'):
        return _save_driver_registration(user_id, db)
    
    elif text_lower in ('нет', 'no', 'жок', 'неверно', '❌'):
        # Начинаем заново
        db.create_telegram_session(user_id)
        db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_TYPE)
        
        buttons = [
            {"text": "🚖 Такси", "callback": "dreg_type_taxi"},
            {"text": "🚛 Портер", "callback": "dreg_type_porter"},
            {"text": "🐜 Муравей", "callback": "dreg_type_ant"}
        ]
        
        send_telegram_private(
            user_id, 
            "🔄 Начинаем заново.\n\n" + config.DRIVER_REG_TYPE_PROMPT,
            buttons
        )
        return jsonify({"status": "ok"}), 200
    
    else:
        send_telegram_private(user_id, "⚠️ Напишите *Да* или *Нет*.")
        return jsonify({"status": "ok"}), 200


def _save_driver_registration(user_id: str, db) -> tuple:
    """Сохранение регистрации водителя"""
    
    session = db.get_telegram_session(user_id)
    temp_data = session.get('temp_data', {})
    
    driver_type = temp_data.get('driver_type', 'taxi')
    name = temp_data.get('name', '')
    phone = temp_data.get('phone', '')
    car_model = temp_data.get('car_model', '')
    plate = temp_data.get('plate', '')
    
    # Сохраняем водителя
    db.add_driver(
        telegram_id=user_id,
        name=name,
        phone=phone,
        car_model=car_model,
        plate=plate,
        driver_type=driver_type
    )
    
    # Очищаем сессию
    db.clear_telegram_session(user_id)
    
    # Получаем баланс
    balance = db.get_driver_balance(user_id)
    
    # Определяем ссылку на группу
    group_link = "https://t.me/jardamchy_go"  # Fallback
    if driver_type == 'taxi':
        group_link = "https://t.me/+ZhceAJUcbmJjODAy"  # ЗАМЕНИТЬ НА РЕАЛЬНУЮ ССЫЛКУ ТАКСИ
    elif driver_type == 'porter':
        group_link = "https://t.me/+l88NvbDcTWg1MThi"  # ЗАМЕНИТЬ НА РЕАЛЬНУЮ ССЫЛКУ ПОРТЕР
    elif driver_type == 'ant':
        group_link = "https://t.me/+l88NvbDcTWg1MThi"  # ЗАМЕНИТЬ НА РЕАЛЬНУЮ ССЫЛКУ МУРАВЕЙ
        
    msg = config.DRIVER_REG_SUCCESS.format(
        driver_type=config.DRIVER_TYPES.get(driver_type, driver_type),
        balance=balance,
        group_link=group_link
    )
    
    send_telegram_private(user_id, msg)
    
    # Логируем
    db.log_transaction(
        "DRIVER_SELF_REGISTERED",
        user_id,
        details=f"Type: {driver_type}, Name: {name}, Car: {car_model} {plate}"
    )
    
    logger.info(f"New driver registered: {name} ({user_id}) - {driver_type}")
    
    return jsonify({"status": "ok"}), 200


# =============================================================================
# ОБРАБОТКА CALLBACK КНОПОК РЕГИСТРАЦИИ
# =============================================================================

def handle_driver_reg_callback(data: str, user_id: str, user_name: str, db) -> tuple:
    """Обработка нажатия кнопок регистрации водителя"""
    try:
        # dreg_type_taxi, dreg_type_porter, dreg_type_ant
        if data.startswith("dreg_type_"):
            driver_type = data.replace("dreg_type_", "")
            
            if driver_type not in ('taxi', 'porter', 'ant'):
                return jsonify({"status": "ok"}), 200
            
            db.set_telegram_session_data(user_id, 'driver_type', driver_type)
            db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_NAME)
            
            type_name = config.DRIVER_TYPES.get(driver_type, driver_type)
            send_telegram_private(
                user_id, 
                f"✅ Выбран тип: *{type_name}*\n\n" + config.DRIVER_REG_NAME_PROMPT
            )
            return jsonify({"status": "ok"}), 200
        
        # dreg_confirm_yes, dreg_confirm_no
        elif data == "dreg_confirm_yes":
            return _save_driver_registration(user_id, db)
        
        elif data == "dreg_confirm_no":
            db.create_telegram_session(user_id)
            db.set_telegram_session_state(user_id, config.STATE_DRIVER_REG_TYPE)
            
            buttons = [
                {"text": "🚖 Такси", "callback": "dreg_type_taxi"},
                {"text": "🚛 Портер", "callback": "dreg_type_porter"},
                {"text": "🐜 Муравей", "callback": "dreg_type_ant"}
            ]
            
            send_telegram_private(
                user_id, 
                "🔄 Начинаем заново.\n\n" + config.DRIVER_REG_TYPE_PROMPT,
                buttons
            )
            return jsonify({"status": "ok"}), 200
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("Error handling driver registration callback")
        return jsonify({"status": "error", "message": str(e)}), 500
