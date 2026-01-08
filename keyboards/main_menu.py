from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import json

def main_menu_keyboard():
    """Главное меню - БЕЗ кнопки Челленджи"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📈 Активность")],
            [KeyboardButton(text="❔ Справка"), KeyboardButton(text='💬 Спросить AI')],
            [KeyboardButton(text="🔍 ПОИСК ЛЮБИМОЙ РАБОТЫ")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def org_type_keyboard():
    """Выбор типа организации"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚽ Спорт", callback_data="dir_sport")]
        ]
    )

def energy_keyboard():
    """Энергия (1-10)"""
    buttons = []
    for i in range(1, 11):
        buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"energy_{i}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+5] for i in range(0, 10, 5)])

def mood_keyboard():
    """Настроение"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="😊 Счастлив", callback_data="mood_happy"),
                InlineKeyboardButton(text="😐 Обычно", callback_data="mood_neutral"),
                InlineKeyboardButton(text="😢 Грустно", callback_data="mood_sad")
            ],
        ]
    )

def sleep_quality_keyboard():
    """Качество сна (1-10)"""
    buttons = []
    for i in range(1, 11):
        buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"sleep_{i}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+5] for i in range(0, 10, 5)])

def readiness_keyboard():
    """Готовность (1-10)"""
    buttons = []
    for i in range(1, 11):
        buttons.append(InlineKeyboardButton(text=str(i), callback_data=f"readiness_{i}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i+5] for i in range(0, 10, 5)])

def challenge_response_keyboard():
    """Принять/отказать челлендж"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✔️ Принял вызов", callback_data="challenge_accept"),
                InlineKeyboardButton(text="⛔ Отказываюсь", callback_data="challenge_reject")
            ],
        ]
    )

def yes_no_keyboard():
    """Да/нет"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✔️ Да", callback_data="yes"),
                InlineKeyboardButton(text="⛔ Нет", callback_data="no")
            ],
        ]
    )

def profile_menu_keyboard():
    """Меню профиля (3 раздела)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👁️ Мой профиль", callback_data="profile_view")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="profile_stats")],
            [InlineKeyboardButton(text="📋 Месячный отчет", callback_data="profile_monthly_report")],
            [InlineKeyboardButton(text="🏆 Награды", callback_data="profile_awards")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def admin_menu_keyboard():
    """Админ-меню"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Создать челлендж", callback_data="admin_create_challenge")],
            [InlineKeyboardButton(text="📊 Статистика команды", callback_data="admin_view_stats")],
            [InlineKeyboardButton(text="👥 Управление членами", callback_data="admin_manage_members")],
            [InlineKeyboardButton(text="💼 Управление вакансиями", callback_data="admin_manage_vacancies")],
            [InlineKeyboardButton(text="📨 Отправить рассылку", callback_data="admin_send_broadcast")],
            [InlineKeyboardButton(text="📈 Ежедневный отчет", callback_data="admin_daily_report")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def back_button_to_profile():
    """Кнопка назад для профиля"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_profile")],
        ]
    )

def back_to_activity_keyboard():
    """Кнопка назад для активности"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_activity")],
        ]
    )

def back_button_to_vacansies():
    """Кнопка назад для поиска работы"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_vacansies")],
        ]
    )  

def vacancies_menu_keyboard():
    """Клавиатура для меню вакансий"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Смотреть вакансии", callback_data="view_vacancies")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def vacancy_navigation_keyboard(current_index: int, total_vacancies: int):
    """Клавиатура для навигации по вакансиям"""
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"vac_prev_{current_index}"))
    
    # Номер текущей вакансии
    nav_buttons.append(InlineKeyboardButton(
        text=f"{current_index + 1}/{total_vacancies}", 
        callback_data="no_action"
    ))
    
    if current_index < total_vacancies - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"vac_next_{current_index}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton(text="🔍 Подробнее", callback_data=f"vac_details_{current_index}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def no_action_button():
    """Кнопка-заглушка без действия"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸️", callback_data="no_action")]
    ])

def admin_vacancy_menu_keyboard():
    """Админ-меню для управления вакансиями"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="admin_add_vacancy")],
            [InlineKeyboardButton(text="📋 Список вакансий", callback_data="admin_list_vacancies")],
            [InlineKeyboardButton(text="🗑️ Удалить вакансию", callback_data="admin_delete_vacancy")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )

def premium_keyboard():
    """Премиум подписка"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Получить доступ", callback_data="buy_premium")],
        [InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="premium_info")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def update_member_fields_keyboard():
    """Выбор поля для обновления"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Энергия (1-10)", callback_data="update_energy")],
        [InlineKeyboardButton(text="😴 Качество сна (1-10)", callback_data="update_sleep")],
        [InlineKeyboardButton(text="🎯 Готовность (1-10)", callback_data="update_readiness")],
        [InlineKeyboardButton(text="😊 Настроение", callback_data="update_mood")],
        [InlineKeyboardButton(text="💎 Добавить очки", callback_data="update_points")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])