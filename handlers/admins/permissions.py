# handlers/admin/permissions.py
from enum import Enum
from typing import Set, Optional, Callable
from functools import wraps
from aiogram.types import CallbackQuery, Message
from database import User, Organization, get_session, UserRole
from config import load_config
import logging

logger = logging.getLogger(__name__)

logger.info(f"DEBUG: UserRole.SUPER_ADMIN.value = {UserRole.SUPER_ADMIN.value}")
logger.info(f"DEBUG: UserRole.ORG_ADMIN.value = {UserRole.ORG_ADMIN.value}")
logger.info(f"DEBUG: UserRole.TRAINER.value = {UserRole.TRAINER.value}")

class AdminPermission(str, Enum):
    """Разрешения для админ-панели"""
    # Базовые
    ACCESS_ADMIN_PANEL = "access_admin_panel"
    
    # Просмотр
    VIEW_STATS = "view_stats"
    VIEW_MEMBERS = "view_members"
    VIEW_LEADERBOARD = "view_leaderboard"
    VIEW_SCHEDULE = "view_schedule"
    
    # Управление
    CREATE_CHALLENGE = "create_challenge"
    SCHEDULE_CHALLENGES = "schedule_challenges"
    SEND_BROADCAST = "send_broadcast"
    MANAGE_VACANCIES = "manage_vacancies"
    
    # Администрирование
    MANAGE_ORG_SETTINGS = "manage_org_settings"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_ROLES = "manage_roles"
    
    # Суперадмин
    VIEW_ALL_ORGS = "view_all_orgs"
    SWITCH_ORGS = "switch_orgs"
    MANAGE_SYSTEM = "manage_system"

class AdminRole:
    """Роль с разрешениями"""
    def __init__(self, name: str, permissions: Set[AdminPermission]):
        self.name = name
        self.permissions = permissions
    
    def has_permission(self, permission: AdminPermission) -> bool:
        return permission in self.permissions

# Определение ролей
ADMIN_ROLES = {
    UserRole.SUPER_ADMIN.value: AdminRole("Супер-админ", {
        AdminPermission.ACCESS_ADMIN_PANEL,
        AdminPermission.VIEW_STATS,
        AdminPermission.VIEW_MEMBERS,
        AdminPermission.VIEW_LEADERBOARD,
        AdminPermission.VIEW_SCHEDULE,
        AdminPermission.CREATE_CHALLENGE,
        AdminPermission.SCHEDULE_CHALLENGES,
        AdminPermission.SEND_BROADCAST,
        AdminPermission.MANAGE_VACANCIES,
        AdminPermission.MANAGE_ORG_SETTINGS,
        AdminPermission.MANAGE_MEMBERS,
        AdminPermission.MANAGE_ROLES,
        AdminPermission.VIEW_ALL_ORGS,
        AdminPermission.SWITCH_ORGS,
        AdminPermission.MANAGE_SYSTEM
    }),
    
    UserRole.ORG_ADMIN.value: AdminRole("Админ организации", {
        AdminPermission.ACCESS_ADMIN_PANEL,
        AdminPermission.VIEW_STATS,
        AdminPermission.VIEW_MEMBERS,
        AdminPermission.VIEW_LEADERBOARD,
        AdminPermission.VIEW_SCHEDULE,
        AdminPermission.CREATE_CHALLENGE,
        AdminPermission.SCHEDULE_CHALLENGES,
        AdminPermission.SEND_BROADCAST,
        AdminPermission.MANAGE_VACANCIES,
        AdminPermission.MANAGE_ORG_SETTINGS,
        AdminPermission.MANAGE_MEMBERS
    }),
    
    UserRole.TRAINER.value: AdminRole("Тренер", {
        AdminPermission.ACCESS_ADMIN_PANEL,
        AdminPermission.VIEW_STATS,
        AdminPermission.VIEW_MEMBERS,
        AdminPermission.VIEW_LEADERBOARD,
        AdminPermission.VIEW_SCHEDULE,
        AdminPermission.CREATE_CHALLENGE
    })
}

class AdminContext:
    """Контекст текущей админ-сессии"""
    def __init__(self, user_id: int, org_id: int = None):
        self.user_id = user_id
        self.current_org_id = org_id
        self.user_role = None
        self.admin_role = None
        self.permissions = set()  
        self._init_context()
    
    def _init_context(self):
        """Инициализация контекста"""
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == self.user_id).first()
            if not user:
                return
            
            db_role = user.role.upper() if user.role else ""
            
            config = load_config()
            if self.user_id in config.admin_ids:
                self.user_role = "SUPER_ADMIN"
            else:
                self.user_role = db_role
        
            
            self.admin_role = ADMIN_ROLES.get(self.user_role)
            
            if self.admin_role:
                self.permissions = self.admin_role.permissions
            
            if self.current_org_id is None:
                self.current_org_id = user.org_id
                    
        finally:
            session.close()
    
    def has_permission(self, permission: AdminPermission) -> bool:
        """Проверка разрешения"""
        if not self.admin_role:
            return False
        return permission in self.permissions
    
    def can_access_org(self, org_id: int) -> bool:
        """Может ли админ работать с этой организацией"""
        # Суперадмины могут всё
        if self.has_permission(AdminPermission.VIEW_ALL_ORGS):
            return True
        
        # Остальные только свою организацию
        return org_id == self.current_org_id
    
    def switch_org(self, org_id: int) -> bool:
        """Переключиться на другую организацию"""
        if not self.has_permission(AdminPermission.SWITCH_ORGS):
            return False
        
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            if org:
                self.current_org_id = org_id
                return True
            return False
        finally:
            session.close()

def require_admin(permission: AdminPermission = None):
    """Декоратор для проверки прав доступа"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Получаем user_id из аргументов
            user_id = None
            
            # Ищем user_id в разных типах событий
            for arg in args:
                if hasattr(arg, 'from_user'):
                    user_id = arg.from_user.id
                    break
                elif hasattr(arg, 'user_id'):
                    user_id = arg.user_id
                    break
            
            if not user_id:
                logger.error("Cannot determine user_id in admin decorator")
                return
            
            # Создаем контекст
            ctx = AdminContext(user_id)
            
            # Базовая проверка на доступ к админке
            if not ctx.has_permission(AdminPermission.ACCESS_ADMIN_PANEL):
                logger.warning(f"User {user_id} tried to access admin without permission")
                return
            
            # Проверка конкретного разрешения если нужно
            if permission and not ctx.has_permission(permission):
                logger.warning(f"User {user_id} lacks permission: {permission}")
                return
            
            # Добавляем контекст в kwargs
            kwargs['admin_context'] = ctx
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

def is_super_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь суперадмином"""
    config = load_config()
    if user_id in config.admin_ids:
        return True
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        return user and user.role == UserRole.SUPER_ADMIN.value
    finally:
        session.close()

def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором любой роли"""
    return is_super_admin(user_id) or AdminContext(user_id).has_permission(AdminPermission.ACCESS_ADMIN_PANEL)