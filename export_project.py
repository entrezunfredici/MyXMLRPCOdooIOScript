#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from project import Project

PROJECT_FILTER = {"type": "name", "value": "MyMemoMaster"}
TASK_FIELD_CANDIDATES = [
    'id', 'name', 'user_id', 'project_id', 'stage_id', 'priority', 'kanban_state',
    'description', 'tag_ids',
    'date_deadline', 'date_assign', 'date_start', 'date_end',
    'planned_hours', 'remaining_hours', 'progress',
    'planned_date_begin', 'planned_date_end',
    'create_date', 'write_date',
]
DEFAULTS = {
    'url': 'https://bleu-canard.odoo.com',
    'db': 'odoo',
    'user': 'superfred2468@gmail.com',
    'password': 'TON_MOT_DE_PASSE',
}


def main() -> None:
    try:
        project = Project(defaults=DEFAULTS)
    except RuntimeError as exc:
        print(exc)
        sys.exit(1)

    try:
        count = project.export_tasks(
            PROJECT_FILTER,
            task_field_candidates=TASK_FIELD_CANDIDATES,
            json_path='tasks.json',
            csv_path='tasks.csv',
        )
    except RuntimeError as exc:
        print(exc)
        sys.exit(1)

    print(f"Export OK: {count} taches -> tasks.json & tasks.csv")


if __name__ == "__main__":
    main()
