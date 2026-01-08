import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class BotConfig:
    """Конфигурация бота"""
    
    def __init__(self):
        self.token = os.getenv("BOT_TOKEN", "")
        
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.admin_ids: List[int] = []
        if admin_ids_str:
            for admin_id in admin_ids_str.split(','):
                try:
                    self.admin_ids.append(int(admin_id.strip()))
                except ValueError:
                    print(f"⚠️ Неверный формат admin_id: {admin_id}")
        
        self.database_url = os.getenv("DATABASE_URL", "postgresql://postgres:new_password_123@localhost:5432/team_bot_db")
        self.huggingface_api_key = os.getenv('HUGGINGFACE_API_KEY', '')

def load_config() -> BotConfig:
    """Загрузить конфигурацию"""
    return BotConfig()