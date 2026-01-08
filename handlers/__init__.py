from aiogram import Dispatcher
from .start import register_start_handlers
from .registration import register_registration_handlers
from .profile import register_profile_handlers
from .activity import register_activity_handlers
from .vacancies import register_vacancies_handlers
from .common import register_common_handlers
from .ai import router as ai_router
from .admins import get_admin_router 
from .reports import router as report_router
from .surveys import router as surveys_router


def register_all_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    register_start_handlers(dp)
    register_registration_handlers(dp)
    register_profile_handlers(dp)
    register_activity_handlers(dp)
    register_vacancies_handlers(dp)
    register_common_handlers(dp)

    admin_router = get_admin_router()
    dp.include_router(admin_router)
    dp.include_router(ai_router)
    dp.include_router(report_router)
    dp.include_router(surveys_router)
