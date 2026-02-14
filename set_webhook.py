"""
Установка Telegram Webhook
Запускайте этот скрипт ПОСЛЕ запуска ngrok и app.py

Использование:
    python set_webhook.py https://your-ngrok-url.ngrok-free.dev
"""

import sys
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN or TOKEN == "your_bot_token":
    print("❌ Укажите TELEGRAM_BOT_TOKEN в .env")
    sys.exit(1)

if len(sys.argv) < 2:
    print("❌ Укажите ngrok URL:")
    print("   python set_webhook.py https://xxxx.ngrok-free.dev")
    sys.exit(1)

ngrok_url = sys.argv[1].rstrip("/")
webhook_url = f"{ngrok_url}/telegram_webhook"

print(f"🔗 Устанавливаем webhook: {webhook_url}")

# Устанавливаем webhook
url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
response = requests.post(url, json={"url": webhook_url})
result = response.json()

if result.get("ok"):
    print(f"✅ Webhook установлен!")
    print(f"   URL: {webhook_url}")
    print(f"\n🎉 Теперь кнопки 'Взять заказ' будут работать!")
else:
    print(f"❌ Ошибка: {result}")
    print("\nВозможные причины:")
    print("1. Неверный токен бота")
    print("2. Ngrok URL недоступен")

# Проверяем текущий webhook
info_url = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
info = requests.get(info_url).json()
print(f"\n📋 Текущий webhook:")
print(f"   URL: {info.get('result', {}).get('url', 'не установлен')}")
print(f"   Pending updates: {info.get('result', {}).get('pending_update_count', 0)}")

# Устанавливаем команды бота (меню внизу чата)
print(f"\n⚙️ Устанавливаем команды бота...")
commands_url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
commands = {
    "commands": [
        {"command": "start", "description": "🏠 Главное меню"},
        {"command": "register", "description": "📝 Регистрация водителя"},
        {"command": "balance", "description": "💰 Проверить баланс"},
        {"command": "profile", "description": "👤 Мой профиль"},
        {"command": "stats", "description": "📊 Моя статистика"},
        {"command": "help", "description": "❓ Помощь"},
    ]
}
cmd_response = requests.post(commands_url, json=commands)
cmd_result = cmd_response.json()

if cmd_result.get("ok"):
    print("✅ Команды бота установлены!")
    print("   /start, /register, /balance, /profile, /stats, /help")
else:
    print(f"❌ Ошибка установки команд: {cmd_result}")
