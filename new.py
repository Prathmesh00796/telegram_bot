import logging
import random
import string
import os
import aiosqlite
from datetime import datetime
from flask import Flask
from threading import Thread

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.helpers import escape_markdown

# ================= CONFIG =================

TOKEN = os.environ.get("7713180596:AAHVmLIsuNzn33MsO6ZKTuDpIN0HTAmvuu0")  # SET THIS IN RENDER
ADMIN_ID = 6843292223
CHANNELS = ["@freecourse6969", "@lootlebigdeels", "@pcsheinstock"]
BOT_USERNAME = "sheinfreecodesbot"
DB_PATH = "referral_bot.db"

# ================= FLASK SERVER FOR RENDER =================

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

Thread(target=run_flask).start()

# ================= DATABASE =================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            referrals INTEGER DEFAULT 0,
            referred_by INTEGER,
            join_date TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            points_used INTEGER,
            voucher_code TEXT UNIQUE,
            voucher_amount INTEGER,
            date TEXT
        )''')
        await db.commit()

# ================= UTILS =================

def esc(text):
    return escape_markdown(str(text), version=2)

async def is_subscribed(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        except:
            return False
    return True

async def generate_voucher(amount):
    prefix = {500: "SVI", 1000: "SVH", 2000: "SVD"}.get(amount, "SVX")
    while True:
        code = prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM withdrawals WHERE voucher_code=?", (code,)) as cur:
                if not await cur.fetchone():
                    return code

# ================= UI =================

def join_markup():
    buttons = [[InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch[1:]}")] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("✅ Verify Joining", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def main_menu():
    keyboard = [
        [KeyboardButton("💰 Balance"), KeyboardButton("🎁 Refer & Earn")],
        [KeyboardButton("🎟 Withdraw Voucher"), KeyboardButton("👤 Profile")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ================= HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    args = context.args

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            user_data = await cur.fetchone()

        if not user_data:
            ref_by = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user_id else None
            await db.execute(
                "INSERT INTO users (user_id, username, referred_by, join_date) VALUES (?,?,?,?)",
                (user_id, user.username, ref_by, datetime.now().strftime("%Y-%m-%d"))
            )
            await db.commit()
            if ref_by:
                context.user_data['pending_ref'] = ref_by

    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            "👋 Welcome!\n\nJoin required channels first.",
            reply_markup=join_markup()
        )
    else:
        await update.message.reply_text("✨ Welcome back!", reply_markup=main_menu())

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        ref_id = context.user_data.pop('pending_ref', None)
        if ref_id:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET points=points+1, referrals=referrals+1 WHERE user_id=?",
                    (ref_id,)
                )
                await db.commit()

        await query.edit_message_text("✅ Verified!")
        await context.bot.send_message(user_id, "Main Menu:", reply_markup=main_menu())
    else:
        await query.answer("Join all channels first!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running correctly.")

# ================= MAIN =================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(TOKEN).post_init(init_db).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is live...")
    app.run_polling()
