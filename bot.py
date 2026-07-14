"""
ActivityMap Bot — Main entry point
Telegram-бот для валидации MVP: поиск людей для совместных активностей

Запуск:
    python bot.py

Переменные окружения (.env):
    BOT_TOKEN=токен_от_BotFather
    ADMIN_ID=твой_telegram_id (для уведомлений об ошибках)
"""
import logging
import os
import asyncio
from datetime import datetime

from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, BotCommand, MenuButtonWebApp, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

import database as db
import keyboards as kb
import messages as msg

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
_admin_raw = os.getenv("ADMIN_ID", "0")
ADMIN_ID    = int(_admin_raw) if _admin_raw.lstrip("-").isdigit() else 0
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://activemap-production.up.railway.app/")  # URL Mini App

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env файле!")

# ── Состояния ConversationHandler ────────────────────────────

# Регистрация
(REG_NAME, REG_AGE, REG_CITY) = range(3)

# Создание метки
(POST_CATEGORY, POST_DESCRIPTION, POST_TIME, POST_TIME_CUSTOM, POST_CITY_CONFIRM) = range(10, 15)

# Смена города
(CITY_INPUT,) = range(20, 21)


# ── Вспомогательные функции ──────────────────────────────────

async def send(update: Update, text: str, **kwargs):
    """Отправить ответ независимо от типа апдейта."""
    kwargs.setdefault("parse_mode", ParseMode.MARKDOWN)
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    elif update.message:
        await update.message.reply_text(text, **kwargs)


def time_label(code: str) -> str:
    now = datetime.now()
    if code == "now":
        return f"прямо сейчас (~{now.strftime('%H:%M')})"
    if code == "1h":
        h = (now.hour + 1) % 24
        return f"~{h:02d}:{now.minute:02d}"
    if code == "2h":
        h = (now.hour + 2) % 24
        return f"~{h:02d}:{now.minute:02d}"
    if code == "evening":
        return "сегодня вечером"
    return code


# ── /start — регистрация ─────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    existing = db.get_user(user.id)
    # Сохраняем/обновляем username (конфиденциально, только в нашей БД)
    if existing:
                db.update_username(user.id, user.username)

    if existing and not ctx.args:
        kb_open = InlineKeyboardMarkup([[InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=MINIAPP_URL))]]) if MINIAPP_URL else None
        await send(update, msg.profile_saved(
            existing["name"], existing["age"], existing["city"]
        ), reply_markup=kb_open)
        return ConversationHandler.END
    await send(update, msg.welcome(user.first_name or "друг"))
        return REG_NAME


async def reg_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 40:
        await send(update, "⚠️ Имя должно быть от 2 до 40 символов. Попробуй ещё раз:")
        return REG_NAME
    ctx.user_data["reg_name"] = name
    await send(update, msg.ask_age())
    return REG_AGE


async def reg_age(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        age = int(update.message.text.strip())
        assert 18 <= age <= 80
    except (ValueError, AssertionError):
        await send(update, msg.error_age())
        return REG_AGE
    ctx.user_data["reg_age"] = age
    await send(update, msg.ask_city())
    return REG_CITY


async def reg_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text.strip().title()
    user = update.effective_user
    db.upsert_user(
        tg_id    = user.id,
        username = user.username,
        name     = ctx.user_data["reg_name"],
        age      = ctx.user_data["reg_age"],
        city     = city,
    )
        kb_open = InlineKeyboardMarkup([[InlineKeyboardButton("🗺 Открыть карту", web_app=WebAppInfo(url=MINIAPP_URL))]]) if MINIAPP_URL else None
        await send(update, msg.profile_saved(
            ctx.user_data["reg_name"], ctx.user_data["reg_age"], city
        ), reply_markup=kb_open)
        ctx.user_data.clear()   
        return ConversationHandler.END


# ── /post — создание метки ───────────────────────────────────

async def cmd_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user_row = db.get_user(update.effective_user.id)
    if not user_row:
        await send(update, msg.not_registered())
        return ConversationHandler.END

    if user_row["is_banned"]:
        await send(update, "🚫 Твой аккаунт заблокирован.")
        return ConversationHandler.END

    existing = db.get_active_activity(update.effective_user.id)
    if existing:
        await send(update, msg.already_has_activity())
        return ConversationHandler.END

    ctx.user_data["post_city"] = user_row["city"]
    await send(update, msg.ask_category(), reply_markup=kb.kb_categories())
    return POST_CATEGORY


async def post_category_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category = query.data.split(":")[1]
    ctx.user_data["post_category"] = category
    await query.edit_message_text(
        f"Категория: {db.CATEGORIES[category][0]} *{db.CATEGORIES[category][1]}*\n\n"
        + msg.ask_description(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_DESCRIPTION


async def post_description(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == "/skip":
        ctx.user_data["post_description"] = ""
    else:
        desc = update.message.text.strip()[:200]
        ctx.user_data["post_description"] = desc
    await send(update, msg.ask_time(), reply_markup=kb.kb_time())
    return POST_TIME


async def post_time_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    code = query.data.split(":")[1]

    if code == "custom":
        await query.edit_message_text(msg.ask_custom_time(), parse_mode=ParseMode.MARKDOWN)
        return POST_TIME_CUSTOM

    ctx.user_data["post_time"] = time_label(code)
    return await _finish_post(query.message, ctx)


async def post_time_custom(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    # Валидация формата HH:MM
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        await send(update, msg.error_time())
        return POST_TIME_CUSTOM
    ctx.user_data["post_time"] = f"сегодня в {text}"
    return await _finish_post(update.message, ctx)


async def _finish_post(message, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранить метку и уведомить пользователя."""
    uid      = message.chat_id
    category = ctx.user_data["post_category"]
    desc     = ctx.user_data["post_description"]
    time_txt = ctx.user_data["post_time"]
    city     = ctx.user_data["post_city"]

    act_id = db.create_activity(uid, category, desc, time_txt, city)

    await message.reply_text(
        msg.activity_created(category, time_txt, city, act_id),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.kb_my_activity(act_id),
    )
    ctx.user_data.clear()
    logger.info(f"[POST] Метка #{act_id} создана пользователем {uid} в {city}")
    return ConversationHandler.END


# ── /browse — просмотр меток ─────────────────────────────────

async def cmd_browse(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_row = db.get_user(update.effective_user.id)
    if not user_row:
        await send(update, msg.not_registered())
        return

    ctx.user_data["browse_city"] = user_row["city"]
    await send(
        update,
        f"📍 Ищу активности в *{user_row['city']}*\n\nФильтр по категории:",
        reply_markup=kb.kb_filter_categories(),
    )


async def browse_filter(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    code = query.data.split(":")[1]
    city = ctx.user_data.get("browse_city")

    if not city:
        user_row = db.get_user(update.effective_user.id)
        city = user_row["city"] if user_row else "Берлин"

    category = None if code == "all" else code
    activities = db.get_activities_in_city(city, category)

    my_id = update.effective_user.id

    if not activities:
        stats = db.get_city_stats(city)
        await query.edit_message_text(
            msg.no_activities(city, stats),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Показать метки (кроме своей)
    header = f"📍 *{city}* — {len(activities)} активност{'ь' if len(activities)==1 else 'и' if 2<=len(activities)<=4 else 'ей'}\n\n"
    await query.edit_message_text(header + "⬇️ Листай:", parse_mode=ParseMode.MARKDOWN)

    for row in activities:
        if row["user_id"] == my_id:
            continue  # не показывать свои метки

        is_open = bool(row.get("open_contact", False))
        text = msg.activity_card(row)
        markup = kb.kb_activity_actions(
            activity_id  = row["id"],
            owner_tg_id  = row["user_id"],
            show_contact = is_open,
        )
        await query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup
        )


# ── /mypost — моя метка ──────────────────────────────────────

async def cmd_mypost(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_row = db.get_user(update.effective_user.id)
    if not user_row:
        await send(update, msg.not_registered())
        return

    act = db.get_active_activity(update.effective_user.id)
    if not act:
        await send(update,
            "У тебя нет активной метки.\n\n/post — создать метку")
        return

    text = msg.activity_card(act)
    ic = db.get_interest_count(act["id"])
    if ic > 0:
        text += f"\n\n👥 Интересуются: *{ic}* человек"

    await send(update, text, reply_markup=kb.kb_my_activity(act["id"]))


# ── /delete ──────────────────────────────────────────────────

async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    act = db.get_active_activity(update.effective_user.id)
    if not act:
        await send(update, "У тебя нет активной метки.")
        return
    await send(update, "Удалить метку?", reply_markup=kb.kb_confirm_delete(act["id"]))


# ── /city — сменить город ────────────────────────────────────

async def cmd_city(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await send(update, msg.ask_city())
    return CITY_INPUT


async def city_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text.strip().title()
    db.update_user_city(update.effective_user.id, city)
    await send(update, msg.city_updated(city))
    return ConversationHandler.END


# ── /help ────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await send(update, msg.help_text())


# ── /app — открыть Mini App ──────────────────────────────────

async def cmd_open_app(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not MINIAPP_URL:
        await send(update, "🔧 Mini App ещё не задеплоен.\nПока используй команды: /post /browse")
        return
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗺 Открыть ActivityMap", web_app=WebAppInfo(url=MINIAPP_URL))
    ]])
    await update.message.reply_text(
        "🗺 *ActivityMap* — найди компанию прямо сейчас!",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ── CallbackQuery обработчик ─────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query  = update.callback_query
    await query.answer()
    data   = query.data
    my_id  = update.effective_user.id
    my_row = db.get_user(my_id)

    # ---- Интерес к метке ----
    if data.startswith("interest:"):
        _, act_id, owner_id = data.split(":")
        act_id   = int(act_id)
        owner_id = int(owner_id)

        if my_id == owner_id:
            await query.answer("Это твоя метка 😊", show_alert=True)
            return

        added = db.add_interest(act_id, my_id)
        if not added:
            await query.answer("Ты уже отметился!", show_alert=True)
            return

        owner_row = db.get_user(owner_id)
        if not owner_row:
            return

        # Уведомить автора метки
        act = db.get_active_activity(owner_id)
        cat_label = db.CATEGORIES.get(act["category"], ("✨", "Другое"))[1] if act else "активность"
        notification = msg.interest_notification(
            from_name     = my_row["name"] if my_row else "Кто-то",
            from_age      = my_row["age"]  if my_row else 0,
            from_username = my_row["username"] if my_row else None,
            activity_label = cat_label,
        )
        try:
            await ctx.bot.send_message(
                chat_id    = owner_id,
                text       = notification,
                parse_mode = ParseMode.MARKDOWN,
            )
        except TelegramError:
            pass  # Пользователь заблокировал бота

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            msg.interest_sent(owner_row["name"]),
            parse_mode=ParseMode.MARKDOWN,
        )

    # ---- Контакт (открытый) ----
    elif data.startswith("contact:"):
        owner_id  = int(data.split(":")[1])
        owner_row = db.get_user(owner_id)
        if owner_row and owner_row["username"]:
            await query.message.reply_text(
                f"✉️ Напиши напрямую: @{owner_row['username']}",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await query.answer("У пользователя нет username.", show_alert=True)

    # ---- Удаление ----
    elif data.startswith("delete:") and not data.startswith("delete_"):
        act_id = int(data.split(":")[1])
        await query.edit_message_reply_markup(
            reply_markup=kb.kb_confirm_delete(act_id)
        )

    elif data.startswith("delete_ok:"):
        act_id = int(data.split(":")[1])
        ok = db.deactivate_activity(act_id, my_id)
        if ok:
            await query.edit_message_text(msg.activity_deleted(), parse_mode=ParseMode.MARKDOWN)
        else:
            await query.answer("Не удалось удалить.", show_alert=True)

    elif data == "delete_cancel":
        await query.edit_message_reply_markup(reply_markup=None)

    # ---- Жалоба ----
    elif data.startswith("report:") and not data.startswith("report_"):
        _, act_id, reported_user = data.split(":")
        await query.edit_message_reply_markup(
            reply_markup=kb.kb_report_reasons(int(act_id), int(reported_user))
        )

    elif data.startswith("report_reason:"):
        parts  = data.split(":")
        act_id, reported_user, reason = int(parts[1]), int(parts[2]), parts[3]
        db.add_report(my_id, reported_user, act_id, reason)
        await query.edit_message_text(
            "✅ Жалоба отправлена. Рассмотрим в течение 24 часов.",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "report_cancel":
        await query.edit_message_reply_markup(reply_markup=None)


# ── Автоочистка ──────────────────────────────────────────────

async def scheduled_cleanup(app: Application) -> None:
    count = db.cleanup_expired()
    if count > 0:
        logger.info(f"[CLEANUP] Удалено просроченных меток: {count}")


# ── Запуск ───────────────────────────────────────────────────

def main() -> None:
    db.init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ---- ConversationHandler: регистрация ----
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name)],
            REG_AGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_age)],
            REG_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, reg_city)],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )

    # ---- ConversationHandler: создание метки ----
    post_handler = ConversationHandler(
        entry_points=[CommandHandler("post", cmd_post)],
        states={
            POST_CATEGORY: [
                CallbackQueryHandler(post_category_chosen, pattern=r"^cat:")
            ],
            POST_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_description),
                CommandHandler("skip", post_description),
            ],
            POST_TIME: [
                CallbackQueryHandler(post_time_chosen, pattern=r"^time:")
            ],
            POST_TIME_CUSTOM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_time_custom)
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )

    # ---- ConversationHandler: смена города ----
    city_handler = ConversationHandler(
        entry_points=[CommandHandler("city", cmd_city)],
        states={
            CITY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_input)],
        },
        fallbacks=[],
    )

    # ---- Регистрация хендлеров ----
    app.add_handler(reg_handler)
    app.add_handler(post_handler)
    app.add_handler(city_handler)
    app.add_handler(CommandHandler("browse", cmd_browse))
    app.add_handler(CommandHandler("mypost", cmd_mypost))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("app",    cmd_open_app))
    app.add_handler(CallbackQueryHandler(browse_filter, pattern=r"^browse:"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # ---- Планировщик автоочистки (каждые 15 минут) ----
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.create_task(scheduled_cleanup(app)),
        trigger="interval",
        minutes=15,
    )
    scheduler.start()

    # ---- Команды в меню бота ----
    async def post_init(application: Application) -> None:
        commands = [
            
            
            
            
            
            BotCommand("help",   "Помощь"),
        ]
        
            
        await application.bot.set_my_commands(commands)

        # Кнопка Menu → открывает Mini App
        
            await application.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="Открыть карту",
                    web_app=WebAppInfo(url=MINIAPP_URL),
                )
            )

    app.post_init = post_init

    logger.info("🚀 ActivityMap Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
