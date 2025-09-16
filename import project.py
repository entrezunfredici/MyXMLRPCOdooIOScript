import json, os, sys
from pathlib import Path
from xmlrpc import client as xmlrpclib

def load_env(path=".env"):
    env_path = (Path(__file__).resolve().parent / path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if (len(value) >= 2) and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env()

URL = os.getenv("ODOO_URL", "https://bleu-canard.odoo.com")
DB = os.getenv("ODOO_DB", "odoo")
USER = os.getenv("ODOO_USER", "email@exemple.com")
PWD = os.getenv("ODOO_PASSWORD", "TON_MOT_DE_PASSE")

MODELS = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/object")
COMMON = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = COMMON.authenticate(DB, USER, PWD, {})
if not uid:
    print("Auth echouee"); sys.exit(1)

def fields_available(model):
    fg = MODELS.execute_kw(DB, uid, PWD, model, 'fields_get', [], {'attributes':['string','type']})
    return set(fg.keys())

avail = fields_available('project.task')

with open('tasks_to_update.json','r',encoding='utf-8') as f:
    updates = json.load(f)

allowed = {'description','date_deadline','planned_date_begin','planned_date_end','date_start','date_end','planned_hours','priority'}
allowed = allowed.intersection(avail)

ok, ko = 0, 0
for item in updates:
    tid = item.get('id')
    if not tid:
        ko += 1
        continue
    vals = {k:v for k,v in item.items() if k in allowed and v is not None}
    if not vals:
        continue
    try:
        MODELS.execute_kw(DB, uid, PWD, 'project.task', 'write', [[tid], vals])
        ok += 1
    except Exception as e:
        print(f"KO id={tid}: {e}")
        ko += 1

print(f"MAJ terminee: OK={ok} KO={ko}")
