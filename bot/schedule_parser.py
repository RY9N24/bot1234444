import datetime as dt
import logging
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .data_manager import save_schedule_cache

logger = logging.getLogger(__name__)

GROUP_URL = "https://lk.tolgas.ru/public-schedule/group"


class ScheduleParser:
    @staticmethod
    def fetch_group_schedule(group: str, start: Optional[dt.date] = None, end: Optional[dt.date] = None) -> Optional[Dict[str, List[str]]]:
        """Парсит расписание по прямой ссылке вида
        https://lk.tolgas.ru/public-schedule/group?id=<GROUP>&dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD"""

        start = start or dt.date.today()
        if end is None:
            end = start + dt.timedelta(days=6)
        params = {"id": group, "dateFrom": start.isoformat(), "dateTo": end.isoformat()}
        headers = {"User-Agent": "Mozilla/5.0 (schedule-bot)"}
        try:
            resp = requests.get(GROUP_URL, params=params, timeout=15, headers=headers)
            if resp.status_code != 200:
                logger.warning("Не удалось получить расписание для %s: %s", group, resp.status_code)
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as exc:  # pragma: no cover
            logger.exception("Ошибка при загрузке расписания для %s: %s", group, exc)
            return None

        table = soup.find("table") or soup.select_one("div table")
        if not table:
            logger.warning("Ответ без таблицы расписания для %s (url %s)", group, resp.url)
            return None

        schedule: Dict[str, List[str]] = {}
        for row in table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cols) < 2:
                continue
            date_label = cols[0]
            lessons = [c for c in cols[1:] if c]
            schedule.setdefault(date_label, []).extend(lessons)
        if schedule:
            logger.info(
                "Спарсили %s дней расписания для %s на период %s — %s",
                len(schedule),
                group,
                start.isoformat(),
                end.isoformat(),
            )
        return schedule if schedule else None

    @staticmethod
    def refresh_cache(groups: List[str]) -> Dict[str, Dict[str, List[str]]]:
        cache: Dict[str, Dict[str, List[str]]] = {}
        today = dt.date.today()
        # API страницы отдаёт неделю, которая начинается в воскресенье (пример: 2025-12-14..2025-12-20).
        # Вычисляем ближайшее прошедшее воскресенье как начало диапазона, чтобы таблица не была пустой.
        weekday = today.weekday()  # Mon=0 ... Sun=6
        offset = (weekday + 1) % 7  # Sun -> 0, Mon -> 1, Tue -> 2, ...
        start = today - dt.timedelta(days=offset)
        end = start + dt.timedelta(days=6)
        for group in groups:
            parsed = ScheduleParser.fetch_group_schedule(group, start=start, end=end)
            if parsed:
                cache[group] = parsed
        logger.info("Кеш расписаний обновлён для %s групп", len(cache))
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
            if scope == "day":
                today_label = today.strftime("%d.%m.%Y")
                if today_label not in date_label and str(today) not in date_label:
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
