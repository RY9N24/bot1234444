import datetime as dt
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .data_manager import save_schedule_cache

SEARCH_URL = "https://lk.tolgas.ru/public-schedule/search/"


class ScheduleParser:
    @staticmethod
    def fetch_group_schedule(group: str) -> Optional[Dict[str, List[str]]]:
        """
        Parse weekly schedule for the given group.

        Returns mapping of date string -> list of lessons.
        """
        resp = requests.get(SEARCH_URL, params={"group": group}, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.find("table")
        if not table:
            return None

        schedule: Dict[str, List[str]] = {}
        for row in table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cols) < 2:
                continue
            date_label = cols[0]
            lessons = cols[1:]
            schedule.setdefault(date_label, []).extend(lessons)
        return schedule if schedule else None

    @staticmethod
    def refresh_cache(groups: List[str]) -> Dict[str, Dict[str, List[str]]]:
        cache: Dict[str, Dict[str, List[str]]] = {}
        for group in groups:
            parsed = ScheduleParser.fetch_group_schedule(group)
            if parsed:
                cache[group] = parsed
        save_schedule_cache(cache)
        return cache

    @staticmethod
    def load_or_fetch(group: str) -> Dict[str, List[str]]:
        from .data_manager import load_schedule_cache

        cache = load_schedule_cache()
        if group in cache:
            return cache[group]
        refreshed = ScheduleParser.refresh_cache([group])
        return refreshed.get(group, {})

    @staticmethod
    def format_schedule(group: str, schedule: Dict[str, List[str]], scope: str) -> str:
        if not schedule:
            return f"Расписание для {group} недоступно."

        today = dt.date.today()
        scope_label = "день" if scope == "day" else "неделя"
        lines = [f"📚 Расписание — {group} ({scope_label})"]
        for date_label, lessons in schedule.items():
            if scope == "day" and str(today.day) not in date_label and str(today) not in date_label:
                continue
            lines.append(f"\n📅 {date_label}")
            if not lessons:
                lines.append("• Выходной")
            else:
                for idx, lesson in enumerate(lessons, 1):
                    lines.append(f"{idx}) {lesson}")
            if scope == "day":
                break
        return "\n".join(lines)
