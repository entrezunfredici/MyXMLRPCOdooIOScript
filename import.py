#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, json, sys
from datetime import datetime
from xmlrpc import client as xmlrpclib

URL = "https://TON_ODOO_URL"   # ex: "https://odoo.mondomaine.com"
DB = "NOM_DE_TA_DB"
USER = "email@exemple.com"
PWD = "TON_MOT_DE_PASSE"

PROJECT_FILTER = {"type": "name", "value": "MyMemoMaster"}  # ou {"type":"id","value":123}

MODELS = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/object")
COMMON = xmlrpclib.ServerProxy(f"{URL}/xmlrpc/2/common")

uid = COMMON.authenticate(DB, USER, PWD, {})
if not uid:
    print("Auth échouée"); sys.exit(1)

def fields_available(model):
    fg = MODELS.execute_kw(DB, uid, PWD, model, 'fields_get', [], {'attributes':['string','type']})
    return set(fg.keys())

def sr(model, domain, fields, limit=0):
    return MODELS.execute_kw(DB, uid, PWD, model, 'search_read', [domain], {'fields':fields, 'limit':limit})

# Champs potentiels utiles (on filtrera selon disponibilité réelle)
task_field_candidates = [
    'id','name','user_id','project_id','stage_id','priority','kanban_state',
    'description','tag_ids',
    'date_deadline','date_assign','date_start','date_end',
    'planned_hours','remaining_hours','progress',
    'planned_date_begin','planned_date_end',            # ≥ v14+
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
    print("Aucun projet trouvé pour le filtre:", PROJECT_FILTER); sys.exit(1)

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
        # Aplatissement léger
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

print(f"Export OK: {len(tasks)} tâches -> tasks.json & tasks.csv")
