"""
ActivityMap Bot — Все тексты сообщений в одном месте
"""
from database import CATEGORIES, PIN_LIFETIME_HOURS
import sqlite3


def welcome(name: str) -> str:
    return (
        f"👋 Привет, {name}! Я — *YAMA*.\n\n"
        "Помогу найти компанию для встречи сегодня: "
        "кофе, прогулка, бар, спорт, языковой обмен и многое другое."
    )


def ask_name() -> str:
    return "Как тебя зовут? Напиши своё имя:"


def ask_age() -> str:
    return "Сколько тебе лет? (18–80)"


def ask_city() -> str:
    return (
        "🇧🇪 В каком городе Бельгии ты сейчас?\n\n"
        "Выбери из списка ниже или напиши название сам:"
    )


def profile_saved(name: str, age: int, city: str) -> str:
    return (
        f"✅ Профиль сохранён!\n\n"
        f"👤 *{name}*, {age} лет\n"
        f"📍 *{city}*\n\n"
        f"🚀 *Жми кнопку ниже — и вперёд, искать компанию!*\n"
        f"Регистрация больше не понадобится: карта откроется сразу. 👇"
    )


def ask_category() -> str:
    return "Выбери категорию активности:"


def ask_description() -> str:
    return (
        "Напиши короткое описание (до 200 символов):\n\n"
        "_Например: Ищу компанию на кофе, хочу поговорить по-русски_\n\n"
        "Или отправь /skip чтобы пропустить."
    )


def ask_time() -> str:
    return "Когда планируешь?"


def ask_custom_time() -> str:
    return (
        "Напиши время в формате *ЧЧ:ММ*\n"
        "_Например: 18:30_"
    )


def activity_created(cat: str, time_text: str, city: str, act_id: int) -> str:
    emoji, label = CATEGORIES.get(cat, ("✨", "Другое"))
    return (
        f"🎉 *Метка опубликована!*\n\n"
        f"{emoji} *{label}* · {time_text}\n"
        f"📍 {city}\n\n"
        f"Люди в твоём городе уже видят тебя.\n"
        f"Метка автоматически удалится через {PIN_LIFETIME_HOURS} часов."
    )


def activity_card(row: sqlite3.Row, show_contact: bool = False) -> str:
    emoji, label = CATEGORIES.get(row["category"], ("✨", "Другое"))
    interest_str = ""
    if row["interest_count"] > 0:
        interest_str = f"\n👥 Интересуются: {row['interest_count']}"

    contact_str = ""
    if show_contact and row["username"]:
        contact_str = f"\n✉️ @{row['username']}"

    return (
        f"{emoji} *{label}* · {row['time_text']}\n"
        f"👤 *{row['name']}*, {row['age']} лет\n"
        f"📍 {row['city']}"
        f"{interest_str}"
        f"{contact_str}\n\n"
        f"_{row['description'] or 'Описание не указано'}_"
    )


def no_activities(city: str, stats: dict) -> str:
    if stats["total_pins"] > 0:
        return (
            f"😴 Сейчас в *{city}* нет активных меток.\n\n"
            f"За последние 24 часа здесь было {stats['total_pins']} активностей "
            f"от {stats['unique_users']} человек.\n\n"
            f"👇 Создай первую метку сегодня!"
        )
    return (
        f"😴 В *{city}* пока нет активностей.\n\n"
        f"🎯 *Ты можешь быть первым!*\n"
        f"Создай метку — люди в городе увидят тебя.\n\n"
        f"/post — создать активность"
    )


def already_has_activity() -> str:
    return (
        "У тебя уже есть активная метка.\n\n"
        "/mypost — посмотреть её\n"
        "Удали текущую метку, чтобы создать новую."
    )


def interest_sent(owner_name: str) -> str:
    return (
        f"👋 Отлично! {owner_name} получит уведомление о твоём интересе.\n\n"
        "Если {owner_name} захочет познакомиться — ты получишь его контакт.\n\n"
        "💡 Пока ждёшь — создай свою метку через /post"
    )


def interest_notification(from_name: str, from_age: int,
                           from_username: str | None,
                           activity_label: str) -> str:
    contact = f"@{from_username}" if from_username else "(username не указан)"
    return (
        f"🔔 *Новый интерес к твоей метке!*\n\n"
        f"👤 *{from_name}*, {from_age} лет хочет присоединиться к: {activity_label}\n\n"
        f"Контакт: {contact}\n\n"
        f"Напиши им напрямую в Telegram!"
    )


def help_text() -> str:
    return (
        "📖 *ActivityMap Bot — помощь*\n\n"
        "*/start* — регистрация / главное меню\n"
        "*/post* — создать метку активности\n"
        "*/browse* — смотреть активности в твоём городе\n"
        "*/mypost* — моя текущая метка\n"
        "*/city* — сменить город\n"
        "*/delete* — удалить свою метку\n"
        "*/help* — эта справка\n\n"
        "❓ Вопросы и предложения: @ActivityMapSupport"
    )


def error_age() -> str:
    return "⚠️ Возраст должен быть от 18 до 80. Попробуй ещё раз:"


def error_time() -> str:
    return "⚠️ Напиши время в формате ЧЧ:ММ, например *18:30*:"


def activity_deleted() -> str:
    return "✅ Метка удалена."


def not_registered() -> str:
    return "Сначала зарегистрируйся: /start"


def city_updated(city: str) -> str:
    return f"📍 Город обновлён: *{city}*"


def edit_data_menu_text() -> str:
    return "Что хочешь изменить?"

def ask_new_name() -> str:
    return "Напиши новое имя:"

def ask_new_age() -> str:
    return "Напиши новый возраст (18–80):"

def ask_new_city() -> str:
    return "🇧🇪 Выбери новый город Бельгии или напиши название:"

def data_updated(field_label: str, value: str) -> str:
    return f"✅ {field_label} обновлено: *{value}*"

def all_pins_deactivated(count: int) -> str:
    if count > 0:
        return f"🗑 Готово! Деактивировано меток: {count}"
    return "У тебя нет активных меток."
