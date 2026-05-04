import sys
import types

# 1. Compatibility Patches for Pydroid3 / Python 3.13
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType('imghdr')
    imghdr.what = lambda file, h=None: None
    sys.modules['imghdr'] = imghdr

try:
    import six
    import http.client
    vendor_six = types.ModuleType('six')
    vendor_six.moves = types.ModuleType('moves')
    vendor_six.moves.http_client = http.client
    sys.modules['telegram.vendor.ptb_urllib3.urllib3.packages.six'] = vendor_six
    sys.modules['telegram.vendor.ptb_urllib3.urllib3.packages.six.moves'] = vendor_six.moves
    sys.modules['telegram.vendor.ptb_urllib3.urllib3.packages.six.moves.http_client'] = http.client
except ImportError:
    pass

import urllib3
if not hasattr(urllib3, 'contrib'):
    urllib3.contrib = types.ModuleType('contrib')

appengine = types.ModuleType('appengine')
appengine.is_appengine_sandbox = lambda: False
appengine.is_appengine = lambda: False
appengine.AppEngineManager = None
sys.modules['urllib3.contrib.appengine'] = appengine
urllib3.contrib.appengine = appengine

import logging
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler

# --- CONFIGURATION ---
TOKEN = '8734728318:AAFMCfcvFJ2s9d9cs60qMo4-ra_z4_HP7-o'
OWNER_ID = 8485479897 # This ID still controls the bot
DB_FILE = 'bot_data.json'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATA MANAGEMENT ---
def load_data():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"channels": {}, "global_delay": 60, "enabled": True}

def save_data(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f)

db = load_data()

# --- FIX: ROBUST SECURITY CHECK ---
def is_authorized(update: Update):
    # Check if the user is the owner defined above
    if update.effective_user and update.effective_user.id == OWNER_ID:
        return True
    return False

# --- CORE LOGIC ---
def delayed_delete(context: CallbackContext):
    job = context.job
    chat_id = job.context['chat_id']
    msg_id = job.context['message_id']
    try:
        context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        # Send log to owner
        context.bot.send_message(OWNER_ID, f"🗑️ **Auto-Deleted**\nChannel: `{chat_id}`\nMsg ID: `{msg_id}`")
    except Exception as e:
        logger.error(f"Delete failed: {e}")

# --- COMMANDS ---
def start(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    update.message.reply_text("⚡ **Bot Control Panel Active**\n\nUse /Add to monitor a channel.\nUse /setdelay to change timing.")

def set_delay(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    args = context.args
    if not args:
        update.message.reply_text("Usage:\n`/setdelay 120` (seconds)\n`/setdelay on`\n`/setdelay off`", parse_mode='Markdown')
        return

    cmd = args[0].lower()
    if cmd == 'on':
        db['enabled'] = True
        msg = "✅ Auto-delete globally **ENABLED**."
    elif cmd == 'off':
        db['enabled'] = False
        msg = "❌ Auto-delete globally **DISABLED**."
    elif cmd.isdigit():
        db['global_delay'] = int(cmd)
        msg = f"⏱ Global delay set to **{cmd}** seconds."
    else:
        msg = "Invalid argument."
    
    save_data(db)
    update.message.reply_text(msg, parse_mode='Markdown')

def add_channel(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    update.message.reply_text("Paste the Channel Chat ID (Example: `-100123456789`):")

def handle_id_input(update: Update, context: CallbackContext):
    # Only process text if it's from the owner and looks like a channel ID
    if not is_authorized(update) or not update.message.text.startswith('-100'): 
        return
    
    chat_id = update.message.text.strip()
    try:
        member = context.bot.get_chat_member(chat_id, context.bot.id)
        if member.status == 'administrator':
            chat_info = context.bot.get_chat(chat_id)
            db['channels'][chat_id] = chat_info.title
            save_data(db)
            update.message.reply_text(f"✅ **Success!**\nNow monitoring: {chat_info.title}")
        else:
            update.message.reply_text("❌ **Error:** Bot must be an **ADMIN** in that channel.")
    except Exception as e:
        update.message.reply_text(f"❌ **Failed:** Check ID or Bot Permissions.\nError: `{e}`")

def remove_list(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    if not db['channels']:
        update.message.reply_text("No channels in database.")
        return

    keyboard = [[InlineKeyboardButton(name, callback_data=f"del_{cid}")] for cid, name in db['channels'].items()]
    update.message.reply_text("Select a channel to stop monitoring:", reply_markup=InlineKeyboardMarkup(keyboard))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    if not is_authorized(update):
        query.answer("Access Denied")
        return

    data = query.data
    if data.startswith("del_"):
        cid = data.replace("del_", "")
        if cid in db['channels']:
            del db['channels'][cid]
            save_data(db)
            query.edit_message_text("✅ Channel removed and ignored.")

# --- AUTO-DELETE TRIGGER ---
def monitor_posts(update: Update, context: CallbackContext):
    chat_id = str(update.channel_post.chat_id)
    
    if db['enabled'] and chat_id in db['channels']:
        delay = db['global_delay']
        
        # Log to owner that a post was detected
        context.bot.send_message(
            OWNER_ID, 
            f"📥 **Post Detected**\nChannel: {db['channels'].get(chat_id)}\nTimer: {delay}s"
        )

        context.job_queue.run_once(
            delayed_delete, 
            delay, 
            context={'chat_id': update.channel_post.chat_id, 'message_id': update.channel_post.message_id}
        )

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("setdelay", set_delay))
    dp.add_handler(CommandHandler("Add", add_channel))
    dp.add_handler(CommandHandler("Remove", remove_list))
    dp.add_handler(CallbackQueryHandler(button_handler))
    
    # Catching ID inputs
    dp.add_handler(MessageHandler(Filters.text & Filters.chat_type.private, handle_id_input))
    
    # Trigger for channel posts
    dp.add_handler(MessageHandler(Filters.chat_type.channel, monitor_posts))

    logger.info("Bot is spinning up...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
