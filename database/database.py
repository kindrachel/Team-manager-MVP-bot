from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, UserRole
import urllib.parse


engine = None
SessionLocal = None

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

def get_database_url():
    """Получить URL базы данных"""
    try:
        from config import load_config
        config = load_config()
        url = config.database_url
        
        # Проверяем и исправляем кодировку
        if isinstance(url, bytes):
            url = url.decode('utf-8')
        
        return url
        
    except Exception as e:
        print(f"⚠️ Не удалось загрузить конфиг: {e}")
        # Fallback на локальную базу
        password = "Subara123"
        encoded_password = urllib.parse.quote(password, safe='')
        return f"postgresql://postgres:{encoded_password}@localhost:5432/team_manager_db"

def init_engine():
    """Инициализировать engine и сессию"""
    global engine, SessionLocal
    
    if engine is None:
        DATABASE_URL = get_database_url()
        
        # Маскируем пароль для логов
        safe_url = DATABASE_URL
        if '@' in safe_url:
            protocol, rest = safe_url.split('://', 1)
            if ':' in rest.split('@')[0]:
                user_pass, host = rest.split('@', 1)
                if ':' in user_pass:
                    user, password = user_pass.split(':', 1)
                    safe_url = f"{protocol}://{user}:*****@{host}"
        
        print(f"🔗 Подключаюсь к БД: {safe_url}")
        
        # Создаем engine
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Создание таблиц"""
    try:
        # Инициализируем engine
        init_engine()
        
        # Создаем все таблицы
        Base.metadata.create_all(engine)
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        return False

def get_session():
    """Получить сессию для запросов"""
    # Убедимся, что engine инициализирован
    if engine is None:
        init_engine()
    
    return SessionLocal()