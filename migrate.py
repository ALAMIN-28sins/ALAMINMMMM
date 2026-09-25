import json
import os

DATA_DIR = os.environ.get('DATA_DIR', '/opt/alaminhosting')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

if not os.path.exists(USERS_FILE):
    print("❌ users.json not found!")
    exit(1)

with open(USERS_FILE, 'r', encoding='utf-8') as f:
    users = json.load(f)

changed = 0
for uname, data in users.items():
    if uname == 'admin':
        continue
    if 'plain_password' not in data:
        data['plain_password'] = 'RESET_NEEDED'
        changed += 1

with open(USERS_FILE, 'w', encoding='utf-8') as f:
    json.dump(users, f, indent=4, ensure_ascii=False)

print(f"✅ Migration complete! Updated {changed} users.")