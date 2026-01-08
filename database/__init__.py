from .database import get_session, init_db, SessionLocal, engine
from .models import User, Organization, Survey, Challenge, UserRole, ChallengeStatus, SurveyType, PendingChallenge, PlayerMetrics

__all__ = [
    'get_session',
    'init_db',
    'SessionLocal',
    'engine',
    'User',
    'Organization',
    'Survey',
    'Challenge',
    'UserRole',
    'ChallengeStatus',
    'SurveyType',
    'PendingChallenge',
    'PlayerMetrics'
]

# database/__init__.py
from .database import (
    engine, 
    SessionLocal, 
    get_session, 
    init_db
)

from .models import (
    Base,
    User,
    Organization,
    Challenge,
    PendingChallenge,
    Survey,
    MetricsSurvey,
    UserRole,
    ChallengeStatus,
    SurveyType
)

# Вспомогательные функции для ролей (создаем здесь или в отдельном файле)
def get_admin_roles():
    """Роли с правами администрирования"""
    return [UserRole.SUPER_ADMIN.value, UserRole.ORG_ADMIN.value]

def get_viewer_roles():
    """Роли с правами просмотра (но не редактирования)"""
    return [UserRole.TRAINER.value]

def get_all_roles():
    """Все доступные роли"""
    return [role.value for role in UserRole]

def is_valid_role(role_str: str) -> bool:
    """Проверить, является ли строка валидной ролью"""
    try:
        UserRole(role_str)
        return True
    except ValueError:
        return False

def get_role_description(role_str: str) -> str:
    """Получить описание роли"""
    role_descriptions = {
        "SUPER_ADMIN": "👑 Суперадмин системы (полный доступ ко всему)",
        "ORG_ADMIN": "👨‍💼 Администратор организации (управление своей командой)",
        "TRAINER": "👨‍🏫 Тренер (создание челленджей и просмотр статистики)",
        "MEMBER": "👤 Обычный участник",
        "GUEST": "👋 Гость (ограниченный доступ)"
    }
    return role_descriptions.get(role_str, "Неизвестная роль")

__all__ = [
    'Base',
    'engine',
    'SessionLocal',
    'get_session',
    'init_db',
    'User',
    'Organization',
    'Challenge',
    'PendingChallenge',
    'Survey',
    'MetricsSurvey',
    'UserRole',
    'ChallengeStatus',
    'SurveyType',
    'get_admin_roles',
    'get_viewer_roles',
    'get_all_roles',
    'is_valid_role',
    'get_role_description'
]
