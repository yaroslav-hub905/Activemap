"""
ActivityMap Bot — Inline keyboards
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import CATEGORIES


def kb_categories(prefix: str = "cat") -> InlineKeyboardMarkup:
    """Клавиатура выбора категории."""
    buttons = []
    row = []
    for key, (emoji, label) in CATEGORIES.items():
        row.append(InlineKeyboardButton(
            f"{emoji} {label}", callback_data=f"{prefix}:{key}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def kb_time() -> InlineKeyboardMarkup:
    """Клавиатура выбора времени."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Прямо сейчас",   callback_data="time:now"),
            InlineKeyboardButton("🕐 Через час",       callback_data="time:1h"),
        ],
        [
            InlineKeyboardButton("🕑 Через 2 часа",   callback_data="time:2h"),
            InlineKeyboardButton("🌙 Сегодня вечером", callback_data="time:evening"),
        ],
        [
            InlineKeyboardButton("✏️ Ввести вручную",  callback_data="time:custom"),
        ],
    ])


def kb_city_confirm(city: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✓ Да, {city}", callback_data=f"city_ok:{city}"),
        InlineKeyboardButton("✏️ Изменить",   callback_data="city_change"),
    ]])


def kb_activity_actions(activity_id: int, owner_tg_id: int,
                         show_contact: bool = False) -> InlineKeyboardMarkup:
    """Кнопки под карточкой активности."""
    rows = []

    if show_contact:
        rows.append([InlineKeyboardButton(
            "✉️ Написать автору", callback_data=f"contact:{owner_tg_id}"
        )])
    else:
        rows.append([InlineKeyboardButton(
            "👋 Интересно! Хочу присоединиться",
            callback_data=f"interest:{activity_id}:{owner_tg_id}"
        )])

    rows.append([
        InlineKeyboardButton("⚑ Пожаловаться", callback_data=f"report:{activity_id}:{owner_tg_id}"),
    ])
    return InlineKeyboardMarkup(rows)


def kb_my_activity(activity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Удалить метку", callback_data=f"delete:{activity_id}"),
    ]])


def kb_filter_categories() -> InlineKeyboardMarkup:
    """Фильтр категорий для /browse."""
    buttons = [[InlineKeyboardButton("🗺 Все категории", callback_data="browse:all")]]
    row = []
    for key, (emoji, label) in CATEGORIES.items():
        row.append(InlineKeyboardButton(f"{emoji}", callback_data=f"browse:{key}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def kb_report_reasons(activity_id: int, reported_user: int) -> InlineKeyboardMarkup:
    reasons = [
        ("Фейк / бот",      "fake"),
        ("Спам",             "spam"),
        ("Неприемлемо",     "inappropriate"),
        ("Домогательство",  "harassment"),
    ]
    rows = [[
        InlineKeyboardButton(label, callback_data=f"report_reason:{activity_id}:{reported_user}:{key}")
    ] for label, key in reasons]
    rows.append([InlineKeyboardButton("Отмена", callback_data="report_cancel")])
    return InlineKeyboardMarkup(rows)


def kb_confirm_delete(activity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✓ Да, удалить", callback_data=f"delete_ok:{activity_id}"),
        InlineKeyboardButton("Отмена",         callback_data="delete_cancel"),
    ]])
