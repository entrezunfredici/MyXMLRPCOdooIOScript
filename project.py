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
        updates_path: str = "tasks_to_update.json",
        allowed_fields: Optional[Iterable[str]] = None,
    ) -> Tuple[int, int]:
        raw_updates = json.loads(Path(updates_path).read_text(encoding="utf-8"))
        if isinstance(raw_updates, dict):
            tasks_section = raw_updates.get("tasks")
            if isinstance(tasks_section, list):
                update_items = tasks_section
            else:
                update_items = [raw_updates]
        elif isinstance(raw_updates, list):
            update_items = raw_updates
        else:
            raise RuntimeError("Invalid update payload: expected a list of task dicts or a dict containing a 'tasks' list.")

        allowed = list(allowed_fields or [
            "description",
            "date_deadline",
            "planned_date_begin",
            "planned_date_end",
            "date_planned_start",
            "date_planned_end",
            "date_start",
            "date_end",
            "planned_hours",
            "allocated_hours",
            "priority",
            "allow_billable",
            "milestone_id",
        ])

        field_metadata = self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            "project.task",
            "fields_get",
            [],
            {"attributes": ["type"]},
        )
        available_fields = set(field_metadata.keys())

        editable_fields, _ = self._resolve_fields("project.task", allowed, available_fields)
        editable_fields_set = set(editable_fields)

        create_candidates = list(dict.fromkeys(allowed + [
            "name",
            "project_id",
            "stage_id",
            "tag_ids",
            "parent_id",
        ]))
        creatable_fields, _ = self._resolve_fields("project.task", create_candidates, available_fields)
        creatable_fields_set = set(creatable_fields)

        default_project_ids: List[int] = []
        if isinstance(raw_updates, dict):
            meta = raw_updates.get("meta")
            if isinstance(meta, dict):
                project_ids = meta.get("project_ids")
                if isinstance(project_ids, list):
                    default_project_ids = [pid for pid in project_ids if isinstance(pid, int)]

        project_field = self._map_field_name("project.task", "project_id", available_fields)
        name_field = self._map_field_name("project.task", "name", available_fields) or "name"

        def normalize_value(field_name: str, value: Any) -> Any:
            if value is None:
                return None
            field_type = (field_metadata.get(field_name) or {}).get("type")
            if isinstance(value, bool):
                if value is False and field_type in {"many2many", "one2many"}:
                    return None
                return value
            if isinstance(value, (list, tuple)):
                if field_type == "many2one":
                    if not value:
                        return False
                    return value[0]
                if field_type in {"many2many", "one2many"}:
                    if not value:
                        return [(6, 0, [])]
                    if all(isinstance(v, int) for v in value):
                        ids = list(dict.fromkeys(value))
                        return [(6, 0, ids)]
                    extracted = [v[0] for v in value if isinstance(v, (list, tuple)) and v]
                    if extracted:
                        ids = list(dict.fromkeys(extracted))
                        return [(6, 0, ids)]
                    return None
            return value

        success, failure = 0, 0
        for index, item in enumerate(update_items, start=1):
            task_id = item.get("id")
            target_fields = editable_fields_set if task_id else creatable_fields_set
            values: Dict[str, Any] = {}
            for key, value in item.items():
                if key == "id":
                    continue
                mapped_key = self._map_field_name("project.task", key, available_fields)
                if not mapped_key or mapped_key not in target_fields:
                    continue
                normalized = normalize_value(mapped_key, value)
                if normalized is None:
                    continue
                values[mapped_key] = normalized

            if task_id:
                if not values:
                    continue
                try:
                    self.models.execute_kw(
                        self.db,
                        self.uid,
                        self.password,
                        "project.task",
                        "write",
                        [[task_id], values],
                    )
                    success += 1
                except Exception as exc:
                    print(f"KO update id={task_id}: {exc}")
                    failure += 1
                continue

            if name_field not in values or not values.get(name_field):
                raw_name = item.get("name")
                normalized_name = normalize_value(name_field, raw_name)
                if normalized_name:
                    values[name_field] = normalized_name

            if project_field and project_field not in values:
                raw_project = item.get("project_id")
                normalized_project = normalize_value(project_field, raw_project)
                if normalized_project is None and default_project_ids:
                    normalized_project = default_project_ids[0]
                if normalized_project:
                    values[project_field] = normalized_project

            if not values.get(name_field):
                failure += 1
                print(f"KO create missing name for task index={index} (payload keys: {sorted(item.keys())})")
                continue

            if project_field:
                project_value = values.get(project_field)
                if not project_value and default_project_ids:
                    values[project_field] = default_project_ids[0]
                    project_value = values[project_field]
                if not project_value:
                    failure += 1
                    print(f"KO create name={values.get(name_field)!r}: missing project_id")
                    continue

            try:
                created_id = self.models.execute_kw(
                    self.db,
                    self.uid,
                    self.password,
                    "project.task",
                    "create",
                    [values],
                )
                if isinstance(created_id, int):
                    success += 1
                else:
                    success += len(created_id or [])
            except Exception as exc:
                print(f"KO create name={values.get(name_field)!r}: {exc}")
                failure += 1

        return success, failure
