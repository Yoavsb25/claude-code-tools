"""State directory and JSON helpers for ~/job-search-data (override with JOB_SEARCH_DIR)."""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path


def state_dir():
    d = Path(os.environ.get("JOB_SEARCH_DIR", "~/job-search-data")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp_path, path)


def read_json_arg(arg):
    raw = sys.stdin.read() if arg == "-" else arg
    return json.loads(raw)


def today_str():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None
