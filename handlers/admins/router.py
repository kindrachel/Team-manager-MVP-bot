from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database import get_session, User
from .permissions import require_admin, AdminContext, AdminPermission
from .menu_manager import menu_manager
import logging

logger = logging.getLogger(__name__)

router = Router()

@router.message(Command("admin"))
@require_admin()
async def admin_command(message: types.Message, admin_context: AdminContext):
    """Команда /admin"""
    await show_admin_menu(message, admin_context)

@router.message(F.text == "⚙️ Админ-панель")
@require_admin()
async def admin_button(message: types.Message, admin_context: AdminContext):
    """Кнопка админ-панели"""
    await show_admin_menu(message, admin_context)

@router.callback_query(F.data == 'admin_back:main')
async def back_to_main_from_challenges(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    from .modules.challenges import back_to_admin_menu
    await back_to_admin_menu(callback)

@router.callback_query(F.data == 'admin_manage_roles')
async def manage_roles_command (callback: types.CallbackQuery):
    from .modules.system import manage_role
    await manage_role(callback)

@router.callback_query(F.data == "admin_select_org")
@require_admin(AdminPermission.VIEW_ALL_ORGS)
async def select_org_menu(callback: types.CallbackQuery, admin_context: AdminContext):
    """Меню выбора организации"""
    kb = menu_manager.get_org_selection_menu(admin_context)
    
    if not kb:
        await callback.answer("❌ Нет доступных организаций", show_alert=True)
        return
    
    text = "🏢 *ВЫБЕРИТЕ ОРГАНИЗАЦИЮ*\n\nДля переключения между организациями"
    
    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("admin_select_org:"))
@require_admin(AdminPermission.SWITCH_ORGS)
async def switch_organization(callback: types.CallbackQuery, admin_context: AdminContext, state: FSMContext):
    """Переключиться на организацию"""
    org_id = int(callback.data.split(":")[-1])
    
    if admin_context.switch_org(org_id):
        # Сохраняем выбор в FSM
        await state.update_data(selected_org_id=org_id)
        
        await callback.answer(f"✅ Переключено", show_alert=True)
        await show_admin_menu(callback.message, admin_context, edit=True)
    else:
        await callback.answer("❌ Ошибка переключения", show_alert=True)


async def show_admin_menu(
    message: types.Message, 
    admin_context: AdminContext,
    edit: bool = False
):
    """Показать главное меню админки (разное для разных ролей)"""
    # Получаем информацию об организации
    org_name = "Неизвестная организация"
    org_stats = ""
    
    if admin_context.current_org_id:
        from database import get_session, Organization, User, UserRole
        session = get_session()
        try:
            org = session.query(Organization).filter(
                Organization.id == admin_context.current_org_id
            ).first()
            if org:
                org_name = org.name
                
                # Добавляем статистику для админов организаций
                if admin_context.user_role in [UserRole.ORG_ADMIN.value, UserRole.TRAINER.value]:
                    member_count = session.query(User).filter(
                        User.org_id == admin_context.current_org_id,
                        User.role == UserRole.MEMBER.value
                    ).count()
                    org_stats = f"👥 Участников: {member_count}\n"
                    
        finally:
            session.close()
    
    # Текст заголовка в зависимости от роли
    role_titles = {
        UserRole.SUPER_ADMIN.value: "👑 СУПЕРАДМИН",
        UserRole.ORG_ADMIN.value: "👨‍💼 АДМИНИСТРАТОР ОРГАНИЗАЦИИ",
        UserRole.TRAINER.value: "👨‍🏫 ТРЕНЕР"
    }
    
    role_title = role_titles.get(admin_context.user_role, "АДМИН")
    
    # Формируем текст
    text_parts = [f"{role_title}\n"]
    
    # Для суперадминов показываем текущую организацию
    if admin_context.current_org_id and admin_context.user_role == UserRole.SUPER_ADMIN.value:
        text_parts.append(f"🏢 Текущая организация: {org_name}\n")
    elif admin_context.user_role in [UserRole.ORG_ADMIN.value, UserRole.TRAINER.value]:
        text_parts.append(f"🏢 Организация: {org_name}\n")
        text_parts.append(org_stats)
    
    text_parts.append(f"👤 Вы: {message.from_user.full_name}\n\n")
    text_parts.append("Выберите действие:")
    
    text = "".join(text_parts)
    
    # Получаем соответствующее меню
    kb = menu_manager.get_main_menu(admin_context)
    
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")