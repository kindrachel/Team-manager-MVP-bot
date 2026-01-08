# keyboards/ai_keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def challenge_types():
    """Клавиатура выбора направления челленджа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚽ Футбол", callback_data="direction_football"),
            InlineKeyboardButton(text="🏢 Компания", callback_data="direction_company")
        ],
        [
            InlineKeyboardButton(text="📈 Личный рост", callback_data="direction_growth"),
            InlineKeyboardButton(text="🎯 Случайный", callback_data="direction_random")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")
        ]
    ])

def report_types():
    """Клавиатура выбора типа отчета"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Персональный", callback_data="report_personal"),
            InlineKeyboardButton(text="👥 Командный", callback_data="report_team")
        ],
        [
            InlineKeyboardButton(text="📈 За месяц", callback_data="report_monthly"),
            InlineKeyboardButton(text="🎯 Рекомендации", callback_data="report_recommendations")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")
        ]
    ])

def progress_actions():
    """Действия с прогрессом"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Детальная статистика", callback_data="progress_detailed"),
            InlineKeyboardButton(text="📈 Графики", callback_data="progress_charts")
        ],
        [
            InlineKeyboardButton(text="🎯 Новый челлендж", callback_data="new_challenge"),
            InlineKeyboardButton(text="💫 Мотивация", callback_data="get_motivation")
        ],
        [
            InlineKeyboardButton(text="📄 Отчет", callback_data="report_personal"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_main")
        ]
    ])

def main_menu():
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Челлендж", callback_data="menu_challenge"),
            InlineKeyboardButton(text="📊 Прогресс", callback_data="menu_progress")
        ],
        [
            InlineKeyboardButton(text="📝 Отчет", callback_data="menu_report"),
            InlineKeyboardButton(text="❓ Вопрос", callback_data="menu_ask")
        ],
        [
            InlineKeyboardButton(text="💫 Мотивация", callback_data="menu_motivation"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings")
        ]
    ])