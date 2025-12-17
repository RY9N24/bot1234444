import asyncio
import datetime as dt
import uuid
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import data_manager
from .groups import CANONICAL_GROUPS, VALID_GROUPS
from .reminder_service import ReminderService
from .schedule_parser import ScheduleParser
from .weather_currency import CurrencyService, WeatherService

GROUP_STATE, CITY_STATE, BROADCAST_TIME_STATE, BROADCAST_SCOPE_STATE, REM_TEXT_STATE, REM_DATE_STATE, REM_TIME_STATE = range(7)


class NotificationBot:
    def __init__(self, token: str):
        self.application = (
            ApplicationBuilder()
            .token(token)
            .rate_limiter(AIORateLimiter())
            .concurrent_updates(True)
            .post_init(self._post_init)
            .build()
        )
        self._last_schedule_refresh: dt.datetime | None = None
        self._register_handlers()

    def _register_handlers(self):
        app = self.application
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("menu", self.start))
        app.add_handler(CommandHandler("profile", self.profile))
        app.add_handler(CommandHandler("broadcast", self.broadcast_settings))
        app.add_handler(CommandHandler("reminder", self.reminder_menu))
        app.add_handler(CommandHandler("help", self.help))

        app.add_handler(CallbackQueryHandler(self.broadcast_now, pattern="^broadcast_now"))

        app.add_handler(ConversationHandler(
            entry_points=[
                CommandHandler("setgroup", self.ask_group),
                MessageHandler(filters.Regex("^👥 Выбрать группу$"), self.ask_group),
            ],
            states={
                GROUP_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_group)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        ))

        app.add_handler(ConversationHandler(
            entry_points=[
                CommandHandler("setcity", self.ask_city),
                MessageHandler(filters.Regex("^📍 Выбрать город$"), self.ask_city),
            ],
            states={
                CITY_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_city)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        ))

        app.add_handler(ConversationHandler(
            entry_points=[
                CommandHandler("setbroadcast", self.ask_broadcast_time),
                MessageHandler(filters.Regex("^⏰ Время рассылки$"), self.ask_broadcast_time),
            ],
            states={
                BROADCAST_TIME_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_broadcast_time)],
                BROADCAST_SCOPE_STATE: [CallbackQueryHandler(self.save_broadcast_scope)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        ))

        app.add_handler(ConversationHandler(
            entry_points=[
                CommandHandler("new_reminder", self.reminder_text),
                MessageHandler(filters.Regex("^🔔 Напоминание$"), self.reminder_text),
            ],
            states={
                REM_TEXT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.reminder_pick_date)],
                REM_DATE_STATE: [CallbackQueryHandler(self.reminder_pick_time)],
                REM_TIME_STATE: [CallbackQueryHandler(self.reminder_adjust_time), MessageHandler(filters.TEXT & ~filters.COMMAND, self.reminder_manual_time)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        ))

        app.add_handler(CallbackQueryHandler(self.handle_reminder_action, pattern="^reminder_action"))
        app.add_handler(MessageHandler(filters.Regex("^🚀 Сообщение сейчас$"), self.broadcast_now_message))
        app.add_handler(MessageHandler(filters.Regex("^ℹ️ Профиль$"), self.profile))

    @staticmethod
    def _main_menu():
        return ReplyKeyboardMarkup(
            [
                ["📍 Выбрать город", "👥 Выбрать группу"],
                ["⏰ Время рассылки", "🚀 Сообщение сейчас"],
                ["🔔 Напоминание", "ℹ️ Профиль"],
            ],
            resize_keyboard=True,
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        data_manager.add_user(user.id)
        profile = data_manager.get_profile(user.id) or {
            "user_id": user.id,
            "username": user.username,
            "city": None,
            "timezone": None,
            "group": None,
            "broadcast_time": None,
            "broadcast_scope": "day",
        }
        data_manager.upsert_profile(profile)
        text = (
            "👋 Добро пожаловать! Все основные действия доступны на кнопках ниже.\n\n"
            "• 📍 Город — выбрать город и часовой пояс\n"
            "• 👥 Группа — указать учебную группу\n"
            "• ⏰ Время рассылки — настроить ежедневное сообщение\n"
            "• 🔔 Напоминание — создать или просмотреть личные напоминания\n"
            "• 🚀 Сообщение сейчас — получить итоговое сообщение в любой момент\n"
            "• ℹ️ Профиль — увидеть текущие настройки"
        )
        await update.message.reply_text(text, reply_markup=self._main_menu())

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Доступные команды: /profile /setcity /setgroup /setbroadcast /reminder /menu",
            reply_markup=self._main_menu(),
        )

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        profile = data_manager.get_profile(update.effective_user.id)
        if not profile:
            await update.message.reply_text("Профиль не найден. Выполните /start")
            return
        text = (
            "ℹ️ Профиль\n"
            f"ID: {profile['user_id']}\n"
            f"Ник: @{profile.get('username')}\n"
            f"Город: {profile.get('city')}\n"
            f"Часовой пояс: {profile.get('timezone')}\n"
            f"Группа: {profile.get('group')}\n"
            f"Время рассылки: {profile.get('broadcast_time')} ({profile.get('broadcast_scope')})"
        )
        await update.message.reply_text(text, reply_markup=self._main_menu())

    async def ask_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👥 Укажите вашу группу (например, БРБ24). Я сверю её с официальным списком.",
            reply_markup=self._main_menu(),
        )
        return GROUP_STATE

    async def save_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        group_raw = update.message.text.strip().lower()
        canonical = CANONICAL_GROUPS.get(group_raw)
        if not canonical:
            await update.message.reply_text(
                "⚠️ Группа не найдена. Попробуйте снова или проверьте регистр — я принимаю БРБ24/брб24 и другие варианты.",
                reply_markup=self._main_menu(),
            )
            return ConversationHandler.END
        profile = data_manager.get_profile(update.effective_user.id) or {"user_id": update.effective_user.id, "username": update.effective_user.username}
        profile.update({"group": canonical})
        data_manager.upsert_profile(profile)
        await update.message.reply_text(
            f"✅ Группа сохранена: {canonical}",
            reply_markup=self._main_menu(),
        )
        return ConversationHandler.END

    async def ask_city(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📍 Напишите город проживания — я подберу часовой пояс автоматически.",
            reply_markup=self._main_menu(),
        )
        return CITY_STATE

    async def save_city(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        city = update.message.text.strip()
        geo = WeatherService.geocode(city)
        if not geo:
            await update.message.reply_text(
                "⚠️ Город не найден, попробуйте ещё раз. Убедитесь, что указали корректное название.",
                reply_markup=self._main_menu(),
            )
            return ConversationHandler.END
        profile = data_manager.get_profile(update.effective_user.id) or {"user_id": update.effective_user.id, "username": update.effective_user.username}
        profile.update({"city": geo.city, "timezone": geo.timezone})
        data_manager.upsert_profile(profile)
        await update.message.reply_text(
            f"✅ Город сохранён: {geo.city}\n🕑 Часовой пояс: {geo.timezone}",
            reply_markup=self._main_menu(),
        )
        return ConversationHandler.END

    async def ask_broadcast_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "⏰ Укажите время рассылки в формате ЧЧ:ММ (ваш часовой пояс).",
            reply_markup=self._main_menu(),
        )
        return BROADCAST_TIME_STATE

    async def save_broadcast_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        time_str = update.message.text.strip()
        try:
            dt.time.fromisoformat(time_str)
        except ValueError:
            await update.message.reply_text(
                "⚠️ Неверный формат времени. Используйте ЧЧ:ММ, например 08:30.",
                reply_markup=self._main_menu(),
            )
            return BROADCAST_TIME_STATE
        context.user_data["broadcast_time"] = time_str
        keyboard = [[InlineKeyboardButton("День", callback_data="scope_day"), InlineKeyboardButton("Неделя", callback_data="scope_week")]]
        await update.message.reply_text(
            "Выберите охват расписания:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return BROADCAST_SCOPE_STATE

    async def save_broadcast_scope(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        scope = "day" if query.data.endswith("day") else "week"
        time_str = context.user_data.get("broadcast_time")
        profile = data_manager.get_profile(query.from_user.id) or {"user_id": query.from_user.id, "username": query.from_user.username}
        profile.update({"broadcast_time": time_str, "broadcast_scope": scope})
        data_manager.upsert_profile(profile)
        scope_label = "день" if scope == "day" else "неделя"
        await query.edit_message_text(f"✅ Время рассылки: {time_str}\n📅 Охват: {scope_label}")
        self._schedule_broadcast_job(profile)
        return ConversationHandler.END

    async def reminder_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        reminders = ReminderService.list_for_user(update.effective_user.id)
        lines = ["🔔 Ваши напоминания:"]
        for r in reminders:
            lines.append(f"• {r['message']} — {r['send_at_local']}")
        if len(lines) == 1:
            lines.append("Пока нет активных напоминаний.")
        keyboard = [[InlineKeyboardButton("Создать напоминание", callback_data="reminder_action_new")]]
        await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_reminder_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data.endswith("new"):
            await query.edit_message_text("Напишите сообщение, которое хотите увидеть позже:")
            context.user_data["from_button"] = True
            return REM_TEXT_STATE
        return ConversationHandler.END

    async def reminder_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Напишите сообщение, которое хотите увидеть позже:")
        return REM_TEXT_STATE

    async def reminder_pick_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["rem_text"] = update.message.text
        today = dt.date.today()
        buttons = []
        for i in range(14):
            target = today + dt.timedelta(days=i)
            buttons.append([InlineKeyboardButton(target.strftime("%d.%m.%Y"), callback_data=f"date_{target.isoformat()}")])
        await update.message.reply_text("📅 Выберите день для напоминания:", reply_markup=InlineKeyboardMarkup(buttons))
        return REM_DATE_STATE

    async def reminder_pick_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        date_iso = query.data.split("_")[1]
        context.user_data["rem_date"] = date_iso
        now = dt.datetime.now()
        time_label = now.strftime("%H:%M")
        keyboard = [
            [
                InlineKeyboardButton("+30 мин", callback_data=f"time_add_{date_iso}_30"),
                InlineKeyboardButton("+5 мин", callback_data=f"time_add_{date_iso}_5"),
            ],
            [
                InlineKeyboardButton("-30 мин", callback_data=f"time_sub_{date_iso}_30"),
                InlineKeyboardButton("-5 мин", callback_data=f"time_sub_{date_iso}_5"),
            ],
            [InlineKeyboardButton("Указать вручную", callback_data=f"time_manual_{date_iso}")],
        ]
        await query.edit_message_text(
            f"⏱ Сейчас (по серверу): {time_label}\nВыберите корректировку или укажите вручную.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        context.user_data["rem_time"] = time_label
        return REM_TIME_STATE

    async def reminder_adjust_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.split("_")
        action = parts[1]
        date_iso = parts[2]
        if action == "manual":
            await query.edit_message_text("Укажите время в формате ЧЧ:ММ")
            context.user_data["rem_date"] = date_iso
            return REM_TIME_STATE
        delta_minutes = int(parts[3])
        current_time = dt.datetime.combine(dt.date.fromisoformat(date_iso), dt.datetime.strptime(context.user_data.get("rem_time", "00:00"), "%H:%M").time())
        if action == "add":
            new_dt = current_time + dt.timedelta(minutes=delta_minutes)
        else:
            new_dt = current_time - dt.timedelta(minutes=delta_minutes)
        context.user_data["rem_time"] = new_dt.strftime("%H:%M")
        await query.edit_message_text(f"Выбрано время: {context.user_data['rem_time']}")
        await self._finalize_reminder(query.from_user.id, context)
        return ConversationHandler.END

    async def reminder_manual_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        time_str = update.message.text.strip()
        try:
            dt.time.fromisoformat(time_str)
        except ValueError:
            await update.message.reply_text("Неверный формат времени. Попробуйте снова.")
            return REM_TIME_STATE
        context.user_data["rem_time"] = time_str
        await self._finalize_reminder(update.effective_user.id, context)
        return ConversationHandler.END

    async def _finalize_reminder(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        profile = data_manager.get_profile(user_id)
        if not profile or not profile.get("timezone"):
            await context.bot.send_message(chat_id=user_id, text="Укажите город для определения часового пояса: /setcity")
            return
        text = context.user_data.get("rem_text")
        date_iso = context.user_data.get("rem_date")
        time_str = context.user_data.get("rem_time")
        local_str = f"{date_iso} {time_str}"
        send_at_utc = ReminderService.build_send_time(profile["timezone"], local_str)
        if not send_at_utc:
            await context.bot.send_message(chat_id=user_id, text="Не удалось вычислить время отправки. Проверьте данные.")
            return
        if send_at_utc <= dt.datetime.now(dt.timezone.utc):
            await context.bot.send_message(chat_id=user_id, text="Нельзя указать прошедшее время. Попробуйте снова.")
            return
        entry = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "message": text,
            "send_at_local": local_str,
            "send_at_utc": send_at_utc.isoformat(),
        }
        ReminderService.add_reminder(entry)
        context.job_queue.run_once(
            ReminderService._send_job,
            when=send_at_utc,
            name=f"reminder-{entry['id']}",
            data={"user_id": user_id, "message": text},
        )
        await context.bot.send_message(chat_id=user_id, text="✅ Сообщение сохранено и ожидает отправки")

    async def broadcast_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [[InlineKeyboardButton("Сообщение сейчас", callback_data="broadcast_now")]]
        await update.message.reply_text(
            "🚀 Быстрый доступ:\n• Установите время рассылки через кнопку ниже.\n• Или запросите сообщение прямо сейчас.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def broadcast_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        profile = data_manager.get_profile(query.from_user.id)
        if not profile:
            await query.edit_message_text("Профиль не найден. Выполните /start")
            return
        messages = await self._prepare_broadcast_messages(profile)
        if not messages:
            await query.edit_message_text("Недостаточно данных для сообщения. Укажите город или группу.")
            return
        await query.edit_message_text("Сообщение отправляется...")
        await context.bot.send_message(chat_id=query.from_user.id, text="\n\n".join(messages))

    async def broadcast_now_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        profile = data_manager.get_profile(update.effective_user.id)
        if not profile:
            await update.message.reply_text("Профиль не найден. Выполните /start", reply_markup=self._main_menu())
            return
        messages = await self._prepare_broadcast_messages(profile)
        if not messages:
            await update.message.reply_text(
                "Недостаточно данных для сообщения. Укажите город или группу.",
                reply_markup=self._main_menu(),
            )
            return
        await update.message.reply_text("\n\n".join(messages), reply_markup=self._main_menu())

    def _schedule_broadcast_job(self, profile):
        time_str = profile.get("broadcast_time")
        tz_name = profile.get("timezone")
        if not time_str or not tz_name:
            return
        hour, minute = map(int, time_str.split(":"))
        tzinfo = ZoneInfo(tz_name)
        self.application.job_queue.run_daily(
            self._broadcast_job,
            time=dt.time(hour=hour, minute=minute, tzinfo=tzinfo),
            name=f"broadcast-{profile['user_id']}",
            data={"user_id": profile["user_id"]},
        )

    async def _broadcast_job(self, context: ContextTypes.DEFAULT_TYPE):
        user_id = context.job.data["user_id"]
        profile = data_manager.get_profile(user_id)
        if not profile:
            return
        messages = await self._prepare_broadcast_messages(profile)
        if not messages:
            return
        await context.bot.send_message(chat_id=user_id, text="\n\n".join(messages))

    async def _ensure_schedule_cache(self):
        now = dt.datetime.now(dt.timezone.utc)
        if self._last_schedule_refresh and (now - self._last_schedule_refresh).total_seconds() < 3600:
            return
        profiles = data_manager.list_profiles()
        groups = {p.get("group") for p in profiles if p.get("group")}
        if groups:
            ScheduleParser.refresh_cache(list(groups))
            self._last_schedule_refresh = now

    async def _prepare_broadcast_messages(self, profile: dict[str, str | int | None]):
        await self._ensure_schedule_cache()
        messages = []
        geo = None
        if profile.get("city"):
            geo = WeatherService.geocode(profile["city"])
            if geo:
                now_descr, today_summary = WeatherService.fetch_weather(geo)
                messages.append(
                    "\n".join(
                        [
                            f"🌦 Погода — {geo.city}",
                            now_descr,
                            f"📈 {today_summary}",
                        ]
                    )
                )
        messages.append(CurrencyService.fetch_currency())
        group = profile.get("group")
        scope = profile.get("broadcast_scope", "day")
        if group:
            schedule = ScheduleParser.load_or_fetch(group)
            messages.append(ScheduleParser.format_schedule(group, schedule, scope))
        return [m for m in messages if m]

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Операция отменена", reply_markup=self._main_menu())
        return ConversationHandler.END

    async def _post_init(self, app: Application):
        await self.load_jobs()

    async def load_jobs(self):
        # schedule overdue reminders and broadcasts
        for profile in data_manager.list_profiles():
            if profile.get("broadcast_time") and profile.get("timezone"):
                self._schedule_broadcast_job(profile)
        await ReminderService.schedule_all(self.application.job_queue, self.application.bot)

    def run(self):
        self.application.run_polling()


def build_app(token: str) -> NotificationBot:
    return NotificationBot(token)


def main():
    import os

    token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "TELEGRAM_TOKEN.txt")
    with open(token_path, "r", encoding="utf-8") as f:
        token = f.read().strip()
    bot = NotificationBot(token)
    bot.run()


if __name__ == "__main__":
    main()
