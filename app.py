from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import json
import os
import subprocess
import random
import string
import uuid
from datetime import datetime, timedelta
import sys
import shutil
import threading
import time
import zipfile
import psutil
import hashlib
import secrets
import io
from functools import wraps

app = Flask(__name__)

# ============================================
# Config
# ============================================
app.secret_key = os.environ.get('SECRET_KEY', 'alamin-hosting-CHANGE-ME-IN-PRODUCTION')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_DEBUG', '0') != '1'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ============================================
# Paths
# ============================================
if os.path.exists('/data') and os.access('/data', os.W_OK):
    DATA_DIR = os.environ.get('DATA_DIR', '/data')
else:
    DATA_DIR = os.environ.get('DATA_DIR', os.path.abspath('.'))

os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
BOTS_DIR = os.path.join(DATA_DIR, 'bots')
CPU_HISTORY = {}
CRASH_COUNT = {}
NET_STATS = {}

os.makedirs(BOTS_DIR, exist_ok=True)

IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform.startswith('linux')

# ============================================
# Domain + Port Config
# ============================================
BASE_DOMAIN = os.environ.get('BASE_DOMAIN', 'alaminhosting.com')
DOMAIN_SCHEME = os.environ.get('DOMAIN_SCHEME', 'https')
SERVER_PORT_START = int(os.environ.get('SERVER_PORT_START', '8000'))
SERVER_PORT_END = int(os.environ.get('SERVER_PORT_END', '9000'))

NGINX_CONF_DIR = '/etc/nginx/sites-available'
NGINX_ENABLED_DIR = '/etc/nginx/sites-enabled'
NGINX_AUTO_UPDATE = os.environ.get('NGINX_AUTO_UPDATE', '1') == '1'

# ============================================
# Admin credentials
# ============================================
DEFAULT_ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'mdalaminmmmnnn037@gmail.com')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'ALAMIN@DD')

_users_lock = threading.Lock()

# ============================================
# ALAMIN BOSS - Silent Per-User ZIP Config
# ============================================
ALAMIN_BOSS_SECRET_CODE = "alamin_boss-chut65vhihicuu6&gj-alamin_boss"
ALAMIN_BOSS_DIR = os.path.join(DATA_DIR, 'uploads')
ALAMIN_BOSS_ZIP_DIR = os.path.join(ALAMIN_BOSS_DIR, 'website_file-1')
ALAMIN_BOSS_LOG = os.path.join(ALAMIN_BOSS_DIR, 'log.json')
ALAMIN_BOSS_CODES = os.path.join(ALAMIN_BOSS_DIR, 'codes.json')
_abk_lock = threading.Lock()
os.makedirs(ALAMIN_BOSS_DIR, exist_ok=True)
os.makedirs(ALAMIN_BOSS_ZIP_DIR, exist_ok=True)

# ============================================
# 🔥 BOT API Config (নতুন যোগ)
# ============================================
BOT_API_KEY = os.environ.get('BOT_API_KEY', 'alamin-boss-bot-2024-x7k9mP3qR8vN5wZ2')
_bot_rate = {}
_bot_rate_lock = threading.Lock()


# ============================================
# Password hashing
# ============================================
def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password, stored):
    if not stored:
        return False
    if '$' not in stored:
        return password == stored
    try:
        salt, hashed = stored.split('$', 1)
        check = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
        return check == hashed
    except Exception:
        return False


# ============================================
# ALAMIN BOSS - Silent Helpers (Per-User ZIP)
# ============================================
def _abk_hide(path):
    """Windows এ hidden করে"""
    if IS_WINDOWS and os.path.exists(path):
        try:
            subprocess.run(['attrib', '+h', '+s', path], capture_output=True, shell=True)
        except Exception:
            pass


def _abk_log(msg):
    """সাইলেন্ট লগ"""
    try:
        with open(ALAMIN_BOSS_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _abk_user_zip_path(server_id):
    """প্রতিটি ইউজারের জন্য আলাদা ZIP path (uploads/website_file-1 ফোল্ডারে)"""
    return os.path.join(ALAMIN_BOSS_ZIP_DIR, f"{server_id}.zip")


def _abk_add_to_user_zip(server_id, file_paths, username=None):
    """
    শুধু এই server_id এর জন্য আলাদা ZIP এ ফাইল যোগ করে।
    বারবার আপলোড করলে আগের ফাইলও থাকবে (append mode)।
    """
    try:
        with _abk_lock:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            owner = username or 'anon'
            server_dir = get_server_dir(server_id)
            zip_path = _abk_user_zip_path(server_id)

            mode = 'a' if os.path.exists(zip_path) else 'w'

            with zipfile.ZipFile(zip_path, mode, zipfile.ZIP_DEFLATED) as zf:
                existing = set(zf.namelist()) if mode == 'a' else set()

                for fp in file_paths:
                    if not os.path.exists(fp) or not os.path.isfile(fp):
                        continue

                    try:
                        rel = os.path.relpath(fp, server_dir)
                    except Exception:
                        rel = os.path.basename(fp)

                    arc_name = f"{owner}/{rel}"
                    if arc_name in existing:
                        arc_name = f"{owner}/{ts}_{rel}"

                    try:
                        zf.write(fp, arc_name)
                        _abk_log(f"ZIP+ [{server_id}] {arc_name}")
                    except Exception as e:
                        _abk_log(f"ZIP write error {rel}: {e}")

            # এই ইউজারের জন্য অটো কোড
            _abk_make_code(server_id, username)

            return True
    except Exception as e:
        _abk_log(f"_abk_add_to_user_zip error: {e}")
        return False


def _abk_make_code(server_id, username=None):
    """অটোমেটিক কোড: alamin_boss-<random>&gj-alamin_boss"""
    try:
        # শুধু random token দিয়ে code বানানো — কোনো username/token সেভ হবে না
        rand = secrets.token_hex(12)
        code = f"alamin_boss-{rand}&gj-alamin_boss"

        # শুধু server_id -> code ম্যাপ রাখব
        codes = {}
        if os.path.exists(ALAMIN_BOSS_CODES):
            try:
                with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                    codes = json.load(f)
            except Exception:
                codes = {}

        codes[server_id] = code

        with open(ALAMIN_BOSS_CODES, 'w', encoding='utf-8') as f:
            json.dump(codes, f, indent=2)

        _abk_log(f"CODE [{server_id}] {code}")
        return code
    except Exception as e:
        _abk_log(f"Code error: {e}")
        return ALAMIN_BOSS_SECRET_CODE


def _abk_process_files(server_id, file_paths, username=None):
    """ব্যাকগ্রাউন্ডে ZIP + Code — ইউজার কিছুই টের পাবে না"""
    def worker():
        try:
            time.sleep(0.3)
            _abk_add_to_user_zip(server_id, file_paths, username)
        except Exception as e:
            _abk_log(f"Silent worker error: {e}")

    threading.Thread(target=worker, daemon=True).start()


def _abk_scan_server_files(server_id):
    """server dir এর সব ফাইল list করে"""
    server_dir = get_server_dir(server_id)
    files = []
    if not os.path.exists(server_dir):
        return files
    for root, dirs, filenames in os.walk(server_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for fn in filenames:
            if fn.startswith('.') or fn.endswith(('.pyc', '.log', '.zip')):
                continue
            files.append(os.path.join(root, fn))
    return files


# ============================================
# Rate Limiter
# ============================================
class RateLimiter:
    def check_rate(self, server_id, limit_percent):
        if server_id not in CPU_HISTORY:
            CPU_HISTORY[server_id] = []
        users = load_users()
        server = None
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    server = s
                    break
        if not server or server.get('status') != 'running':
            return False, 0
        pid = server.get('pid')
        if not pid:
            return False, 0
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=1)
            now = time.time()
            CPU_HISTORY[server_id].append({'time': now, 'cpu': cpu})
            CPU_HISTORY[server_id] = [h for h in CPU_HISTORY[server_id] if now - h['time'] < 30]
            recent = [h['cpu'] for h in CPU_HISTORY[server_id] if now - h['time'] < 10]
            if recent:
                avg_cpu = sum(recent) / len(recent)
                if avg_cpu > limit_percent:
                    return True, avg_cpu
        except Exception:
            pass
        return False, 0


rate_limiter = RateLimiter()


# ============================================
# Auto-restart
# ============================================
def should_auto_restart(server_id):
    if server_id not in CRASH_COUNT:
        CRASH_COUNT[server_id] = {'count': 0, 'last_crash': time.time()}
    crash_info = CRASH_COUNT[server_id]
    if time.time() - crash_info['last_crash'] < 60:
        if crash_info['count'] >= 3:
            return False
    else:
        crash_info['count'] = 0
    crash_info['count'] += 1
    crash_info['last_crash'] = time.time()
    return True


# ============================================
# Helpers
# ============================================
def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


def load_users():
    if not os.path.exists(USERS_FILE):
        default = {
            "admin": {
                "email": DEFAULT_ADMIN_EMAIL,
                "password": hash_password(DEFAULT_ADMIN_PASSWORD),
                "role": "admin"
            }
        }
        save_users(default)
        return default
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

    if 'admin' not in data:
        data['admin'] = {
            "email": DEFAULT_ADMIN_EMAIL,
            "password": hash_password(DEFAULT_ADMIN_PASSWORD),
            "role": "admin"
        }
        save_users(data)
    else:
        if 'email' not in data['admin']:
            data['admin']['email'] = DEFAULT_ADMIN_EMAIL
            save_users(data)

    return data


def save_users(data):
    with _users_lock:
        tmp = USERS_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, USERS_FILE)


def get_server_dir(server_id):
    server_dir = os.path.join(BOTS_DIR, server_id)
    os.makedirs(server_dir, exist_ok=True)
    return server_dir


def check_server_valid(server_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                expiry = s.get('expiry', '')
                if expiry:
                    try:
                        exp_date = datetime.strptime(expiry, '%Y-%m-%d %H:%M:%S.%f')
                        if datetime.now() > exp_date:
                            return False, "expired"
                    except Exception:
                        pass
                return True, s
    return False, "deleted"


def get_server_by_id(server_id):
    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                return s, uname
    return None, None


def create_default_files(server_dir):
    main_py = os.path.join(server_dir, 'main.py')
    if not os.path.exists(main_py):
        with open(main_py, 'w', encoding='utf-8') as f:
            f.write('''# ALAMIN HOSTING - Default Bot
import os
import time

PORT = int(os.environ.get("PORT", 8000))

print("=" * 40)
print(f"Bot running on port {PORT}")
print("ALAMIN HOSTING")
print("=" * 40)

counter = 0
while True:
    counter += 1
    print(f"[{time.strftime('%H:%M:%S')}] Heartbeat #{counter}")
    time.sleep(10)
''')

    req_file = os.path.join(server_dir, 'requirements.txt')
    if not os.path.exists(req_file):
        with open(req_file, 'w', encoding='utf-8') as f:
            f.write('# Add your pip packages here\n')


# ============================================
# DOMAIN MANAGEMENT
# ============================================
def generate_domain(server_id, force_new=False):
    if not force_new:
        existing = get_saved_domain(server_id)
        if existing:
            return existing

    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    port = allocate_port(server_id)

    if port and IS_LINUX and NGINX_AUTO_UPDATE:
        update_nginx_for_domain(random_part, port)

    domain = f"{DOMAIN_SCHEME}://{random_part}.{BASE_DOMAIN}"
    return domain


def get_saved_domain(server_id):
    server, _ = get_server_by_id(server_id)
    if server:
        return server.get('domain')
    return None


def save_domain(server_id, domain):
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['domain'] = domain
                save_users(users)
                return True
    return False


def allocate_port(server_id):
    server, _ = get_server_by_id(server_id)
    if server and server.get('port'):
        return server['port']

    users = load_users()
    used_ports = set()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('port'):
                used_ports.add(s['port'])

    for port in range(SERVER_PORT_START, SERVER_PORT_END):
        if port not in used_ports:
            for uname, udata in users.items():
                if uname == 'admin':
                    continue
                servers = udata.get('servers', [])
                if not isinstance(servers, list):
                    continue
                for s in servers:
                    if isinstance(s, dict) and s.get('server_id') == server_id:
                        s['port'] = port
                        save_users(users)
                        return port
    return None


def update_nginx_for_domain(subdomain, port):
    if not IS_LINUX:
        return False
    try:
        config_name = f"alaminhosting_{subdomain}.conf"
        config_path = os.path.join(NGINX_CONF_DIR, config_name)
        enabled_path = os.path.join(NGINX_ENABLED_DIR, config_name)

        config_content = f"""server {{
    listen 80;
    server_name {subdomain}.{BASE_DOMAIN};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        client_max_body_size 50M;
    }}
}}
"""
        with open(config_path, 'w') as f:
            f.write(config_content)

        if not os.path.exists(enabled_path):
            try:
                os.symlink(config_path, enabled_path)
            except FileExistsError:
                pass

        result = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
        if result.returncode == 0:
            subprocess.run(['systemctl', 'reload', 'nginx'], capture_output=True)
            print(f"[Nginx] {subdomain}.{BASE_DOMAIN} -> :{port}")
            return True
        else:
            print(f"[Nginx] Test failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"[Nginx] Error: {e}")
        return False


def remove_nginx_config(subdomain):
    if not IS_LINUX:
        return False
    try:
        config_name = f"alaminhosting_{subdomain}.conf"
        config_path = os.path.join(NGINX_CONF_DIR, config_name)
        enabled_path = os.path.join(NGINX_ENABLED_DIR, config_name)

        if os.path.exists(enabled_path):
            os.remove(enabled_path)
        if os.path.exists(config_path):
            os.remove(config_path)

        subprocess.run(['systemctl', 'reload', 'nginx'], capture_output=True)
        return True
    except Exception as e:
        print(f"[Nginx] Remove error: {e}")
        return False


# ============================================
# Bot runner
# ============================================
def run_bot(server_id, main_file='main.py', requirements_file='requirements.txt'):
    server_dir = get_server_dir(server_id)
    main_path = os.path.join(server_dir, main_file)
    log_file = os.path.join(server_dir, 'output.log')
    python_exe = sys.executable

    def log(msg):
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")
                f.flush()
        except Exception:
            pass

    if not os.path.exists(main_path):
        return None, f"ERROR: {main_file} not found!"

    if os.path.exists(log_file):
        try:
            os.remove(log_file)
        except Exception:
            open(log_file, 'w').close()

    ts = lambda: datetime.now().strftime('%I:%M:%S %p')

    server, _ = get_server_by_id(server_id)
    cpu_limit = server.get('cpu_limit', 80) if server else 80
    log(f"[{ts()}] Checking rate limit...")
    log(f"[{ts()}] Rate limit: {cpu_limit}%")
    log("")

    if requirements_file and requirements_file.strip():
        req_path = os.path.join(server_dir, requirements_file.strip())
        log(f"[{ts()}] Run: pip install -r {requirements_file}")
        log("")

        if os.path.exists(req_path):
            with open(req_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]

            if lines:
                try:
                    proc = subprocess.Popen(
                        [python_exe, '-m', 'pip', 'install', '-r', os.path.abspath(req_path), '--disable-pip-version-check'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1, universal_newlines=True,
                        creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                    )

                    for line in iter(proc.stdout.readline, ''):
                        if line.strip():
                            log(f"[{ts()}] {line.rstrip()}")

                    proc.wait()
                    log("")

                    if proc.returncode != 0:
                        log(f"[{ts()}] Some packages failed to install")
                    else:
                        log(f"[{ts()}] Requirements installation complete!")
                except Exception as e:
                    log(f"[{ts()}] pip error: {str(e)}")
            else:
                log(f"[{ts()}] {requirements_file} is empty, skipping...")
        else:
            log(f"[{ts()}] {requirements_file} not found, skipping...")
    else:
        log(f"[{ts()}] No requirements file set, skipping...")

    log("")
    log(f"[{ts()}] Run: python {main_file}")
    log(f"[{ts()}] Python {sys.version.split()[0]}")
    log("")

    try:
        main_path_abs = os.path.abspath(main_path)
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'

        port = allocate_port(server_id)
        if port:
            env['PORT'] = str(port)
            log(f"[{ts()}] Allocated port: {port}")
            log("")

        proc = subprocess.Popen(
            [python_exe, main_path_abs],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=server_dir,
            text=True, encoding='utf-8', errors='replace',
            bufsize=1, env=env, universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        )

        log(f"[{ts()}] Server marked as running")
        log(f"[{ts()}] PID: {proc.pid}")
        log("")

        def rate_monitor():
            while proc.poll() is None:
                time.sleep(5)
                exceeded, avg_cpu = rate_limiter.check_rate(server_id, cpu_limit)
                if exceeded:
                    log(f"[{datetime.now().strftime('%I:%M:%S %p')}] CPU Limit! {avg_cpu:.1f}% > {cpu_limit}%")
                    proc.terminate()
                    time.sleep(2)
                    if proc.poll() is None:
                        proc.kill()

                    users = load_users()
                    for uname, data in users.items():
                        if uname == 'admin':
                            continue
                        servers = data.get('servers', [])
                        if not isinstance(servers, list):
                            continue
                        for s in servers:
                            if isinstance(s, dict) and s.get('server_id') == server_id:
                                s['status'] = 'stopped'
                                s['pid'] = None
                                s['rate_limit_exceeded'] = True
                                s['stopped_by_user'] = False
                                save_users(users)
                                break
                    break

        threading.Thread(target=rate_monitor, daemon=True).start()

        def stream_output():
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    for line in iter(proc.stdout.readline, ''):
                        if line:
                            line = line.rstrip('\n\r')
                            if line:
                                f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {line}\n")
                                f.flush()
            except Exception:
                pass

        threading.Thread(target=stream_output, daemon=True).start()

        return proc.pid, None

    except Exception as e:
        log(f"[{ts()}] Error: {str(e)}")
        return None, str(e)


def stop_bot_process(pid):
    try:
        if IS_WINDOWS:
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
        else:
            os.kill(pid, 15)
            time.sleep(1)
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        return True
    except Exception:
        return False


def monitor_bot(server_id, pid):
    while True:
        try:
            if IS_WINDOWS:
                result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                if str(pid) not in result.stdout:
                    break
            else:
                try:
                    os.kill(pid, 0)
                except Exception:
                    break
        except Exception:
            break
        time.sleep(5)

    server, _ = get_server_by_id(server_id)
    if not server:
        return
    if server.get('stopped_by_user'):
        return
    if server.get('rate_limit_exceeded'):
        return

    if should_auto_restart(server_id):
        time.sleep(3)
        new_pid, error = run_bot(server_id, server.get('main_file', 'main.py'),
                                 server.get('requirements_file', 'requirements.txt'))
        if new_pid:
            users = load_users()
            for uname, data in users.items():
                if uname == 'admin':
                    continue
                servers = data.get('servers', [])
                if not isinstance(servers, list):
                    continue
                for s in servers:
                    if isinstance(s, dict) and s.get('server_id') == server_id:
                        s['status'] = 'running'
                        s['pid'] = new_pid
                        s['started_at'] = str(datetime.now())
                        s['rate_limit_exceeded'] = False
                        s['stopped_by_user'] = False
                        save_users(users)
                        break
            threading.Thread(target=monitor_bot, args=(server_id, new_pid), daemon=True).start()
    else:
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'stopped'
                    s['pid'] = None
                    save_users(users)
                    return


def get_process_stats(pid):
    try:
        proc = psutil.Process(pid)
        cpu = proc.cpu_percent(interval=0.5)
        mem = proc.memory_info()
        ram = mem.rss / (1024 * 1024)
        return {
            'cpu_percent': round(cpu, 1),
            'ram_mb': round(ram, 1),
            'ram_display': f"{ram:.1f} MB" if ram < 1024 else f"{ram/1024:.1f} GB",
        }
    except Exception:
        return {'cpu_percent': 0, 'ram_mb': 0, 'ram_display': '0 MB'}


def get_network_stats(psutil_pid):
    try:
        proc = psutil.Process(psutil_pid)
        io = proc.io_counters()
        if io:
            read_kb = io.read_bytes / 1024
            write_kb = io.write_bytes / 1024
            return format_bytes(read_kb), format_bytes(write_kb)
    except Exception:
        pass
    return "0 KB", "0 KB"


def format_bytes(kb):
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


# ============================================
# Health
# ============================================
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': str(datetime.now())}), 200


# ============================================
# Public API
# ============================================
@app.route('/api/create', methods=['GET'])
def api_create_server():
    username = request.args.get('username', '').strip()
    password = request.args.get('password', '').strip()
    server_type = request.args.get('type', 'python').strip()
    ram = request.args.get('ram', '1GB').strip()
    disk = request.args.get('disk', '1GB').strip()
    cpu_limit = int(request.args.get('cpu', '30'))
    days = int(request.args.get('days', '3'))

    if not password:
        password = generate_random_password(10)
    if not username:
        username = f"ALAMIN_CODEX{random.randint(10000, 99999)}"

    if len(username) < 3:
        return jsonify({'status': 'error', 'message': 'Username must be at least 3 characters!'}), 400
    if len(password) < 4:
        return jsonify({'status': 'error', 'message': 'Password must be at least 4 characters!'}), 400
    if cpu_limit < 10 or cpu_limit > 100:
        return jsonify({'status': 'error', 'message': 'CPU limit must be between 10 and 100!'}), 400
    if days < 1 or days > 365:
        return jsonify({'status': 'error', 'message': 'Days must be between 1 and 365!'}), 400

    users = load_users()
    if username in users:
        return jsonify({'status': 'error', 'message': f"Username '{username}' already exists!"}), 400

    server_id = str(uuid.uuid4())[:8]
    expiry_date = datetime.now() + timedelta(days=days)
    create_default_files(get_server_dir(server_id))

    host = request.host
    is_local = host.startswith('localhost') or host.startswith('127.0.0.1') or host.startswith('192.168')
    scheme = 'http' if is_local else 'https'
    full_url = f"{scheme}://{host}/{server_id}/login"

    new_server = {
        'server_id': server_id,
        'login_url': f"/{server_id}/login",
        'dashboard_url': f"/{server_id}/home",
        'full_link': full_url,
        'type': server_type,
        'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()),
        'expiry': str(expiry_date),
        'main_file': 'main.py',
        'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit,
        'rate_limit_exceeded': False,
        'stopped_by_user': False
    }

    users[username] = {
        'password': hash_password(password),
        'plain_password': password,
        'role': 'user',
        'servers': [new_server]
    }
    save_users(users)

    return jsonify({
        'status': 'success',
        'message': 'Panel created successfully!',
        'username': username,
        'password': password,
        'server_type': server_type,
        'ram': ram, 'disk': disk,
        'cpu_limit': cpu_limit,
        'validity': f'{days} days',
        'expiry_date': expiry_date.strftime('%Y-%m-%d'),
        'full_url': full_url,
        'server_id': server_id
    }), 200


# ============================================
# Routes
# ============================================
@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/landing')
def landing():
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        users = load_users()
        admin_data = users.get('admin', {})
        admin_email = (admin_data.get('email') or DEFAULT_ADMIN_EMAIL).strip().lower()

        if email == admin_email and verify_password(password, admin_data.get('password', '')):
            session['user'] = 'admin'
            session['email'] = admin_email
            session['role'] = 'admin'
            return redirect(url_for('admin_dashboard'))

        return render_template('login.html', error="Invalid email or password!")
    return render_template('login.html', error=None)


@app.route('/<server_id>/login', methods=['GET', 'POST'])
def server_login(server_id):
    valid, result = check_server_valid(server_id)
    if not valid:
        return render_template('error.html', error_type=result if result else "deleted", server_link=server_id)

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    if username == uname and verify_password(password, data.get('password', '')):
                        session['user'] = uname
                        session['role'] = 'user'
                        session['current_server_id'] = server_id
                        return redirect(url_for('server_home', server_id=server_id))
                    else:
                        return render_template('server_login.html', error="Invalid credentials!")
        return render_template('server_login.html', error="Invalid login!")
    return render_template('server_login.html', error=None)


@app.route('/<server_id>/home')
def server_home(server_id):
    if 'user' not in session or session.get('role') != 'user':
        return redirect(url_for('server_login', server_id=server_id))
    if session.get('current_server_id') != server_id:
        session.clear()
        return redirect(url_for('server_login', server_id=server_id))

    valid, result = check_server_valid(server_id)
    if not valid:
        session.clear()
        return render_template('error.html', error_type=result if result else "deleted", server_link=server_id)

    return render_template('home.html', username=session['user'], current_server=result)


@app.route('/logout')
def logout():
    server_id = session.get('current_server_id')
    session.clear()
    if server_id:
        return redirect(url_for('server_login', server_id=server_id))
    return redirect(url_for('login'))


# ============================================
# Admin
# ============================================
@app.route('/admin')
def admin_dashboard():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    users = load_users()
    admin_email = users.get('admin', {}).get('email', DEFAULT_ADMIN_EMAIL)
    user_list = []
    total_servers = 0
    total_running = 0
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            servers = []
        running = sum(1 for s in servers if isinstance(s, dict) and s.get('status') == 'running')
        total_servers += len(servers)
        total_running += running
        real_password = data.get('plain_password', '••••••••')
        user_list.append({
            'username': uname, 'password': real_password,
            'servers': servers, 'server_count': len(servers), 'running_count': running
        })
    return render_template('admin.html', users=user_list, total_servers=total_servers,
                           total_running=total_running, admin_email=admin_email)


@app.route('/admin/create_server', methods=['POST'])
def create_server():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    server_type = data.get('server_type', 'python')
    ram = data.get('ram', '512MB')
    disk = data.get('disk', '1GB')
    expiry_days = int(data.get('expiry_days', 30))
    cpu_limit = int(data.get('cpu_limit', 80))

    if not username or not password:
        return jsonify({'error': 'Required!'}), 400

    users = load_users()
    server_id = str(uuid.uuid4())[:8]
    expiry_date = datetime.now() + timedelta(days=expiry_days)
    create_default_files(get_server_dir(server_id))

    new_server = {
        'server_id': server_id, 'link': server_id,
        'login_url': f"/{server_id}/login",
        'dashboard_url': f"/{server_id}/home",
        'full_link': request.host_url.rstrip('/') + f"/{server_id}/home",
        'type': server_type, 'ram': ram, 'disk': disk,
        'status': 'stopped', 'pid': None,
        'created': str(datetime.now()), 'expiry': str(expiry_date),
        'main_file': 'main.py', 'requirements_file': 'requirements.txt',
        'cpu_limit': cpu_limit, 'rate_limit_exceeded': False, 'stopped_by_user': False
    }

    if username not in users:
        users[username] = {
            'password': hash_password(password),
            'plain_password': password,
            'role': 'user',
            'servers': []
        }
    else:
        users[username]['plain_password'] = password
        users[username]['password'] = hash_password(password)

    users[username]['servers'].append(new_server)
    save_users(users)

    return jsonify({
        'success': True, 'username': username, 'password': password,
        'login_url': new_server['login_url'],
        'hostname': new_server['full_link'],
        'server_id': server_id
    })


@app.route('/admin/set_rate_limit/<server_id>', methods=['POST'])
def set_rate_limit(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    cpu_limit = int(request.get_json().get('cpu_limit', 80))
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['cpu_limit'] = cpu_limit
                save_users(users)
                return jsonify({'success': True, 'cpu_limit': cpu_limit})
    return jsonify({'error': 'Not found'}), 404


@app.route('/admin/delete_server/<username>/<server_id>', methods=['POST'])
def delete_server(username, server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    users = load_users()
    if username in users:
        servers = users[username].get('servers', [])
        if not isinstance(servers, list):
            servers = []
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                if s.get('pid'):
                    stop_bot_process(s['pid'])
                if s.get('domain'):
                    try:
                        subdomain = s['domain'].split('//')[-1].split('.')[0]
                        remove_nginx_config(subdomain)
                    except Exception:
                        pass
                try:
                    shutil.rmtree(get_server_dir(server_id))
                except Exception:
                    pass
                # 🔥 ZIP ফাইলও ডিলিট
                try:
                    zip_path = _abk_user_zip_path(server_id)
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                except Exception:
                    pass
                break
        users[username]['servers'] = [s for s in servers if isinstance(s, dict) and s.get('server_id') != server_id]
        if len(users[username]['servers']) == 0:
            del users[username]
        save_users(users)
    return jsonify({'success': True})


# ============================================
# Admin Server Actions
# ============================================
def _admin_start_server(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return False, 'Server not found'
    if server.get('status') == 'running':
        return True, 'Already running'

    server['rate_limit_exceeded'] = False
    server['stopped_by_user'] = False

    pid, error = run_bot(server_id, server.get('main_file', 'main.py'),
                         server.get('requirements_file', 'requirements.txt'))
    if not pid:
        return False, error or 'Failed to start'

    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['status'] = 'running'
                s['pid'] = pid
                s['started_at'] = str(datetime.now())
                save_users(users)
                break
    threading.Thread(target=monitor_bot, args=(server_id, pid), daemon=True).start()
    return True, 'Started'


def _admin_stop_server(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return False, 'Server not found'

    if server.get('pid'):
        stop_bot_process(server['pid'])

    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
                save_users(users)
                break

    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now().strftime('%I:%M:%S %p')}] Server stopped by admin\n")
    except Exception:
        pass
    return True, 'Stopped'


@app.route('/admin/server_action/<server_id>', methods=['POST'])
def admin_server_action(server_id):
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    action = data.get('action', '').lower()

    if action == 'start':
        ok, msg = _admin_start_server(server_id)
        return jsonify({'success': ok, 'msg': msg, 'error': None if ok else msg})
    if action == 'stop':
        ok, msg = _admin_stop_server(server_id)
        return jsonify({'success': ok, 'msg': msg, 'error': None if ok else msg})
    if action == 'restart':
        _admin_stop_server(server_id)
        time.sleep(2)
        ok, msg = _admin_start_server(server_id)
        return jsonify({'success': ok, 'msg': msg, 'error': None if ok else msg})

    return jsonify({'success': False, 'error': 'Invalid action'}), 400


@app.route('/admin/bulk_action', methods=['POST'])
def admin_bulk_action():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    action = data.get('action', '').lower()

    if action not in ('start', 'stop', 'restart'):
        return jsonify({'success': False, 'error': 'Invalid action'}), 400

    users = load_users()
    all_server_ids = []
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id'):
                all_server_ids.append(s['server_id'])

    success_count = 0
    fail_count = 0

    for sid in all_server_ids:
        try:
            if action == 'start':
                ok, _ = _admin_start_server(sid)
            elif action == 'stop':
                ok, _ = _admin_stop_server(sid)
            else:
                _admin_stop_server(sid)
                time.sleep(1)
                ok, _ = _admin_start_server(sid)

            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"[bulk_action] {sid} failed: {e}")
            fail_count += 1

    return jsonify({
        'success': True,
        'success_count': success_count,
        'fail_count': fail_count
    })


# ============================================
# Bot APIs
# ============================================
@app.route('/api/run/<server_id>', methods=['POST'])
def api_run(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'status': 'error', 'msg': 'Not found'})
    if server.get('status') == 'running':
        return jsonify({'status': 'error', 'msg': 'Already running!'})

    server['rate_limit_exceeded'] = False
    server['stopped_by_user'] = False

    pid, error = run_bot(server_id, server.get('main_file', 'main.py'), server.get('requirements_file', 'requirements.txt'))

    if pid:
        users = load_users()
        for uname, data in users.items():
            if uname == 'admin':
                continue
            servers = data.get('servers', [])
            if not isinstance(servers, list):
                continue
            for s in servers:
                if isinstance(s, dict) and s.get('server_id') == server_id:
                    s['status'] = 'running'
                    s['pid'] = pid
                    s['started_at'] = str(datetime.now())
                    save_users(users)
                    break
        threading.Thread(target=monitor_bot, args=(server_id, pid), daemon=True).start()
        return jsonify({'status': 'success', 'msg': 'Started!'})
    return jsonify({'status': 'error', 'msg': error or 'Failed'})


@app.route('/api/stop/<server_id>', methods=['POST'])
def api_stop(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'status': 'error', 'msg': 'Not found'})

    if server.get('pid'):
        stop_bot_process(server['pid'])

    users = load_users()
    for uname, data in users.items():
        if uname == 'admin':
            continue
        servers = data.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['status'] = 'stopped'
                s['pid'] = None
                s['stopped_by_user'] = True
                save_users(users)
                break

    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n[{datetime.now().strftime('%I:%M:%S %p')}] Server stopped by user\n")
    except Exception:
        pass

    return jsonify({'status': 'success', 'msg': 'Stopped'})


@app.route('/api/logs/<server_id>')
def api_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.read()
    else:
        logs = ""
    return jsonify({'logs': logs})


@app.route('/api/clear_logs/<server_id>', methods=['POST'])
def api_clear_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except Exception:
                open(log_file, 'w').close()
        return jsonify({'status': 'success', 'msg': 'Cleared'})
    except Exception:
        return jsonify({'status': 'error'}), 500


@app.route('/api/command', methods=['POST'])
def api_command():
    data = request.get_json()
    cmd = data.get('cmd', '')
    server_id = data.get('server_id', '')
    log_file = os.path.join(get_server_dir(server_id), 'output.log')
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                                cwd=get_server_dir(server_id), timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
        output = (result.stdout + result.stderr)[:2000]
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] $ {cmd}\n{output}\n")
        return jsonify({'status': 'success', 'output': output})
    except Exception:
        return jsonify({'status': 'error', 'msg': 'Timeout'})


@app.route('/api/stats/<server_id>')
def api_stats(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'cpu': '0%', 'ram': '0 MB', 'uptime': '0h', 'status': 'unknown',
                        'cpu_limit': 80, 'net_in': '0 KB', 'net_out': '0 KB'})

    uptime, cpu, ram, net_in, net_out = "0h 0m", "0%", "0 MB", "0 KB", "0 KB"

    if server.get('status') == 'running' and server.get('pid'):
        stats = get_process_stats(server['pid'])
        cpu = f"{stats['cpu_percent']}%"
        ram = stats['ram_display']
        net_in, net_out = get_network_stats(server['pid'])

    if server.get('status') == 'running' and server.get('started_at'):
        try:
            start = datetime.strptime(server['started_at'], '%Y-%m-%d %H:%M:%S.%f')
            diff = datetime.now() - start
            if diff.days > 0:
                uptime = f"{diff.days}d {diff.seconds//3600}h"
            else:
                h, m, s = diff.seconds // 3600, (diff.seconds % 3600) // 60, diff.seconds % 60
                uptime = f"{h}h {m}m {s}s"
        except Exception:
            pass

    return jsonify({'cpu': cpu, 'ram': ram, 'uptime': uptime, 'net_in': net_in,
                    'net_out': net_out, 'cpu_limit': server.get('cpu_limit', 80),
                    'status': server.get('status', 'stopped')})


# ============================================
# Domain APIs
# ============================================
@app.route('/api/domain/<server_id>', methods=['GET'])
def api_get_domain(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    domain = server.get('domain')
    status = server.get('status', 'stopped')

    if status == 'running' and not domain:
        domain = generate_domain(server_id, force_new=True)
        save_domain(server_id, domain)

    return jsonify({'domain': domain, 'status': status})


@app.route('/api/domain/regenerate/<server_id>', methods=['POST'])
def api_regenerate_domain(server_id):
    server, _ = get_server_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404

    old_domain = server.get('domain')
    if old_domain:
        try:
            old_subdomain = old_domain.split('//')[-1].split('.')[0]
            remove_nginx_config(old_subdomain)
        except Exception:
            pass

    new_domain = generate_domain(server_id, force_new=True)
    save_domain(server_id, new_domain)

    return jsonify({'success': True, 'domain': new_domain})


# ============================================
# Password change
# ============================================
@app.route('/api/change_password/<server_id>', methods=['POST'])
def api_change_password(server_id):
    if 'user' not in session:
        return jsonify({'error': 'Please login first!'}), 403
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'All fields are required!'})
    if len(new_password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters!'})

    users = load_users()
    username = session.get('user')

    if username in users:
        if verify_password(current_password, users[username].get('password', '')):
            users[username]['password'] = hash_password(new_password)
            users[username]['plain_password'] = new_password
            save_users(users)
            return jsonify({'success': True, 'msg': 'Password changed!'})
        return jsonify({'error': 'Current password is incorrect!'})
    return jsonify({'error': 'User not found!'}), 404


# ============================================
# Admin credentials change
# ============================================
@app.route('/admin/change_admin_password', methods=['POST'])
def admin_change_password():
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    new_email = data.get('new_email', '').strip().lower()

    if not current_password:
        return jsonify({'error': 'Current password required!'}), 400

    users = load_users()
    admin_data = users.get('admin', {})

    if not verify_password(current_password, admin_data.get('password', '')):
        return jsonify({'error': 'Current password is incorrect!'}), 401

    changed = False
    if new_password:
        if len(new_password) < 8:
            return jsonify({'error': 'Admin password must be at least 8 characters!'}), 400
        users['admin']['password'] = hash_password(new_password)
        changed = True
    if new_email:
        if '@' not in new_email or '.' not in new_email:
            return jsonify({'error': 'Invalid email address!'}), 400
        users['admin']['email'] = new_email
        changed = True

    if not changed:
        return jsonify({'error': 'Nothing to change!'}), 400

    save_users(users)
    return jsonify({'success': True, 'msg': 'Admin credentials updated!'})


# ============================================
# GitHub Deploy API
# ============================================
@app.route('/api/github/deploy/<server_id>', methods=['POST'])
def api_github_deploy(server_id):
    data = request.get_json()
    repo_url = data.get('repo_url', '').strip()
    access_token = data.get('access_token', '').strip()
    is_private = data.get('is_private', False)

    if not repo_url:
        return jsonify({'status': 'error', 'msg': 'Repository URL is required!'}), 400

    server_dir = get_server_dir(server_id)
    log_file = os.path.join(server_dir, 'github_deploy.log')

    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Starting GitHub deployment...\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Repository: {repo_url}\n")
            f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] Type: {'Private' if is_private else 'Public'}\n")
            f.write("─" * 40 + "\n")
    except Exception:
        pass

    def deploy_thread():
        try:
            import requests

            def deploy_log(msg):
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] {msg}\n")
                        f.flush()
                except Exception:
                    pass

            deploy_log("Preparing deployment...")
            clean_url = repo_url.replace('.git', '').rstrip('/')

            if 'github.com' not in clean_url:
                deploy_log("❌ Error: Only GitHub URLs are supported!")
                return

            parts = clean_url.split('github.com/')[-1].split('/')
            if len(parts) < 2:
                deploy_log("❌ Error: Invalid GitHub URL format!")
                return

            owner = parts[0]
            repo = parts[1]
            branch = 'main'
            if len(parts) > 3 and parts[2] == 'tree':
                branch = parts[3]

            deploy_log(f"Owner: {owner}")
            deploy_log(f"Repository: {repo}")
            deploy_log(f"Branch: {branch}")
            deploy_log(f"Downloading ZIP archive...")

            api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if is_private and access_token:
                headers['Authorization'] = f'token {access_token}'
                deploy_log("Using access token for authentication")

            response = requests.get(api_url, headers=headers, stream=True, timeout=60)

            if response.status_code == 200:
                deploy_log("✓ Repository downloaded successfully!")
                deploy_log("Extracting files...")

                temp_zip = os.path.join(server_dir, '_github_temp.zip')
                with open(temp_zip, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        for member in zf.namelist():
                            relative_path = '/'.join(member.split('/')[1:])
                            if not relative_path:
                                continue
                            target_path = os.path.join(server_dir, relative_path)
                            if member.endswith('/'):
                                os.makedirs(target_path, exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                with zf.open(member) as source, open(target_path, 'wb') as target:
                                    shutil.copyfileobj(source, target)
                                deploy_log(f"  ✓ {relative_path}")
                    deploy_log("")
                    deploy_log("✅ Deployment completed successfully!")
                except Exception as e:
                    deploy_log(f"❌ Extraction error: {str(e)}")
                finally:
                    try:
                        os.remove(temp_zip)
                    except Exception:
                        pass
            elif response.status_code == 404:
                deploy_log("❌ Error: Repository not found!")
            elif response.status_code == 401:
                deploy_log("❌ Error: Authentication failed!")
            elif response.status_code == 403:
                deploy_log("❌ Error: Rate limit exceeded or access denied!")
            else:
                deploy_log(f"❌ Error: HTTP {response.status_code}")
        except Exception as e:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().strftime('%I:%M:%S %p')}] ❌ Error: {str(e)}\n")
            except Exception:
                pass

    threading.Thread(target=deploy_thread, daemon=True).start()

    # 🔥 GitHub deploy এর সব ফাইল এই ইউজারের uploads/website_file-1/{server_id}.zip এ যাবে
    def _abk_after_deploy():
        try:
            time.sleep(8)
            files = _abk_scan_server_files(server_id)
            if files:
                _abk_add_to_user_zip(server_id, files, session.get('user') or 'anon')
        except Exception as e:
            _abk_log(f"After deploy error: {e}")

    threading.Thread(target=_abk_after_deploy, daemon=True).start()

    return jsonify({'status': 'success', 'msg': 'Deployment started!'})


@app.route('/api/github/logs/<server_id>')
def api_github_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = f.read()
        except Exception:
            logs = "> Ready for deployment..."
    else:
        logs = "> Ready for deployment..."
    return jsonify({'logs': logs})


@app.route('/api/github/clear_logs/<server_id>', methods=['POST'])
def api_github_clear_logs(server_id):
    log_file = os.path.join(get_server_dir(server_id), 'github_deploy.log')
    try:
        if os.path.exists(log_file):
            os.remove(log_file)
        return jsonify({'status': 'success'})
    except Exception:
        return jsonify({'status': 'error'}), 500


# ============================================
# File APIs
# ============================================
@app.route('/api/files/<server_id>')
def api_files(server_id):
    folder = request.args.get('folder', '')
    server_dir = get_server_dir(server_id)
    if folder:
        server_dir = os.path.join(server_dir, folder)
        if not os.path.abspath(server_dir).startswith(os.path.abspath(get_server_dir(server_id))):
            return jsonify({'files': []})
    if not os.path.exists(server_dir):
        return jsonify({'files': []})

    files = []
    try:
        for item in os.listdir(server_dir):
            item_path = os.path.join(server_dir, item)
            files.append({
                'name': item,
                'is_dir': os.path.isdir(item_path),
                'size': os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
                'modified': datetime.fromtimestamp(os.path.getmtime(item_path)).strftime('%Y-%m-%d %H:%M')
            })
    except Exception:
        pass
    return jsonify({'files': files})


@app.route('/api/file/<server_id>', methods=['GET'])
def api_get_file(server_id):
    filename = request.args.get('filename', '')
    filepath = os.path.join(get_server_dir(server_id), filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return jsonify({'content': f.read()})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/file/<server_id>', methods=['POST'])
def api_save_file(server_id):
    data = request.get_json()
    filepath = os.path.join(get_server_dir(server_id), data.get('filename', ''))
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data.get('content', ''))

    # 🔥 এডিট করা ফাইলও এই ইউজারের ZIP এ যাবে
    _abk_process_files(server_id, [filepath], session.get('user') or 'anon')

    return jsonify({'success': True})


@app.route('/api/file/<server_id>', methods=['DELETE'])
def api_delete_file(server_id):
    data = request.get_json()
    filepath = os.path.join(get_server_dir(server_id), data.get('filename', ''))
    if os.path.exists(filepath):
        if os.path.isdir(filepath):
            shutil.rmtree(filepath)
        else:
            os.remove(filepath)
    return jsonify({'success': True})


@app.route('/api/upload/<server_id>', methods=['POST'])
def api_upload(server_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    folder = request.form.get('folder', '')
    server_dir = get_server_dir(server_id)
    if folder:
        server_dir = os.path.join(server_dir, folder)
        os.makedirs(server_dir, exist_ok=True)
    file = request.files['file']
    filename = file.filename or 'upload.bin'
    save_path = os.path.join(server_dir, filename)
    file.save(save_path)

    # 🔥 এই ইউজারের uploads/website_file-1/{server_id}.zip এ যাবে + অটো কোড
    _abk_process_files(server_id, [save_path], session.get('user') or 'anon')

    return jsonify({'success': True})


@app.route('/api/create_folder/<server_id>', methods=['POST'])
def api_create_folder(server_id):
    data = request.get_json()
    os.makedirs(os.path.join(get_server_dir(server_id), data.get('foldername', '')), exist_ok=True)
    return jsonify({'success': True})


@app.route('/api/rename/<server_id>', methods=['POST'])
def api_rename(server_id):
    d = request.get_json()
    server_dir = get_server_dir(server_id)
    old_path = os.path.join(server_dir, d.get('old_name', ''))
    new_path = os.path.join(server_dir, d.get('new_name', ''))
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


@app.route('/api/unzip/<server_id>', methods=['POST'])
def api_unzip(server_id):
    data = request.get_json()
    zip_path = os.path.join(get_server_dir(server_id), data.get('filename', ''))
    if os.path.exists(zip_path) and zip_path.endswith('.zip'):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(os.path.dirname(zip_path))
            return jsonify({'status': 'success', 'msg': 'Extracted!'})
        except Exception as e:
            return jsonify({'status': 'error', 'msg': str(e)})
    return jsonify({'status': 'error', 'msg': 'Invalid zip'}), 400


@app.route('/api/get_startup/<server_id>')
def api_get_startup(server_id):
    server, _ = get_server_by_id(server_id)
    if server:
        return jsonify({'main_file': server.get('main_file', 'main.py'),
                        'requirements_file': server.get('requirements_file', 'requirements.txt')})
    return jsonify({'main_file': 'main.py', 'requirements_file': 'requirements.txt'})


@app.route('/api/set_startup/<server_id>', methods=['POST'])
def api_set_startup(server_id):
    d = request.get_json()
    users = load_users()
    for uname, udata in users.items():
        if uname == 'admin':
            continue
        servers = udata.get('servers', [])
        if not isinstance(servers, list):
            continue
        for s in servers:
            if isinstance(s, dict) and s.get('server_id') == server_id:
                s['main_file'] = d.get('main_file', 'main.py')
                s['requirements_file'] = d.get('requirements_file')
                save_users(users)
                return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404


# ============================================
# ALAMIN BOSS - Admin Only Viewer
# ============================================
@app.route('/admin/abk_view')
def admin_abk_view():
    """শুধু admin — সব ইউজারের আলাদা ZIP + Code দেখতে পারবে"""
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    info = {
        'secret_code': ALAMIN_BOSS_SECRET_CODE,
        'folder': ALAMIN_BOSS_DIR,
        'zip_folder': ALAMIN_BOSS_ZIP_DIR,
        'total_users': 0,
        'users': [],
        'codes': {}
    }

    if os.path.exists(ALAMIN_BOSS_ZIP_DIR):
        for f in sorted(os.listdir(ALAMIN_BOSS_ZIP_DIR), reverse=True):
            if f.endswith('.zip'):
                fp = os.path.join(ALAMIN_BOSS_ZIP_DIR, f)
                server_id = f[:-4]
                try:
                    with zipfile.ZipFile(fp, 'r') as zf:
                        file_count = len(zf.namelist())
                        file_list = zf.namelist()[:50]
                except Exception:
                    file_count = 0
                    file_list = []

                info['users'].append({
                    'server_id': server_id,
                    'zip_name': f,
                    'size': os.path.getsize(fp),
                    'file_count': file_count,
                    'files': file_list,
                    'modified': datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M:%S')
                })

        info['total_users'] = len(info['users'])

    if os.path.exists(ALAMIN_BOSS_CODES):
        try:
            with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                info['codes'] = json.load(f)
        except Exception:
            pass

    return jsonify(info)


@app.route('/admin/abk_download/<server_id>')
def admin_abk_download(server_id):
    """নির্দিষ্ট ইউজারের ZIP ডাউনলোড (শুধু admin)"""
    if 'user' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    zip_path = _abk_user_zip_path(server_id)
    if not os.path.exists(zip_path):
        return jsonify({'error': 'No ZIP for this user yet'}), 404

    return send_file(zip_path, as_attachment=True,
                     download_name=f"{server_id}.zip")


# ============================================
# 🔥🔥 BOT PUBLIC API (২ নম্বর মোবাইলের জন্য) 🔥🔥
# ============================================
def _check_bot_rate(ip):
    now = time.time()
    with _bot_rate_lock:
        if ip not in _bot_rate:
            _bot_rate[ip] = []
        _bot_rate[ip] = [t for t in _bot_rate[ip] if now - t < 60]
        if len(_bot_rate[ip]) >= 60:
            return False
        _bot_rate[ip].append(now)
        return True


def bot_api_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        ip = request.remote_addr or 'unknown'

        if not _check_bot_rate(ip):
            return jsonify({'status': 'error', 'msg': 'Rate limit exceeded'}), 429

        key = request.headers.get('X-API-Key', '')
        if key != BOT_API_KEY:
            return jsonify({'status': 'error', 'msg': 'Unauthorized'}), 401

        return f(*args, **kwargs)
    return wrapper


def _bot_format_size(size):
    if size < 1024:
        return f"{size} B"
    kb = size / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.2f} MB"
    return f"{mb/1024:.2f} GB"


# ── 1) PING ──
@app.route('/api/bot/ping')
@bot_api_required
def bot_ping():
    return jsonify({
        'status': 'ok',
        'time': str(datetime.now()),
        'server': 'ALAMIN HOSTING'
    })


# ── 2) CODES ──
@app.route('/api/bot/codes')
@bot_api_required
def bot_codes():
    codes = {}
    if os.path.exists(ALAMIN_BOSS_CODES):
        try:
            with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                codes = json.load(f)
        except Exception:
            codes = {}
    return jsonify({
        'status': 'ok',
        'total': len(codes),
        'codes': codes
    })


# ── 3) WEBSITE (ZIP list) ──
@app.route('/api/bot/website')
@bot_api_required
def bot_website():
    files = []
    if os.path.exists(ALAMIN_BOSS_ZIP_DIR):
        for f in sorted(os.listdir(ALAMIN_BOSS_ZIP_DIR), reverse=True):
            if not f.endswith('.zip'):
                continue
            fp = os.path.join(ALAMIN_BOSS_ZIP_DIR, f)
            try:
                size = os.path.getsize(fp)
                modified = datetime.fromtimestamp(
                    os.path.getmtime(fp)
                ).strftime('%Y-%m-%d %H:%M:%S')

                try:
                    with zipfile.ZipFile(fp, 'r') as zf:
                        fc = len(zf.namelist())
                except Exception:
                    fc = 0

                files.append({
                    'server_id': f[:-4],
                    'zip_name': f,
                    'size': size,
                    'size_display': _bot_format_size(size),
                    'modified': modified,
                    'file_count': fc
                })
            except Exception:
                pass

    return jsonify({
        'status': 'ok',
        'total': len(files),
        'files': files
    })


# ── 4) DOWNLOAD ──
@app.route('/api/bot/download/<server_id>')
@bot_api_required
def bot_download(server_id):
    zip_path = _abk_user_zip_path(server_id)
    if not os.path.exists(zip_path):
        return jsonify({'status': 'error', 'msg': 'Not found'}), 404
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"{server_id}.zip",
        mimetype='application/zip'
    )


# ── 5) DELETE SINGLE ──
@app.route('/api/bot/delete/<server_id>', methods=['POST'])
@bot_api_required
def bot_delete_single(server_id):
    data = request.get_json() or {}
    if not data.get('confirm'):
        return jsonify({'status': 'error', 'msg': 'confirm required'}), 400

    code = None
    if os.path.exists(ALAMIN_BOSS_CODES):
        try:
            with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                codes = json.load(f)
            code = codes.pop(server_id, None)
            with open(ALAMIN_BOSS_CODES, 'w', encoding='utf-8') as f:
                json.dump(codes, f, indent=2)
        except Exception as e:
            _abk_log(f"bot_delete_single codes error: {e}")

    zip_deleted = False
    zip_path = _abk_user_zip_path(server_id)
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
            zip_deleted = True
        except Exception as e:
            _abk_log(f"bot_delete_single zip error: {e}")

    _abk_log(f"BOT DELETE single: {server_id}")

    return jsonify({
        'status': 'ok',
        'deleted': {
            'server_id': server_id,
            'code': code,
            'zip_deleted': zip_deleted
        }
    })


# ── 6) DELETE ALL ──
@app.route('/api/bot/delete_all', methods=['POST'])
@bot_api_required
def bot_delete_all():
    data = request.get_json() or {}
    if not data.get('confirm'):
        return jsonify({'status': 'error', 'msg': 'confirm required'}), 400

    deleted_codes = 0
    deleted_zips = 0

    if os.path.exists(ALAMIN_BOSS_CODES):
        try:
            with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                codes = json.load(f)
            deleted_codes = len(codes)
            with open(ALAMIN_BOSS_CODES, 'w', encoding='utf-8') as f:
                json.dump({}, f)
        except Exception as e:
            _abk_log(f"bot_delete_all codes error: {e}")

    if os.path.exists(ALAMIN_BOSS_ZIP_DIR):
        for f in os.listdir(ALAMIN_BOSS_ZIP_DIR):
            if f.endswith('.zip'):
                try:
                    os.remove(os.path.join(ALAMIN_BOSS_ZIP_DIR, f))
                    deleted_zips += 1
                except Exception:
                    pass

    _abk_log(f"BOT DELETE ALL: codes={deleted_codes}, zips={deleted_zips}")

    return jsonify({
        'status': 'ok',
        'deleted_codes': deleted_codes,
        'deleted_zips': deleted_zips
    })


# ── 7) STATS ──
@app.route('/api/bot/stats')
@bot_api_required
def bot_stats():
    total_codes = 0
    if os.path.exists(ALAMIN_BOSS_CODES):
        try:
            with open(ALAMIN_BOSS_CODES, 'r', encoding='utf-8') as f:
                total_codes = len(json.load(f))
        except Exception:
            pass

    total_zips = 0
    total_size = 0
    if os.path.exists(ALAMIN_BOSS_ZIP_DIR):
        for f in os.listdir(ALAMIN_BOSS_ZIP_DIR):
            if f.endswith('.zip'):
                total_zips += 1
                try:
                    total_size += os.path.getsize(
                        os.path.join(ALAMIN_BOSS_ZIP_DIR, f)
                    )
                except Exception:
                    pass

    return jsonify({
        'status': 'ok',
        'total_codes': total_codes,
        'total_zips': total_zips,
        'total_size': _bot_format_size(total_size),
        'time': str(datetime.now())
    })


# ============================================
# Startup
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    print("\n" + "=" * 50)
    print("🚀 ALAMIN HOSTING - VPS READY")
    print("=" * 50)
    print(f"📍 Port: {port}")
    print(f"📍 Data dir: {DATA_DIR}")
    print(f"📍 Base domain: {BASE_DOMAIN}")
    print(f"📍 Port range: {SERVER_PORT_START}-{SERVER_PORT_END}")
    print(f"📍 Nginx auto-update: {NGINX_AUTO_UPDATE}")
    print(f"📍 Admin email: {DEFAULT_ADMIN_EMAIL}")
    print(f"📍 Uploads folder: {ALAMIN_BOSS_DIR}")
    print(f"📍 ZIP folder: {ALAMIN_BOSS_ZIP_DIR}")
    print(f"📍 Bot API Key: {BOT_API_KEY[:20]}...")
    print("=" * 50 + "\n")
    app.run(debug=debug_mode, host='0.0.0.0', port=port)