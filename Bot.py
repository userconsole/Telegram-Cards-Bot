import sqlite3
import os
import random
import time
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --------- #
TOKEN = 'TOKEN'
# create base
DB_PATH = 'dataBase.db'
CARDS_DIR = 'cards'
db_lock = asyncio.Lock()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            total_points INTEGER DEFAULT 0,
            last_used INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_cards (
            user_id INTEGER,
            card_id INTEGER,
            count INTEGER DEFAULT 1,
            UNIQUE(user_id, card_id)
        )
    ''')
    conn.commit()
    conn.close()

# Сохранение пользователя
async def save_user(user):
    async with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (id, username, first_name, last_name, total_points)
            VALUES (?, ?, ?, ?, 0)
        ''', (user.id, user.username, user.first_name, user.last_name))
        conn.commit()
        conn.close()

# Получение случайной карточки
def get_random_card():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM cards ORDER BY RANDOM() LIMIT 1')
    card = cursor.fetchone()
    conn.close()
    return card

# Получение очков пользователя
def get_user_points(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT total_points FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result is None:
        return 0
    return result[0]

# Проверка времени, прошедшего с последнего использования команды
def check_time_limit(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT last_used FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        last_used = result[0]
        current_time = int(time.time())
        # Проверяем разницу во времени
        if current_time - last_used < 1800:  # 1800 секунд = 30 минут
            return False  # Время ещё не истекло
    return True  # Либо времени достаточно, либо запись отсутствует

# Обновление времени последнего использования команды
async def update_last_used(user_id):
    async with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        cursor = conn.cursor()
        current_time = int(time.time())
        cursor.execute('UPDATE users SET last_used = ? WHERE id = ?', (current_time, user_id))
        conn.commit()
        conn.close()

# Добавление карточки в коллекцию пользователя
async def add_card_to_collection(user_id, card_id, points):
    async with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_cards (user_id, card_id, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, card_id) DO UPDATE SET count = count + 1
        ''', (user_id, card_id))
        cursor.execute('''
            UPDATE users
            SET total_points = total_points + ?
            WHERE id = ?
        ''', (points, user_id))
        conn.commit()
        conn.close()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    await update.message.reply_text(f"Приветик,  {user.first_name}! Используй команду /cards, чтобы получить свою первую карточку.")

# Обработчик команды /cards
async def cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    if not check_time_limit(user.id):  # Проверяем, истекло ли 30 минут
        await update.message.reply_text("Карту можно получать раз в 30 минут.")
        return

    card = get_random_card()
    if not card:
        await update.message.reply_text("Карточек пока нет. Упс.")
        return

    card_id, name, rarity, points, image = card
    await add_card_to_collection(user.id, card_id, points)
    await update_last_used(user.id)  # Обновляем время последнего использования
    total_points = get_user_points(user.id)

    caption = (f"🏷️ Название: {name}\n"
               f"🌟 Редкость: {rarity}\n"
               f"💯 Очки карточки: {points}\n"
               f"📝 Ваши общие очки: {total_points}")

    image_path = os.path.join(CARDS_DIR, image)
    try:
        with open(image_path, 'rb') as img:
            await update.message.reply_photo(photo=img, caption=caption)
    except FileNotFoundError:
        await update.message.reply_text("Карточек нет в базе...")

# Обработчик команды /collection
async def collection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.name, c.rarity, uc.count
            FROM user_cards uc
            JOIN cards c ON uc.card_id = c.id
            WHERE uc.user_id = ?
        ''', (user.id,))
        cards = cursor.fetchall()
        conn.close()

    if not cards:
        await update.message.reply_text("Ваша коллекция пуста.")
        return

    collection_text = "\n".join([f"🏷️ {name} [{rarity}] {count}x" for name, rarity, count in cards])
    await update.message.reply_text(f"📜 Ваша коллекция:\n{collection_text}")

# Обработчик команды /leaderboard
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db_lock:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT first_name, total_points FROM users
            ORDER BY total_points DESC
            LIMIT 10
        ''')
        top_users = cursor.fetchall()
        conn.close()

    if not top_users:
        await update.message.reply_text("Рейтинг пока пуст.")
        return

    message = "🏆 **Топ-10 пользователей:**\n"
    for i, (first_name, points) in enumerate(top_users, start=1):
        message += f"{i}. {first_name}: {points} очков\n \n"

    await update.message.reply_text(message)

# Основная функция запуска бота
def main():
    init_db()
   
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cards", cards))
    app.add_handler(CommandHandler("collection", collection))
    app.add_handler(CommandHandler("leaderboard", leaderboard))

    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
