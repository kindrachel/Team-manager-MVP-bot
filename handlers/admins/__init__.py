from aiogram import Router, Dispatcher
from .permissions import AdminPermission, require_admin, AdminContext
from .menu_manager import menu_manager

__all__ = ['get_admin_router', 'AdminPermission', 'require_admin', 'AdminContext', 'menu_manager']

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

def register_all_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    
    try:
        admin_router = get_admin_router()
        dp.include_router(admin_router)
        print("✅ Админ-роутер подключен")
    except Exception as e:
        print(f"❌ Ошибка подключения админ-роутера: {e}")

def get_admin_router() -> Router:
    """Создать и настроить роутер админ-панели"""
    admin_router = Router()
    
    # Импортируем каждый модуль явно
    try:
        from .modules.challenges import router as challenges_router
        admin_router.include_router(challenges_router)
        print("✅ challenges загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить challenges: {e}")
    
    try:
        from .modules.members import router as members_router
        admin_router.include_router(members_router)
        print("✅ members загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить members: {e}")
    
    try:
        from .modules.statistics import router as statistics_router
        admin_router.include_router(statistics_router)
        print("✅ statistics загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить statistics: {e}")
    
    try:
        from .modules.vacancies import router as vacancies_router
        admin_router.include_router(vacancies_router)
        print("✅ vacancies загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить vacancies: {e}")
    
    try:
        from .modules.broadcast import router as broadcast_router
        admin_router.include_router(broadcast_router)
        print("✅ broadcast загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить broadcast: {e}")
    
    try:
        from .modules.schedule import router as schedule_router
        admin_router.include_router(schedule_router)
        print("✅ schedule загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить schedule: {e}")
    
    try:
        from .modules.system import router as system_router
        admin_router.include_router(system_router)
        print("✅ system загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить system: {e}")
    
    try:
        from .modules.organizations import router as organisation_router
        admin_router.include_router(organisation_router)
        print("✅ organisation загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить organisation: {e}")

    try:
        from .modules.timezone import router as timezone_router
        admin_router.include_router(timezone_router)
        print("✅ timezone загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить timezone: {e}")

    try:
        from .modules.verify import router as verify_router
        admin_router.include_router(verify_router)
        print("✅ verify загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить verify: {e}")

    try:
        from .modules import metrics
        admin_router.include_router(metrics.router)
        print("✅ metrics загружен")
    except ImportError as e:
        print(f"⚠️ Не удалось загрузить metrics: {e}")
        print(f"Ошибка: {e}")
    
    
    return admin_router

# Экспортируем основные объекты
from .permissions import AdminPermission, require_admin, AdminContext
from .menu_manager import menu_manager