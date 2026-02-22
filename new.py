import logging
import random
import string
import os
import aiosqlite
import asyncio
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

# UPDATED TOKEN AS REQUESTED
TOKEN = "8136516055:AAGfHKSlQoSrWVVVmXGUcDqMGy7oA2DjtKA" 
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
    # Use port 10000 for Render compatibility
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# Start Flask in a separate thread
Thread(target=run_flask, daemon=True).start()

# ================= DATABASE =================

async def init_db(app):
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
    return escape_markdown(str(text or ""), version=2)

async def is_subscribed(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        except Exception:
            return False
    return True

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
            ref_by = None
            if args and args[0].isdigit():
                ref_candidate = int(args[0])
                if ref_candidate != user_id:
                    ref_by = ref_candidate
            
            await db.execute(
                "INSERT INTO users (user_id, username, referred_by, join_date) VALUES (?,?,?,?)",
                (user_id, user.username, ref_by, datetime.now().strftime("%Y-%m-%d"))
            )
            await db.commit()
            if ref_by:
                # Store pending referral in context until they verify joining channels
                context.user_data['pending_ref'] = ref_by

    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text(
            f"👋 *Welcome {esc(user.first_name)}*\!\n\nTo use this bot, you must join our channels first\.",
            reply_markup=join_markup(),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text("✨ Welcome back to the SHEIN Voucher Bot!", reply_markup=main_menu())

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        ref_id = context.user_data.pop('pending_ref', None)
        if ref_id:
            async with aiosqlite.connect(DB_PATH) as db:
                # Credit the referrer 1 point for a successful referral
                await db.execute(
                    "UPDATE users SET points=points+1, referrals=referrals+1 WHERE user_id=?",
                    (ref_id,)
                )
                await db.commit()
                try:
                    await context.bot.send_message(ref_id, "🎉 Someone joined using your link! You earned 1 point.")
                except:
                    pass

        await query.edit_message_text("✅ Membership Verified! You can now use the bot.")
        await context.bot.send_message(user_id, "Main Menu:", reply_markup=main_menu())
    else:
        await query.answer("❌ You haven't joined all channels yet!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            user = await cur.fetchone()

    if text == "💰 Balance":
        await update.message.reply_text(f"Your Current Balance: *{user['points']} Points*", parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🎁 Refer & Earn":
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        msg = (
            f"🔗 *Your Referral Link:*\n`{ref_link}`\n\n"
            f"Share this link with friends\! For every friend who joins, you get *1 Point*\.\n"
            f"Total Referrals: {user['referrals']}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "👤 Profile":
        msg = (
            f"👤 *User Profile*\n"
            f"ID: `{user['user_id']}`\n"
            f"Points: {user['points']}\n"
            f"Joined: {user['join_date']}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🎟 Withdraw Voucher":
        await update.message.reply_text("Voucher withdrawal system is being updated. Minimum points required: 10.")

# ================= MAIN =================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(TOKEN).post_init(init_db).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is live...")
    app.run_polling()
