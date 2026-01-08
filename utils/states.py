from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_direction = State()
    waiting_for_sport_type = State()
    waiting_for_org_selection = State()
    waiting_for_phone = State()
    waiting_for_position = State()
    waiting_for_custom_position = State()
    waiting_for_role = State()
    waiting_for_name_confirmation = State()
    waiting_for_profile_photo = State()
    waiting_for_phone_confirmation = State()

class AdminStates(StatesGroup):
    waiting_for_challenge_text = State()
    waiting_for_energy = State()
    waiting_for_sleep = State()
    waiting_for_readiness = State()
    waiting_for_mood = State()
    waiting_for_points = State()
    waiting_for_challenge_points = State()  
    waiting_for_challenge_confirmation = State()
    waiting_for_org_selection = State()

class SurveyStates(StatesGroup):
    waiting_for_sleep = State()
    waiting_for_energy = State()
    waiting_for_readiness = State()
    waiting_for_mood = State()
    waiting_for_challenge_result = State()
    waiting_for_post_training = State()

class ChallengeStates(StatesGroup):
    waiting_for_schedule = State()
    generated_challenges = State()

class ChallengeWaitStates(StatesGroup):
    """Состояния для работы с челленджами"""
    waiting_for_custom_challenge = State()
    waiting_for_custom_points = State()

class VacancyStates(StatesGroup):
    waiting_for_vacancy_title = State()
    waiting_for_vacancy_company = State()
    waiting_for_vacancy_type = State()
    waiting_for_vacancy_description = State()
    waiting_for_vacancy_contact = State()
    waiting_for_vacancy_confirm = State()

class CreateOrganizationStates(StatesGroup):
    WAITING_FOR_NAME = State()      
    WAITING_FOR_TYPE = State()        
    WAITING_FOR_ADMIN = State()      
    CONFIRMATION = State()            

class TimezoneStates(StatesGroup):
    waiting_timezone = State()  
    waiting_confirmation = State() 

class BroadcastStates(StatesGroup):
    waiting_for_text = State()        
    waiting_confirmation = State()    
    waiting_for_time = State() 

class TimeSettingStates(StatesGroup):
    waiting_for_time = State()
    waiting_for_message_text = State()

class ScheduleEditStates(StatesGroup):
    """Состояния для редактирования расписания"""
    waiting_for_time = State()
    waiting_for_text = State()
    waiting_for_title = State()
    waiting_for_new_schedule = State()

class RoleManagementStates(StatesGroup):
    waiting_for_target_user = State()
    waiting_for_role_selection = State()

class MetricsStates(StatesGroup):
    """Состояния для оценки метрик"""
    waiting_for_technical = State()
    waiting_for_physical = State()
    waiting_for_mental = State()
    waiting_for_notes = State()