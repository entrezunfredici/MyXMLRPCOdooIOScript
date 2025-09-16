#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, json, os, sys
from datetime import datetime
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

URL = os.getenv("ODOO_URL", "https://bleu-canard.odoo.com")   # ex: "https://odoo.mondomaine.com"
DB = os.getenv("ODOO_DB", "odoo")
USER = os.getenv("ODOO_USER", "superfred2468@gmail.com")
PWD = os.getenv("ODOO_PASSWORD", "TON_MOT_DE_PASSE")

PROJECT_FILTER = {"type": "name", "value": "MyMemoMaster"}  # ou {"type":"id","value":123}

MODELS = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/object")
COMMON = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/common")

uid = COMMON.authenticate(DB, USER, PWD, {})
if not uid:
    print("Auth echouee"); sys.exit(1)


def fields_available(model):
    fg = MODELS.execute_kw(DB, uid, PWD, model, 'fields_get', [], {'attributes':['string','type']})
    return set(fg.keys())


def sr(model, domain, fields, limit=0):
    return MODELS.execute_kw(DB, uid, PWD, model, 'search_read', [domain], {'fields':fields, 'limit':limit})


task_field_candidates = [
    'id','name','user_id','project_id','stage_id','priority','kanban_state',
    'description','tag_ids',
    'date_deadline','date_assign','date_start','date_end',
    'planned_hours','remaining_hours','progress',
    'planned_date_begin','planned_date_end',
    'create_date','write_date'
]


proj_fields = ['id','name','partner_id','company_id','active']
available_task_fields = list(fields_available('project.task').intersection(task_field_candidates))

# 1) Trouver le projet
proj_domain = []
if PROJECT_FILTER["type"] == "name":
    proj_domain = [('name','ilike', PROJECT_FILTER["value"])]
elif PROJECT_FILTER["type"] == "id":
    proj_domain = [('id','=', PROJECT_FILTER["value"])]

projects = sr('project.project', proj_domain, proj_fields)
if not projects:
    print("Aucun projet trouve pour le filtre:", PROJECT_FILTER); sys.exit(1)

project_ids = [p['id'] for p in projects]
tasks = sr('project.task', [('project_id','in', project_ids)], available_task_fields)

# 2) Export JSON
with open('tasks.json','w',encoding='utf-8') as f:
    json.dump({
        'meta': {
            'exported_at': datetime.utcnow().isoformat()+'Z',
            'odoo_url': URL,
            'db': DB,
            'project_ids': project_ids,
            'task_fields': available_task_fields,
        },
        'projects': projects,
        'tasks': tasks
    }, f, ensure_ascii=False, indent=2)

# 3) Export CSV
csv_fields = available_task_fields
with open('tasks.csv','w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=csv_fields)
    w.writeheader()
    for t in tasks:
        # Aplatissement leger
        row = {}
        for k in csv_fields:
            v = t.get(k)
            if isinstance(v, list):
                # tag_ids etc.
                row[k] = ",".join(map(str, v))
            elif isinstance(v, tuple):
                row[k] = v[0]
            else:
                row[k] = v
        w.writerow(row)

print(f"Export OK: {len(tasks)} taches -> tasks.json & tasks.csv")
