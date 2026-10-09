"""Search preferences in profile.json."""

import json

from jobsearch.store import load_json, read_json_arg, save_json, state_dir, today_str


def profile_path():
    return state_dir() / "profile.json"


def cmd_profile_show(_args):
    profile = load_json(profile_path(), {})
    print(json.dumps(profile, indent=2))


def cmd_profile_set(args):
    patch = read_json_arg(args.patch)
    profile = load_json(profile_path(), {})
    profile.update(patch)
    profile["updated"] = today_str()
    save_json(profile_path(), profile)
    print(json.dumps(profile, indent=2))
