"""
Обработчик подтверждений от клиента (WhatsApp)
Client Confirmation Handler for Business Assistant GO
Обновленная версия согласно ТЗ v2.0
"""

import logging
from typing import Tuple

import config
from db import get_db, User
from services import send_whatsapp, send_telegram_group

logger = logging.getLogger(__name__)


# =============================================================================
# PHARMACY CONFIRMATION
# =============================================================================

def handle_pharmacy_client_confirm(user: User, response: str, db) -> Tuple[dict, int]:
    """Обработка подтверждения/отмены заказа аптеки клиентом"""
    try:
        # Определяем действие
        if "yes" in response.lower() or "да" in response.lower() or "ооба" in response.lower():
            return _confirm_pharmacy_order(user, db)
        else:
            return _cancel_pharmacy_order(user, db)
        
    except Exception as e:
        logger.exception("Error handling pharmacy client confirm")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500


def _confirm_pharmacy_order(user: User, db) -> Tuple[dict, int]:
    """Подтверждение заказа аптеки"""
    try:
        # Получаем ID заказа из временных данных
        order_id = user.get_temp_data('pharmacy_order_id')
        
        if not order_id:
            send_whatsapp(user.phone, "❌ Ошибка: заказ не найден.")
            user.set_state(config.STATE_IDLE)
            return {"status": "error", "message": "Order not found"}, 404
        
        # Получаем заказ
        order = db.get_order(order_id)
        if not order:
            send_whatsapp(user.phone, "❌ Заказ не найден.")
            user.set_state(config.STATE_IDLE)
            return {"status": "error", "message": "Order not found"}, 404
        
        # Получаем выбранное предложение аптеки
        bids = db.get_pharmacy_bids(order_id)
        selected_bid = None
        
        for bid in bids:
            if bid.get('is_selected'):
                selected_bid = bid
                break
        
        # Если нет выбранного, берем первое (самое дешевое)
        if not selected_bid and bids:
            selected_bid = bids[0]
        
        if not selected_bid:
            send_whatsapp(user.phone, "❌ Ошибка: предложение аптеки не найдено.")
            user.set_state(config.STATE_IDLE)
            return {"status": "error", "message": "Bid not found"}, 404
        
        drug_price = float(selected_bid['price'])
        # Цена для клиента: лекарство + доставка + комиссия таксиста
        total_price = drug_price + config.PHARMACY_DELIVERY_FEE + config.TAXI_PHARMACY_COMMISSION
        
        # Обновляем заказ
        db.update_order_status(
            order_id, 
            config.ORDER_STATUS_READY,
            provider_id=selected_bid['pharmacy_id'],
            price=total_price
        )
        
        # Формируем заявку для таксистов
        taxi_msg = f"""💊 *ЗАКАЗ АПТЕКА (ДОСТАВКА)*

📋 *Детали:*
{order.get('details', '')}

💵 *Надо выкупить:* {drug_price} сом
💰 *С клиента взять:* {total_price} сом (включая комиссию {config.TAXI_PHARMACY_COMMISSION} сом)
📞 *Клиент:* {user.phone}

💳 *Оплата:* МБанк / Наличные

⚠️ *Важно:* Позвоните клиенту для предоплаты на МБанк, если нет своих денег на выкуп."""
        
        buttons = [{
            "text": "🚖 Взять заказ",
            "callback": f"delivery_take_{order_id}"
        }]
        
        send_telegram_group(config.GROUP_TAXI_ID, taxi_msg, buttons)
        
        # Сбрасываем состояние
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        
        # Отправляем подтверждение клиенту
        response_msg = f"""✅ *Заказ подтвержден!*

💊 Лекарство будет доставлено.
🚖 Ищем курьера...

💰 К оплате: *{total_price} сом*
(лекарство {drug_price} сом + доставка {config.PHARMACY_DELIVERY_FEE} сом + комиссия {config.TAXI_PHARMACY_COMMISSION} сом)

⏱ Ожидайте, курьер скоро свяжется."""
        
        send_whatsapp(user.phone, response_msg)
        
        # Уведомляем аптеку
        pharmacy_msg = f"""✅ *Заказ подтвержден клиентом!*

💊 *Лекарство:* {order.get('details', '')[:50]}
💵 *Цена:* {drug_price} сом

🚖 Курьер заберет у вас.
📞 Клиент: {user.phone}"""
        
        send_telegram_private(selected_bid['pharmacy_id'], pharmacy_msg)
        
        db.log_transaction(
            "PHARMACY_ORDER_CONFIRMED",
            user.phone,
            order_id,
            amount=total_price,
            details=f"Drug: {drug_price}, Delivery: {config.PHARMACY_DELIVERY_FEE}, Commission: {config.TAXI_PHARMACY_COMMISSION}"
        )
        
        return {"status": "ok", "message": "Pharmacy order confirmed"}, 200
        
    except Exception as e:
        logger.exception("Error confirming pharmacy order")
        send_whatsapp(user.phone, "❌ Произошла ошибка. Попробуйте еще раз.")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500


def _cancel_pharmacy_order(user: User, db) -> Tuple[dict, int]:
    """Отмена заказа аптеки"""
    try:
        order_id = user.get_temp_data('pharmacy_order_id')
        
        if order_id:
            db.update_order_status(order_id, config.ORDER_STATUS_CANCELLED)
            
            db.log_transaction(
                "PHARMACY_ORDER_CANCELLED",
                user.phone,
                order_id,
                details="Client cancelled"
            )
        
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        
        send_whatsapp(user.phone, "❌ Заказ отменен.\n\nЕсли передумаете - начните заново.")
        
        return {"status": "ok", "message": "Order cancelled"}, 200
        
    except Exception as e:
        logger.exception("Error cancelling pharmacy order")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500


# =============================================================================
# SHOP CONFIRMATION (если нужно дополнительное подтверждение)
# =============================================================================

def handle_shop_client_confirm(user: User, response: str, db) -> Tuple[dict, int]:
    """Обработка подтверждения заказа магазина клиентом"""
    try:
        msg_lower = response.lower()
        
        if any(word in msg_lower for word in ["да", "yes", "ооба"]):
            return _confirm_shop_order(user, db)
        else:
            return _cancel_shop_order(user, db)
        
    except Exception as e:
        logger.exception("Error handling shop client confirm")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500


def _confirm_shop_order(user: User, db) -> Tuple[dict, int]:
    """Подтверждение заказа магазина"""
    try:
        shop_list = user.get_temp_data('shop_list')
        
        if not shop_list:
            send_whatsapp(user.phone, "❌ Список покупок не найден.")
            user.set_state(config.STATE_IDLE)
            return {"status": "error", "message": "Shop list not found"}, 404
        
        # Создаем заказ
        order_id = db.create_order(
            client_phone=user.phone,
            service_type=config.SERVICE_SHOP,
            details=shop_list
        )
        
        # Отправляем закупщику
        shopper = db.get_shopper()
        
        if shopper:
            msg = f"""🛒 *НОВЫЙ ЗАКАЗ (Магазин)*

📋 *Список:*
{shop_list}

📞 *Клиент:* {user.phone}
💰 *Ваш заработок:* {config.SHOPPER_SERVICE_FEE} сом"""
            
            from services import send_telegram_private
            buttons = [{
                "text": "🛒 Взять в работу",
                "callback": f"shop_take_{order_id}"
            }]
            
            send_telegram_private(shopper['telegram_id'], msg, buttons)
        
        user.set_state(config.STATE_IDLE)
        user.clear_temp_data()
        
        response_msg = f"""✅ *Заказ подтвержден!*

🛒 Список передан закупщику.

💰 Услуга: *{config.SHOPPER_SERVICE_FEE} сом*
📦 Товары: по чеку

⏱ Закупщик скоро свяжется."""
        
        send_whatsapp(user.phone, response_msg)
        
        db.log_transaction("SHOP_ORDER_CONFIRMED", user.phone, order_id)
        
        return {"status": "ok"}, 200
        
    except Exception as e:
        logger.exception("Error confirming shop order")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500


def _cancel_shop_order(user: User, db) -> Tuple[dict, int]:
    """Отмена заказа магазина"""
    user.set_state(config.STATE_IDLE)
    user.clear_temp_data()
    send_whatsapp(user.phone, "❌ Заказ отменен.")
    return {"status": "ok"}, 200


# =============================================================================
# GENERAL CONFIRMATION HANDLER
# =============================================================================

def handle_confirmation(user: User, response: str, db) -> Tuple[dict, int]:
    """Общий обработчик подтверждений"""
    try:
        if user.current_state == config.STATE_PHARMACY_CONFIRM:
            return handle_pharmacy_client_confirm(user, response, db)
        elif user.current_state == config.STATE_SHOP_CONFIRM:
            return handle_shop_client_confirm(user, response, db)
        
        user.set_state(config.STATE_IDLE)
        send_whatsapp(user.phone, config.WELCOME_MESSAGE)
        
        return {"status": "ok"}, 200
        
    except Exception as e:
        logger.exception("Error handling confirmation")
        user.set_state(config.STATE_IDLE)
        return {"status": "error", "message": str(e)}, 500
