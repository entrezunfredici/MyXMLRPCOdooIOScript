#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from xmlrpc import client as xmlrpclib

MINIMUM_SUPPORTED_MAJOR = 18

FIELD_ALIASES: Dict[str, Dict[str, Tuple[str, ...]]] = {
    'project.task': {
        'planned_date_begin': ('date_planned_start',),
        'planned_date_end': ('date_planned_end',),
        'date_planned_start': ('planned_date_begin',),
        'date_planned_end': ('planned_date_end',),
        'allocated_hours': ('planned_hours',),
        'planned_hours': ('allocated_hours',),
    },
}


class Project:
    """Wrapper around the Odoo XML-RPC project API with shared helpers."""

    def __init__(self, env_path: str = ".env", defaults: Optional[Dict[str, str]] = None) -> None:
        self._load_env(env_path)
        defaults = defaults or {}

        self.url = os.getenv("ODOO_URL", defaults.get("url", "https://bleu-canard.odoo.com"))
        self.db = os.getenv("ODOO_DB", defaults.get("db", "odoo"))
        self.user = os.getenv("ODOO_USER", defaults.get("user", ""))
        self.password = os.getenv("ODOO_PASSWORD", defaults.get("password", ""))

        self.models = xmlrpclib.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
        self.common = xmlrpclib.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)

        version_data: Dict[str, Any] = self.common.version()
        self.server_serie: str = version_data.get("server_serie", "")
        server_version_info: Sequence[Any] = version_data.get("server_version_info") or ()
        self.server_version_info: Tuple[Any, ...] = tuple(server_version_info)
        try:
            self.server_major_version = int(self.server_version_info[0])
        except (ValueError, TypeError, IndexError):
            self.server_major_version = 0
        if self.server_major_version and self.server_major_version < MINIMUM_SUPPORTED_MAJOR:
            raise RuntimeError(
                f"Serveur Odoo non supporte: version {self.server_serie or self.server_version_info}. "
                f"La compatibilite ciblee est Odoo {MINIMUM_SUPPORTED_MAJOR}.x ou plus recent."
            )

        self.uid = self.common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise RuntimeError("Authentication failed; please check Odoo credentials.")

    @staticmethod
    def _load_env(path: str) -> None:
        env_path = Path(__file__).resolve().parent / path
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
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ.setdefault(key, value)

    def fields_available(self, model: str) -> List[str]:
        fields = self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            'fields_get',
            [],
            {'attributes': ['string', 'type']},
        )
        return list(fields.keys())

    def _map_field_name(self, model: str, field: str, available_fields: Set[str]) -> Optional[str]:
        if field in available_fields:
            return field
        model_aliases = FIELD_ALIASES.get(model, {})
        for alias in model_aliases.get(field, ()): 
            if alias in available_fields:
                return alias
        return None

    def _resolve_fields(
        self,
        model: str,
        candidates: Iterable[str],
        available_fields: Optional[Set[str]] = None,
    ) -> Tuple[List[str], Dict[str, str]]:
        available_fields = available_fields or set(self.fields_available(model))
        resolved: List[str] = []
        alias_usage: Dict[str, str] = {}
        seen: Set[str] = set()
        for field in candidates:
            mapped = self._map_field_name(model, field, available_fields)
            if not mapped or mapped in seen:
                continue
            resolved.append(mapped)
            seen.add(mapped)
            if mapped != field:
                alias_usage[field] = mapped
        return resolved, alias_usage

    def search_read(
        self,
        model: str,
        domain: Sequence,
        fields: Sequence[str],
        limit: int = 0,
    ) -> List[Dict[str, object]]:
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            'search_read',
            [list(domain)],
            {'fields': list(fields), 'limit': limit},
        )

    def export_tasks(
        self,
        project_filter: Dict[str, object],
        task_field_candidates: Optional[Iterable[str]] = None,
        json_path: str = 'tasks.json',
        csv_path: str = 'tasks.csv',
    ) -> int:
        candidates = list(task_field_candidates or []) or [
            'id', 'name', 'user_id', 'project_id', 'stage_id', 'task_type_id',
            'priority', 'kanban_state', 'kanban_state_label',
            'description', 'tag_ids', 'milestone_id', 'parent_id',
            'date_deadline', 'date_assign', 'date_start', 'date_end',
            'planned_hours', 'allocated_hours', 'remaining_hours', 'progress',
            'planned_date_begin', 'planned_date_end', 'date_planned_start', 'date_planned_end',
            'create_date', 'write_date',
        ]
        available_fields = set(self.fields_available('project.task'))
        task_fields, alias_usage = self._resolve_fields('project.task', candidates, available_fields)
        if not task_fields:
            raise RuntimeError("Aucun champ valide trouve pour l'export des taches.")

        proj_domain: List[Tuple[str, str, object]] = []
        if project_filter.get('type') == 'name':
            proj_domain = [('name', 'ilike', project_filter.get('value'))]
        elif project_filter.get('type') == 'id':
            proj_domain = [('id', '=', project_filter.get('value'))]

        projects = self.search_read(
            'project.project',
            proj_domain,
            ['id', 'name', 'partner_id', 'company_id', 'active'],
        )
        if not projects:
            raise RuntimeError(f"No project found for filter {project_filter}.")

        project_ids = [project['id'] for project in projects]
        tasks = self.search_read('project.task', [('project_id', 'in', project_ids)], task_fields)

        data = {
            'meta': {
                'exported_at': datetime.utcnow().isoformat() + 'Z',
                'odoo_url': self.url,
                'db': self.db,
                'server_serie': self.server_serie,
                'server_version_info': list(self.server_version_info),
                'field_aliases': alias_usage,
                'project_ids': project_ids,
                'task_fields': task_fields,
            },
            'projects': projects,
            'tasks': tasks,
        }
        Path(json_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

        with open(csv_path, 'w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=task_fields)
            writer.writeheader()
            for task in tasks:
                row = {}
                for field in task_fields:
                    value = task.get(field)
                    if isinstance(value, list):
                        row[field] = ','.join(map(str, value))
                    elif isinstance(value, tuple):
                        row[field] = value[0]
                    else:
                        row[field] = value
                writer.writerow(row)

        return len(tasks)

    def import_tasks(
        self,
        updates_path: str = 'tasks_to_update.json',
        allowed_fields: Optional[Iterable[str]] = None,
    ) -> Tuple[int, int]:
        update_data = json.loads(Path(updates_path).read_text(encoding='utf-8'))
        allowed = list(allowed_fields or [
            'description', 'date_deadline', 'planned_date_begin', 'planned_date_end',
            'date_planned_start', 'date_planned_end',
            'date_start', 'date_end', 'planned_hours', 'allocated_hours', 'priority',
        ])
        available_fields = set(self.fields_available('project.task'))
        editable_fields, _ = self._resolve_fields('project.task', allowed, available_fields)
        editable_fields_set = set(editable_fields)

        success, failure = 0, 0
        for item in update_data:
            task_id = item.get('id')
            if not task_id:
                failure += 1
                continue
            values = {
                mapped_key: value
                for key, value in item.items()
                if key != 'id'
                for mapped_key in [self._map_field_name('project.task', key, available_fields)]
                if mapped_key and mapped_key in editable_fields_set and value is not None
            }
            if not values:
                continue
            try:
                self.models.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    'project.task',
                    'write',
                    [[task_id], values],
                )
                success += 1
            except Exception as exc:
                print(f"KO id={task_id}: {exc}")
                failure += 1
        return success, failure
