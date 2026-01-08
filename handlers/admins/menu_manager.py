from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, List, Optional
from .permissions import AdminPermission, AdminContext
from database import User, get_session, UserRole
import logging

logger = logging.getLogger(__name__)

class AdminMenuManager:
    """Управление меню админ-панели"""
    
    def __init__(self):
        self.menu_cache = {}
    
    def get_super_admin_menu(self, ctx: AdminContext) -> InlineKeyboardMarkup:
        """Меню суперадмина"""
        builder = InlineKeyboardBuilder()
        
        builder.row(
            InlineKeyboardButton(
                text="🏢 Выбрать организацию",
                callback_data="admin_select_organization"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="⚡ Создать челлендж",
                callback_data="admin_select_org"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="🎯 Сгенерировать челленджи",
                callback_data="admin_generate_challenges"
            )
        )

        builder.row(
            InlineKeyboardButton(
                text="Команды",
                callback_data='admin_commands'
            )
        )
        
        return builder.as_markup()
    
    def get_org_admin_menu(self, ctx: AdminContext) -> InlineKeyboardMarkup:
        """Меню администратора организации"""
        builder = InlineKeyboardBuilder()
        
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == ctx.user_id).first()
            org_id = user.org_id if user and hasattr(user, 'org_id') else None
            
            builder.row(
                InlineKeyboardButton(
                    text="⚡ Создать челлендж",
                    callback_data=f"admin_create_challenge_{org_id}" if org_id else "no_org"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="🎯 Сгенерировать челленджи",
                    callback_data=f"admin_generate_challenges_{org_id}" if org_id else "no_org"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="📊 Месячный отчет (PDF)",
                    callback_data="admin_monthly_report"
                )
            )
            
            
            builder.row(
                InlineKeyboardButton(
                    text="📊 Статистика команды",
                    callback_data=f"admin_view_stats_{org_id}" if org_id else "no_org"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="👥 Управление членами",
                    callback_data=f"admin_manage_members"
                )
            )

            builder.row(
                InlineKeyboardButton(
                    text="🕐 Часовой пояс",
                    callback_data="admin_change_timezone"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="💼 Управление вакансиями",
                    callback_data="admin_manage_vacancies"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="📨 Отправить рассылку",
                    callback_data="admin_send_broadcast"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="🏆 Лидерборд",
                    callback_data="admin_leaderboard"
                )
            )
            
            builder.row(
                InlineKeyboardButton(
                    text="📅 Расписание сообщений",
                    callback_data="admin_schedule_preview"
                )
            )
            
        finally:
            session.close()
        
        return builder.as_markup()
    
    def get_trainer_menu(self, ctx: AdminContext) -> InlineKeyboardMarkup:
        """Меню тренера (только для верифицированных)"""
        builder = InlineKeyboardBuilder()
        
        # Проверяем, верифицирован ли тренер
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == ctx.user_id).first()
            if not user or user.role != UserRole.TRAINER.value or not user.trainer_verified:
                # Если не верифицирован, показываем ограниченное меню
                builder.row(
                    InlineKeyboardButton(
                        text="⏳ Ожидание подтверждения",
                        callback_data="trainer_pending"
                    )
                )
                builder.row(
                    InlineKeyboardButton(
                        text="📊 Моя статистика",
                        callback_data="user_stats"
                    )
                )
                return builder.as_markup()
        finally:
            session.close()
        
        # Меню для верифицированного тренера
        builder.row(
            InlineKeyboardButton(
                text="⚡ Создать челлендж",
                callback_data="admin_create_challenge"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="📊 Статистика команды",
                callback_data="admin_view_stats"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="👥 Просмотр участников",
                callback_data="admin_manage_members"
            )
        )
        
        builder.row(
            InlineKeyboardButton(
                text="🏆 Лидерборд",
                callback_data="admin_leaderboard"
            )
        )

        builder.row(
            InlineKeyboardButton(
                text = 'Команды',
                callback_data='trainer_commands'
            )
        )
        
        return builder.as_markup()
    
    def get_main_menu(self, ctx: AdminContext) -> InlineKeyboardMarkup:
        """Главное меню в зависимости от роли"""
        
        # Константы ролей (все возможные варианты написания)
        SUPER_ADMIN_ROLES = {"super_admin", "superadmin", "super admin", "super", "суперадмин"}
        ORG_ADMIN_ROLES = {"org_admin", "organization_admin", "organization admin", "org admin", "admin", "админ"}
        TRAINER_ROLES = {"trainer", "тренер", "coach"}
        
        if not ctx.user_role:
            return self.get_trainer_menu(ctx)
        
        user_role_normalized = ctx.user_role.lower().strip().replace("_", " ").replace("-", " ")
        
        # Проверяем конфиг в первую очередь
        from config import load_config
        config = load_config()
        if ctx.user_id in config.admin_ids:
            return self.get_super_admin_menu(ctx)
        
        # Проверяем по ролям
        if any(role in user_role_normalized for role in SUPER_ADMIN_ROLES):
            return self.get_super_admin_menu(ctx)
        elif any(role in user_role_normalized for role in ORG_ADMIN_ROLES):
            return self.get_org_admin_menu(ctx)
        elif any(role in user_role_normalized for role in TRAINER_ROLES):
            return self.get_trainer_menu(ctx)
        else:
            # Запасной вариант - проверка прав
            if ctx.has_permission(AdminPermission.VIEW_ALL_ORGS):
                return self.get_super_admin_menu(ctx)
            elif ctx.has_permission(AdminPermission.MANAGE_MEMBERS):
                return self.get_org_admin_menu(ctx)
            else:
                return self.get_trainer_menu(ctx)
    
    def get_back_button(self, target: str = "main") -> InlineKeyboardMarkup:
        """Кнопка возврата"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"admin:back:{target}"
            )
        )
        return builder.as_markup()
    
    def get_org_selection_menu(self, ctx: AdminContext) -> Optional[InlineKeyboardMarkup]:
        """Меню выбора организации для суперадминов"""
        if not ctx.has_permission(AdminPermission.VIEW_ALL_ORGS):
            return None
        
        from database import get_session, Organization
        
        session = get_session()
        try:
            orgs = session.query(Organization).filter(
                Organization.org_type != "super_admins"
            ).order_by(Organization.name).all()
            
            if not orgs:
                return None
            
            builder = InlineKeyboardBuilder()
            
            for org in orgs:
                builder.row(
                    InlineKeyboardButton(
                        text=f"🏢 {org.name}",
                        callback_data=f"admin:select_org:{org.id}"
                    )
                )
            
            builder.row(
                InlineKeyboardButton(
                    text="◀️ Назад",
                    callback_data="admin:back:main"
                )
            )
            
            return builder.as_markup()
            
        finally:
            session.close()

menu_manager = AdminMenuManager()