from .main_menu import (
    main_menu_keyboard,
    admin_menu_keyboard,
    org_type_keyboard,
    energy_keyboard,
    mood_keyboard,
    sleep_quality_keyboard,
    readiness_keyboard,
    challenge_response_keyboard,
    yes_no_keyboard,
    profile_menu_keyboard,
    back_button_to_profile,
    back_to_activity_keyboard,
    back_button_to_vacansies,
    vacancies_menu_keyboard,
    vacancy_navigation_keyboard,
    no_action_button,
    admin_vacancy_menu_keyboard,
    premium_keyboard,
    update_member_fields_keyboard
)

# Добавьте импорт из ai_keyboards
from .ai_keyboard import (
    main_menu,
    challenge_types,
    report_types,
    progress_actions
)

__all__ = [
    'main_menu_keyboard',
    'admin_menu_keyboard',
    'org_type_keyboard',
    'energy_keyboard',
    'mood_keyboard',
    'sleep_quality_keyboard',
    'readiness_keyboard',
    'challenge_response_keyboard',
    'yes_no_keyboard',
    'profile_menu_keyboard',
    'back_button_to_profile',
    'back_to_activity_keyboard',
    'back_button_to_vacansies',
    'vacancies_menu_keyboard',
    'admin_vacancy_menu_keyboard',
    'premium_keyboard',
    'update_member_fields_keyboard',
    'vacancy_navigation_keyboard',
    'no_action_button',
    # AI клавиатуры
    'main_menu',
    'challenge_types',
    'report_types',
    'progress_actions'
]