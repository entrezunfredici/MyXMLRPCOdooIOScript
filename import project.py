#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from project import Project

DEFAULTS = {
    'url': 'https://bleu-canard.odoo.com',
    'db': 'odoo',
    'user': 'email@exemple.com',
    'password': 'TON_MOT_DE_PASSE',
}
ALLOWED_FIELDS = {
    'description', 'date_deadline', 'planned_date_begin', 'planned_date_end',
    'date_planned_start', 'date_planned_end',
    'date_start', 'date_end', 'planned_hours', 'allocated_hours', 'priority',
    'allow_billable', 'milestone_id',
}


def main() -> None:
    try:
        project = Project(defaults=DEFAULTS)
    except RuntimeError as exc:
        print(exc)
        sys.exit(1)

    ok, ko = project.import_tasks(
        updates_path='tasks_to_update.json',
        allowed_fields=ALLOWED_FIELDS,
    )
    print(f"MAJ terminee: OK={ok} KO={ko}")


if __name__ == "__main__":
    main()
