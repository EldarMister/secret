# Структура проекта Business Assistant GO

```
business-assistant-go/
│
├── src/                              # Исходный код
│   ├── __init__.py                   # Инициализация пакета
│   ├── app.py                        # Flask Application Factory
│   ├── config.py                     # Конфигурация и константы
│   ├── main.py                       # Обработчик WhatsApp webhook
│   ├── telegram_handler.py           # Обработчик Telegram callback
│   ├── client_confirm_handler.py     # Обработка подтверждений клиента
│   ├── services.py                   # Вспомогательные функции (API)
│   ├── db.py                         # Работа с базой данных (Google Sheets)
│   └── cron_jobs.py                  # Планировщик задач (таймауты)
│
├── logs/                             # Логи приложения
│   ├── business_assistant.log        # Основной лог
│   ├── access.log                    # Access лог (Gunicorn)
│   ├── error.log                     # Error лог (Gunicorn)
│   └── cron.log                      # Лог cron-задач
│
├── .env                              # Переменные окружения (не в git!)
├── .env.example                      # Пример переменных окружения
├── .gitignore                        # Исключения для git
│
├── requirements.txt                  # Python зависимости
├── README.md                         # Документация проекта
├── PROJECT_STRUCTURE.md              # Этот файл
│
├── deploy.sh                         # Скрипт деплоя
├── setup_cron.sh                     # Настройка cron-задач
└── business-assistant.service        # Systemd сервис
```

## Описание модулей

### src/app.py
**Назначение:** Application Factory для Flask  
**Функции:**
- Создание экземпляра Flask приложения
- Регистрация маршрутов (routes)
- Инициализация базы данных при старте

### src/config.py
**Назначение:** Конфигурация приложения  
**Содержит:**
- Флаги акций (IS_RAMADAN)
- Комиссии и тарифы
- ID Telegram групп
- API ключи (из .env)
- Состояния State Machine
- Константы сообщений

### src/main.py
**Назначение:** Обработчик WhatsApp webhook  
**Функции:**
- `handle_whatsapp()` - главный обработчик
- `handle_idle_state()` - обработка выбора услуги
- `handle_cafe_order()` - заказ в кафе
- `handle_shop_order()` - заказ в магазин
- `handle_pharmacy_order()` - заказ в аптеку
- `handle_taxi_order()` - заказ такси
- `handle_porter_order()` - заказ грузоперевозки

### src/telegram_handler.py
**Назначение:** Обработчик Telegram callback  
**Функции:**
- `handle_telegram_webhook()` - главный обработчик
- `handle_taxi_take()` - таксист берет заказ
- `handle_pharmacy_bid()` - аптека предлагает цену
- `handle_cafe_accept()` - кафе принимает заказ
- `handle_shop_take()` - закупщик берет заказ
- `handle_porter_take()` - портер берет заказ

### src/client_confirm_handler.py
**Назначение:** Обработка подтверждений клиента  
**Функции:**
- `handle_pharmacy_confirm()` - подтверждение аптеки
- `handle_pharmacy_cancel()` - отмена аптеки
- `handle_shop_confirm()` - подтверждение магазина
- `handle_confirmation()` - общий обработчик

### src/services.py
**Назначение:** Вспомогательные функции API  
**Функции:**
- `send_whatsapp()` - отправка сообщения WhatsApp
- `send_whatsapp_buttons()` - отправка кнопок WhatsApp
- `send_whatsapp_image()` - отправка изображения WhatsApp
- `send_telegram_group()` - отправка в группу Telegram
- `send_telegram_private()` - личное сообщение Telegram
- `send_telegram_photo()` - отправка фото Telegram
- `speech_to_text()` - распознавание голоса
- `calculate_taxi_price()` - расчет цены такси

### src/db.py
**Назначение:** Работа с базой данных  
**Классы:**
- `Database` - основной класс для работы с Google Sheets
- `User` - класс пользователя
- `DriverInfo` - класс информации о водителе

**Методы:**
- `get_user()` - получить пользователя
- `create_user()` - создать пользователя
- `update_user()` - обновить пользователя
- `create_order()` - создать заказ
- `get_order()` - получить заказ
- `update_order_status()` - обновить статус заказа
- `get_driver_info()` - получить информацию о водителе
- `update_balance()` - обновить баланс
- `log_transaction()` - логирование транзакций

### src/cron_jobs.py
**Назначение:** Планировщик задач  
**Функции:**
- `check_cafe_timeouts()` - проверка таймаутов кафе (2 мин)
- `check_pharmacy_timeouts()` - проверка таймаутов аптек (3 мин)
- `check_taxi_timeouts()` - проверка таймаутов такси (1 мин)
- `run_all_cron_jobs()` - запуск всех проверок

## Потоки данных

### 1. Заказ в Кафе
```
Клиент (WhatsApp) → main.py → db.py (создать заказ)
                                         ↓
Telegram Группа Кафе ← services.py ← telegram_handler.py
       ↓
Кафе принимает → telegram_handler.py → services.py → Клиент (WhatsApp)
       ↓
Автоматически: telegram_handler.py → Telegram Группа Такси (доставка)
```

### 2. Заказ в Магазин
```
Клиент (WhatsApp) → main.py → db.py (сохранить список)
                                         ↓
Закупщик (Telegram ЛС) ← services.py ← main.py
       ↓
Закупщик берет → telegram_handler.py → services.py → Клиент (WhatsApp)
```

### 3. Заказ в Аптеку
```
Клиент (WhatsApp) → main.py → db.py (создать заказ)
                                         ↓
Telegram Группа Аптек ← services.py ← main.py
       ↓
Аптека указывает цену → telegram_handler.py
       ↓
Клиент подтверждает → client_confirm_handler.py → Telegram Группа Такси
```

### 4. Заказ Такси
```
Клиент (WhatsApp) → main.py → db.py (создать заказ)
                                         ↓
Telegram Группа Такси ← services.py ← main.py
       ↓
Таксист берет → telegram_handler.py → db.py (списать комиссию)
                                         ↓
Клиент (WhatsApp) ← services.py ← telegram_handler.py
```

### 5. Заказ Портера
```
Клиент (WhatsApp) → main.py → db.py (создать заказ)
                                         ↓
Telegram Группа Портер ← services.py ← main.py
       ↓
Водитель берет → telegram_handler.py → services.py → Клиент (WhatsApp)
```

## State Machine (Состояния пользователя)

```
                    ┌─────────────────────────────────────┐
                    │              IDLE                   │
                    │  (Ожидание выбора услуги)           │
                    └──────────────┬──────────────────────┘
                                   │
        ┌──────────┬───────────┬───┴───┬───────────┬──────────┐
        ▼          ▼           ▼       ▼           ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────────┐ ┌────────┐
   │  CAFE  │ │  SHOP  │ │ PHARM  │ │ TAXI │ │  PORTER  │ │  ...   │
   │ _ORDER │ │ _LIST  │ │_WAIT_RX│ │_ROUTE│ │ _DETAILS │ │        │
   └───┬────┘ └────┬───┘ └───┬────┘ └───┬──┘ └────┬─────┘ └────────┘
       │           │         │          │         │
       ▼           ▼         ▼          ▼         ▼
   Telegram    Telegram  Telegram   Telegram  Telegram
    Группа     Закупщик   Группа     Группа    Группа
    Кафе         ЛС      Аптек      Такси     Портер
       │           │         │          │         │
       └───────────┴─────────┴──────────┴─────────┘
                          │
                          ▼
                    ┌────────────┐
                    │    IDLE    │
                    │  (Сброс)   │
                    └────────────┘
```

## База данных (Google Sheets)

### Таблица Users
| Колонка | Описание |
|---------|----------|
| phone | Номер телефона (ID) |
| name | Имя пользователя |
| current_state | Текущее состояние |
| temp_data | Временные данные (JSON) |
| created_at | Дата создания |
| updated_at | Дата обновления |

### Таблица Orders
| Колонка | Описание |
|---------|----------|
| id | ID заказа |
| type | Тип (cafe/shop/pharmacy/taxi/porter) |
| status | Статус (pending/accepted/in_progress/completed/cancelled) |
| client_phone | Телефон клиента |
| details | Детали заказа |
| price_total | Общая сумма |
| commission | Комиссия |
| provider_id | ID провайдера (кафе/аптека) |
| driver_id | ID водителя |
| created_at | Дата создания |
| updated_at | Дата обновления |

### Таблица Drivers
| Колонка | Описание |
|---------|----------|
| telegram_id | Telegram ID |
| name | Имя |
| car_model | Марка авто |
| plate | Номер |
| balance | Баланс |
| phone | Телефон |
| is_active | Активен |
| created_at | Дата создания |

### Таблица Logs
| Колонка | Описание |
|---------|----------|
| timestamp | Время |
| action | Действие |
| user_id | ID пользователя |
| order_id | ID заказа |
| details | Детали |
| amount | Сумма |

## API Endpoints

| Endpoint | Method | Описание | Request | Response |
|----------|--------|----------|---------|----------|
| `/whatsapp_webhook` | POST | Webhook WhatsApp | FormData | JSON |
| `/telegram_webhook` | POST | Webhook Telegram | JSON | JSON |
| `/health` | GET | Health check | - | JSON |

## Cron Jobs

| Задача | Период | Описание |
|--------|--------|----------|
| check_cafe_timeouts | Каждую минуту | Проверка таймаутов кафе (2 мин) |
| check_pharmacy_timeouts | Каждую минуту | Проверка таймаутов аптек (3 мин) |
| check_taxi_timeouts | Каждую минуту | Проверка таймаутов такси (1 мин) |

## Environment Variables

| Переменная | Описание | Обязательная |
|------------|----------|--------------|
| GREEN_API_INSTANCE | ID инстанса GREEN API | Да |
| GREEN_API_TOKEN | Токен GREEN API | Да |
| TELEGRAM_BOT_TOKEN | Токен Telegram бота | Да |
| GOOGLE_SHEETS_CREDENTIALS | Путь к credentials.json | Да |
| GOOGLE_SHEETS_SPREADSHEET_ID | ID Google таблицы | Да |
| GROUP_CAFE_ID | ID группы кафе | Да |
| GROUP_PHARMACY_ID | ID группы аптек | Да |
| GROUP_TAXI_ID | ID группы такси | Да |
| GROUP_PORTER_ID | ID группы портер | Да |
| SHOPPER_TELEGRAM_ID | ID закупщика | Да |
| OPENAI_API_KEY | Ключ OpenAI (для голоса) | Нет |
| LOG_LEVEL | Уровень логирования | Нет |
