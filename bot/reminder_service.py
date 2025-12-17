import datetime as dt
import logging
from typing import Dict, List, Optional

import pytz
from dateutil import parser

from .data_manager import load_reminders, save_reminders
from .weather_currency import utc_now


logger = logging.getLogger(__name__)


class ReminderService:
    @staticmethod
    def add_reminder(entry: Dict):
        reminders = load_reminders()
        reminders.append(entry)
        save_reminders(reminders)
        logger.info("Сохранено напоминание id=%s для пользователя=%s", entry.get("id"), entry.get("user_id"))

    @staticmethod
    def replace_reminders(reminders: List[Dict]):
        save_reminders(reminders)

    @staticmethod
    def due_reminders(now: dt.datetime) -> List[Dict]:
        reminders = load_reminders()
        return [r for r in reminders if parser.isoparse(r["send_at_utc"]) <= now]

    @staticmethod
    def remove(ids: List[str]):
        reminders = load_reminders()
        filtered = [r for r in reminders if r.get("id") not in ids]
        save_reminders(filtered)

    @staticmethod
    def list_for_user(user_id: int) -> List[Dict]:
        return [r for r in load_reminders() if r.get("user_id") == user_id]

    @staticmethod
    def build_send_time(city_tz: str, target_dt_str: str) -> Optional[dt.datetime]:
        try:
            tz = pytz.timezone(city_tz)
        except Exception:
            return None
        local_dt = parser.parse(target_dt_str)
        if local_dt.tzinfo is None:
            local_dt = tz.localize(local_dt)
        else:
            local_dt = local_dt.astimezone(tz)
        return local_dt.astimezone(dt.timezone.utc)

    @staticmethod
    async def purge_and_reschedule(job_queue, bot):
        now = utc_now()
        overdue = ReminderService.due_reminders(now)
        if overdue:
            ReminderService.remove([r["id"] for r in overdue])
        for rem in overdue:
            await bot.send_message(
                chat_id=rem["user_id"],
                text=f"{rem['message']}\n\nСообщение отправлено с задержкой по техническим причинам.",
            )
        if overdue:
            logger.info("Отправлено просроченных напоминаний: %s", len(overdue))

    @staticmethod
    async def schedule_all(job_queue, bot):
        reminders = load_reminders()
        now = utc_now()
        overdue_ids: List[str] = []

        for rem in reminders:
            send_at = parser.isoparse(rem["send_at_utc"])
            if send_at <= now:
                overdue_ids.append(rem["id"])
                await bot.send_message(
                    chat_id=rem["user_id"],
                    text=f"{rem['message']}\n\nСообщение отправлено с задержкой по техническим причинам.",
                )
                logger.info("Просроченное напоминание отправлено id=%s", rem["id"])
            else:
                job_queue.run_once(
                    ReminderService._send_job,
                    when=send_at,
                    name=f"reminder-{rem['id']}",
                    data={"user_id": rem["user_id"], "message": rem["message"]},
                )
                logger.info("Напоминание %s запланировано на %s", rem["id"], send_at.isoformat())

        if overdue_ids:
            ReminderService.remove(overdue_ids)
            logger.info("Удалены просроченные напоминания: %s", ", ".join(overdue_ids))

    @staticmethod
    async def _send_job(ctx):
        await ctx.bot.send_message(chat_id=ctx.job.data["user_id"], text=ctx.job.data["message"])
        logger.info("Отправлено напоминание job=%s пользователю=%s", ctx.job.name, ctx.job.data.get("user_id"))
