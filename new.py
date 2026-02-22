import logging
import random
import string
import asyncio
import aiosqlite
import os
from datetime import datetime
from threading import Thread
from flask import Flask

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

# --- CONFIGURATION ---
TOKEN = "8136516055:AAGfHKSlQoSrWVVVmXGUcDqMGy7oA2DjtKA"
ADMIN_ID = 6843292223 
CHANNELS = ["@freecourse6969", "@lootlebigdeels" , "@pcsheinstock"] 
BOT_USERNAME = "sheinfreecodesbot" 
DB_PATH = "referral_bot1.db"

# --- WEB SERVER FOR RENDER ---
# This keeps Render happy by providing an HTTP port
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    # Render provides a PORT environment variable automatically
    port = int(os.environ.get('PORT', 8080))
    app_flask.run(host='0.0.0.0', port=port)

# --- DATABASE LOGIC ---
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

# --- UTILS ---
def esc(text):
    return escape_markdown(str(text or "User"), version=2)

async def is_subscribed(bot, user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                return False
        except Exception: 
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

# --- UI COMPONENTS ---
def join_markup():
    buttons = [[InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch[1:]}")] for ch in CHANNELS]
    buttons.append([InlineKeyboardButton("✅ Verify Joining", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def main_menu():
    keyboard = [
        [KeyboardButton("💰 Balance"), KeyboardButton("🎁 Refer & Earn")],
        [KeyboardButton("🎟 Withdraw Voucher"), KeyboardButton("👤 Profile")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, input_field_placeholder="Select an option...")

# --- HANDLERS ---
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
            "👋 *Welcome\\!*\n\nTo use this bot and earn vouchers, you must join our official channels below\\.",
            reply_markup=join_markup(), parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text("✨ *Welcome back\\!* Access granted\\.", reply_markup=main_menu(), parse_mode=ParseMode.MARKDOWN_V2)

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if await is_subscribed(context.bot, user_id):
        ref_id = context.user_data.pop('pending_ref', None)
        if ref_id:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET points=points+1, referrals=referrals+1 WHERE user_id=?", (ref_id,))
                await db.commit()
                try: 
                    await context.bot.send_message(ref_id, "🎊 *New Referral\\!* You earned 1 point\\.", parse_mode=ParseMode.MARKDOWN_V2)
                except: 
                    pass

        await query.edit_message_text("✅ *Verified\\!* You can now start earning\\.", parse_mode=ParseMode.MARKDOWN_V2)
        await context.bot.send_message(user_id, "Main Menu opened\\:", reply_markup=main_menu())
    else:
        await query.answer("❌ Please join all channels first!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if not await is_subscribed(context.bot, user_id):
        await update.message.reply_text("🚫 *Action Denied\\!* Join channels first\\.", reply_markup=join_markup(), parse_mode=ParseMode.MARKDOWN_V2)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            user = await cur.fetchone()

    if not user: return

    if text == "💰 Balance":
        msg = (f"💳 *Your Wallet*\n\n"
               f"Points balance: `{user['points']}`\n\n"
               f"• 2 Pts → ₹500\n• 5 Pts → ₹1000\n• 10 Pts → ₹2000")
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🎁 Refer & Earn":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        msg = (f"🎁 *Referral Program*\n\n"
               f"Earn *1 Point* for every friend who joins\\!\n\n"
               f"🔗 *Your Link\\:* \n`{link}`")
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "👤 Profile":
        msg = (f"👤 *Profile Details*\n\n"
               f"ID: `{user['user_id']}`\n"
               f"User: @{esc(user['username'])}\n"
               f"Total Referrals: `{user['referrals']}`\n"
               f"Join Date: `{user['join_date']}`")
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)

    elif text == "🎟 Withdraw Voucher":
        pts = user['points']
        btns = []
        if pts >= 2: btns.append([InlineKeyboardButton("🎟 Redeem ₹500 (2 Pts)", callback_data="wd_500")])
        if pts >= 5: btns.append([InlineKeyboardButton("🎟 Redeem ₹1000 (5 Pts)", callback_data="wd_1000")])
        if pts >= 10: btns.append([InlineKeyboardButton("🎟 Redeem ₹2000 (10 Pts)", callback_data="wd_2000")])

        if not btns:
            await update.message.reply_text("❌ *Insufficient Points\\!*\nYou need at least 2 points to withdraw\\.", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("💎 *Select Voucher Amount\\:*", reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN_V2)

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    amount = int(query.data.split("_")[1])
    cost = {500: 2, 1000: 5, 2000: 10}[amount]
    user_id = query.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT points FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row or row[0] < cost:
                await query.answer("Error: Insufficient points!", show_alert=True)
                return

        code = await generate_voucher(amount)
        await db.execute("UPDATE users SET points = points - ? WHERE user_id = ?", (cost, user_id))
        await db.execute("INSERT INTO withdrawals (user_id, points_used, voucher_code, voucher_amount, date) VALUES (?,?,?,?,?)",
                         (user_id, cost, code, amount, datetime.now().strftime("%Y-%m-%d %H:%M")))
        await db.commit()

    success_msg = (f"🎉 *Withdrawal Successful\\!*\n\n"
                   f"💰 Amount: *₹{amount}*\n"
                   f"🎫 Code: `{code}`\n\n"
                   f"Use this on the SHEIN checkout page\\.")
    await query.edit_message_text(success_msg, parse_mode=ParseMode.MARKDOWN_V2)

# --- MAIN ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Start the background flask server
    Thread(target=run_flask).start()
    
    # Initialize the local database
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^wd_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot is live with Keep-Alive Server...")
    app.run_polling()
