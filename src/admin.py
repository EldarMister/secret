"""
Модуль администрирования для Business Assistant GO
Admin Module — расширенная версия с визуальной админкой
"""

from flask import Blueprint, request, jsonify, send_from_directory
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import config
from db import get_db
from services import send_telegram_private, send_telegram_broadcast, send_telegram_group

logger = logging.getLogger(__name__)

# Создаем Blueprint для админских роутов
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Путь к файлам админ-панели
ADMIN_PANEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'admin_panel')


def is_admin(telegram_id: str) -> bool:
    """Проверить, является ли пользователь администратором"""
    return telegram_id in config.ADMIN_TELEGRAM_IDS


def _serialize(obj):
    """Сериализация объектов для JSON"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def _clean_row(row):
    """Очистить строку от несериализуемых типов"""
    if not row:
        return row
    return {k: _serialize(v) for k, v in row.items()}


def _clean_rows(rows):
    """Очистить список строк"""
    return [_clean_row(r) for r in rows]


# =============================================================================
# ADMIN PANEL STATIC FILES
# =============================================================================

@admin_bp.route('/panel')
@admin_bp.route('/panel/')
def serve_panel():
    """Отдать главную страницу админки"""
    return send_from_directory(ADMIN_PANEL_DIR, 'index.html')


@admin_bp.route('/panel/<path:filename>')
def serve_panel_file(filename):
    """Отдать статические файлы админки"""
    return send_from_directory(ADMIN_PANEL_DIR, filename)


# =============================================================================
# DASHBOARD
# =============================================================================

@admin_bp.route('/dashboard', methods=['GET'])
def get_dashboard():
    """Агрегированная статистика для дашборда"""
    try:
        db = get_db()

        # --- Заказы и заработок по периодам ---
        with db.get_cursor() as cur:
            # Сегодня
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed,
                    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) as cancelled,
                    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending,
                    COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN price_total ELSE 0 END), 0) as revenue,
                    COALESCE(SUM(commission), 0) as commission
                FROM orders WHERE DATE(created_at) = CURRENT_DATE
            """)
            today = _clean_row(cur.fetchone())

            # Неделя
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed,
                    COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN price_total ELSE 0 END), 0) as revenue,
                    COALESCE(SUM(commission), 0) as commission
                FROM orders WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            week = _clean_row(cur.fetchone())

            # Месяц
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed,
                    COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN price_total ELSE 0 END), 0) as revenue,
                    COALESCE(SUM(commission), 0) as commission
                FROM orders WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
            """)
            month = _clean_row(cur.fetchone())

            # Все время
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed,
                    COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN price_total ELSE 0 END), 0) as revenue,
                    COALESCE(SUM(commission), 0) as commission
                FROM orders
            """)
            all_time = _clean_row(cur.fetchone())

            # По типам услуг
            cur.execute("""
                SELECT 
                    service_type,
                    COUNT(*) as count,
                    COALESCE(SUM(price_total), 0) as revenue
                FROM orders 
                GROUP BY service_type
            """)
            by_service = _clean_rows(cur.fetchall())

            # Заказы по дням за последние 7 дней
            cur.execute("""
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as count,
                    COALESCE(SUM(CASE WHEN status = 'COMPLETED' THEN price_total ELSE 0 END), 0) as revenue
                FROM orders 
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(created_at)
                ORDER BY date
            """)
            daily_chart = _clean_rows(cur.fetchall())

            # Кол-во сущностей
            cur.execute("SELECT COUNT(*) as count FROM drivers WHERE is_active = TRUE")
            drivers_count = cur.fetchone()['count']

            cur.execute("SELECT COUNT(*) as count FROM cafes WHERE is_active = TRUE")
            cafes_count = cur.fetchone()['count']

            cur.execute("SELECT COUNT(*) as count FROM users")
            users_count = cur.fetchone()['count']

            cur.execute("SELECT COUNT(*) as count FROM pharmacies WHERE is_active = TRUE")
            pharmacies_count = cur.fetchone()['count']

        return jsonify({
            "today": today,
            "week": week,
            "month": month,
            "all_time": all_time,
            "by_service": by_service,
            "daily_chart": daily_chart,
            "counts": {
                "drivers": drivers_count,
                "cafes": cafes_count,
                "users": users_count,
                "pharmacies": pharmacies_count
            },
            "ramadan_mode": config.IS_RAMADAN
        }), 200

    except Exception as e:
        logger.exception("Error getting dashboard")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# DRIVER MANAGEMENT
# =============================================================================

@admin_bp.route('/drivers', methods=['GET'])
def list_drivers():
    """Получить список водителей"""
    try:
        db = get_db()
        driver_type = request.args.get('type')
        active_only = request.args.get('active', 'true').lower() == 'true'
        drivers = db.list_drivers(driver_type=driver_type, active_only=active_only)

        # Добавляем статистику заказов к каждому водителю
        for d in drivers:
            stats = db.get_driver_order_stats(d['telegram_id'])
            d['order_stats'] = _clean_row(stats)

        return jsonify({
            "count": len(drivers),
            "drivers": _clean_rows(drivers)
        }), 200

    except Exception as e:
        logger.exception("Error listing drivers")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/drivers', methods=['POST'])
def add_driver():
    """Добавить нового водителя"""
    try:
        data = request.get_json()

        telegram_id = data.get('telegram_id')
        name = data.get('name')
        phone = data.get('phone')
        car_model = data.get('car_model')
        plate = data.get('plate')
        driver_type = data.get('type', 'taxi')

        if not telegram_id or not name:
            return jsonify({"error": "telegram_id and name are required"}), 400

        db = get_db()
        success = db.add_driver(telegram_id, name, phone, car_model, plate, driver_type)

        if success:
            welcome_msg = f"""✅ *Вы добавлены в систему Жардамчы ГО!*

👤 *Имя:* {name}
🚗 *Тип:* {driver_type}

Теперь вы можете принимать заказы в группе.

💰 Не забудьте пополнить баланс для приема заказов."""

            send_telegram_private(telegram_id, welcome_msg)

            return jsonify({"success": True, "message": "Driver added successfully"}), 201
        else:
            return jsonify({"error": "Failed to add driver"}), 500

    except Exception as e:
        logger.exception("Error adding driver")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/drivers/<telegram_id>', methods=['PUT'])
def update_driver(telegram_id):
    """Обновить данные водителя"""
    try:
        data = request.get_json()

        name = data.get('name')
        phone = data.get('phone')
        car_model = data.get('car_model')
        plate = data.get('plate')

        db = get_db()
        success = db.update_driver_info(
            telegram_id,
            name=name,
            phone=phone,
            car_model=car_model,
            plate=plate
        )

        if success:
            return jsonify({"success": True, "message": "Driver updated"}), 200
        else:
            return jsonify({"error": "Driver not found or no changes"}), 404

    except Exception as e:
        logger.exception("Error updating driver")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/drivers/<telegram_id>', methods=['DELETE'])
def remove_driver(telegram_id):
    """Удалить водителя"""
    try:
        db = get_db()
        success = db.remove_driver(telegram_id)

        if success:
            msg = "❌ Вы удалены из системы Жардамчы ГО.\n\nОбратитесь к администратору для уточнения."
            send_telegram_private(telegram_id, msg)

            return jsonify({"success": True, "message": "Driver removed"}), 200
        else:
            return jsonify({"error": "Driver not found"}), 404

    except Exception as e:
        logger.exception("Error removing driver")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/drivers/<telegram_id>/balance', methods=['POST'])
def update_driver_balance(telegram_id):
    """Обновить баланс водителя"""
    try:
        data = request.get_json()
        amount = data.get('amount')
        reason = data.get('reason', 'Пополнение через админку')

        if amount is None:
            return jsonify({"error": "amount is required"}), 400

        db = get_db()
        success, new_balance = db.update_driver_balance(telegram_id, amount, reason)

        if success:
            action = "пополнен" if amount > 0 else "списан"
            msg = f"""💰 *Баланс {action}*

Сумма: {abs(amount)} сом
Причина: {reason}

💳 Новый баланс: {new_balance} сом"""

            send_telegram_private(telegram_id, msg)

            return jsonify({
                "success": True,
                "new_balance": float(new_balance)
            }), 200
        else:
            return jsonify({"error": "Insufficient balance or driver not found"}), 400

    except Exception as e:
        logger.exception("Error updating driver balance")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# CAFE MANAGEMENT
# =============================================================================

@admin_bp.route('/cafes', methods=['GET'])
def list_cafes():
    """Получить список кафе"""
    try:
        db = get_db()
        cafes = db.list_cafes(active_only=False)

        return jsonify({
            "count": len(cafes),
            "cafes": _clean_rows(cafes)
        }), 200

    except Exception as e:
        logger.exception("Error listing cafes")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/cafes', methods=['POST'])
def add_cafe():
    """Добавить новое кафе"""
    try:
        data = request.get_json()

        telegram_id = data.get('telegram_id')
        name = data.get('name')
        phone = data.get('phone')
        address = data.get('address')

        if not telegram_id or not name:
            return jsonify({"error": "telegram_id and name are required"}), 400

        db = get_db()
        success = db.add_cafe(telegram_id, name, phone, address)

        if success:
            welcome_msg = f"""✅ *{name} добавлено в систему Жардамчы ГО!*

Теперь вы будете получать заказы в группе.

💰 Комиссия: {config.CAFE_COMMISSION_PERCENT}% от суммы заказа."""

            send_telegram_private(telegram_id, welcome_msg)

            return jsonify({"success": True, "message": "Cafe added successfully"}), 201
        else:
            return jsonify({"error": "Failed to add cafe"}), 500

    except Exception as e:
        logger.exception("Error adding cafe")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/cafes/<telegram_id>', methods=['PUT'])
def update_cafe(telegram_id):
    """Обновить данные кафе"""
    try:
        data = request.get_json()

        name = data.get('name')
        phone = data.get('phone')
        address = data.get('address')
        commission_percent = data.get('commission_percent')
        is_active = data.get('is_active')

        db = get_db()
        success = db.update_cafe_info(
            telegram_id,
            name=name,
            phone=phone,
            address=address,
            commission_percent=commission_percent,
            is_active=is_active
        )

        if success:
            return jsonify({"success": True, "message": "Cafe updated"}), 200
        else:
            return jsonify({"error": "Cafe not found or no changes"}), 404

    except Exception as e:
        logger.exception("Error updating cafe")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/cafes/<telegram_id>', methods=['DELETE'])
def remove_cafe(telegram_id):
    """Деактивировать/удалить кафе"""
    try:
        db = get_db()
        success = db.remove_cafe(telegram_id)

        if success:
            return jsonify({"success": True, "message": "Cafe removed"}), 200
        else:
            return jsonify({"error": "Cafe not found"}), 404

    except Exception as e:
        logger.exception("Error removing cafe")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/cafes/<telegram_id>/debt', methods=['GET'])
def get_cafe_debt(telegram_id):
    """Получить долг кафе"""
    try:
        db = get_db()
        debt = db.get_cafe_debt(telegram_id)

        return jsonify({"debt": float(debt)}), 200

    except Exception as e:
        logger.exception("Error getting cafe debt")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# ORDERS MANAGEMENT
# =============================================================================

@admin_bp.route('/orders', methods=['GET'])
def list_orders():
    """Получить список заказов с фильтрацией"""
    try:
        db = get_db()
        status = request.args.get('status')
        service = request.args.get('service')
        period = request.args.get('period', 'all')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        with db.get_cursor() as cur:
            query = "SELECT * FROM orders WHERE 1=1"
            count_query = "SELECT COUNT(*) as total FROM orders WHERE 1=1"
            params = []
            count_params = []

            if status:
                query += " AND status = %s"
                count_query += " AND status = %s"
                params.append(status)
                count_params.append(status)

            if service:
                query += " AND service_type = %s"
                count_query += " AND service_type = %s"
                params.append(service)
                count_params.append(service)

            if period == 'day':
                query += " AND DATE(created_at) = CURRENT_DATE"
                count_query += " AND DATE(created_at) = CURRENT_DATE"
            elif period == 'week':
                query += " AND created_at >= CURRENT_DATE - INTERVAL '7 days'"
                count_query += " AND created_at >= CURRENT_DATE - INTERVAL '7 days'"
            elif period == 'month':
                query += " AND created_at >= CURRENT_DATE - INTERVAL '30 days'"
                count_query += " AND created_at >= CURRENT_DATE - INTERVAL '30 days'"

            # Count
            cur.execute(count_query, count_params)
            total = cur.fetchone()['total']

            # Data
            query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cur.execute(query, params)
            orders = _clean_rows([dict(row) for row in cur.fetchall()])

        return jsonify({
            "total": total,
            "count": len(orders),
            "orders": orders
        }), 200

    except Exception as e:
        logger.exception("Error listing orders")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/orders/<order_id>', methods=['GET'])
def get_order_detail(order_id):
    """Получить детали заказа"""
    try:
        db = get_db()
        order = db.get_order(order_id)
        if not order:
            return jsonify({"error": "Order not found"}), 404

        return jsonify({"order": _clean_row(order)}), 200

    except Exception as e:
        logger.exception("Error getting order")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# PHARMACIES
# =============================================================================

@admin_bp.route('/pharmacies', methods=['GET'])
def list_pharmacies():
    """Получить список аптек"""
    try:
        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("SELECT * FROM pharmacies ORDER BY name")
            pharmacies = _clean_rows([dict(row) for row in cur.fetchall()])

        return jsonify({
            "count": len(pharmacies),
            "pharmacies": pharmacies
        }), 200

    except Exception as e:
        logger.exception("Error listing pharmacies")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/pharmacies', methods=['POST'])
def add_pharmacy():
    """Добавить новую аптеку"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        name = data.get('name')
        phone = data.get('phone', '')
        address = data.get('address', '')

        if not telegram_id or not name:
            return jsonify({"error": "telegram_id and name are required"}), 400

        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("""
                INSERT INTO pharmacies (telegram_id, name, phone, address, is_active, created_at)
                VALUES (%s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_id) DO UPDATE SET name = %s, phone = %s, address = %s, is_active = TRUE
            """, (telegram_id, name, phone, address, name, phone, address))

        send_telegram_private(telegram_id, f"✅ *{name}* добавлена в систему Жардамчы ГО!")

        return jsonify({"success": True, "message": "Pharmacy added"}), 201

    except Exception as e:
        logger.exception("Error adding pharmacy")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/pharmacies/<telegram_id>', methods=['DELETE'])
def remove_pharmacy(telegram_id):
    """Удалить аптеку"""
    try:
        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("UPDATE pharmacies SET is_active = FALSE WHERE telegram_id = %s", (telegram_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Pharmacy not found"}), 404

        return jsonify({"success": True, "message": "Pharmacy removed"}), 200

    except Exception as e:
        logger.exception("Error removing pharmacy")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# SHOPPERS
# =============================================================================

@admin_bp.route('/shoppers', methods=['GET'])
def list_shoppers():
    """Получить список закупщиков"""
    try:
        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("SELECT * FROM shoppers ORDER BY name")
            shoppers = _clean_rows([dict(row) for row in cur.fetchall()])

        return jsonify({
            "count": len(shoppers),
            "shoppers": shoppers
        }), 200

    except Exception as e:
        logger.exception("Error listing shoppers")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/shoppers', methods=['POST'])
def add_shopper():
    """Добавить нового закупщика"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        name = data.get('name')
        phone = data.get('phone', '')

        if not telegram_id or not name:
            return jsonify({"error": "telegram_id and name are required"}), 400

        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("""
                INSERT INTO shoppers (telegram_id, name, phone, is_active, balance, created_at)
                VALUES (%s, %s, %s, TRUE, 0, CURRENT_TIMESTAMP)
                ON CONFLICT (telegram_id) DO UPDATE SET name = %s, phone = %s, is_active = TRUE
            """, (telegram_id, name, phone, name, phone))

        send_telegram_private(telegram_id, f"✅ *{name}*, вы добавлены в систему Жардамчы ГО как закупщик!")

        return jsonify({"success": True, "message": "Shopper added"}), 201

    except Exception as e:
        logger.exception("Error adding shopper")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/shoppers/<telegram_id>', methods=['DELETE'])
def remove_shopper(telegram_id):
    """Удалить закупщика"""
    try:
        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("UPDATE shoppers SET is_active = FALSE WHERE telegram_id = %s", (telegram_id,))
            if cur.rowcount == 0:
                return jsonify({"error": "Shopper not found"}), 404

        return jsonify({"success": True, "message": "Shopper removed"}), 200

    except Exception as e:
        logger.exception("Error removing shopper")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# USERS (WhatsApp)
# =============================================================================

@admin_bp.route('/users', methods=['GET'])
def list_users():
    """Получить список WhatsApp пользователей"""
    try:
        db = get_db()
        with db.get_cursor() as cur:
            cur.execute("""
                SELECT u.*, 
                    (SELECT COUNT(*) FROM orders WHERE client_phone = u.phone) as order_count
                FROM users u
                ORDER BY u.created_at DESC
                LIMIT 200
            """)
            users = _clean_rows([dict(row) for row in cur.fetchall()])

        return jsonify({
            "count": len(users),
            "users": users
        }), 200

    except Exception as e:
        logger.exception("Error listing users")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# BROADCAST
# =============================================================================

@admin_bp.route('/broadcast', methods=['POST'])
def broadcast_message():
    """Рассылка сообщения всем выбранным группам и чатам"""
    try:
        data = request.get_json()
        message = data.get('message')
        targets = data.get('targets', [])  # Expecting a list: ['drivers', 'group_taxi', ...]

        if not message:
            return jsonify({"error": "message is required"}), 400
        
        if not targets:
             return jsonify({"error": "No targets selected"}), 400

        db = get_db()
        recipient_ids = set()
        group_ids = []

        # Helper to get IDs
        def get_ids(table):
            with db.get_cursor() as cur:
                cur.execute(f"SELECT telegram_id FROM {table} WHERE is_active = TRUE")
                return [row['telegram_id'] for row in cur.fetchall()]

        # --- Private Chats ---
        if 'drivers' in targets:
            recipient_ids.update(get_ids('drivers'))
        
        if 'cafes' in targets:
            recipient_ids.update(get_ids('cafes'))
            
        if 'pharmacies' in targets:
            recipient_ids.update(get_ids('pharmacies'))
            
        if 'shoppers' in targets:
            recipient_ids.update(get_ids('shoppers'))
            
        # --- Telegram Groups ---
        if 'group_taxi' in targets:
            group_ids.append(config.GROUP_TAXI_ID)
            
        if 'group_cafe' in targets:
            group_ids.append(config.GROUP_CAFE_ID)
            
        if 'group_porter' in targets:
            group_ids.append(config.GROUP_PORTER_ID)
            
        if 'group_ant' in targets:
            # Avoid duplicate if Ant group is same as Porter group
            if config.GROUP_ANT_ID != config.GROUP_PORTER_ID or 'group_porter' not in targets:
                group_ids.append(config.GROUP_ANT_ID)
                
        if 'group_pharmacy' in targets:
            group_ids.append(config.GROUP_PHARMACY_ID)
            
        if 'group_shop' in targets:
            group_ids.append(config.GROUP_SHOP_ID)

        # Send broadcast to private users
        results = send_telegram_broadcast(list(recipient_ids), message)
        
        # Send broadcast to groups
        group_success = 0
        group_failed = 0
        
        for chat_id in group_ids:
            try:
                # Use send_telegram_group from services
                if send_telegram_group(chat_id, message):
                    group_success += 1
                else:
                    group_failed += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to group {chat_id}: {e}")
                group_failed += 1

        successful = sum(1 for v in results.values() if v)
        failed = len(results) - successful

        db.log_transaction(
            "BROADCAST_SENT",
            details=f"Targets: {', '.join(targets)}. Users: {successful}/{len(recipient_ids)}. Groups: {group_success}/{len(group_ids)}"
        )

        return jsonify({
            "success": True,
            "sent": successful + group_success,
            "failed": failed + group_failed,
            "total": len(results) + len(group_ids),
            "groups_sent": group_success
        }), 200

    except Exception as e:
        logger.exception("Error broadcasting message")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# STATISTICS
# =============================================================================

@admin_bp.route('/stats', methods=['GET'])
def get_statistics():
    """Получить статистику"""
    try:
        db = get_db()

        daily_stats = db.get_daily_stats()
        service_stats = db.get_service_stats(days=7)

        return jsonify({
            "today": _clean_row(daily_stats),
            "weekly_by_service": _clean_rows(service_stats),
            "ramadan_mode": config.IS_RAMADAN
        }), 200

    except Exception as e:
        logger.exception("Error getting statistics")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/transactions', methods=['GET'])
def get_transactions():
    """Получить историю транзакций"""
    try:
        db = get_db()
        user_id = request.args.get('user_id')
        limit = request.args.get('limit', 100, type=int)

        transactions = db.get_transactions(user_id=user_id, limit=limit)

        return jsonify({
            "count": len(transactions),
            "transactions": _clean_rows(transactions)
        }), 200

    except Exception as e:
        logger.exception("Error getting transactions")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# SETTINGS
# =============================================================================

@admin_bp.route('/settings', methods=['GET'])
def get_settings():
    """Получить текущие настройки"""
    try:
        return jsonify({
            "is_ramadan": config.IS_RAMADAN,
            "cafe_commission": config.CAFE_COMMISSION_PERCENT,
            "taxi_commission": config.TAXI_COMMISSION,
            "porter_commission": config.PORTER_COMMISSION,
            "shopper_fee": config.SHOPPER_SERVICE_FEE,
            "pharmacy_delivery_fee": config.PHARMACY_DELIVERY_FEE
        }), 200

    except Exception as e:
        logger.exception("Error getting settings")
        return jsonify({"error": str(e)}), 500


@admin_bp.route('/settings/ramadan', methods=['POST'])
def toggle_ramadan_mode():
    """Переключить режим Рамазан"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)

        mode_str = "включен" if enabled else "выключен"

        db = get_db()
        db.log_transaction(
            "RAMADAN_MODE_CHANGED",
            details=f"Ramadan mode {mode_str}"
        )

        return jsonify({
            "success": True,
            "message": f"Ramadan mode {mode_str}",
            "enabled": enabled
        }), 200

    except Exception as e:
        logger.exception("Error toggling ramadan mode")
        return jsonify({"error": str(e)}), 500
