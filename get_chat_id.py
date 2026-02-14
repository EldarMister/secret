import os
import time
import requests
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN or TOKEN == "your_bot_token":
    print("❌ ОШИБКА: Сначала укажите ваш TELEGRAM_BOT_TOKEN в файле .env")
    print("1. Создайте бота в @BotFather")
    print("2. Скопируйте токен")
    print("3. Вставьте его в .env вместо 'your_bot_token'")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

print(f"✅ Токен найден: {TOKEN[:5]}...{TOKEN[-5:]}")
print("🤖 Бот запущен в режиме получения ID чатов...")
print("\n📝 ИНСТРУКЦИЯ:")
print("1. Добавьте вашего бота в нужную группу (Такси, Кафе и т.д.)")
print("2. Сделайте его администратором (не обязательно, но желательно)")
print("3. Напишите любое сообщение в группу")
print("4. ID группы появится здесь ↓\n")

offset = 0

while True:
    try:
        response = requests.get(URL, params={"offset": offset, "timeout": 30})
        data = response.json()
        
        if data.get("ok"):
            for result in data.get("result", []):
                offset = result["update_id"] + 1
                
                message = result.get("message") or result.get("my_chat_member") or result.get("channel_post")
                
                if message:
                    chat = message.get("chat", {})
                    chat_id = chat.get("id")
                    title = chat.get("title", "Личный чат")
                    type_ = chat.get("type")
                    
                    print(f"📢 Обнаружен чат: {title}")
                    print(f"🆔 ID: {chat_id}")
                    print(f"Тип: {type_}")
                    print("-" * 30)
                    
        time.sleep(1)
        
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        time.sleep(5)
