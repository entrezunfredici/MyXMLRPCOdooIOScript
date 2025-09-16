
import json, sys
from xmlrpc import client as xmlrpclib

URL = "https://bleu-canard.odoo.com"
DB = "odoo"
USER = "email@exemple.com"
PWD = "TON_MOT_DE_PASSE"

MODELS = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/object")
COMMON = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = COMMON.authenticate(DB, USER, PWD, {})
if not uid:
    print("Auth échouée"); sys.exit(1)

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
        ko += 1; 
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

print(f"MAJ terminée: OK={ok} KO={ko}")
