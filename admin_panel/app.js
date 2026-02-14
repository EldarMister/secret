/**
 * ЖАРДАМЧЫ ГО — Admin Panel SPA
 * Полноценная визуальная админка
 */

// ============================================================================
// CONFIG
// ============================================================================

const API_BASE = '/admin';
const REFRESH_INTERVAL = 30000;

// Service type labels
const SERVICE_LABELS = {
    taxi: { icon: '🚖', name: 'Такси', cls: 'taxi' },
    cafe: { icon: '🍔', name: 'Кафе', cls: 'cafe' },
    porter: { icon: '🚛', name: 'Портер', cls: 'porter' },
    ant: { icon: '🐜', name: 'Муравей', cls: 'ant' },
    pharmacy: { icon: '💊', name: 'Аптека', cls: 'pharmacy' },
    shop: { icon: '🛒', name: 'Магазин', cls: 'shop' },
};

const STATUS_LABELS = {
    PENDING: { label: 'Ожидает', cls: 'warning' },
    AUCTION: { label: 'Аукцион', cls: 'info' },
    ACCEPTED: { label: 'Принят', cls: 'info' },
    READY: { label: 'Готов', cls: 'success' },
    IN_DELIVERY: { label: 'В доставке', cls: 'info' },
    COMPLETED: { label: 'Завершён', cls: 'success' },
    CANCELLED: { label: 'Отменён', cls: 'danger' },
    URGENT: { label: 'Срочный', cls: 'danger' },
};

const DRIVER_TYPE_LABELS = {
    taxi: { icon: '🚖', name: 'Такси' },
    porter: { icon: '🚛', name: 'Портер' },
    ant: { icon: '🐜', name: 'Муравей' },
};

const SERVICE_COLORS = {
    taxi: '#fdcb6e',
    cafe: '#ff7675',
    porter: '#e17055',
    ant: '#00cec9',
    pharmacy: '#74b9ff',
    shop: '#00b894',
};

// ============================================================================
// STATE
// ============================================================================

let currentSection = 'dashboard';
let dashboardData = null;
let statsPeriod = 'day';
let menuCategories = [];

// ============================================================================
// API HELPERS
// ============================================================================

async function api(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    try {
        const res = await fetch(url, { ...options, headers });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || `HTTP ${res.status}`);
        }
        return data;
    } catch (err) {
        console.error(`API error [${path}]:`, err);
        throw err;
    }
}

// ============================================================================
// NAVIGATION
// ============================================================================

const sectionTitles = {
    dashboard: '📊 Дашборд',
    orders: '📋 Заказы',
    drivers: '🚖 Водители',
    cafes: '🍔 Кафе',
    pharmacies: '💊 Аптеки',
    shoppers: '🛒 Закупщики',
    stats: '📈 Статистика',
    transactions: '💰 Транзакции',
    users: '👥 Пользователи',
    broadcast: '📢 Рассылка',
    settings: '⚙️ Настройки',
};

function navigate(section) {
    currentSection = section;

    document.querySelectorAll('.nav-item').forEach((el) => {
        el.classList.toggle('active', el.dataset.section === section);
    });

    document.querySelectorAll('.section').forEach((el) => {
        el.classList.toggle('active', el.id === `sec-${section}`);
    });

    document.getElementById('header-title').textContent = sectionTitles[section] || section;

    loadSectionData(section);
}

function loadSectionData(section) {
    switch (section) {
        case 'dashboard': loadDashboard(); break;
        case 'orders': loadOrders(); break;
        case 'drivers': loadDrivers(); break;
        case 'cafes': loadCafes(); break;
        case 'pharmacies': loadPharmacies(); break;
        case 'shoppers': loadShoppers(); break;
        case 'stats': loadStats(); break;
        case 'transactions': loadTransactions(); break;
        case 'users': loadUsers(); break;
        case 'settings': loadSettings(); break;
        case 'menu': loadMenuSection(); break;
    }
}

// ============================================================================
// DASHBOARD
// ============================================================================

async function loadDashboard() {
    try {
        const data = await api('/dashboard');
        dashboardData = data;
        renderDashboard(data);
    } catch (err) {
        toast('Ошибка загрузки дашборда', 'error');
    }
}

function renderDashboard(data) {
    const { today, week, month, all_time, counts, by_service, daily_chart } = data;

    const kpiGrid = document.getElementById('kpi-grid');
    kpiGrid.innerHTML = `
        <div class="kpi-card green">
            <div class="kpi-header">
                <span class="kpi-label">Заказов сегодня</span>
                <span class="kpi-icon">📦</span>
            </div>
            <div class="kpi-value">${today.total || 0}</div>
            <div class="kpi-sub">Выполнено: ${today.completed || 0} · Ожидает: ${today.pending || 0}</div>
        </div>
        <div class="kpi-card orange">
            <div class="kpi-header">
                <span class="kpi-label">Выручка сегодня</span>
                <span class="kpi-icon">💰</span>
            </div>
            <div class="kpi-value">${formatMoney(today.revenue)} сом</div>
            <div class="kpi-sub">Комиссия: ${formatMoney(today.commission)} сом</div>
        </div>
        <div class="kpi-card pink">
            <div class="kpi-header">
                <span class="kpi-label">Заказов за месяц</span>
                <span class="kpi-icon">📊</span>
            </div>
            <div class="kpi-value">${month.total || 0}</div>
            <div class="kpi-sub">Выполнено: ${month.completed || 0}</div>
        </div>
        <div class="kpi-card info">
            <div class="kpi-header">
                <span class="kpi-label">Водителей</span>
                <span class="kpi-icon">🚖</span>
            </div>
            <div class="kpi-value">${counts.drivers || 0}</div>
            <div class="kpi-sub">Кафе: ${counts.cafes || 0} · Аптек: ${counts.pharmacies || 0} · Клиентов: ${counts.users || 0}</div>
        </div>
    `;

    renderBarChart('chart-weekly', daily_chart || [], 'count', 'date');
    renderServiceChart('chart-services', by_service || []);
    loadRecentOrders();
}

async function loadRecentOrders() {
    try {
        const data = await api('/orders?limit=8');
        const body = document.getElementById('dashboard-orders-body');
        if (!data.orders || data.orders.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:30px;">Нет заказов</td></tr>';
            return;
        }
        body.innerHTML = data.orders.map((o) => `
            <tr>
                <td>${o.order_id || o.id || '—'}</td>
                <td>${serviceTag(o.service_type)}</td>
                <td>${statusBadge(o.status)}</td>
                <td>${o.client_phone || '—'}</td>
                <td>${formatMoney(o.price_total)} сом</td>
                <td>${formatDate(o.created_at)}</td>
            </tr>
        `).join('');

        document.getElementById('nav-orders-badge').textContent = data.total || data.count;
    } catch (err) {
        console.error(err);
    }
}

// ============================================================================
// ORDERS
// ============================================================================

async function loadOrders() {
    const status = document.getElementById('filter-order-status').value;
    const service = document.getElementById('filter-order-service').value;
    const period = document.getElementById('filter-order-period').value;

    let qs = `?limit=200`;
    if (status) qs += `&status=${status}`;
    if (service) qs += `&service=${service}`;
    if (period && period !== 'all') qs += `&period=${period}`;

    try {
        const data = await api(`/orders${qs}`);
        const body = document.getElementById('orders-body');
        document.getElementById('orders-total-label').textContent = `Всего: ${data.total}`;

        if (!data.orders || data.orders.length === 0) {
            body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:40px;">Нет заказов по выбранным фильтрам</td></tr>';
            return;
        }

        body.innerHTML = data.orders.map((o) => `
            <tr>
                <td>${o.order_id || o.id || '—'}</td>
                <td>${serviceTag(o.service_type)}</td>
                <td>${statusBadge(o.status)}</td>
                <td>${o.client_phone || '—'}</td>
                <td>${truncate(o.address, 25)}</td>
                <td>${truncate(o.details, 30)}</td>
                <td>${formatMoney(o.price_total)} сом</td>
                <td>${o.driver_id || o.provider_id || '—'}</td>
                <td>${formatDate(o.created_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        toast('Ошибка загрузки заказов', 'error');
    }
}

// ============================================================================
// DRIVERS
// ============================================================================

async function loadDrivers() {
    const type = document.getElementById('filter-driver-type').value;
    let qs = '';
    if (type) qs = `?type=${type}`;

    try {
        const data = await api(`/drivers${qs}`);
        const body = document.getElementById('drivers-body');

        if (!data.drivers || data.drivers.length === 0) {
            body.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:40px;">Нет водителей</td></tr>';
            return;
        }

        body.innerHTML = data.drivers.map((d) => {
            const bal = parseFloat(d.balance) || 0;
            const balClass = bal > 0 ? 'positive' : bal < 0 ? 'negative' : 'zero';
            const stats = d.order_stats || {};
            return `
            <tr>
                <td>${d.name || '—'}</td>
                <td>${driverTypeTag(d.driver_type)}</td>
                <td style="font-family:monospace;font-size:12px;">${d.telegram_id}</td>
                <td>${d.phone || '—'}</td>
                <td>${d.car_model || '—'}</td>
                <td>${d.plate || '—'}</td>
                <td>
                    <div class="balance-display">
                        <span class="balance-amount ${balClass}">${formatMoney(bal)}</span>
                        <span class="balance-currency">сом</span>
                    </div>
                </td>
                <td>${stats.total_orders || 0}</td>
                <td>${d.is_active ? '<span class="badge success">Активен</span>' : '<span class="badge danger">Неактивен</span>'}</td>
                <td>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-ghost btn-sm" onclick="showEditDriverModal('${d.telegram_id}', '${esc(d.name)}', '${esc(d.phone || '')}', '${esc(d.car_model || '')}', '${esc(d.plate || '')}')" title="Редактировать">✏️</button>
                        <button class="btn btn-success btn-sm" onclick="showBalanceModal('driver', '${d.telegram_id}', '${esc(d.name)}', ${bal})" title="Пополнить баланс">💰</button>
                        <button class="btn btn-danger btn-sm" onclick="removeEntity('drivers', '${d.telegram_id}')" title="Удалить">🗑️</button>
                    </div>
                </td>
            </tr>`;
        }).join('');
    } catch (err) {
        toast('Ошибка загрузки водителей', 'error');
    }
}

function showAddDriverModal() {
    document.getElementById('add-driver-tg-id').value = '';
    document.getElementById('add-driver-name').value = '';
    document.getElementById('add-driver-type').value = 'taxi';
    document.getElementById('add-driver-phone').value = '';
    document.getElementById('add-driver-car').value = '';
    document.getElementById('add-driver-plate').value = '';
    openModal('modal-add-driver');
}

async function submitAddDriver() {
    const telegram_id = document.getElementById('add-driver-tg-id').value.trim();
    const name = document.getElementById('add-driver-name').value.trim();
    const type = document.getElementById('add-driver-type').value;
    const phone = document.getElementById('add-driver-phone').value.trim();
    const car_model = document.getElementById('add-driver-car').value.trim();
    const plate = document.getElementById('add-driver-plate').value.trim();

    if (!telegram_id || !name) {
        toast('Telegram ID и ФИО обязательны', 'error');
        return;
    }

    try {
        await api('/drivers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegram_id, name, type, phone, car_model, plate }),
        });
        toast('Водитель добавлен');
        closeModal('modal-add-driver');
        loadDrivers();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

function showEditDriverModal(telegramId, name, phone, carModel, plate) {
    document.getElementById('edit-driver-id').value = telegramId;
    document.getElementById('edit-driver-name').value = name || '';
    document.getElementById('edit-driver-phone').value = phone || '';
    document.getElementById('edit-driver-car').value = carModel || '';
    document.getElementById('edit-driver-plate').value = plate || '';
    openModal('modal-edit-driver');
}

async function submitEditDriver() {
    const telegramId = document.getElementById('edit-driver-id').value;
    const name = document.getElementById('edit-driver-name').value.trim();
    const phone = document.getElementById('edit-driver-phone').value.trim();
    const car_model = document.getElementById('edit-driver-car').value.trim();
    const plate = document.getElementById('edit-driver-plate').value.trim();

    if (!name) {
        toast('ФИО обязательно', 'error');
        return;
    }

    try {
        await api(`/drivers/${telegramId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, phone, car_model, plate }),
        });
        toast('Данные водителя обновлены ✅');
        closeModal('modal-edit-driver');
        loadDrivers();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// CAFES
// ============================================================================

async function loadCafes() {
    try {
        const data = await api('/cafes');
        const body = document.getElementById('cafes-body');

        if (!data.cafes || data.cafes.length === 0) {
            body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:40px;">Нет кафе</td></tr>';
            return;
        }

        body.innerHTML = data.cafes.map((c) => {
            const debt = parseFloat(c.debt) || 0;
            return `
            <tr>
                <td>${c.name || '—'}</td>
                <td style="font-family:monospace;font-size:12px;">${c.telegram_id}</td>
                <td>${c.phone || '—'}</td>
                <td>${c.address || '—'}</td>
                <td>
                    <div class="balance-display">
                        <span class="balance-amount ${debt > 0 ? 'negative' : 'zero'}">${formatMoney(debt)}</span>
                        <span class="balance-currency">сом</span>
                    </div>
                </td>
                <td>${c.commission_percent || 5}%</td>
                <td>${c.is_active ? '<span class="badge success">Активно</span>' : '<span class="badge danger">Неакт.</span>'}</td>
                <td>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-ghost btn-sm" onclick="showEditCafeModal('${c.telegram_id}', '${esc(c.name)}', '${esc(c.phone || '')}', '${esc(c.address || '')}', ${c.commission_percent || 5}, ${c.is_active ? 'true' : 'false'})" title="Редактировать">✏️</button>
                        <button class="btn btn-success btn-sm" onclick="showBalanceModal('cafe', '${c.telegram_id}', '${esc(c.name)}', ${-debt})" title="Оплата долга">💰</button>
                        <button class="btn btn-danger btn-sm" onclick="removeEntity('cafes', '${c.telegram_id}')" title="Удалить">🗑️</button>
                    </div>
                </td>
            </tr>`;
        }).join('');
    } catch (err) {
        toast('Ошибка загрузки кафе', 'error');
    }
}

function showAddCafeModal() {
    document.getElementById('add-cafe-tg-id').value = '';
    document.getElementById('add-cafe-name').value = '';
    document.getElementById('add-cafe-phone').value = '';
    document.getElementById('add-cafe-address').value = '';
    openModal('modal-add-cafe');
}

async function submitAddCafe() {
    const data = {
        telegram_id: val('add-cafe-tg-id'),
        name: val('add-cafe-name'),
        phone: val('add-cafe-phone'),
        address: val('add-cafe-address'),
    };

    if (!data.telegram_id || !data.name) {
        toast('Telegram ID и Название обязательны', 'error');
        return;
    }

    try {
        await api('/cafes', { method: 'POST', body: JSON.stringify(data) });
        toast('✅ Кафе добавлено!', 'success');
        closeModal('modal-add-cafe');
        loadCafes();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

function showEditCafeModal(telegramId, name, phone, address, commission, isActive) {
    document.getElementById('edit-cafe-id').value = telegramId;
    document.getElementById('edit-cafe-name').value = name || '';
    document.getElementById('edit-cafe-phone').value = phone || '';
    document.getElementById('edit-cafe-address').value = address || '';
    document.getElementById('edit-cafe-comm').value = commission || 5;
    document.getElementById('edit-cafe-active').checked = !!isActive;
    openModal('modal-edit-cafe');
}

async function submitEditCafe() {
    const telegram_id = val('edit-cafe-id');
    const data = {
        name: val('edit-cafe-name'),
        phone: val('edit-cafe-phone'),
        address: val('edit-cafe-address'),
        commission_percent: parseInt(val('edit-cafe-comm') || '5', 10),
        is_active: document.getElementById('edit-cafe-active').checked
    };

    if (!data.name) {
        toast('Название обязательно', 'error');
        return;
    }

    try {
        await api(`/cafes/${telegram_id}`, { method: 'PUT', body: JSON.stringify(data) });
        toast('Данные кафе обновлены', 'success');
        closeModal('modal-edit-cafe');
        loadCafes();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// PHARMACIES
// ============================================================================

async function loadPharmacies() {
    try {
        const data = await api('/pharmacies');
        const body = document.getElementById('pharmacies-body');

        if (!data.pharmacies || data.pharmacies.length === 0) {
            body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:40px;">Нет аптек</td></tr>';
            return;
        }

        body.innerHTML = data.pharmacies.map((p) => {
            const bal = parseFloat(p.balance) || 0;
            return `
            <tr>
                <td>${p.name || '—'}</td>
                <td style="font-family:monospace;font-size:12px;">${p.telegram_id}</td>
                <td>${p.phone || '—'}</td>
                <td>${p.address || '—'}</td>
                <td>
                    <div class="balance-display">
                        <span class="balance-amount ${bal > 0 ? 'positive' : bal < 0 ? 'negative' : 'zero'}">${formatMoney(bal)}</span>
                        <span class="balance-currency">сом</span>
                    </div>
                </td>
                <td>${p.is_active ? '<span class="badge success">Активна</span>' : '<span class="badge danger">Неакт.</span>'}</td>
                <td>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-success btn-sm" onclick="showBalanceModal('pharmacy', '${p.telegram_id}', '${esc(p.name)}', ${bal})" title="Пополнить баланс">💰</button>
                        <button class="btn btn-danger btn-sm" onclick="removeEntity('pharmacies', '${p.telegram_id}')" title="Удалить">🗑️</button>
                    </div>
                </td>
            </tr>
        `}).join('');
    } catch (err) {
        toast('Ошибка загрузки аптек', 'error');
    }
}

function showAddPharmacyModal() {
    document.getElementById('add-pharmacy-tg-id').value = '';
    document.getElementById('add-pharmacy-name').value = '';
    document.getElementById('add-pharmacy-phone').value = '';
    document.getElementById('add-pharmacy-address').value = '';
    openModal('modal-add-pharmacy');
}

async function submitAddPharmacy() {
    const data = {
        telegram_id: val('add-pharmacy-tg-id'),
        name: val('add-pharmacy-name'),
        phone: val('add-pharmacy-phone'),
        address: val('add-pharmacy-address'),
    };

    if (!data.telegram_id || !data.name) {
        toast('Telegram ID и Название обязательны', 'error');
        return;
    }

    try {
        await api('/pharmacies', { method: 'POST', body: JSON.stringify(data) });
        toast('✅ Аптека добавлена!', 'success');
        closeModal('modal-add-pharmacy');
        loadPharmacies();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// SHOPPERS
// ============================================================================

async function loadShoppers() {
    try {
        const data = await api('/shoppers');
        const body = document.getElementById('shoppers-body');

        if (!data.shoppers || data.shoppers.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:40px;">Нет закупщиков</td></tr>';
            return;
        }

        body.innerHTML = data.shoppers.map((s) => {
            const bal = parseFloat(s.balance) || 0;
            return `
            <tr>
                <td>${s.name || '—'}</td>
                <td style="font-family:monospace;font-size:12px;">${s.telegram_id}</td>
                <td>${s.phone || '—'}</td>
                <td>
                    <div class="balance-display">
                        <span class="balance-amount ${bal > 0 ? 'positive' : bal < 0 ? 'negative' : 'zero'}">${formatMoney(bal)}</span>
                        <span class="balance-currency">сом</span>
                    </div>
                </td>
                <td>${s.is_active ? '<span class="badge success">Активен</span>' : '<span class="badge danger">Неакт.</span>'}</td>
                <td>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-success btn-sm" onclick="showBalanceModal('shopper', '${s.telegram_id}', '${esc(s.name)}', ${bal})" title="Пополнить баланс">💰</button>
                        <button class="btn btn-danger btn-sm" onclick="removeEntity('shoppers', '${s.telegram_id}')" title="Удалить">🗑️</button>
                    </div>
                </td>
            </tr>`;
        }).join('');
    } catch (err) {
        toast('Ошибка загрузки закупщиков', 'error');
    }
}

function showAddShopperModal() {
    document.getElementById('add-shopper-tg-id').value = '';
    document.getElementById('add-shopper-name').value = '';
    document.getElementById('add-shopper-phone').value = '';
    openModal('modal-add-shopper');
}

async function submitAddShopper() {
    const data = {
        telegram_id: val('add-shopper-tg-id'),
        name: val('add-shopper-name'),
        phone: val('add-shopper-phone'),
    };

    if (!data.telegram_id || !data.name) {
        toast('Telegram ID и ФИО обязательны', 'error');
        return;
    }

    try {
        await api('/shoppers', { method: 'POST', body: JSON.stringify(data) });
        toast('✅ Закупщик добавлен!', 'success');
        closeModal('modal-add-shopper');
        loadShoppers();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// UNIVERSAL BALANCE TOP-UP / WRITE-OFF
// ============================================================================

function showBalanceModal(entityType, telegramId, name, currentBalance) {
    const typeNames = {
        driver: 'Водитель',
        cafe: 'Кафе',
        pharmacy: 'Аптека',
        shopper: 'Закупщик'
    };

    document.getElementById('balance-modal-title').textContent = `💰 Баланс — ${typeNames[entityType] || entityType}`;
    document.getElementById('balance-entity-label').textContent = typeNames[entityType] || 'Имя';
    document.getElementById('balance-entity-name').value = name || telegramId;
    document.getElementById('balance-entity-id').value = telegramId;
    document.getElementById('balance-entity-type').value = entityType;
    document.getElementById('balance-current').value = `${formatMoney(currentBalance)} сом`;
    document.getElementById('balance-amount').value = 100;
    document.getElementById('balance-reason').value = 'Пополнение через админку';
    openModal('modal-balance');
}

async function submitBalanceWithSign(sign) {
    const telegramId = document.getElementById('balance-entity-id').value;
    const entityType = document.getElementById('balance-entity-type').value;
    const rawAmount = parseFloat(document.getElementById('balance-amount').value);
    const reason = document.getElementById('balance-reason').value;

    if (!rawAmount || rawAmount <= 0) {
        toast('Введите корректную сумму (положительное число)', 'error');
        return;
    }

    const amount = rawAmount * sign;

    // Determine API path based on entity type
    const pathMap = {
        driver: `/drivers/${telegramId}/balance`,
        cafe: `/drivers/${telegramId}/balance`,
        pharmacy: `/drivers/${telegramId}/balance`,
        shopper: `/drivers/${telegramId}/balance`,
    };

    const reloadMap = {
        driver: loadDrivers,
        cafe: loadCafes,
        pharmacy: loadPharmacies,
        shopper: loadShoppers,
    };

    try {
        const result = await api(pathMap[entityType] || `/drivers/${telegramId}/balance`, {
            method: 'POST',
            body: JSON.stringify({ amount, reason }),
        });

        const action = sign > 0 ? 'пополнен' : 'списан';
        toast(`✅ Баланс ${action}! Новый баланс: ${formatMoney(result.new_balance)} сом`, 'success');
        closeModal('modal-balance');
        if (reloadMap[entityType]) reloadMap[entityType]();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// REMOVE ENTITY
// ============================================================================

async function removeEntity(type, telegramId) {
    const names = { drivers: 'водителя', pharmacies: 'аптеку', shoppers: 'закупщика', cafes: 'кафе' };
    if (!confirm(`Вы уверены, что хотите удалить ${names[type] || 'запись'}?`)) return;

    try {
        await api(`/${type}/${telegramId}`, { method: 'DELETE' });
        toast('✅ Удалено!', 'success');
        loadSectionData(currentSection);
    } catch (err) {
        toast('Ошибка удаления: ' + err.message, 'error');
    }
}

// ============================================================================
// STATISTICS
// ============================================================================

async function loadStats() {
    try {
        const data = await api('/dashboard');
        dashboardData = data;
        renderStats(data);
    } catch (err) {
        toast('Ошибка загрузки статистики', 'error');
    }
}

function selectStatsPeriod(period) {
    statsPeriod = period;
    document.querySelectorAll('#stats-period-tabs .period-tab').forEach((el) => {
        el.classList.toggle('active', el.dataset.period === period);
    });
    if (dashboardData) renderStats(dashboardData);
}

function renderStats(data) {
    const periodMap = { day: data.today, week: data.week, month: data.month, all: data.all_time };
    const p = periodMap[statsPeriod] || data.today;
    const periodNames = { day: 'за сегодня', week: 'за неделю', month: 'за месяц', all: 'за всё время' };

    document.getElementById('stats-kpi').innerHTML = `
        <div class="kpi-card green">
            <div class="kpi-header">
                <span class="kpi-label">Заказов ${periodNames[statsPeriod]}</span>
                <span class="kpi-icon">📦</span>
            </div>
            <div class="kpi-value">${p.total || 0}</div>
        </div>
        <div class="kpi-card orange">
            <div class="kpi-header">
                <span class="kpi-label">Выручка ${periodNames[statsPeriod]}</span>
                <span class="kpi-icon">💰</span>
            </div>
            <div class="kpi-value">${formatMoney(p.revenue)} сом</div>
        </div>
        <div class="kpi-card pink">
            <div class="kpi-header">
                <span class="kpi-label">Комиссия ${periodNames[statsPeriod]}</span>
                <span class="kpi-icon">🏦</span>
            </div>
            <div class="kpi-value">${formatMoney(p.commission)} сом</div>
        </div>
        <div class="kpi-card info">
            <div class="kpi-header">
                <span class="kpi-label">Выполнено ${periodNames[statsPeriod]}</span>
                <span class="kpi-icon">✅</span>
            </div>
            <div class="kpi-value">${p.completed || 0}</div>
        </div>
    `;

    const services = data.by_service || [];
    renderServiceBars('stats-service-bars', services, 'count');
    renderServiceBars('stats-revenue-bars', services, 'revenue');
}

function renderServiceBars(containerId, services, field) {
    const container = document.getElementById(containerId);
    if (!services || services.length === 0) {
        container.innerHTML = '<div class="empty-state" style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;"><div class="empty-state-icon">📊</div><div class="empty-state-text">Нет данных</div></div>';
        return;
    }

    const maxVal = Math.max(...services.map((s) => parseFloat(s[field]) || 0), 1);

    container.innerHTML = services.map((s) => {
        const val = parseFloat(s[field]) || 0;
        const pct = Math.max((val / maxVal) * 100, 4);
        const color = SERVICE_COLORS[s.service_type] || '#6c5ce7';
        const lbl = SERVICE_LABELS[s.service_type] || { icon: '❓', name: s.service_type };
        return `
            <div class="bar-item">
                <div class="bar-value">${field === 'revenue' ? formatMoney(val) : val}</div>
                <div class="bar" style="height:${pct}%;background:${color};" title="${lbl.name}: ${val}"></div>
                <div class="bar-label">${lbl.icon} ${lbl.name}</div>
            </div>
        `;
    }).join('');
}

// ============================================================================
// TRANSACTIONS
// ============================================================================

async function loadTransactions() {
    try {
        const data = await api('/transactions?limit=100');
        const body = document.getElementById('transactions-body');

        if (!data.transactions || data.transactions.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:40px;">Нет транзакций</td></tr>';
            return;
        }

        body.innerHTML = data.transactions.map((t) => `
            <tr>
                <td><span class="badge neutral">${t.action}</span></td>
                <td>${t.user_id || '—'}</td>
                <td>${t.order_id || '—'}</td>
                <td>${t.amount != null ? formatMoney(t.amount) + ' сом' : '—'}</td>
                <td>${truncate(t.details, 40)}</td>
                <td>${formatDate(t.created_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        toast('Ошибка загрузки транзакций', 'error');
    }
}

// ============================================================================
// USERS
// ============================================================================

async function loadUsers() {
    try {
        const data = await api('/users');
        const body = document.getElementById('users-body');

        if (!data.users || data.users.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:40px;">Нет пользователей</td></tr>';
            return;
        }

        body.innerHTML = data.users.map((u) => `
            <tr>
                <td style="font-family:monospace;">${u.phone}</td>
                <td>${u.name || '—'}</td>
                <td>${u.language === 'ky' ? '🇰🇬 Кыргыз' : '🇷🇺 Русский'}</td>
                <td><span class="badge neutral">${u.current_state || '—'}</span></td>
                <td>${u.order_count || 0}</td>
                <td>${formatDate(u.created_at)}</td>
            </tr>
        `).join('');
    } catch (err) {
        toast('Ошибка загрузки пользователей', 'error');
    }
}

// ============================================================================
// MENU MANAGEMENT
// ============================================================================

async function loadMenuSection() {
    try {
        const data = await api('/cafes');
        const select = document.getElementById('menu-cafe-select');
        // Сохраняем текущий выбор если есть
        const current = select.value;

        select.innerHTML = '<option value="">Выберите кафе</option>';

        if (data.cafes && data.cafes.length > 0) {
            data.cafes.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name + (c.telegram_id ? ` (${c.telegram_id})` : '');
                select.appendChild(opt);
            });
        }

        if (current) {
            select.value = current;
            handleMenuCafeChange();
        } else {
            document.getElementById('menu-body').innerHTML = '';
        }
    } catch (err) {
        toast('Ошибка загрузки списка кафе', 'error');
    }
}

function handleMenuCafeChange() {
    loadMenuCategories();
    loadMenuTable();
}

async function loadMenuCategories() {
    const cafeId = document.getElementById('menu-cafe-select').value;
    menuCategories = [];
    const listEl = document.getElementById('menu-categories-list');
    listEl.innerHTML = '';
    if (!cafeId) return;
    try {
        const cats = await api(`/../menu/api/admin/categories?cafe_id=${cafeId}`);
        menuCategories = cats || [];
        renderCategoryBadges();
        setCategorySelectOptions('add-item-category');
        setCategorySelectOptions('edit-item-category');
    } catch (e) {
        console.error(e);
    }
}

function renderCategoryBadges() {
    const listEl = document.getElementById('menu-categories-list');
    if (!listEl) return;
    if (!menuCategories || menuCategories.length === 0) {
        listEl.innerHTML = '<span class="text-muted">Категории не заданы</span>';
        return;
    }
    listEl.innerHTML = menuCategories.map(c => `
        <span class="badge neutral" style="display:flex;align-items:center;gap:6px;">
            ${c.name}
            <button class="btn btn-ghost btn-xs" style="padding:0 4px;" onclick="deleteCategory(${c.id})">✕</button>
        </span>
    `).join('');
}

async function submitAddCategory() {
    const cafeId = document.getElementById('menu-cafe-select').value;
    const name = document.getElementById('add-category-name').value.trim();
    if (!cafeId || !name) {
        toast('Выберите кафе и введите название категории', 'warning');
        return;
    }
    try {
        await api('/../menu/api/admin/categories', {
            method: 'POST',
            body: JSON.stringify({ cafe_id: parseInt(cafeId), name })
        });
        document.getElementById('add-category-name').value = '';
        await loadMenuCategories();
        toast('Категория добавлена', 'success');
    } catch (e) {
        toast('Ошибка добавления категории: ' + e.message, 'error');
    }
}

async function deleteCategory(id) {
    if (!confirm('Удалить категорию? Блюда останутся, но категория исчезнет.')) return;
    try {
        await api(`/../menu/api/admin/categories/${id}`, { method: 'DELETE' });
        await loadMenuCategories();
        loadMenuTable();
    } catch (e) {
        toast('Ошибка удаления: ' + e.message, 'error');
    }
}

async function loadMenuTable() {
    const cafeId = document.getElementById('menu-cafe-select').value;
    if (!cafeId) {
        document.getElementById('menu-body').innerHTML = '';
        return;
    }

    try {
        // Используем относительный путь для выхода из /admin/ префикса
        const items = await api(`/../menu/api/admin/items?cafe_id=${cafeId}`);
        const body = document.getElementById('menu-body');

        if (!items || items.length === 0) {
            body.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:20px;">Меню пусто</td></tr>';
            return;
        }

        body.innerHTML = items.map(i => `
            <tr>
                <td>
                    <div style="display:flex;align-items:center;gap:10px;">
                        ${i.image_url
                ? `<img src="${i.image_url}" style="width:40px;height:40px;border-radius:6px;object-fit:cover;" onerror="this.style.display='none'">`
                : '<span style="font-size:20px;">🍽️</span>'}
                        <span>${i.name}</span>
                    </div>
                </td>
                <td>${i.price} сом</td>
                <td><span class="badge neutral">${i.category_name || i.category || '—'}</span></td>
                <td>${i.description ? `<span class="text-muted">${esc(i.description)}</span>` : '—'}</td>
                <td>${i.is_available ? '<span class="badge success">Да</span>' : '<span class="badge danger">Нет</span>'}</td>
                <td>
                    <button class="btn btn-ghost btn-sm" onclick="showEditMenuItemModal(${i.id}, '${i.name.replace(/'/g, "\\'").replace(/"/g, '&quot;')}', ${i.price}, ${i.category_id || 'null'}, '${(i.category || '').replace(/'/g, "\\'").replace(/"/g, '&quot;')}', ${i.is_available}, '${(i.image_url || '').replace(/'/g, "\\'").replace(/"/g, '&quot;')}', '${(i.description || '').replace(/'/g, "\\'").replace(/"/g, '&quot;')}')" title="Редактировать">✏️</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteMenuItem(${i.id})" title="Удалить">🗑️</button>
                </td>
            </tr>
        `).join('');
    } catch (err) {
        console.error(err);
        toast('Ошибка загрузки меню', 'error');
    }
}

function showAddMenuItemModal() {
    const cafeId = document.getElementById('menu-cafe-select').value;
    if (!cafeId) {
        toast('Сначала выберите кафе из списка!', 'warning');
        return;
    }

    document.getElementById('add-item-name').value = '';
    document.getElementById('add-item-price').value = '';
    setCategorySelectOptions('add-item-category');
    document.getElementById('add-item-description').value = '';
    document.getElementById('add-item-image-url').value = '';
    const fileInput = document.getElementById('add-item-image-file');
    if (fileInput) fileInput.value = '';
    document.getElementById('add-image-preview').style.display = 'none';
    switchPhotoTab('add', 'url');
    openModal('modal-add-item');
}

async function submitAddMenuItem() {
    const cafeId = document.getElementById('menu-cafe-select').value;
    if (!cafeId) return;

    const imageUrl = getImageUrlFromModal('add');

    const data = {
        cafe_id: parseInt(cafeId),
        name: document.getElementById('add-item-name').value.trim(),
        price: parseFloat(document.getElementById('add-item-price').value),
        category_id: parseInt(document.getElementById('add-item-category').value) || null,
        category: getCategoryNameById(document.getElementById('add-item-category').value),
        description: document.getElementById('add-item-description').value.trim() || null,
        image_url: imageUrl || null
    };

    if (!data.name || isNaN(data.price)) {
        toast('Заполните название и цену корректно', 'error');
        return;
    }

    try {
        await api('/../menu/api/admin/items', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        toast('✅ Блюдо добавлено', 'success');
        closeModal('modal-add-item');
        loadMenuTable();
    } catch (e) {
        toast('Ошибка: ' + e.message, 'error');
    }
}

async function deleteMenuItem(id) {
    if (!confirm('Вы уверены, что хотите удалить это блюдо?')) return;
    try {
        await api(`/../menu/api/admin/items/${id}`, { method: 'DELETE' });
        toast('🗑️ Удалено', 'success');
        loadMenuTable();
    } catch (e) {
        toast('Ошибка удаления: ' + e.message, 'error');
    }
}

// ============ EDIT MENU ITEM ============

function showEditMenuItemModal(id, name, price, categoryId, category, isAvailable, imageUrl, description) {
    document.getElementById('edit-item-id').value = id;
    document.getElementById('edit-item-name').value = name;
    document.getElementById('edit-item-price').value = price;
    setCategorySelectOptions('edit-item-category', categoryId);
    document.getElementById('edit-item-description').value = description ? description.replace(/&quot;/g, '"') : '';
    document.getElementById('edit-item-available').value = isAvailable ? 'true' : 'false';
    document.getElementById('edit-item-image-url').value = imageUrl || '';
    const fileInput = document.getElementById('edit-item-image-file');
    if (fileInput) fileInput.value = '';

    // Show preview if image exists
    const preview = document.getElementById('edit-image-preview');
    const previewImg = document.getElementById('edit-preview-img');
    if (imageUrl && imageUrl.length > 0) {
        previewImg.src = imageUrl;
        preview.style.display = 'block';
    } else {
        preview.style.display = 'none';
    }

    switchPhotoTab('edit', 'url');
    openModal('modal-edit-item');
}

async function submitEditMenuItem() {
    const itemId = document.getElementById('edit-item-id').value;
    if (!itemId) return;

    const imageUrl = getImageUrlFromModal('edit');

    const data = {
        name: document.getElementById('edit-item-name').value.trim(),
        price: parseFloat(document.getElementById('edit-item-price').value),
        category_id: parseInt(document.getElementById('edit-item-category').value) || null,
        category: getCategoryNameById(document.getElementById('edit-item-category').value),
        description: document.getElementById('edit-item-description').value.trim() || null,
        is_available: document.getElementById('edit-item-available').value === 'true',
        image_url: imageUrl || null
    };

    if (!data.name || isNaN(data.price)) {
        toast('Заполните название и цену корректно', 'error');
        return;
    }

    try {
        await api(`/../menu/api/admin/items/${itemId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
        toast('✅ Блюдо обновлено', 'success');
        closeModal('modal-edit-item');
        loadMenuTable();
    } catch (e) {
        toast('Ошибка: ' + e.message, 'error');
    }
}

// ============ PHOTO UPLOAD HELPERS ============

function switchPhotoTab(prefix, tab) {
    const urlBlock = document.getElementById(`${prefix}-photo-url-block`);
    const fileBlock = document.getElementById(`${prefix}-photo-file-block`);
    const urlBtn = document.getElementById(`${prefix}-photo-tab-url`);
    const fileBtn = document.getElementById(`${prefix}-photo-tab-file`);

    if (tab === 'url') {
        urlBlock.style.display = 'block';
        fileBlock.style.display = 'none';
        urlBtn.classList.add('active');
        urlBtn.style.background = 'var(--accent-gradient)';
        urlBtn.style.color = '#fff';
        fileBtn.classList.remove('active');
        fileBtn.style.background = '';
        fileBtn.style.color = '';
    } else {
        urlBlock.style.display = 'none';
        fileBlock.style.display = 'block';
        fileBtn.classList.add('active');
        fileBtn.style.background = 'var(--accent-gradient)';
        fileBtn.style.color = '#fff';
        urlBtn.classList.remove('active');
        urlBtn.style.background = '';
        urlBtn.style.color = '';
    }
}

function previewImageUrl(prefix) {
    const url = document.getElementById(`${prefix}-item-image-url`).value.trim();
    const preview = document.getElementById(`${prefix}-image-preview`);
    const img = document.getElementById(`${prefix}-preview-img`);

    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
        img.src = url;
        img.onerror = () => { preview.style.display = 'none'; };
        preview.style.display = 'block';
    } else {
        preview.style.display = 'none';
    }
}

function previewImageFile(prefix) {
    const fileInput = document.getElementById(`${prefix}-item-image-file`);
    const preview = document.getElementById(`${prefix}-image-preview`);
    const img = document.getElementById(`${prefix}-preview-img`);

    if (fileInput.files && fileInput.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            img.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(fileInput.files[0]);
    }
}

function getImageUrlFromModal(prefix) {
    // Priority: file upload (as data URI) > URL input
    const fileInput = document.getElementById(`${prefix}-item-image-file`);
    if (fileInput && fileInput.files && fileInput.files[0]) {
        // File was selected — use the preview img src (which is a data URI)
        const previewImg = document.getElementById(`${prefix}-preview-img`);
        if (previewImg && previewImg.src && previewImg.src.startsWith('data:')) {
            return previewImg.src;
        }
    }
    // Fallback to URL input
    const urlInput = document.getElementById(`${prefix}-item-image-url`);
    return urlInput ? urlInput.value.trim() : '';
}

// ============================================================================
// BROADCAST
// ============================================================================

async function sendBroadcast() {
    const message = document.getElementById('broadcast-message').value.trim();

    // Collect checked values
    const targets = Array.from(document.querySelectorAll('#broadcast-targets input:checked'))
        .map(cb => cb.value);

    if (!message) {
        toast('Введите текст сообщения', 'error');
        return;
    }

    if (targets.length === 0) {
        toast('Выберите хотя бы одну группу получателей', 'error');
        return;
    }

    const targetNames = {
        drivers: '👤 Водители',
        cafes: '👤 Кафе',
        pharmacies: '👤 Аптеки',
        shoppers: '👤 Закупщики',
        group_taxi: '📢 Группа Такси',
        group_porter: '📢 Группа Портер',
        group_cafe: '📢 Группа Кафе',
        group_pharmacy: '📢 Группа Аптеки',
        group_shop: '📢 Группа Магазины'
    };
    const targetList = targets.map(t => targetNames[t] || t).join(', ');

    if (!confirm(`Отправить рассылку?\n\nПолучатели: ${targetList}\n\nТекст: ${message.substring(0, 50)}${message.length > 50 ? '...' : ''}`)) return;

    try {
        const result = await api('/broadcast', {
            method: 'POST',
            body: JSON.stringify({ message, targets }),
        });
        toast(`✅ Рассылка отправлена! Успешно: ${result.sent}, Ошибок: ${result.failed}`, 'success');
        document.getElementById('broadcast-message').value = '';
    } catch (err) {
        toast('Ошибка рассылки: ' + err.message, 'error');
    }
}

// ============================================================================
// SETTINGS
// ============================================================================

async function loadSettings() {
    try {
        const data = await api('/settings');
        document.getElementById('setting-ramadan').textContent = data.is_ramadan ? '✅ Включён' : '❌ Выключен';
        document.getElementById('setting-cafe-comm').textContent = data.cafe_commission + '%';
        document.getElementById('setting-taxi-comm').textContent = data.taxi_commission + ' сом';
        document.getElementById('setting-porter-comm').textContent = data.porter_commission + ' сом';
    } catch (err) {
        toast('Ошибка загрузки настроек', 'error');
    }
}

async function toggleRamadan() {
    const current = document.getElementById('setting-ramadan').textContent.includes('Включён');
    try {
        await api('/settings/ramadan', {
            method: 'POST',
            body: JSON.stringify({ enabled: !current }),
        });
        toast(`Режим Рамазан ${!current ? 'включён' : 'выключен'}`, 'success');
        loadSettings();
    } catch (err) {
        toast('Ошибка: ' + err.message, 'error');
    }
}

// ============================================================================
// CHARTS
// ============================================================================

function renderBarChart(containerId, data, valueField, labelField) {
    const container = document.getElementById(containerId);
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="empty-state" style="height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;"><div class="empty-state-icon">📊</div><div class="empty-state-text">Нет данных за неделю</div></div>';
        return;
    }

    const maxVal = Math.max(...data.map((d) => parseFloat(d[valueField]) || 0), 1);

    container.innerHTML = data.map((d) => {
        const v = parseFloat(d[valueField]) || 0;
        const pct = Math.max((v / maxVal) * 100, 4);
        const label = typeof d[labelField] === 'string'
            ? (d[labelField].length > 10 ? d[labelField].slice(5) : d[labelField])
            : d[labelField];
        return `
            <div class="bar-item">
                <div class="bar-value">${v}</div>
                <div class="bar" style="height:${pct}%;" title="${label}: ${v}"></div>
                <div class="bar-label">${label}</div>
            </div>
        `;
    }).join('');
}

function renderServiceChart(containerId, services) {
    const container = document.getElementById(containerId);
    if (!services || services.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🍩</div><div class="empty-state-text">Нет данных</div></div>';
        return;
    }

    const total = services.reduce((s, v) => s + (parseInt(v.count) || 0), 0) || 1;

    let cumPct = 0;
    const segments = services.map((s) => {
        const pct = ((parseInt(s.count) || 0) / total) * 100;
        const offset = 100 - pct;
        const rotation = (cumPct / 100) * 360;
        cumPct += pct;
        const color = SERVICE_COLORS[s.service_type] || '#6c5ce7';
        return `<circle cx="70" cy="70" r="56" fill="none" stroke="${color}" stroke-width="20"
            stroke-dasharray="${pct} ${offset}" stroke-dashoffset="0"
            transform="rotate(${rotation - 90} 70 70)" />`;
    });

    const svg = `<svg viewBox="0 0 140 140" class="donut-ring">
        <circle cx="70" cy="70" r="56" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="20"/>
        ${segments.join('')}
        <text x="70" y="66" text-anchor="middle" fill="var(--text-primary)" font-size="22" font-weight="800">${total}</text>
        <text x="70" y="82" text-anchor="middle" fill="var(--text-muted)" font-size="10">заказов</text>
    </svg>`;

    const legend = services.map((s) => {
        const lbl = SERVICE_LABELS[s.service_type] || { icon: '❓', name: s.service_type };
        const color = SERVICE_COLORS[s.service_type] || '#6c5ce7';
        const pct = Math.round(((parseInt(s.count) || 0) / total) * 100);
        return `
            <div class="legend-item">
                <span class="legend-dot" style="background:${color}"></span>
                <span>${lbl.icon} ${lbl.name}</span>
                <span class="legend-value">${s.count} (${pct}%)</span>
            </div>
        `;
    }).join('');

    container.innerHTML = svg + `<div class="donut-legend">${legend}</div>`;
}

// ============================================================================
// MODALS
// ============================================================================

function openModal(id) {
    document.getElementById(id).classList.add('show');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('show');
}

document.querySelectorAll('.modal-overlay').forEach((overlay) => {
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.classList.remove('show');
    });
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.show').forEach((m) => m.classList.remove('show'));
    }
});

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================

function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${message}</span>`;
    container.appendChild(el);

    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = 'all 0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function val(id) {
    return (document.getElementById(id).value || '').trim();
}

function esc(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function getCategoryNameById(id) {
    const cid = parseInt(id);
    const found = menuCategories.find(c => c.id === cid);
    return found ? found.name : null;
}

function setCategorySelectOptions(selectId, selectedId = null) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.innerHTML = '';
    if (!menuCategories || menuCategories.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Без категории';
        select.appendChild(opt);
        return;
    }
    menuCategories.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name;
        select.appendChild(opt);
    });
    if (selectedId) {
        select.value = selectedId;
    }
}

function formatMoney(v) {
    const num = parseFloat(v) || 0;
    return num.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr);
        return d.toLocaleString('ru-RU', {
            day: '2-digit', month: '2-digit', year: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    } catch {
        return dateStr;
    }
}

function serviceTag(type) {
    const s = SERVICE_LABELS[type];
    if (!s) return `<span class="type-badge">${type || '—'}</span>`;
    return `<span class="type-badge ${s.cls}">${s.icon} ${s.name}</span>`;
}

function driverTypeTag(type) {
    const d = DRIVER_TYPE_LABELS[type];
    if (!d) return type || '—';
    return `<span class="type-badge ${type}">${d.icon} ${d.name}</span>`;
}

function statusBadge(status) {
    const s = STATUS_LABELS[status];
    if (!s) return `<span class="badge neutral">${status || '—'}</span>`;
    return `<span class="badge ${s.cls}">${s.label}</span>`;
}

function truncate(str, len) {
    if (!str) return '—';
    return str.length > len ? str.substring(0, len) + '…' : str;
}

function updateClock() {
    const now = new Date();
    document.getElementById('header-time').textContent = now.toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
}

// ============================================================================
// INIT
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-item').forEach((item) => {
        item.addEventListener('click', () => {
            const section = item.dataset.section;
            if (section) navigate(section);
        });
    });

    updateClock();
    setInterval(updateClock, 1000);

    loadDashboard();

    setInterval(() => {
        if (currentSection === 'dashboard') loadDashboard();
    }, REFRESH_INTERVAL);
});
