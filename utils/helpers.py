from datetime import datetime, timezone
from database import User, Organization, UserRole

def get_level_name(level: int) -> str:
    """Получить название уровня"""
    levels = {
        1: "🥉 Новичок",
        2: "🥈 Развивающийся",
        3: "🥇 Профи",
        4: "👑 Лидер",
        5: "🏆 Капитан"
    }
    return levels.get(level, "???")

def format_user_full_profile(user, org) -> str:
    """Форматировать профиль пользователя"""
    level_name = get_level_name(user.level)
    return (
        f"*👤 ЛИЧНЫЙ ПРОФИЛЬ*\n\n"
        f"📌 ФИО: {user.name}\n"
        f"📌 Телефон: {user.phone}\n\n"
        f"*🏟 Клуб:* {org.name if org else 'N/A'}\n"
        f"*⚽ Позиция:* {user.position}\n\n"
        f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n'
        f'*🔥 Статистика:*\n'
        f"✅ Опыт: {level_name} ({user.level}/5)\n"
        f"💼 Баллы: {user.points}\n"
        f"📅 Зарегистрирован: {user.registered_at.strftime('%d.%m.%Y')}\n\n"
        f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n'
        f"*Текущие показатели:*\n"
        f"  🔋 Энергия {user.energy or '—'}/10\n"
        f"  😴 Отдых: {user.sleep_quality or '—'}/10\n"
        f"  💨 Готовность: {user.readiness or '—'}/10\n"
        f"  🙂 Настроение: {user.mood or '—'}\n\n"
        f'⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n'
        f"*Игровая роль:* {'Тренер' if user.role == UserRole.TRAINER.value else 'Игрок'}"
    )

def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """
    Разбивает длинное сообщение на части
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина части (Telegram limit ~4096)
    
    Returns:
        Список частей текста
    """
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    paragraphs = text.split('\n')
    
    for paragraph in paragraphs:
        if len(paragraph) > max_length:
            sentences = paragraph.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').split('\n')
            for sentence in sentences:
                if len(current_part) + len(sentence) + 1 <= max_length:
                    current_part += sentence + ". "
                else:
                    if current_part:
                        parts.append(current_part.strip())
                    current_part = sentence + ". "
        else:
            if len(current_part) + len(paragraph) + 1 <= max_length:
                current_part += paragraph + "\n"
            else:
                if current_part:
                    parts.append(current_part.strip())
                current_part = paragraph + "\n"
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

