import pytz
from datetime import datetime, timezone as tz
from typing import Optional, Tuple
from database import get_session
from database.models import Organization, User

# Периоды опросов (можно оставить как есть или подстроить)
SURVEY_PERIODS = {
    "morning": {"start": 6, "end": 11},    # 6:00 - 12:00
    "afternoon": {"start": 12, "end": 17},  # 12:00 - 18:00  
    "evening": {"start": 18, "end": 22},    # 18:00 - 22:00
    "none": {"start": 22, "end": 6}         # Ночью недоступно
}

def get_current_survey_period_for_org(org_id: int) -> str:
    """Определить текущий период опроса для конкретной организации"""
    timezone_str = get_org_timezone(org_id)
    
    try:
        org_tz = pytz.timezone(timezone_str)
    except pytz.exceptions.UnknownTimeZoneError:
        org_tz = pytz.timezone('Asia/Novosibirsk')
    
    now = datetime.now(org_tz)
    hour = now.hour
    
    if 6 <= hour < 12:      
        return "morning"
    elif 12 <= hour < 18:   
        return "afternoon"
    elif 18 <= hour < 22:  
        return "evening"
    else:
        return "none"    

def get_current_survey_period_for_user(user_id: int) -> str:
    """Определить текущий период опроса для конкретного пользователя"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.org_id:
            return get_current_survey_period_for_org(user.org_id)
        else:
            return get_current_survey_period()  # fallback
    finally:
        session.close()

def get_current_survey_period() -> str:
    """Определить текущий период опроса (старая функция для обратной совместимости)"""
    return get_current_survey_period_for_org(1)  # Для тестов или по умолчанию

def get_period_display_name(period: str) -> str:
    """Получить отображаемое название периода"""
    names = {
        "morning": "🌅 Утренний опрос",
        "afternoon": "☀️ Дневной опрос", 
        "evening": "🌙 Вечерний опрос",
        "none": "⏳ Время опросов"
    }
    return names.get(period, period)

def get_period_time_range(period: str) -> str:
    """Получить временной диапазон периода"""
    ranges = {
        "morning": "6:00 - 12:00",
        "afternoon": "12:00 - 18:00",
        "evening": "18:00 - 22:00",
        "none": "22:00 - 6:00"
    }
    return ranges.get(period, "не определено")

def is_survey_available_for_user(user_id: int) -> Tuple[bool, str, Optional[str]]:
    """
    Проверить, доступен ли опрос для пользователя
    
    Returns:
        (available, message, period)
    """
    period = get_current_survey_period_for_user(user_id)
    
    if period == "none":
        return False, "🌙 Сейчас не время для опросов", None
    
    # Получаем время в часовом поясе организации
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.org_id:
            org_time = get_current_org_time(user.org_id)
            time_str = org_time.strftime("%H:%M")
        else:
            time_str = "неизвестно"
    finally:
        session.close()
    
    return True, f"🕐 Текущее время: {time_str}", period

def get_org_timezone(org_id: int) -> str:
    """Получить часовой пояс организации"""
    session = get_session()
    try:
        org = session.query(Organization).filter(Organization.id == org_id).first()
        return org.timezone if org and org.timezone else "Asia/Novosibirsk"
    finally:
        session.close()

def get_user_timezone(user_id: int) -> str:
    """Получить часовой пояс пользователя (через его организацию)"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user and user.org_id:
            return get_org_timezone(user.org_id)
        return "Asia/Novosibirsk"
    finally:
        session.close()

def convert_utc_to_local(utc_time: datetime, timezone_str: str) -> datetime:
    """Конвертировать UTC время в локальное время организации"""
    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=tz.utc)
    
    try:
        local_tz = pytz.timezone(timezone_str)
        return utc_time.astimezone(local_tz)
    except:
        return utc_time.astimezone(pytz.timezone("Asia/Novosibirsk"))

def format_datetime(dt: datetime, timezone_str: str, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """Отформатировать дату-время с учетом часового пояса"""
    local_dt = convert_utc_to_local(dt, timezone_str) if dt.tzinfo else dt
    return local_dt.strftime(format_str)

def get_current_org_time(org_id: int) -> datetime:
    """Получить текущее время в часовом поясе организации"""
    timezone_str = get_org_timezone(org_id)
    return datetime.now(pytz.timezone(timezone_str))

def create_timezone_keyboard():
    """Создать клавиатуру для выбора часового пояса"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    row = []
    
    for i, (display_name, tz_name) in enumerate(SUPPORTED_TIMEZONES, 1):
        row.append(InlineKeyboardButton(text=display_name, callback_data=f"tz_{tz_name}"))
        if i % 2 == 0:
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_timezone")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

SUPPORTED_TIMEZONES = [
    ("🇷🇺 Москва", "Europe/Moscow"),
    ("🇷🇺 Новосибирск", "Asia/Novosibirsk"),
    ("🇷🇺 Екатеринбург", "Asia/Yekaterinburg"),
    ("🇷🇺 Владивосток", "Asia/Vladivostok"),
    ("🇷🇺 Калининград", "Europe/Kaliningrad"),
    ("🇰🇿 Алматы", "Asia/Almaty"),
    ("🇺🇦 Киев", "Europe/Kiev"),
    ("🇧🇾 Минск", "Europe/Minsk"),
    ("🇪🇺 Берлин", "Europe/Berlin"),
    ("🇺🇸 Нью-Йорк", "America/New_York"),
    ("🇺🇸 Лос-Анджелес", "America/Los_Angeles"),
    ("🇨🇳 Пекин", "Asia/Shanghai"),
    ("🇯🇵 Токио", "Asia/Tokyo"),
]