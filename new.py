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

TOKEN = "8136516055:AAGfHKSlQoSrWVVVmXGUcDqMGy7oA2DjtKA" 
ADMIN_ID = 6843292223
CHANNELS = ["@freecourse6969", "@lootlebigdeels", "@pcsheinstock"]
DB_PATH = "shein_premium_data.db" 

# ================= FLASK SERVER =================

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is active and healthy!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

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

# ================= ENHANCED UI ELEMENTS =================

def join_markup():
    buttons = [[InlineKeyboardButton(f"🔗 Join {ch}", url=f"https://t.me/{ch[1:]}")] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("🔄 Verify Membership", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def main_menu():
    keyboard = [
        [KeyboardButton("💰 My Wallet"), KeyboardButton("🚀 Invite Friends")],
        [KeyboardButton("🎁 Redeem Voucher"), KeyboardButton("⚙️ Account Stats")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def withdrawal_menu():
    buttons = [
        [InlineKeyboardButton("🛍️ ₹500 SHEIN Card (2 Pts)", callback_data="wd_500")],
        [InlineKeyboardButton("🛍️ ₹1000 SHEIN Card (5 Pts)", callback_data="wd_1000")],
        [InlineKeyboardButton("🛍️ ₹2000 SHEIN Card (10 Pts)", callback_data="wd_2500")]
    ]
    return InlineKeyboardMarkup(buttons)

# ================= HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    args = context.args

    if 'bot_username' not in context.bot_data:
        bot_info = await context.bot.get_me()
        context.bot_data['bot_username'] = bot_info.username

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            user_exists = await cur.fetchone()

        if not user_exists:
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
                context.user_data['pending_ref'] = ref_by

    if not await is_subscribed(context.bot, user_id):
        welcome_text = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👋 *Hi {esc(user.first_name)}\!*\n\n"
            f"Welcome to the *SHEIN Premium Bot*\. To access free gift cards and rewards, you must join our official channels below\.\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(welcome_text, reply_markup=join_markup(), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text("🌟 *Welcome back\!* Accessing your dashboard\.\.\.", reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN_V2)

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        ref_id = context.user_data.pop('pending_ref', None)
        if ref_id:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET points = points + 1, referrals = referrals + 1 WHERE user_id = ?", (ref_id,))
                await db.commit()
                try:
                    await context.bot.send_message(ref_id, "🎊 *Success\!* A new friend joined\. You earned *1 Point*\.", parse_mode=ParseMode.MARKDOWN_V2)
                except: pass

        await query.edit_message_text("✅ *Access Granted\!* Enjoy your rewards\.")
        await context.bot.send_message(user_id, "🏠 *Main Menu*", reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await query.answer("⚠️ Please join all channels first!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    bot_username = context.bot_data.get('bot_username', 'bot')

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            user = await cur.fetchone()

    if not user: return

    if text == "💰 My Wallet":
        msg = (
            f"💳 *Your Wallet Balance*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💎 Points Available: `{user['points']}`\n"
            f"👥 Total Referrals: `{user['referrals']}`\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🚀 Invite Friends":
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        msg = (
            f"🎁 *Invite & Earn Points*\n\n"
            f"Share your link with friends\. When they join, you get *1 Point*\.\n\n"
            f"🔗 *Your Personal Link:*\n`{ref_link}`"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "⚙️ Account Stats":
        msg = (
            f"👤 *Account Overview*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🆔 User ID: `{user_id}`\n"
            f"📅 Join Date: `{user['join_date']}`\n"
            f"🏆 Status: *Premium Member*\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🎁 Redeem Voucher":
        await update.message.reply_text("💎 *Choose Your Reward Card:*", reply_markup=withdrawal_menu(), parse_mode=ParseMode.MARKDOWN_V2)

# ================= ADMIN CMDS =================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            count = (await cur.fetchone())[0]
    await update.message.reply_text(f"📊 *Bot Statistics*\nTotal Users: `{count}`", parse_mode=ParseMode.MARKDOWN_V2)

# ================= MAIN =================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).post_init(init_db).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer("⚠️ Insufficient points!", show_alert=True), pattern="^wd_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print(f"Enhanced Bot Live. DB: {DB_PATH}")
    app.run_polling()

