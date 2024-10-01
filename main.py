import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from pymongo import MongoClient
from dotenv import load_dotenv

# Завантаження змінних середовища з .env файлу
load_dotenv()
API_TOKEN = os.getenv('API_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))  # Додайте ваш Telegram user_id у .env файлі

# Перевірка наявності необхідних змінних
if not API_TOKEN:
    raise ValueError("Не вдалося знайти API_TOKEN в .env файлі.")
if not MONGO_URI:
    raise ValueError("Не вдалося знайти MONGO_URI в .env файлі.")
if not ADMIN_USER_ID:
    raise ValueError("Не вдалося знайти ADMIN_USER_ID в .env файлі.")

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація бота та диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Підключення до MongoDB
try:
    client = MongoClient(MONGO_URI)
    db = client['nc_helper_bot']
    chats_collection = db['chats']
    tickets_collection = db['tickets']
    # Тестове підключення
    client.admin.command('ping')
    logging.info("Успішно підключено до MongoDB.")
except Exception as e:
    logging.error(f"Не вдалося підключитися до MongoDB: {e}")
    exit(1)

# Створення клавіатури з командами
start_buttons = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='/dev'),
            KeyboardButton(text='/prod'),
            KeyboardButton(text='/all')
        ],
        [
            KeyboardButton(text='/tickets'),
            # KeyboardButton(text='/history'),
            KeyboardButton(text='/id'),
            KeyboardButton(text='/help')
        ]
    ],
    resize_keyboard=True
)

# Функція для збереження чату в MongoDB
def save_chat(chat_data):
    try:
        existing = chats_collection.find_one({"chat_id": chat_data["chat_id"]})
        if not existing:
            chats_collection.insert_one(chat_data)
            logging.info(f"Збережено новий чат: {chat_data}")
        else:
            chats_collection.update_one({"chat_id": chat_data["chat_id"]}, {"$set": chat_data})
            logging.info(f"Оновлено чат: {chat_data}")
    except Exception as e:
        logging.error(f"Помилка при збереженні чату в базу даних: {e}")


# Створення інлайн-кнопок для закриття тікетів
def get_close_ticket_keyboard(ticket_id: str):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Закрити тікет ✅", callback_data=f"close_{ticket_id}")
            ]
        ]
    )
    return keyboard


# Створення інлайн-кнопок для призначення групи чату
def get_assign_group_keyboard(chat_id: int):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="DEV", callback_data=f"assign_DEV_{chat_id}"),
                InlineKeyboardButton(text="PROD", callback_data=f"assign_PROD_{chat_id}")
            ]
        ]
    )
    return keyboard


# Обробник події, коли статус бота змінюється в чаті
@dp.my_chat_member()
async def on_my_chat_member(update: types.ChatMemberUpdated):
    logging.info(f"Отримано оновлення my_chat_member: {update}")
    try:
        if update.new_chat_member.user.id != bot.id:
            return

        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status

        # Реагуємо лише якщо бот був доданий до чату
        if old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
            chat = update.chat
            chat_data = {
                "chat_id": chat.id,
                "type": chat.type,
                "title": chat.title if hasattr(chat, 'title') else None,
                "assigned_group": None
            }

            # Надсилання тестового повідомлення та його видалення
            try:
                test_message = await bot.send_message(chat.id, "🤖 Бот успішно доданий до чату!")
                await asyncio.sleep(2)
                await test_message.delete()
            except Exception as e:
                logging.error(f"Помилка при відправці або видаленні повідомлення в чаті: {e}")

            # Збереження чату в базу даних
            save_chat(chat_data)

            # Надсилання повідомлення адміністратору
            try:
                await bot.send_message(
                    ADMIN_USER_ID,
                    f"🔔 Новий чат додано:\n"
                    f"🔹 <b>ID чату:</b> {chat.id}\n"
                    f"🔹 <b>Тип чату:</b> {chat.type}\n"
                    f"🔹 <b>Назва чату:</b> {chat.title}",
                    parse_mode='HTML',
                    reply_markup=get_assign_group_keyboard(chat.id)
                )
            except Exception as e:
                logging.error(f"Помилка при відправці повідомлення адміністратору: {e}")
    except Exception as e:
        logging.error(f"Помилка в обробнику on_my_chat_member: {e}")


# Обробник для призначення групи чату
@dp.callback_query(F.data.startswith('assign_'))
async def assign_chat_group(callback_query: types.CallbackQuery):
    data_parts = callback_query.data.split('_')
    group_name = data_parts[1]
    chat_id = int(data_parts[2])

    # Оновлення групи в базі даних
    chats_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"assigned_group": group_name}}
    )

    await callback_query.answer(f"Чат призначено до групи {group_name}")
    await callback_query.message.edit_text(
        f"✅ Чат призначено до групи {group_name}."
    )


# Команда /start та /help (тільки в приватному чаті)
@dp.message(Command(commands=['start', 'help']), F.chat.type == ChatType.PRIVATE)
async def send_welcome(message: types.Message):
    welcome_text = (
        "👋 Вітаю! Я допоміжний бот для розсилки повідомлень у різні групи.\n\n"
        "📋 <b>Список доступних команд:</b>\n\n"
        "➡️ <b>/dev [повідомлення]</b> - Надіслати повідомлення у DEV-чати.\n"
        "➡️ <b>/prod [повідомлення]</b> - Надіслати повідомлення у PROD-чати.\n"
        "➡️ <b>/all [повідомлення]</b> - Надіслати повідомлення у всі чати.\n"
        "➡️ <b>/tickets</b> - Показати всі відкриті тікети.\n"
        "➡️ <b>/history</b> - Показати історію закритих тікетів.\n"
        "➡️ <b>/id</b> - Отримати ID поточного чату.\n\n"
        "ℹ️ <b>Як працюють тікети:</b>\n"
        "- При відправці повідомлення створюється тікет.\n"
        "- Тікет відображається у всіх чатах, куди він був надісланий.\n"
        "- Кожен чат може закрити тікет незалежно.\n"
        "- Коли тікет закрито в усіх чатах, він переміщується в історію.\n\n"
        "🔘 Використовуйте кнопки нижче для зручності."
    )
    await message.reply(welcome_text, reply_markup=start_buttons, parse_mode='HTML')



# Команда /id для отримання ID чату (тільки в приватному чаті)
@dp.message(Command(commands=['id']), F.chat.type == ChatType.PRIVATE)
async def send_chat_id(message: types.Message):
    chat = message.chat
    chat_id = chat.id
    chat_type = chat.type
    chat_name = chat.title if hasattr(chat, 'title') else (
        f"{message.from_user.first_name} {message.from_user.last_name}" if message.from_user.last_name else message.from_user.first_name
    )

    user_id = message.from_user.id

    # Відправка інформації в особисті повідомлення користувача
    try:
        await bot.send_message(
            user_id,
            f"📌 <b>Інформація про чат:</b>\n"
            f"🔹 <b>ID чату:</b> {chat_id}\n"
            f"🔹 <b>Тип чату:</b> {chat_type}\n"
            f"🔹 <b>Назва чату:</b> {chat_name}",
            parse_mode='HTML'
        )
    except Exception as e:
        logging.error(f"Помилка при відправці особистого повідомлення: {e}")
        await message.reply(
            "❌ Не вдалося відправити інформацію в особисті повідомлення. Переконайтесь, що ви дозволили боту надсилати вам повідомлення.")


# Функція для створення унікального ID тікета
def generate_ticket_id():
    import uuid
    return str(uuid.uuid4())


# Команда для надсилання повідомлень у DEV чати (тільки в приватному чаті)
@dp.message(Command(commands=['dev']), F.chat.type == ChatType.PRIVATE)
async def send_dev_message(message: types.Message):
    text = message.text.partition('/dev ')[2]
    if not text:
        await message.reply("⚠️ Введіть повідомлення після /dev для відправки.")
        return

    ticket_id = generate_ticket_id()
    ticket_data = {
        "ticket_id": ticket_id,
        "status": {},
        "text": text,
        "message_ids": []
    }

    # Отримуємо всі чати, призначені до групи DEV
    dev_chats = chats_collection.find({"assigned_group": "DEV"})
    for chat in dev_chats:
        try:
            sent_message = await bot.send_message(
                chat["chat_id"], f"🛠️ <b>{text}</b>",
                parse_mode='HTML', reply_markup=get_close_ticket_keyboard(ticket_id)
            )
            ticket_data["message_ids"].append({
                "chat_id": chat["chat_id"],
                "message_id": sent_message.message_id
            })
            ticket_data["status"][str(chat["chat_id"])] = "open"
        except Exception as e:
            logging.error(f"Не вдалося надіслати повідомлення в чат {chat['chat_id']}: {e}")

    tickets_collection.insert_one(ticket_data)
    await message.reply(f"✅ Повідомлення відправлено у DEV чати: {text}")


# Команда для надсилання повідомлень у PROD чати (тільки в приватному чаті)
@dp.message(Command(commands=['prod']), F.chat.type == ChatType.PRIVATE)
async def send_prod_message(message: types.Message):
    text = message.text.partition('/prod ')[2]
    if not text:
        await message.reply("⚠️ Введіть повідомлення після /prod для відправки.")
        return

    ticket_id = generate_ticket_id()
    ticket_data = {
        "ticket_id": ticket_id,
        "status": {},
        "text": text,
        "message_ids": []
    }

    # Отримуємо всі чати, призначені до групи PROD
    prod_chats = chats_collection.find({"assigned_group": "PROD"})
    for chat in prod_chats:
        try:
            sent_message = await bot.send_message(
                chat["chat_id"], f"🚀 <b>{text}</b>",
                parse_mode='HTML', reply_markup=get_close_ticket_keyboard(ticket_id)
            )
            ticket_data["message_ids"].append({
                "chat_id": chat["chat_id"],
                "message_id": sent_message.message_id
            })
            ticket_data["status"][str(chat["chat_id"])] = "open"
        except Exception as e:
            logging.error(f"Не вдалося надіслати повідомлення в чат {chat['chat_id']}: {e}")

    tickets_collection.insert_one(ticket_data)
    await message.reply(f"✅ Повідомлення відправлено у PROD чати: {text}")


# Команда для надсилання повідомлень у всі чати (тільки в приватному чаті)
@dp.message(Command(commands=['all']), F.chat.type == ChatType.PRIVATE)
async def send_all_message(message: types.Message):
    text = message.text.partition('/all ')[2]
    if not text:
        await message.reply("⚠️ Введіть повідомлення після /all для відправки.")
        return

    ticket_id = generate_ticket_id()
    ticket_data = {
        "ticket_id": ticket_id,
        "status": {},
        "text": text,
        "message_ids": []
    }

    # Отримуємо всі чати, незалежно від групи
    all_chats = chats_collection.find({"assigned_group": {"$in": ["DEV", "PROD"]}})
    for chat in all_chats:
        try:
            sent_message = await bot.send_message(
                chat["chat_id"], f"📢 <b>{text}</b>",
                parse_mode='HTML', reply_markup=get_close_ticket_keyboard(ticket_id)
            )
            ticket_data["message_ids"].append({
                "chat_id": chat["chat_id"],
                "message_id": sent_message.message_id
            })
            ticket_data["status"][str(chat["chat_id"])] = "open"
        except Exception as e:
            logging.error(f"Не вдалося надіслати повідомлення в чат {chat['chat_id']}: {e}")

    tickets_collection.insert_one(ticket_data)
    await message.reply(f"✅ Повідомлення відправлено у всі чати: {text}")


# Команда для показу відкритих тікетів (тільки в приватному чаті)
@dp.message(Command(commands=['tickets']), F.chat.type == ChatType.PRIVATE)
async def show_tickets(message: types.Message):
    open_tickets = list(tickets_collection.find({"status": {"$ne": "closed"}}))
    if not open_tickets:
        await message.reply("ℹ️ Немає відкритих тікетів.")
        return

    response = "📝 <b>Відкриті тікети:</b>\n"
    for ticket in open_tickets:
        response += f"• <b>{ticket['text']}</b>\n"

    await message.reply(response, parse_mode='HTML')


# Команда для показу історії закритих тікетів з текстом (тільки в приватному чаті)
@dp.message(Command(commands=['history']), F.chat.type == ChatType.PRIVATE)
async def show_history(message: types.Message):
    closed_tickets = list(tickets_collection.find({"status": "closed"}))
    if not closed_tickets:
        await message.reply("ℹ️ Немає закритих тікетів.")
        return

    response = "📜 <b>Історія закритих тікетів:</b>\n"
    for ticket in closed_tickets:
        response += (
            f"• <b>{ticket['text']}</b>\n"
            f"  Статус: закрито\n\n"
        )

    await message.reply(response, parse_mode='HTML')


# Обробка запиту на закриття тікета
@dp.callback_query(F.data.startswith('close_'))
async def close_ticket(callback_query: types.CallbackQuery):
    ticket_id = callback_query.data.split('_')[1]
    chat_id = str(callback_query.message.chat.id)
    ticket = tickets_collection.find_one({"ticket_id": ticket_id})

    if ticket:
        # Перевіряємо статус тікета в конкретному чаті
        if ticket["status"].get(chat_id) != "closed":
            # Оновлюємо статус тікета для цього чату
            ticket["status"][chat_id] = "closed"
            tickets_collection.update_one({"ticket_id": ticket_id}, {"$set": {"status": ticket["status"]}})
            await callback_query.answer("Тікет закрито.")
            # Оновлюємо повідомлення в чаті
            new_text = callback_query.message.text + "\n\n✅ <b>Тікет закрито.</b>"
            new_text = new_text.replace("🛠️", "✅").replace("🚀", "✅").replace("📢", "✅")
            try:
                await bot.edit_message_text(
                    text=new_text,
                    chat_id=callback_query.message.chat.id,
                    message_id=callback_query.message.message_id,
                    parse_mode='HTML'
                )
            except Exception as e:
                logging.error(f"Не вдалося оновити повідомлення в чаті {callback_query.message.chat.id}: {e}")
        else:
            await callback_query.answer("❌ Тікет вже закрито.")
    else:
        await callback_query.answer("❌ Тікет не знайдено.")


# Обробка невідомих команд у приватному чаті
@dp.message(F.chat.type == ChatType.PRIVATE)
async def handle_unknown(message: types.Message):
    if message.text and message.text.startswith('/'):
        await message.reply("❓ Я не розумію цю команду. Використовуйте /help для перегляду доступних команд.")
    else:
        await message.reply("Ви надіслали повідомлення, але я не можу його обробити.")


if __name__ == '__main__':
    async def main():
        # Запуск бота
        await dp.start_polling(bot)


    asyncio.run(main())
