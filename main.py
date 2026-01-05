import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from pyrogram import Client

# --- SOZLAMALAR ---
API_ID = 31451873  # my.telegram.org dan olingan
API_HASH = "894c69cddf1d16015f0f42461fe408ae"
BOT_TOKEN = "8523215322:AAHu8zECN-D8sMKgLfOJmUMLQhWZt3aHUvs"
ADMIN_ID = 6915674403  # O'zingizning Telegram ID raqamingiz
BOT_USERNAME = "@Auto_XabarBot" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- MA'LUMOTLAR BAZASI ---
def db_query(sql, params=(), fetch=False):
    conn = sqlite3.connect('autoxabar.db')
    cursor = conn.cursor()
    cursor.execute(sql, params)
    data = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (user_id INTEGER PRIMARY KEY, session TEXT, msg_text TEXT, 
                 photo_id TEXT, interval INTEGER DEFAULT 600, is_pro INTEGER DEFAULT 0,
                 selected_groups TEXT DEFAULT '', total_sent INTEGER DEFAULT 0)''')

# --- HOLATLAR ---
class States(StatesGroup):
    waiting_for_msg = State()
    waiting_for_pro_id = State()

# --- MENYU ---
def main_menu(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("👥 Profillar", "📊 Statistika", "💬 Xabar", "📁 Guruhlar")
    kb.add("▶️ Ishga tushirish", "⏹ To'xtatish", "⏱ Interval")
    kb.add("⭐ Pro", "👤 Profil")
    if uid == ADMIN_ID: kb.add("👨‍💻 Admin Panel")
    return kb

# --- XABAR YUBORISH LOOP ---
active_tasks = {}

async def working_loop(user_id, session_str):
    try:
        async with Client(f"u_{user_id}", api_id=API_ID, api_hash=API_HASH, session_string=session_str) as app:
            while True:
                user = db_query("SELECT msg_text, photo_id, interval, is_pro, selected_groups FROM users WHERE user_id=?", (user_id,), True)[0]
                if not user[0] or not user[4]: break
                
                msg_text = user[0]
                # Reklama (Footer) qo'shish - Faqat PRO bo'lmaganlar uchun
                if user[3] == 0:
                    msg_text += f"\n\n🤖 {BOT_USERNAME} orqali yuborildi"
                
                groups = user[4].split(",")
                for gid in groups:
                    try:
                        if user[1]: # Rasm bo'lsa
                            await app.send_photo(int(gid), user[1], caption=msg_text)
                        else: # Faqat matn
                            await app.send_message(int(gid), msg_text)
                        # Statistikani yangilash
                        db_query("UPDATE users SET total_sent = total_sent + 1 WHERE user_id=?", (user_id,))
                        await asyncio.sleep(3) # Bloklanmaslik uchun pauza
                    except: continue
                
                await asyncio.sleep(user[2]) 
    except Exception as e:
        logging.error(f"Xatolik: {e}")

# --- HANDLERLAR ---

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang.", reply_markup=main_menu(message.from_user.id))

# Interval tanlash (Hamma uchun bir xil)
@dp.message_handler(lambda m: m.text == "⏱ Interval")
async def set_int(message: types.Message):
    kb = types.InlineKeyboardMarkup(row_width=3)
    ints = [("2 daq", 120), ("3 daq", 180), ("5 daq", 300), ("10 daq", 600), ("30 daq", 1800)]
    btns = [types.InlineKeyboardButton(text=i[0], callback_data=f"setint_{i[1]}") for i in ints]
    kb.add(*btns)
    await message.answer("Xabar yuborish vaqtini tanlang (Hamma uchun ochiq):", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('setint_'))
async def save_int(call: types.CallbackQuery):
    val = int(call.data.split("_")[1])
    db_query("UPDATE users SET interval=? WHERE user_id=?", (val, call.from_user.id))
    await call.message.edit_text(f"Tayyor! Xabarlar har {val//60} daqiqada yuboriladi. ✅")

# Xabarni ko'rish va Statistika
@dp.message_handler(lambda m: m.text == "📊 Statistika")
async def stats(message: types.Message):
    user = db_query("SELECT total_sent, is_pro FROM users WHERE user_id=?", (message.from_user.id,), True)[0]
    status = "Premium ⭐" if user[1] == 1 else "Oddiy 👤"
    await message.answer(f"📊 **Statistika:**\n\nStatus: {status}\nJami yuborilgan xabarlar: {user[0]} ta", parse_mode="Markdown")

# Pro sotib olish
@dp.message_handler(lambda m: m.text == "⭐ Pro")
async def pro_buy(message: types.Message):
    await message.answer("⭐ **PRO Tarif imkoniyatlari:**\n\n"
                         "1. Xabar tagidagi reklama olib tashlanadi.\n"
                         "2. Cheksiz guruhlarga yuborish.\n"
                         "3. Admin tomonidan qo'llab-quvvatlash.\n\n"
                         "💳 To'lov uchun adminga murojaat qiling.")

# Ishga tushirish va To'xtatish
@dp.message_handler(lambda m: m.text == "▶️ Ishga tushirish")
async def run_bot(message: types.Message):
    uid = message.from_user.id
    user = db_query("SELECT session, msg_text, selected_groups FROM users WHERE user_id=?", (uid,), True)[0]
    if not user[0]: return await message.answer("Avval akkaunt ulanmagan! 👤 Profil bo'limiga o'ting.")
    if not user[1]: return await message.answer("Xabar matni kiritilmagan! 💬 Xabar bo'limiga o'ting.")
    
    active_tasks[uid] = asyncio.create_task(working_loop(uid, user[0]))
    await message.answer("Bot ishga tushdi! ✅")

@dp.message_handler(lambda m: m.text == "⏹ To'xtatish")
async def stop_bot(message: types.Message):
    uid = message.from_user.id
    if uid in active_tasks:
        active_tasks[uid].cancel()
        del active_tasks[uid]
        await message.answer("Bot to'xtatildi! 🛑")
    else:
        await message.answer("Bot ishlamayapti.")

if __name__ == '__main__':
    init_db()
    executor.start_polling(dp, skip_updates=True)
  
