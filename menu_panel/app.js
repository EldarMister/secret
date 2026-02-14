/* ============================================
   JARDAMCHЫ GO — Web Menu Logic
   ============================================ */

const API_BASE = '/menu/api';

// State
let state = {
    cafes: [],
    currentCafe: null,
    menuItems: [],
    categories: [],
    activeCategory: null,
    activeCategoryName: null,
    cart: {
        cafeId: null,
        items: {} // itemId -> { ...item, count: 0 }
    }
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    loadCafes();

    // Check if we have a saved cart in localStorage?
    // For MVP, start fresh.
});

// --- API Calls ---
async function loadCafes() {
    showLoader(true);
    try {
        const res = await fetch(`${API_BASE}/cafes`);
        const data = await res.json();
        state.cafes = data;
        renderCafes(data);
    } catch (e) {
        console.error("Failed to load cafes", e);
        alert("Ошибка загрузки списка кафе");
    } finally {
        showLoader(false);
    }
}

async function loadMenu(cafeId) {
    showLoader(true);
    try {
        const res = await fetch(`${API_BASE}/cafes/${cafeId}/items`);
        const data = await res.json();
        state.menuItems = data;

        // Находим имя кафе
        const cafe = state.cafes.find(c => c.id === cafeId);
        state.currentCafe = cafe;

        // Загружаем категории
        try {
            const catRes = await fetch(`${API_BASE}/cafes/${cafeId}/categories`);
            if (catRes.ok) {
                state.categories = await catRes.json();
            } else {
                state.categories = [];
            }
        } catch (e) {
            console.warn('No categories', e);
            state.categories = [];
        }
        if (!state.categories || state.categories.length === 0) {
            state.categories = deriveCategoriesFromItems(state.menuItems);
        }
        state.activeCategory = null;
        state.activeCategoryName = null;

        renderCategories();
        renderMenu(data, cafe);
        switchView('menuView');
    } catch (e) {
        console.error("Failed to load menu", e);
        alert("Ошибка загрузки меню");
    } finally {
        showLoader(false);
    }
}

async function sendOrder(orderData) {
    showLoader(true);
    try {
        const res = await fetch(`${API_BASE}/order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });
        const data = await res.json();
        if (data.success) {
            showSuccess(data);
        } else {
            alert("Ошибка при создании заказа: " + (data.error || "Неизвестная ошибка"));
        }
    } catch (e) {
        console.error("Order failed", e);
        alert("Ошибка соединения с сервером");
    } finally {
        showLoader(false);
    }
}

// --- Rendering ---
function renderCafes(cafes) {
    const grid = document.getElementById('cafeGrid');
    grid.innerHTML = '';

    if (cafes.length === 0) {
        grid.innerHTML = '<p class="text-muted" style="text-align:center;">Нет активных кафе</p>';
        return;
    }

    cafes.forEach(cafe => {
        const card = document.createElement('div');
        card.className = 'cafe-card';
        card.onclick = () => loadMenu(cafe.id);
        card.innerHTML = `
            <div style="display: flex; align-items: center; gap: 14px;">
                <div style="width: 44px; height: 44px; border-radius: 12px; background: linear-gradient(135deg, #e17055, #fdcb6e); display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; box-shadow: 0 4px 15px rgba(225, 112, 85, 0.3);">
                    🍽️
                </div>
                <div>
                    <div class="cafe-name">${cafe.name}</div>
                    <div class="cafe-info">${cafe.address || 'Адрес не указан'}</div>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

function renderMenu(items, cafe) {
    const list = document.getElementById('menuList');
    list.innerHTML = '';

    // Update header
    document.getElementById('pageTitle').innerText = cafe.name;
    document.getElementById('backBtn').style.display = 'block';

    if (items.length === 0) {
        list.innerHTML = '<p class="text-muted" style="text-align:center;">Меню пусто</p>';
        return;
    }

    // Фильтрация по активной категории
    if (!state.activeCategory) {
        list.innerHTML = '<p class="text-muted" style="text-align:center;">Выберите категорию, чтобы увидеть блюда</p>';
        updateCategoryVisibility();
        return;
    }

    const filtered = state.activeCategory === 'all'
        ? items
        : items.filter(i =>
            i.category_id === state.activeCategory ||
            i.category === state.activeCategory ||
            i.category_name === state.activeCategory
        );

    // Группируем по категории
    const grouped = filtered.reduce((acc, item) => {
        const cat = item.category || item.category_name || 'Другое';
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(item);
        return acc;
    }, {});

    // Food emoji map for visual placeholders
    const foodEmojis = {
        'Напитки': '🥤', 'напитки': '🥤', 'drink': '🥤',
        'Пицца': '🍕', 'пицца': '🍕', 'pizza': '🍕',
        'Бургеры': '🍔', 'бургеры': '🍔', 'burger': '🍔',
        'Салаты': '🥗', 'салаты': '🥗', 'salad': '🥗',
        'Десерты': '🍰', 'десерты': '🍰', 'dessert': '🍰',
        'Горячее': '🍲', 'горячее': '🍲',
        'Супы': '🍜', 'супы': '🍜', 'Суп': '🍜',
        'Завтраки': '🍳', 'завтраки': '🍳',
    };
    const defaultEmoji = '🍽️';

    Object.keys(grouped).forEach(cat => {
        const header = document.createElement('div');
        header.className = 'category-header';
        header.innerHTML = `<div class="category-title">${cat}</div>`;
        list.appendChild(header);

        grouped[cat].forEach(item => {
            const div = document.createElement('div');
            div.className = 'menu-item';

            const count = state.cart.items[item.id] ? state.cart.items[item.id].count : 0;
            const emoji = foodEmojis[cat] || foodEmojis[item.category] || defaultEmoji;

            div.innerHTML = `
                <div class="item-photo">
                    ${item.image_url ? `<img src="${item.image_url}" alt="${item.name}" loading="lazy">` : emoji}
                </div>
                <div class="item-details">
                    <div class="item-name">${item.name}</div>
                    <div class="text-muted" style="font-size: 0.78rem;">${item.category}</div>
                    ${item.description ? `<div class="text-muted" style="font-size:0.78rem;margin-top:4px;">${item.description}</div>` : ''}
                    <div class="item-price">${item.price} с</div>
                </div>
                <div class="item-controls" id="controls-${item.id}">
                    ${renderItemControls(item, count)}
                </div>
            `;
            list.appendChild(div);
        });
    });

    updateCartBar();
    updateCategoryBack();
    updateCategoryVisibility();
}

function deriveCategoriesFromItems(items) {
    const map = {};
    items.forEach(i => {
        const name = i.category || i.category_name;
        if (!name) return;
        const key = i.category_id || name;
        if (!map[key]) map[key] = { id: key, name };
    });
    return Object.values(map);
}

function renderCategories() {
    const wrap = document.getElementById('categoryStrip');
    if (!wrap) return;
    wrap.innerHTML = '';

    // Показываем категории только когда не выбрана активная
    if (state.activeCategory) {
        wrap.style.display = 'none';
        return;
    }

    wrap.style.display = 'grid';

    const cats = [{ id: 'all', name: 'Все блюда' }, ...state.categories];

    cats.forEach(cat => {
        const card = document.createElement('div');
        card.className = 'category-card';
        card.onclick = () => {
            state.activeCategory = cat.id;
            state.activeCategoryName = cat.name;
            renderMenu(state.menuItems, state.currentCafe);
            updateCategoryBack();
            updateHeaderTitle();
        };
        card.innerHTML = `
            <div class="cat-icon">🍽️</div>
            <div class="cat-text">
                <div class="cat-name">${cat.name}</div>
            </div>
        `;
        wrap.appendChild(card);
    });
}

function resetCategorySelection() {
    state.activeCategory = null;
    state.activeCategoryName = null;
    updateHeaderTitle();
    renderCategories();
    renderMenu(state.menuItems, state.currentCafe);
}

function updateCategoryBack() {
    const back = document.getElementById('categoryBackBar');
    if (state.activeCategory && state.activeCategory !== 'all') {
        back.style.display = 'block';
    } else {
        back.style.display = 'none';
    }
}

function updateHeaderTitle() {
    const base = state.currentCafe ? state.currentCafe.name : 'Jardamchy GO 🍔';
    if (state.activeCategory && state.activeCategory !== 'all' && state.activeCategoryName) {
        document.getElementById('pageTitle').innerText = `${base} • ${state.activeCategoryName}`;
    } else {
        document.getElementById('pageTitle').innerText = base;
    }
}

function updateCategoryVisibility() {
    const wrap = document.getElementById('categoryStrip');
    if (!wrap) return;
    if (state.activeCategory) {
        wrap.style.display = 'none';
    } else {
        wrap.style.display = 'grid';
    }
}
function renderItemControls(item, count) {
    if (count > 0) {
        return `
            <button class="qty-btn" onclick="updateItem(${item.id}, -1)">-</button>
            <span class="qty-val">${count}</span>
            <button class="qty-btn" onclick="updateItem(${item.id}, 1)">+</button>
        `;
    } else {
        return `
            <button class="add-btn" onclick="updateItem(${item.id}, 1)">Добавить</button>
        `;
    }
}

// --- Logic ---

function goHome() {
    state.currentCafe = null;
    state.activeCategory = null;
    state.activeCategoryName = null;
    updateCategoryBack();
    document.getElementById('pageTitle').innerText = 'Jardamchy GO 🍔';
    document.getElementById('backBtn').style.display = 'none';
    switchView('cafeListView');
}

function switchView(viewId) {
    document.querySelectorAll('.view').forEach(el => el.style.display = 'none');
    document.getElementById(viewId).style.display = 'block';
}

function showLoader(show) {
    document.getElementById('loader').style.display = show ? 'block' : 'none';
}

function updateItem(itemId, change) {
    if (!state.currentCafe) return;

    const cafeId = state.currentCafe.id;

    // Check cafe conflict
    if (state.cart.cafeId && state.cart.cafeId !== cafeId) {
        if (confirm("Вы перешли в другое кафе. Очистить корзину?")) {
            state.cart = { cafeId: null, items: {} };
        } else {
            return;
        }
    }

    state.cart.cafeId = cafeId;

    const item = state.menuItems.find(i => i.id === itemId);
    if (!item) return;

    if (!state.cart.items[itemId]) {
        state.cart.items[itemId] = { ...item, count: 0 };
    }

    state.cart.items[itemId].count += change;

    if (state.cart.items[itemId].count <= 0) {
        delete state.cart.items[itemId];
        if (Object.keys(state.cart.items).length === 0) {
            state.cart.cafeId = null;
        }
    }

    // Rerender controls
    const controls = document.getElementById(`controls-${itemId}`);
    if (controls) {
        const newCount = state.cart.items[itemId] ? state.cart.items[itemId].count : 0;
        controls.innerHTML = renderItemControls(item, newCount);
    }

    updateCartBar();
}

function getCartStats() {
    let total = 0;
    let count = 0;
    Object.values(state.cart.items).forEach(i => {
        total += i.price * i.count;
        count += i.count;
    });
    return { total, count };
}

function updateCartBar() {
    const { total, count } = getCartStats();

    document.getElementById('barTotal').innerText = `${total} с`;
    document.getElementById('barCount').innerText = `${count} блюд`;

    const bar = document.getElementById('cartBar');
    if (count > 0) {
        bar.classList.add('visible');
    } else {
        bar.classList.remove('visible');
    }
}

// --- Cart Modal ---
function openCartModal() {
    const { total } = getCartStats();
    if (total === 0) return;

    const list = document.getElementById('cartItemsList');
    list.innerHTML = '';

    Object.values(state.cart.items).forEach(item => {
        const div = document.createElement('div');
        div.className = 'cart-item';
        div.innerHTML = `
            <div>
                <div style="font-weight:600;">${item.name}</div>
                <div class="text-muted">${item.price} с x ${item.count}</div>
            </div>
            <div style="font-weight:700;">
                ${item.price * item.count} с
            </div>
        `;
        list.appendChild(div);
    });

    document.getElementById('cartModalTotal').innerText = `${total} с`;
    document.getElementById('cartModal').classList.add('active');
}

function closeCartModal() {
    document.getElementById('cartModal').classList.remove('active');
}

function submitOrder() {
    const { total } = getCartStats();
    if (total === 0) return;

    const orderData = {
        cafe_id: state.cart.cafeId,
        items: Object.values(state.cart.items).map(i => ({
            id: i.id,
            name: i.name,
            price: i.price,
            count: i.count
        })),
        total_price: total
    };

    sendOrder(orderData);
}

function showSuccess(data) {
    closeCartModal();

    // Clear cart
    state.cart = { cafeId: null, items: {} };
    updateCartBar();

    // Show success modal
    document.getElementById('successOrderCode').innerText = data.order_code;
    document.getElementById('whatsappLink').href = data.whatsapp_link;
    document.getElementById('successModal').classList.add('active');
}

function closeSuccessModal() {
    document.getElementById('successModal').classList.remove('active');
    goHome();
}

// Search
function filterCafes() {
    const term = document.getElementById('cafeSearch').value.toLowerCase();
    const filtered = state.cafes.filter(c => c.name.toLowerCase().includes(term));
    renderCafes(filtered);
}
