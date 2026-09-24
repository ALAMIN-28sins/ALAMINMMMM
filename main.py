import os, re, sys, json, random, string, asyncio, logging, threading, subprocess, shutil
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ═══════════════════════════════════════════
# KEEP ALIVE
# ═══════════════════════════════════════════
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# ═══════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════
TOKEN       = "8871493019:AAFHpD1-YLrQcV4lYatNDcKszLT2JNKGWNk"
OWNER_ID    = 8917082487
CHANNEL_URL = "https://t.me/ALAMINOOPOU"

BASE_DIR      = os.path.abspath(os.getcwd())
UPLOAD_DIR    = os.path.join(BASE_DIR, "uploads")
DOWNLOAD_DIR  = os.path.join(BASE_DIR, "downloads")
DB_FILE       = os.path.join(BASE_DIR, "codes.json")
USERS_FILE    = os.path.join(BASE_DIR, "approved_users.json")
CONFIG_FILE   = os.path.join(BASE_DIR, "config.json")
USERINFO_FILE = os.path.join(BASE_DIR, "user_info.json")
CODE_LENGTH   = 6

DEFAULT_MAX_RUN   = 5
DEFAULT_MAX_STORE = 5

for d in (UPLOAD_DIR, DOWNLOAD_DIR):
    try:
        os.makedirs(d, exist_ok=True)
        logger.info(f"✅ Directory ready: {d}")
    except Exception as e:
        logger.error(f"❌ Cannot create {d}: {e}")

running_scripts = {}

# ═══════════════════════════════════════════
# HTML SAFE
# ═══════════════════════════════════════════
def html_escape(s):
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))

# ═══════════════════════════════════════════
# USER INFO
# ═══════════════════════════════════════════
def load_user_info():
    if os.path.exists(USERINFO_FILE):
        try:
            with open(USERINFO_FILE, "r", encoding="utf-8") as f:
                return {str(k): v for k, v in json.load(f).items()}
        except Exception:
            return {}
    return {}

def save_user_info_file():
    try:
        with open(USERINFO_FILE, "w", encoding="utf-8") as f:
            json.dump(user_info, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"user_info save error: {e}")

user_info = load_user_info()

def save_user_info(uid, first_name=None, username=None):
    key = str(uid)
    if key not in user_info:
        user_info[key] = {"name": "", "username": ""}
    changed = False
    if first_name and user_info[key].get("name") != first_name:
        user_info[key]["name"] = first_name
        changed = True
    new_uname = username or ""
    if user_info[key].get("username") != new_uname:
        user_info[key]["username"] = new_uname
        changed = True
    if changed:
        save_user_info_file()

def get_user_display_html(uid):
    info = user_info.get(str(uid), {})
    name = html_escape(info.get("name") or "Unknown")
    uname = info.get("username") or ""
    uname_str = f"@{html_escape(uname)}" if uname else "No username"
    return f"{name} ({uname_str})"

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════
def load_config():
    default = {"password": "AA", "blocked_users": [], "user_limits": {}}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "password" in data:
                default["password"] = str(data["password"])
            if "blocked_users" in data:
                default["blocked_users"] = [int(x) for x in data["blocked_users"]]
            if "user_limits" in data:
                default["user_limits"] = {str(k): v for k, v in data["user_limits"].items()}
        except Exception as e:
            logger.error(f"Config load error: {e}")
    return default

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Config save error: {e}")

CONFIG = load_config()

def get_password():     return CONFIG.get("password", "AA")
def set_password(new_p):
    CONFIG["password"] = new_p
    save_config(CONFIG)

def is_blocked(uid):    return uid in CONFIG.get("blocked_users", [])
def block_user(uid):
    if uid == OWNER_ID: return
    if uid not in CONFIG["blocked_users"]:
        CONFIG["blocked_users"].append(uid)
        save_config(CONFIG)
def unblock_user(uid):
    if uid in CONFIG["blocked_users"]:
        CONFIG["blocked_users"].remove(uid)
        save_config(CONFIG)

def get_user_limits(uid):
    if uid == OWNER_ID:
        return (9999, 9999)
    limits = CONFIG.get("user_limits", {}).get(str(uid), {})
    max_run   = int(limits.get("max_run",   DEFAULT_MAX_RUN))
    max_store = int(limits.get("max_store", DEFAULT_MAX_STORE))
    return (max_run, max_store)

def set_user_limits(uid, max_run=None, max_store=None):
    if str(uid) not in CONFIG.setdefault("user_limits", {}):
        CONFIG["user_limits"][str(uid)] = {}
    if max_run is not None:
        CONFIG["user_limits"][str(uid)]["max_run"] = int(max_run)
    if max_store is not None:
        CONFIG["user_limits"][str(uid)]["max_store"] = int(max_store)
    save_config(CONFIG)

# ═══════════════════════════════════════════
# APPROVED USERS
# ═══════════════════════════════════════════
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except Exception:
            return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in users.items()}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Users save error: {e}")

approved_users = load_users()

# ═══════════════════════════════════════════
# CODE DB
# ═══════════════════════════════════════════
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"DB save error: {e}")

CODE_DB = load_db()

def generate_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=CODE_LENGTH))
        if code not in CODE_DB:
            return code

# ═══════════════════════════════════════════
# DEP SCANNERS
# ═══════════════════════════════════════════
def scan_python_dependencies(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        imports = re.findall(r'^(?:from|import)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
        return list(set(imports))
    except Exception as e:
        logger.error(f"Error scanning python deps: {e}")
        return []

def scan_js_dependencies(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        requires = re.findall(r'require\([\'"](.+?)[\'"]\)', content)
        imports  = re.findall(r'from\s+[\'"](.+?)[\'"]', content)
        return list(set(requires + imports))
    except Exception as e:
        logger.error(f"Error scanning js deps: {e}")
        return []

# ═══════════════════════════════════════════
# FILE HELPERS
# ═══════════════════════════════════════════
def get_user_files(user_id):
    udir = os.path.join(DOWNLOAD_DIR, str(user_id))
    if not os.path.exists(udir):
        return []
    out = []
    for f in sorted(os.listdir(udir)):
        fp = os.path.join(udir, f)
        if os.path.isfile(fp) and f.endswith(('.py', '.js')):
            out.append((f, fp))
    return out

def get_all_files():
    out = []
    if not os.path.exists(DOWNLOAD_DIR):
        return out
    for uid_str in sorted(os.listdir(DOWNLOAD_DIR)):
        udir = os.path.join(DOWNLOAD_DIR, uid_str)
        if not os.path.isdir(udir):
            continue
        for f in sorted(os.listdir(udir)):
            fp = os.path.join(udir, f)
            if os.path.isfile(fp) and f.endswith(('.py', '.js')):
                out.append((uid_str, f, fp))
    return out

def is_running(user_id, name):
    s = running_scripts.get(f"{user_id}:{name}")
    return s is not None and s["proc"].poll() is None

def count_user_running(user_id):
    return sum(
        1 for s in running_scripts.values()
        if s["owner"] == user_id and s["proc"].poll() is None
    )

def launch_script(user_id, file_name, file_path):
    if file_name.endswith('.py'):
        cmd = [sys.executable, "-u", file_path]
    elif file_name.endswith('.js'):
        cmd = ["node", "--max-old-space-size=512", file_path]
    else:
        return None, "Unsupported file type"

    key = f"{user_id}:{file_name}"
    existing = running_scripts.get(key)
    if existing and existing["proc"].poll() is None:
        return existing["proc"], None

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    work_dir = os.path.dirname(file_path)

    try:
        log_file = open(f"{file_path}.log", "w", encoding="utf-8", errors="ignore")
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
            env=env,
            encoding='utf-8',
            errors='replace',
            cwd=work_dir,
            stdin=subprocess.DEVNULL
        )
    except Exception as e:
        return None, str(e)

    running_scripts[key] = {
        "name": file_name, "proc": proc, "log": log_file,
        "path": file_path, "owner": user_id
    }
    return proc, None

def stop_script_by_owner(owner_id, file_name):
    key = f"{owner_id}:{file_name}"
    s = running_scripts.get(key)
    if not s:
        return False, "not found"
    if s["proc"].poll() is not None:
        return False, "already stopped"
    try:
        s["proc"].terminate()
        try: s["log"].close()
        except Exception: pass
        return True, "stopped"
    except Exception as e:
        return False, str(e)

def delete_script_file(owner_id, file_name, file_path):
    """Stop + delete downloads file+log ONLY.
    uploads/ folder এবং codes.json entry কখনো মুছবে না।"""
    key = f"{owner_id}:{file_name}"
    s = running_scripts.get(key)
    if s:
        try:
            if s["proc"].poll() is None:
                s["proc"].terminate()
        except Exception:
            pass
        try:
            s["log"].close()
        except Exception:
            pass
        running_scripts.pop(key, None)

    # শুধু downloads/ থেকে মুছবে (ফাইল + তার log)
    for p in (file_path, file_path + ".log"):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            logger.error(f"delete {p} failed: {e}")

    return True

# ═══════════════════════════════════════════
# ACCESS
# ═══════════════════════════════════════════
def is_allowed(user_id):
    return user_id == OWNER_ID or user_id in approved_users

def show_menu_keyboard(is_admin=False):
    rows = [
        [KeyboardButton("𝐔𝐏𝐋𝐎𝐀𝐃 𝐅𝐈𝐋𝐄𝐒 👾"), KeyboardButton("📂 𝐂𝐇𝐄𝐀𝐊 𝐅𝐈𝐋𝐄𝐒")],
        [KeyboardButton("⚡ 𝐁𝐎𝐓 𝐒𝐏𝐄𝐄𝐃"),    KeyboardButton("📊 Statistics")],
        [KeyboardButton("📞 Contact Owner")],
        [KeyboardButton("🛑 𝐒𝐓𝐎𝐏 𝐒𝐂𝐑𝐈𝐏𝐓"),  KeyboardButton("🔄 𝐑𝐄-𝐑𝐔𝐍 𝐅𝐈𝐋𝐄𝐒")],
    ]
    if is_admin:
        rows.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def blocked_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📞 Contact Owner")]],
        resize_keyboard=True
    )

# ═══════════════════════════════════════════
# BROADCAST HELPER
# ═══════════════════════════════════════════
async def broadcast_to_all(context, text, exclude_owner=True):
    sent = 0
    failed = 0
    for uid in list(approved_users.keys()):
        if exclude_owner and uid == OWNER_ID:
            continue
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode="HTML",
                                            disable_web_page_preview=True)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast to {uid} failed: {e}")
    return sent, failed

# ═══════════════════════════════════════════
# WELCOME
# ═══════════════════════════════════════════
async def send_welcome(message):
    user = message.from_user
    save_user_info(user.id, user.first_name, user.username)
    role = "👑 Owner" if user.id == OWNER_ID else "🆓 Free User"
    welcome_text = (
        f"〽️ Welcome, {user.first_name}...💞!\n\n"
        f"🆔 Your User ID: {user.id}\n"
        f"✳️ Username: @{user.username if user.username else 'Not set'}\n"
        f"🔰 Your Status: {role}\n\n"
        f"🤖 আপনার ফাইল পাঠান — আপনার ফাইলটি রানকরে দেওয়া হবে।"
    )
    inline_keyboard = [[InlineKeyboardButton("📢 Updates Channel", url=CHANNEL_URL)]]
    await message.reply_text(welcome_text, reply_markup=show_menu_keyboard(user.id == OWNER_ID))
    await message.reply_text("Options menu activated!", reply_markup=InlineKeyboardMarkup(inline_keyboard))

# ═══════════════════════════════════════════
# /start
# ═══════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    save_user_info(user_id, user.first_name, user.username)

    if is_blocked(user_id):
        await update.message.reply_text(
            "🚫 আপনি ব্লক হয়েছেন।\n\n"
            "শুধু Owner এর সাথে যোগাযোগ করতে পারবেন 👇",
            reply_markup=blocked_keyboard()
        )
        return

    if not is_allowed(user_id):
        await update.message.reply_text(
            "🔐 <b>Access Restricted!</b>\n\n"
            "বট ব্যবহার করতে <b>পাসওয়ার্ড</b> পাঠান।\n\n"
            f"📢 পাসওয়ার্ড পেতে চ্যানেলে জয়েন করুন:\n{CHANNEL_URL}",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return

    await send_welcome(update.message)

# ═══════════════════════════════════════════
# FILE LIST
# ═══════════════════════════════════════════
async def list_hosted_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("🔐 আগে পাসওয়ার্ড দিন।")
        return

    if user_id == OWNER_ID:
        entries = get_all_files()
    else:
        entries = [(str(user_id), n, p) for (n, p) in get_user_files(user_id)]

    if not entries:
        await update.message.reply_text("📂 কোন ফাইল নেই।")
        return

    context.user_data["file_entries"] = entries

    if user_id != OWNER_ID:
        max_run, max_store = get_user_limits(user_id)
        used_run = count_user_running(user_id)
        header = (f"🗂️ আপনার ফাইলসমূহ:\n"
                  f"🟢 Running: {used_run}/{max_run}   "
                  f"📦 Stored: {len(entries)}/{max_store}\n")
    else:
        header = "🗂️ সব ফাইল:\n"

    keyboard = []
    lines = [header]
    for idx, (owner, fname, fpath) in enumerate(entries):
        owner_int = int(owner)
        running = is_running(owner_int, fname)
        status = "🟢 Running" if running else "🔴 Stopped"
        size_kb = round(os.path.getsize(fpath) / 1024, 1)
        label = f"{fname}"
        if user_id == OWNER_ID:
            label += f" (uid:{owner})"
        lines.append(f"{idx+1}. {label} ({size_kb} KB) — {status}")

        if running:
            row = [InlineKeyboardButton(f"🛑 Stop {fname}", callback_data=f"stopf_{idx}")]
        else:
            row = [InlineKeyboardButton(f"▶️ Run {fname}", callback_data=f"runf_{idx}")]
        row.append(InlineKeyboardButton("🗑️ Delete", callback_data=f"delfile_{idx}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close_menu")])
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ═══════════════════════════════════════════
# STOP SCRIPT
# ═══════════════════════════════════════════
async def stop_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("🔐 আগে পাসওয়ার্ড দিন।")
        return

    if user_id == OWNER_ID:
        scripts = [(k, s) for k, s in running_scripts.items() if s["proc"].poll() is None]
    else:
        scripts = [(k, s) for k, s in running_scripts.items()
                   if s["owner"] == user_id and s["proc"].poll() is None]

    if not scripts:
        await update.message.reply_text("❌ কোন স্ক্রিপ্ট চলছে না।")
        return

    if not context.args:
        keyboard = []
        for i, (_, s) in enumerate(scripts):
            label = s['name'] if user_id != OWNER_ID else f"{s['name']} (uid:{s['owner']})"
            keyboard.append([InlineKeyboardButton(f"🛑 Stop {label}", callback_data=f"stop_{i}")])
        context.user_data["scripts_list"] = [s for _, s in scripts]
        await update.message.reply_text("Select a script to stop:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    target = context.args[0]
    for _, s in scripts:
        if s["name"] == target:
            if user_id != OWNER_ID and s["owner"] != user_id:
                continue
            ok, msg = stop_script_by_owner(s["owner"], s["name"])
            if ok:
                await update.message.reply_text(f"✅ Stopped <code>{html_escape(target)}</code>.", parse_mode="HTML")
            else:
                await update.message.reply_text(f"❌ {html_escape(msg)}", parse_mode="HTML")
            return
    await update.message.reply_text(f"❌ Script <code>{html_escape(target)}</code> not found.", parse_mode="HTML")

# ═══════════════════════════════════════════
# RE-RUN
# ═══════════════════════════════════════════
async def run_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("🔐 আগে পাসওয়ার্ড দিন।")
        return

    if not context.args:
        await list_hosted_files(update, context)
        return

    target = context.args[0]
    fpath = os.path.join(DOWNLOAD_DIR, str(user_id), target)
    if not os.path.exists(fpath):
        await update.message.reply_text(f"❌ <code>{html_escape(target)}</code> নামে আপনার কোন ফাইল নেই.", parse_mode="HTML")
        return

    if is_running(user_id, target):
        await update.message.reply_text(f"ℹ️ <code>{html_escape(target)}</code> আগে থেকেই রানিং আছে।", parse_mode="HTML")
        return

    max_run, _ = get_user_limits(user_id)
    if count_user_running(user_id) >= max_run:
        await update.message.reply_text(
            f"⚠️ আপনি সর্বোচ্চ {max_run}টি স্ক্রিপ্ট একসাথে চালাতে পারবেন।\n\n"
            f"📞 লিমিট বাড়ানোর জন্য এডমিনের সাথে যোগাযোগ করুন: @ALAMIN_1BOSS"
        )
        return

    msg = await update.message.reply_text(f"🚀 Re-launching <code>{html_escape(target)}</code>...", parse_mode="HTML")
    proc, err = launch_script(user_id, target, fpath)
    if err:
        await msg.edit_text(f"❌ Failed: {html_escape(err)}", parse_mode="HTML")
        return
    await asyncio.sleep(4)
    if proc.poll() is not None:
        try:
            with open(f"{fpath}.log", "r", encoding="utf-8", errors="ignore") as f:
                el = f.read()[-500:]
            await msg.edit_text(
                f"❌ <code>{html_escape(target)}</code> crashed:\n<pre>{html_escape(el)}</pre>",
                parse_mode="HTML"
            )
        except Exception:
            await msg.edit_text(f"❌ <code>{html_escape(target)}</code> crashed।", parse_mode="HTML")
    else:
        await msg.edit_text(f"✅ <code>{html_escape(target)}</code> আবার চালু হয়েছে!", parse_mode="HTML")

# ═══════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════
def admin_panel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 All Users", callback_data="admin_users")],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="admin_blocked")],
        [InlineKeyboardButton("🔢 User Limits", callback_data="admin_limits")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔑 Change Password", callback_data="admin_changepass")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("📂 All Files", callback_data="admin_files")],
        [InlineKeyboardButton("❌ Close", callback_data="close_menu")],
    ])

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    await update.message.reply_text(
        "👑 <b>Admin Panel</b>\n\nএকটি অপশন বেছে নিন:",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )

# ═══════════════════════════════════════════
# USERS VIEW
# ═══════════════════════════════════════════
def build_users_view():
    users = list(approved_users.keys())
    if OWNER_ID not in users:
        users.insert(0, OWNER_ID)

    header = f"👥 <b>All Users</b> ({len(users)}):\n\n"
    chunks = []
    current = header
    for uid in users:
        disp = get_user_display_html(uid)
        tag = "🚫 Blocked" if is_blocked(uid) else "✅ Active"
        if uid == OWNER_ID:
            tag = "👑 Owner"
        mr, ms = get_user_limits(uid)
        entry = (f"• <code>{uid}</code>\n"
                 f"   {disp}\n"
                 f"   {tag} | Run:{mr} Store:{ms}\n\n")
        if len(current) + len(entry) > 3500:
            chunks.append(current)
            current = ""
        current += entry
    chunks.append(current)

    kb = []
    for uid in users:
        if uid == OWNER_ID:
            continue
        if is_blocked(uid):
            kb.append([InlineKeyboardButton(f"✅ Unblock {uid}", callback_data=f"unblock_{uid}")])
        else:
            kb.append([InlineKeyboardButton(f"🚫 Block {uid}", callback_data=f"block_{uid}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])

    return chunks, InlineKeyboardMarkup(kb)

# ═══════════════════════════════════════════
# CALLBACK HANDLER
# ═══════════════════════════════════════════
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    save_user_info(user_id, user.first_name, user.username)

    if is_blocked(user_id):
        try:
            await query.answer(
                "🚫 আপনি ব্লক হয়েছেন।\nশুধু Contact Owner ব্যবহার করতে পারবেন।",
                show_alert=True
            )
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="🚫 আপনি ব্লক হয়েছেন।\n\nশুধু Owner এর সাথে যোগাযোগ করতে পারবেন 👇",
                reply_markup=blocked_keyboard()
            )
        except Exception as e:
            logger.error(f"notify blocked user failed: {e}")
        return

    if not is_allowed(user_id):
        try:
            await query.answer("🔐 আগে পাসওয়ার্ড দিন।", show_alert=True)
        except Exception:
            pass
        return

    try:
        await query.answer()
    except Exception:
        pass

    data = query.data

    # ═══ Admin: All Users ═══
    if data == "admin_users":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        try:
            chunks, kb = build_users_view()
            try:
                await query.edit_message_text(chunks[0], reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                logger.error(f"edit failed, sending new: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=chunks[0], reply_markup=kb, parse_mode="HTML"
                )
            for extra in chunks[1:]:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=extra, parse_mode="HTML"
                )
        except Exception as e:
            logger.exception("build_users_view failed")
            await query.answer(f"Error: {e}", show_alert=True)

    # ═══ Blocked Users ═══
    elif data == "admin_blocked":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        blocked = CONFIG.get("blocked_users", [])
        if not blocked:
            await query.edit_message_text(
                "No blocked users.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]])
            )
            return
        lines = [f"🚫 <b>Blocked Users</b> ({len(blocked)}):\n\n"]
        kb = []
        for uid in blocked:
            disp = get_user_display_html(uid)
            lines.append(f"• <code>{uid}</code>\n   {disp}\n\n")
            kb.append([InlineKeyboardButton(f"✅ Unblock {uid}", callback_data=f"unblock_{uid}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])
        try:
            await query.edit_message_text(
                "".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"blocked view: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    # ═══ User Limits ═══
    elif data == "admin_limits":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        users = list(approved_users.keys())
        if not users:
            await query.edit_message_text(
                "No users yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]])
            )
            return
        lines = [f"🔢 <b>User Limits</b>\n(Default: Run={DEFAULT_MAX_RUN}, Store={DEFAULT_MAX_STORE})\n\n"]
        kb = []
        for uid in users:
            mr, ms = get_user_limits(uid)
            disp = get_user_display_html(uid)
            lines.append(f"• <code>{uid}</code> — {disp}\n   → Run:{mr} Store:{ms}\n\n")
            kb.append([InlineKeyboardButton(f"⚙️ Edit {uid}", callback_data=f"editlimit_{uid}")])
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])
        try:
            await query.edit_message_text(
                "".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"limits view: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    elif data.startswith("editlimit_"):
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        target = int(data.split("_")[1])
        context.user_data["edit_limit_uid"] = target
        await _refresh_limit_view(query, target)

    elif data.startswith("limit_runadd_"):
        target = int(data.split("_")[2]); mr, ms = get_user_limits(target)
        set_user_limits(target, max_run=mr + 1)
        await _refresh_limit_view(query, target)

    elif data.startswith("limit_runsub_"):
        target = int(data.split("_")[2]); mr, ms = get_user_limits(target)
        set_user_limits(target, max_run=max(1, mr - 1))
        await _refresh_limit_view(query, target)

    elif data.startswith("limit_storeadd_"):
        target = int(data.split("_")[2]); mr, ms = get_user_limits(target)
        set_user_limits(target, max_store=ms + 1)
        await _refresh_limit_view(query, target)

    elif data.startswith("limit_storesub_"):
        target = int(data.split("_")[2]); mr, ms = get_user_limits(target)
        set_user_limits(target, max_store=max(1, ms - 1))
        await _refresh_limit_view(query, target)

    elif data.startswith("limit_reset_"):
        target = int(data.split("_")[2])
        if str(target) in CONFIG.get("user_limits", {}):
            CONFIG["user_limits"].pop(str(target), None)
            save_config(CONFIG)
        await _refresh_limit_view(query, target)

    # ═══ Broadcast ═══
    elif data == "admin_broadcast":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        context.user_data["state"] = "awaiting_broadcast"
        await query.edit_message_text(
            "📢 <b>Broadcast</b>\n\n"
            "আপনি যে মেসেজটি সব ইউজারের কাছে পাঠাতে চান সেটি লিখে পাঠান:\n\n"
            "<i>(Text / ছবি / ভিডিও / ডকুমেন্ট সবই পাঠাতে পারবেন।\n"
            "HTML সাপোর্টেড: &lt;b&gt;bold&lt;/b&gt;, &lt;i&gt;italic&lt;/i&gt;, &lt;code&gt;code&lt;/code&gt;)</i>",
            parse_mode="HTML"
        )

    elif data == "admin_changepass":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        context.user_data["state"] = "awaiting_new_password"
        await query.edit_message_text(
            "🔑 নতুন পাসওয়ার্ড পাঠান (একটি মেসেজে লিখে পাঠান):\n\n"
            "⚠️ <b>সতর্কতা:</b>\n"
            "• পাসওয়ার্ড চেঞ্জ হলে সব পুরনো ইউজার auto logout হবে\n"
            "• সবাইকে নতুন পাসওয়ার্ড দিতে হবে\n"
            "• সব ইউজার চ্যানেল জয়েন করার নোটিফিকেশন পাবে",
            parse_mode="HTML"
        )

    elif data == "admin_stats":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        total_users = len(approved_users)
        blocked_cnt = len(CONFIG.get("blocked_users", []))
        total_files = len(get_all_files())
        running_cnt = sum(1 for s in running_scripts.values() if s["proc"].poll() is None)
        await query.edit_message_text(
            f"📊 <b>Statistics</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🚫 Blocked Users: {blocked_cnt}\n"
            f"📂 Total Files: {total_files}\n"
            f"🟢 Running Scripts: {running_cnt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]]),
            parse_mode="HTML"
        )

    elif data == "admin_files":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        entries = get_all_files()
        if not entries:
            await query.edit_message_text(
                "No files.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="admin_back")]])
            )
            return
        context.user_data["file_entries"] = entries
        lines = ["📂 <b>All Files</b>:\n\n"]
        kb = []
        for idx, (owner, fname, fpath) in enumerate(entries):
            running = is_running(int(owner), fname)
            lines.append(f"{idx+1}. <code>{html_escape(fname)}</code> (uid:<code>{owner}</code>) — {'🟢' if running else '🔴'}\n")
            if running:
                row = [InlineKeyboardButton(f"🛑 {fname} @{owner}", callback_data=f"stopf_{idx}")]
            else:
                row = [InlineKeyboardButton(f"▶️ {fname} @{owner}", callback_data=f"runf_{idx}")]
            row.append(InlineKeyboardButton("🗑️ Delete", callback_data=f"delfile_{idx}"))
            kb.append(row)
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])
        try:
            await query.edit_message_text(
                "".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"files view: {e}")
            await query.answer(f"Error: {e}", show_alert=True)

    elif data == "admin_back":
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        await query.edit_message_text(
            "👑 <b>Admin Panel</b>\n\nএকটি অপশন বেছে নিন:",
            reply_markup=admin_panel_kb(), parse_mode="HTML"
        )

    elif data.startswith("block_"):
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        target = int(data.split("_")[1])
        if target == OWNER_ID:
            await query.answer("Cannot block owner.", show_alert=True); return
        block_user(target)
        await query.answer("User blocked!")
        try:
            chunks, kb = build_users_view()
            await query.edit_message_text(chunks[0], reply_markup=kb, parse_mode="HTML")
            for extra in chunks[1:]:
                await context.bot.send_message(chat_id=query.message.chat_id, text=extra, parse_mode="HTML")
        except Exception as e:
            logger.error(f"refresh after block: {e}")

    elif data.startswith("unblock_"):
        if user_id != OWNER_ID:
            await query.answer("❌ Owner only.", show_alert=True); return
        target = int(data.split("_")[1])
        unblock_user(target)
        await query.answer("User unblocked!")
        blocked = CONFIG.get("blocked_users", [])
        lines = [f"🚫 <b>Blocked Users</b> ({len(blocked)}):\n\n"]
        kb = []
        for uid in blocked:
            disp = get_user_display_html(uid)
            lines.append(f"• <code>{uid}</code>\n   {disp}\n\n")
            kb.append([InlineKeyboardButton(f"✅ Unblock {uid}", callback_data=f"unblock_{uid}")])
        if not blocked:
            lines.append("(none)")
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_back")])
        try:
            await query.edit_message_text(
                "".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"refresh unblock: {e}")

    elif data.startswith('stop_'):
        idx = int(data.split('_')[1])
        scripts_list = context.user_data.get("scripts_list", [])
        if idx >= len(scripts_list):
            await query.edit_message_text("❌ Not found."); return
        s = scripts_list[idx]
        if user_id != OWNER_ID and s["owner"] != user_id:
            await query.answer("🚫 Permission denied.", show_alert=True); return
        ok, msg = stop_script_by_owner(s["owner"], s["name"])
        if ok:
            await query.edit_message_text(
                f"✅ Stopped <code>{html_escape(s['name'])}</code>.", parse_mode="HTML"
            )
        else:
            await query.edit_message_text(f"❌ {html_escape(msg)}", parse_mode="HTML")

    elif data.startswith('runf_'):
        idx = int(data.split('_')[1])
        entries = context.user_data.get("file_entries", [])
        if idx >= len(entries):
            await query.edit_message_text("❌ ফাইল পাওয়া যায়নি।"); return
        owner, fname, fpath = entries[idx]
        owner_int = int(owner)

        if user_id != OWNER_ID and owner_int != user_id:
            await query.answer("🚫 আপনি শুধু নিজের ফাইল চালাতে পারবেন।", show_alert=True); return
        if is_running(owner_int, fname):
            await query.edit_message_text(
                f"ℹ️ <code>{html_escape(fname)}</code> already running.",
                parse_mode="HTML"
            ); return

        if user_id != OWNER_ID:
            max_run, _ = get_user_limits(owner_int)
            if count_user_running(owner_int) >= max_run:
                await query.edit_message_text(
                    f"⚠️ আপনি সর্বোচ্চ <b>{max_run}</b> টি স্ক্রিপ্ট একসাথে চালাতে পারবেন।\n\n"
                    f"📞 লিমিট বাড়ানোর জন্য এডমিনের সাথে যোগাযোগ করুন:\n@ALAMIN_1BOSS",
                    parse_mode="HTML"
                )
                return

        await query.edit_message_text(f"🚀 Launching <code>{html_escape(fname)}</code>...",
                                      parse_mode="HTML")
        proc, err = launch_script(owner_int, fname, fpath)
        if err:
            await query.edit_message_text(f"❌ {html_escape(err)}", parse_mode="HTML"); return
        await asyncio.sleep(4)
        if proc.poll() is not None:
            try:
                with open(f"{fpath}.log", "r", encoding="utf-8", errors="ignore") as f:
                    el = f.read()[-500:]
                await query.edit_message_text(
                    f"❌ <code>{html_escape(fname)}</code> failed:\n<pre>{html_escape(el)}</pre>",
                    parse_mode="HTML"
                )
            except Exception:
                await query.edit_message_text(
                    f"❌ <code>{html_escape(fname)}</code> failed.", parse_mode="HTML"
                )
        else:
            await query.edit_message_text(
                f"✅ <code>{html_escape(fname)}</code> চালু হয়েছে!", parse_mode="HTML"
            )

    elif data.startswith('stopf_'):
        idx = int(data.split('_')[1])
        entries = context.user_data.get("file_entries", [])
        if idx >= len(entries):
            await query.edit_message_text("❌ ফাইল পাওয়া যায়নি।"); return
        owner, fname, _ = entries[idx]
        owner_int = int(owner)

        if user_id != OWNER_ID and owner_int != user_id:
            await query.answer("🚫 আপনি শুধু নিজের ফাইল স্টপ করতে পারবেন।", show_alert=True); return

        ok, msg = stop_script_by_owner(owner_int, fname)
        if ok:
            await query.edit_message_text(
                f"✅ Stopped <code>{html_escape(fname)}</code>.", parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                f"ℹ️ <code>{html_escape(fname)}</code> {html_escape(msg)}.", parse_mode="HTML"
            )

    # ── Delete file ──
    elif data.startswith('delfile_'):
        idx = int(data.split('_')[1])
        entries = context.user_data.get("file_entries", [])
        if idx >= len(entries):
            await query.edit_message_text("❌ ফাইল পাওয়া যায়নি।"); return
        owner, fname, fpath = entries[idx]
        owner_int = int(owner)

        if user_id != OWNER_ID and owner_int != user_id:
            await query.answer(
                "🚫 আপনি শুধু নিজের ফাইল ডিলিট করতে পারবেন।",
                show_alert=True
            )
            return

        try:
            delete_script_file(owner_int, fname, fpath)
        except Exception as e:
            logger.error(f"delete failed: {e}")
            await query.answer(f"❌ Error: {e}", show_alert=True)
            return

        await query.answer("File deleted ✅")

        # Refresh list
        if user_id == OWNER_ID:
            entries2 = get_all_files()
        else:
            entries2 = [(str(user_id), n, p) for (n, p) in get_user_files(user_id)]

        if not entries2:
            await query.edit_message_text(
                "🗑️ <b>ফাইল ডিলিট হয়েছে।</b>\n\n"
                "📂 এখন আপনার লিস্টে কোন ফাইল নেই।",
                parse_mode="HTML"
            )
            return

        context.user_data["file_entries"] = entries2

        if user_id != OWNER_ID:
            max_run, max_store = get_user_limits(user_id)
            used_run = count_user_running(user_id)
            header = (f"🗂️ আপনার ফাইলসমূহ:\n"
                      f"🟢 Running: {used_run}/{max_run}   "
                      f"📦 Stored: {len(entries2)}/{max_store}\n")
        else:
            header = "🗂️ সব ফাইল:\n"

        keyboard = []
        lines = [header]
        for i, (owner2, fname2, fpath2) in enumerate(entries2):
            o2 = int(owner2)
            running = is_running(o2, fname2)
            status = "🟢 Running" if running else "🔴 Stopped"
            size_kb = round(os.path.getsize(fpath2) / 1024, 1)
            label = fname2
            if user_id == OWNER_ID:
                label += f" (uid:{owner2})"
            lines.append(f"{i+1}. {label} ({size_kb} KB) — {status}")

            if running:
                row = [InlineKeyboardButton(f"🛑 Stop {fname2}", callback_data=f"stopf_{i}")]
            else:
                row = [InlineKeyboardButton(f"▶️ Run {fname2}", callback_data=f"runf_{i}")]
            row.append(InlineKeyboardButton("🗑️ Delete", callback_data=f"delfile_{i}"))
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="close_menu")])
        try:
            await query.edit_message_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"refresh after delete: {e}")

    elif data == "close_menu":
        try:
            await query.message.delete()
        except Exception:
            pass

async def _refresh_limit_view(query, target):
    mr, ms = get_user_limits(target)
    disp = get_user_display_html(target)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Run +1",  callback_data=f"limit_runadd_{target}"),
         InlineKeyboardButton("➖ Run -1",  callback_data=f"limit_runsub_{target}")],
        [InlineKeyboardButton("➕ Store +1", callback_data=f"limit_storeadd_{target}"),
         InlineKeyboardButton("➖ Store -1", callback_data=f"limit_storesub_{target}")],
        [InlineKeyboardButton("♻️ Reset Default", callback_data=f"limit_reset_{target}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_limits")],
    ])
    try:
        await query.edit_message_text(
            f"⚙️ <b>Limits for</b> <code>{target}</code>\n"
            f"👤 {disp}\n\n"
            f"🟢 Max Run: <code>{mr}</code>\n"
            f"📦 Max Store: <code>{ms}</code>\n\n"
            f"কত পরিবর্তন করবেন সেট করুন:",
            reply_markup=kb, parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"limit view: {e}")
        await query.answer(f"Error: {e}", show_alert=True)

# ═══════════════════════════════════════════
# /install
# ═══════════════════════════════════════════
async def install_module(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("🔐 আগে পাসওয়ার্ড দিন।"); return
    if not context.args:
        await update.message.reply_text("Usage: /install <package_name>"); return

    package = context.args[0]
    if package.lower() == "telegram":
        package = "python-telegram-bot"
    await update.message.reply_text(f"⏳ Installing <code>{html_escape(package)}</code>...", parse_mode="HTML")
    try:
        p = subprocess.run([sys.executable, "-m", "pip", "install", package, "--no-cache-dir"],
                           capture_output=True, text=True)
        if p.returncode == 0:
            await update.message.reply_text(f"✅ Installed <code>{html_escape(package)}</code>!", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ Failed:\n<pre>{html_escape(p.stderr[:500])}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {html_escape(e)}", parse_mode="HTML")

# ═══════════════════════════════════════════
# /debug
# ═══════════════════════════════════════════
async def debug_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return

    uploads_list   = os.listdir(UPLOAD_DIR)   if os.path.exists(UPLOAD_DIR)   else []
    downloads_list = os.listdir(DOWNLOAD_DIR) if os.path.exists(DOWNLOAD_DIR) else []

    msg = (
        f"🐞 <b>DEBUG INFO</b>\n\n"
        f"📂 UPLOAD_DIR: <code>{html_escape(UPLOAD_DIR)}</code> ({len(uploads_list)})\n"
        f"📂 DOWNLOAD_DIR: <code>{html_escape(DOWNLOAD_DIR)}</code> ({len(downloads_list)})\n\n"
        f"📥 Uploads (first 10):\n<code>{html_escape(', '.join(uploads_list[:10]) or 'empty')}</code>\n\n"
        f"⚙️ Downloads (first 10):\n<code>{html_escape(', '.join(downloads_list[:10]) or 'empty')}</code>\n\n"
        f"🔑 Total codes: {len(CODE_DB)}\n"
        f"👥 Approved users: {len(approved_users)}\n"
        f"🚫 Blocked users: {len(CONFIG.get('blocked_users', []))}\n"
        f"🟢 Running scripts: {sum(1 for s in running_scripts.values() if s['proc'].poll() is None)}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")

# ═══════════════════════════════════════════
# MAIN MESSAGE HANDLER
# ═══════════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message.text else ""
    user = update.effective_user
    user_id = user.id
    save_user_info(user_id, user.first_name, user.username)

    # 🚫 Blocked user
    if is_blocked(user_id):
        if text == "📞 Contact Owner":
            await update.message.reply_text(
                "📞 <b>Contact Owner</b>\n\n"
                "👤 Owner: @ALAMIN_1BOSS\n"
                "💬 আপনার সমস্যা লিখে পাঠান।",
                reply_markup=blocked_keyboard(),
                parse_mode="HTML"
            )
            return
        await update.message.reply_text(
            "🚫 আপনি ব্লক হয়েছেন।\n\n"
            "শুধু Owner এর সাথে যোগাযোগ করতে পারবেন 👇",
            reply_markup=blocked_keyboard()
        )
        return

    # ═══ ADMIN STATES ═══
    if user_id == OWNER_ID:
        state = context.user_data.get("state")

        # ── Awaiting new password ──
        if state == "awaiting_new_password" and text:
            new_pass = text.strip()
            if not new_pass:
                await update.message.reply_text("❌ খালি পাসওয়ার্ড গ্রহণযোগ্য নয়।")
                return

            old_users = list(approved_users.keys())

            set_password(new_pass)
            context.user_data.pop("state", None)

            approved_users.clear()
            save_users(approved_users)

            await update.message.reply_text(
                f"✅ নতুন পাসওয়ার্ড সেট হয়েছে: <code>{html_escape(new_pass)}</code>\n\n"
                f"🔒 সব ইউজারকে এখন নতুন পাসওয়ার্ড দিতে হবে।\n"
                f"📢 {max(0, len(old_users)-1)} জন ইউজারকে নোটিফিকেশন পাঠানো হচ্ছে...",
                parse_mode="HTML"
            )

            notification = (
                "🔐 <b>পাসওয়ার্ড পরিবর্তন হয়েছে!</b>\n\n"
                "বট ব্যবহার করতে এখন <b>নতুন পাসওয়ার্ড</b> দিতে হবে।\n\n"
                "নতুন পাসওয়ার্ড পেতে আমাদের টেলিগ্রাম চ্যানেলে জয়েন করুন 👇\n\n"
                f"📢 <b>Channel:</b> {CHANNEL_URL}\n\n"
                "চ্যানেলে গিয়ে পাসওয়ার্ড নিন — এরপর সেটি এখানে পাঠালেই বট আবার চালু হবে ✅"
            )

            sent, failed = 0, 0
            for uid in old_users:
                if uid == OWNER_ID:
                    continue
                try:
                    await context.bot.send_message(
                        chat_id=uid, text=notification,
                        parse_mode="HTML", disable_web_page_preview=True
                    )
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    failed += 1
                    logger.error(f"Notify {uid} failed: {e}")

            await update.message.reply_text(
                f"📢 <b>Notification সম্পন্ন!</b>\n\n"
                f"✅ Sent: {sent}\n❌ Failed: {failed}\n\n"
                f"👉 এখন সব ইউজারকে নতুন পাসওয়ার্ড দিতে হবে।",
                parse_mode="HTML"
            )
            return

        # ── Awaiting broadcast message ──
        if state == "awaiting_broadcast":
            context.user_data.pop("state", None)

            btext = text or ""
            has_media = bool(update.message.photo or update.message.video or
                             update.message.document or update.message.audio)

            if not btext and not has_media:
                await update.message.reply_text("❌ খালি মেসেজ। Broadcast বাতিল।")
                return

            await update.message.reply_text("📢 পাঠানো হচ্ছে...")

            sent, failed = 0, 0
            for uid in list(approved_users.keys()):
                if uid == OWNER_ID:
                    continue
                try:
                    if btext:
                        await context.bot.send_message(chat_id=uid, text=btext, parse_mode="HTML")
                    elif update.message.photo:
                        await context.bot.send_photo(
                            chat_id=uid,
                            photo=update.message.photo[-1].file_id,
                            caption=update.message.caption or ""
                        )
                    elif update.message.video:
                        await context.bot.send_video(
                            chat_id=uid,
                            video=update.message.video.file_id,
                            caption=update.message.caption or ""
                        )
                    elif update.message.document:
                        await context.bot.send_document(
                            chat_id=uid,
                            document=update.message.document.file_id,
                            caption=update.message.caption or ""
                        )
                    elif update.message.audio:
                        await context.bot.send_audio(
                            chat_id=uid,
                            audio=update.message.audio.file_id,
                            caption=update.message.caption or ""
                        )
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    failed += 1
                    logger.error(f"Broadcast to {uid} failed: {e}")

            await update.message.reply_text(
                f"📢 <b>Broadcast সম্পন্ন!</b>\n\n"
                f"✅ Sent: {sent}\n❌ Failed: {failed}",
                parse_mode="HTML"
            )
            return

    # 🔐 Password gate
    if not is_allowed(user_id):
        if text == get_password():
            approved_users[user_id] = True
            save_users(approved_users)
            await update.message.reply_text("✅ Password correct! এখন বট চালু হয়েছে 🎉")
            await send_welcome(update.message)
        else:
            await update.message.reply_text(
                "🔐 <b>Access Restricted!</b>\n\n"
                "বট ব্যবহার করতে <b>নতুন পাসওয়ার্ড</b> পাঠান।\n\n"
                f"📢 পাসওয়ার্ড পেতে চ্যানেলে জয়েন করুন:\n{CHANNEL_URL}",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        return

    # ═══════════ Approved section ═══════════
    if text == "𝐔𝐏𝐋𝐎𝐀𝐃 𝐅𝐈𝐋𝐄𝐒 👾":
        if user_id == OWNER_ID:
            await update.message.reply_text("📤 আপনার ফাইল পাঠান (unlimited)")
        else:
            _, max_store = get_user_limits(user_id)
            await update.message.reply_text(f"📤 আপনার ফাইল পাঠান (সর্বোচ্চ {max_store}টি স্টোর)")

    elif text in ("📂 𝐂𝐇𝐄𝐀𝐊 𝐅𝐈𝐋𝐄𝐒", "🔄 𝐑𝐄-𝐑𝐔𝐍 𝐅𝐈𝐋𝐄𝐒"):
        await list_hosted_files(update, context)

    elif text == "⚡ 𝐁𝐎𝐓 𝐒𝐏𝐄𝐄𝐃":
        await update.message.reply_text("⚡ Bot latency: 0.1s")

    elif text == "📊 Statistics":
        if user_id == OWNER_ID:
            total_users = len(approved_users)
            blocked_cnt = len(CONFIG.get("blocked_users", []))
            total_files = len(get_all_files())
            running_cnt = sum(1 for s in running_scripts.values() if s["proc"].poll() is None)
            await update.message.reply_text(
                f"📊 <b>Admin Statistics</b>\n\n"
                f"👥 Total Users: {total_users}\n"
                f"🚫 Blocked: {blocked_cnt}\n"
                f"📂 Total Files: {total_files}\n"
                f"🟢 Running: {running_cnt}",
                parse_mode="HTML"
            )
        else:
            my_files = get_user_files(user_id)
            max_run, max_store = get_user_limits(user_id)
            running_cnt = count_user_running(user_id)
            await update.message.reply_text(
                f"📊 Running: {running_cnt}/{max_run}\n"
                f"📂 Stored: {len(my_files)}/{max_store}"
            )

    elif text == "📞 Contact Owner":
        await update.message.reply_text("📞 Contact: @ALAMIN_1BOSS")

    elif text == "🛑 𝐒𝐓𝐎𝐏 𝐒𝐂𝐑𝐈𝐏𝐓":
        await stop_script(update, context)

    elif text == "👑 Admin Panel" and user_id == OWNER_ID:
        await admin_panel(update, context)

    elif text and text.strip().upper() in CODE_DB:
        code = text.strip().upper()
        entry = CODE_DB[code]
        path = entry["path"]
        if not os.path.exists(path):
            await update.message.reply_text("❌ ফাইলটি আর নেই।"); return
        await update.message.reply_text("📤 ফাইল পাঠানো হচ্ছে...")
        try:
            with open(path, "rb") as f:
                await update.message.reply_document(document=f, filename=entry["name"])
            entry["used"] = entry.get("used", 0) + 1
            save_db(CODE_DB)
        except Exception as e:
            await update.message.reply_text(f"❌ সমস্যা: {html_escape(e)}", parse_mode="HTML")
        return

    elif (update.message.document or update.message.video or
          update.message.audio or update.message.photo):

        msg = await update.message.reply_text("⏳ আপনার ফাইলটি প্রসেস করা হচ্ছে...")
        try:
            if update.message.document:
                tg_file = await update.message.document.get_file()
                name = update.message.document.file_name or "file"
            elif update.message.video:
                tg_file = await update.message.video.get_file()
                name = update.message.video.file_name or "video.mp4"
            elif update.message.audio:
                tg_file = await update.message.audio.get_file()
                name = update.message.audio.file_name or "audio.mp3"
            else:
                tg_file = await update.message.photo[-1].get_file()
                name = "photo.jpg"

            if user_id != OWNER_ID:
                _, max_store = get_user_limits(user_id)
                existing = get_user_files(user_id)
                existing_names = [n for n, _ in existing]
                if name not in existing_names and len(existing) >= max_store:
                    await msg.edit_text(
                        f"⚠️ আপনি সর্বোচ্চ <b>{max_store}</b> টি ফাইল স্টোর করতে পারবেন।\n\n"
                        f"📞 লিমিট বাড়ানোর জন্য এডমিনের সাথে যোগাযোগ করুন:\n@ALAMIN_1BOSS",
                        parse_mode="HTML"
                    )
                    return

            code = generate_code()
            safe_name = f"{code}_{name}"

            path_uploads = os.path.join(UPLOAD_DIR, safe_name)
            await tg_file.download_to_drive(path_uploads)

            user_download_dir = os.path.join(DOWNLOAD_DIR, str(user_id))
            os.makedirs(user_download_dir, exist_ok=True)
            path_downloads = os.path.join(user_download_dir, name)
            try:
                shutil.copy2(path_uploads, path_downloads)
            except Exception as e:
                logger.error(f"Copy failed: {e}")

            CODE_DB[code] = {
                "path": path_uploads,
                "name": name,
                "owner": str(user_id),
                "used": 0
            }
            save_db(CODE_DB)

            if name.endswith(('.py', '.js')):
                if user_id != OWNER_ID:
                    max_run, _ = get_user_limits(user_id)
                    if count_user_running(user_id) >= max_run:
                        await msg.edit_text(
                            f"⚠️ আপনি সর্বোচ্চ <b>{max_run}</b> টি স্ক্রিপ্ট একসাথে চালাতে পারবেন।\n\n"
                            f"📞 লিমিট বাড়ানোর জন্য এডমিনের সাথে যোগাযোগ করুন:\n@ALAMIN_1BOSS\n\n"
                            f"✅ ফাইলটি স্টোরে রাখা হয়েছে।",
                            parse_mode="HTML"
                        )
                        return

                deps, pkg_mgr = [], "pip"
                if name.endswith('.py'):
                    deps = scan_python_dependencies(path_downloads)
                elif name.endswith('.js'):
                    deps = scan_js_dependencies(path_downloads)
                    pkg_mgr = "npm"

                if deps:
                    await msg.edit_text(f"📦 Installing {len(deps)} dependencies...")
                    for dep in deps:
                        if dep == "telegram" and pkg_mgr == "pip":
                            dep = "python-telegram-bot"
                        try:
                            subprocess.run(
                                [sys.executable, "-m", "pip", "install", dep, "--no-cache-dir"],
                                capture_output=True, timeout=60
                            )
                        except Exception as e:
                            logger.error(f"Failed {dep}: {e}")
                    await msg.edit_text(f"🚀 Launching <code>{html_escape(name)}</code>...",
                                        parse_mode="HTML")

                proc, err = launch_script(user_id, name, path_downloads)
                if err:
                    await msg.edit_text(f"❌ Hosting failed: {html_escape(err)}", parse_mode="HTML")
                    return

                await asyncio.sleep(4)
                if proc.poll() is not None:
                    try:
                        with open(f"{path_downloads}.log", "r", encoding="utf-8", errors="ignore") as f:
                            el = f.read()[-500:]
                        await msg.edit_text(
                            f"❌ <code>{html_escape(name)}</code> crashed:\n<pre>{html_escape(el)}</pre>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        await msg.edit_text(
                            f"❌ <code>{html_escape(name)}</code> crashed।", parse_mode="HTML"
                        )
                    return

                await asyncio.sleep(8)
                if proc.poll() is not None:
                    try:
                        with open(f"{path_downloads}.log", "r", encoding="utf-8", errors="ignore") as f:
                            el = f.read()[-500:]
                        await msg.edit_text(
                            f"❌ <code>{html_escape(name)}</code> 12 সেকেন্ডে বন্ধ হয়ে গেছে।\n"
                            f"<b>Log:</b>\n<pre>{html_escape(el) or 'empty'}</pre>\n\n"
                            f"💡 <i>নিজের টোকেন/কনফিগ যোগ করুন।</i>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        await msg.edit_text(
                            f"❌ <code>{html_escape(name)}</code> crashed।", parse_mode="HTML"
                        )
                    return

                try:
                    with open(f"{path_downloads}.log", "r", encoding="utf-8", errors="ignore") as f:
                        log_snippet = f.read()[-300:].strip()
                except Exception:
                    log_snippet = ""

                status_msg = f"🚀 <code>{html_escape(name)}</code> হোস্ট হয়েছে — Running 24/7!"
                if log_snippet:
                    status_msg += f"\n\n📄 <b>Log:</b>\n<pre>{html_escape(log_snippet)}</pre>"
                await msg.edit_text(status_msg, parse_mode="HTML")
            else:
                await msg.edit_text("✅ আপনার ফাইলটি সংরক্ষণ করা হয়েছে।")
            return

        except Exception as e:
            logger.exception("Upload failed")
            await msg.edit_text(f"❌ সমস্যা: {html_escape(e)}", parse_mode="HTML")
            return

    else:
        await update.message.reply_text("Please use menu buttons or send a file.")

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════
if __name__ == '__main__':
    keep_alive()
    application = (ApplicationBuilder().token(TOKEN)
                   .connect_timeout(60).read_timeout(60).write_timeout(60).build())
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('admin', admin_panel))
    application.add_handler(CommandHandler('install', install_module))
    application.add_handler(CommandHandler('stop', stop_script))
    application.add_handler(CommandHandler('run', run_saved))
    application.add_handler(CommandHandler('debug', debug_info))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO | (filters.TEXT & ~filters.COMMAND),
        handle_message
    ))
    print("🔥 Bot started!")
    application.run_polling()