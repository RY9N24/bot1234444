import json
import os
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


@contextmanager
def _atomic_write(path: str):
    with NamedTemporaryFile("w", delete=False, dir=os.path.dirname(path)) as tmp:
        temp_name = tmp.name
        yield tmp
    os.replace(temp_name, path)


def _ensure_file(path: str, default: Any):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)


def load_json(path: str, default: Any):
    _ensure_file(path, default)
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(path: str, data: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _atomic_write(path) as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)


USERS_FILE = os.path.join(DATA_DIR, "users.json")
PROFILES_FILE = os.path.join(DATA_DIR, "profiles.json")
REMINDERS_FILE = os.path.join(DATA_DIR, "reminders.json")
SCHEDULE_CACHE_FILE = os.path.join(DATA_DIR, "schedule_cache.json")


def add_user(user_id: int):
    users: List[int] = load_json(USERS_FILE, [])
    if user_id not in users:
        users.append(user_id)
        save_json(USERS_FILE, users)


def upsert_profile(profile: Dict[str, Any]):
    profiles: List[Dict[str, Any]] = load_json(PROFILES_FILE, [])
    existing = next((p for p in profiles if p.get("user_id") == profile.get("user_id")), None)
    if existing:
        existing.update(profile)
    else:
        profiles.append(profile)
    save_json(PROFILES_FILE, profiles)


def get_profile(user_id: int) -> Dict[str, Any] | None:
    profiles: List[Dict[str, Any]] = load_json(PROFILES_FILE, [])
    profile = next((p for p in profiles if p.get("user_id") == user_id), None)
    if profile is not None and "broadcast_times" not in profile:
        times = []
        if profile.get("broadcast_time"):
            times.append(profile["broadcast_time"])
        profile["broadcast_times"] = times
        upsert_profile(profile)
    return profile


def list_profiles() -> List[Dict[str, Any]]:
    return load_json(PROFILES_FILE, [])


def save_reminders(reminders: List[Dict[str, Any]]):
    save_json(REMINDERS_FILE, reminders)


def load_reminders() -> List[Dict[str, Any]]:
    return load_json(REMINDERS_FILE, [])


def save_schedule_cache(data: Dict[str, Any]):
    save_json(SCHEDULE_CACHE_FILE, data)


def load_schedule_cache() -> Dict[str, Any]:
    return load_json(SCHEDULE_CACHE_FILE, {})
