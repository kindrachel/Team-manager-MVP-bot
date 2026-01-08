from middlewares.middlewares import CacheMiddleware
from middlewares.autoregister import ensure_super_admin_exists
import os
import asyncio
import logging
import sys
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Создаем Flask сервер для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is running on Render"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    """Запуск Flask сервера в отдельном потоке"""
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Оригинальный код продолжается ниже...
from middlewares.middlewares import CacheMiddleware
from middlewares.autoregister import ensure_super_admin_exists
from services.timezone_scheduler import TimezoneMessageScheduler

TEMP_DIR = "temp_reports"
os.makedirs(TEMP_DIR, exist_ok=True)

if sys.platform == 'win32':
    try:
        os.system('chcp 65001 > nul')
    except:
        pass
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def cleanup_pending_challenges(bot: Bot):
    """Фоновая задача для очистки устаревших записей"""
    logger.info("Запуск задачи очистки устаревших челленджей...")
    
    try:
        from services.challenge_storage import challenge_storage
        
        while True:
            try:
                cleaned = await challenge_storage.cleanup_expired()
                if cleaned > 0:
                    logger.info(f"Очищено {cleaned} просроченных записей")
                
                stats = await challenge_storage.get_statistics()
                logger.debug(f"Статистика хранилища: {stats}")
                
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки: {e}")
            
            # Спим 6 часов между проверками
            await asyncio.sleep(6 * 3600)
            
    except Exception as e:
        logger.error(f"Критическая ошибка задачи очистки: {e}")

async def check_and_send_scheduled_challenges(bot: Bot):
    """Фоновая задача для проверки и отправки запланированных челленджей"""
    logger.info("Запуск задачи проверки запланированных челленджей...")
    
    try:
        from services.challenge_sheduler import ChallengeScheduler
        
        # Создаем и запускаем планировщик
        scheduler = ChallengeScheduler(bot)
        await scheduler.start()
        
        logger.info("✅ Задача проверки запланированных челленджей запущена")
        
    except Exception as e:
        logger.error(f"Ошибка запуска задачи проверки челленджей: {e}")

async def bot_main():
    """Главная функция бота"""
    try:
        logger.info("🚀 Запуск бота...")
        await ensure_super_admin_exists()
        
        logger.info("1. Загружаю конфигурацию...")
        try:
            from config import load_config
            config = load_config()
            logger.info(f"✅ Конфигурация загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            raise
        
        logger.info("2. Инициализирую бота...")
        try:
            storage = MemoryStorage()
            bot = Bot(token=config.token) 
            dp = Dispatcher(storage=storage)
            logger.info("✅ Бот и диспетчер инициализированы")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота: {e}")
            raise
        
        logger.info("3. Регистрирую мидлвари...")
        try:
            from middlewares import (
                ClearStateMiddleware,
                AutoRegisterUserMiddleware,
                LoggingMiddleware,
                AntiFloodMiddleware
            )
            
            dp.update.middleware(LoggingMiddleware())
            dp.update.middleware(AntiFloodMiddleware(delay=0.3))
            dp.update.middleware(ClearStateMiddleware())
            dp.update.middleware(AutoRegisterUserMiddleware())
            
            dp.update.middleware(CacheMiddleware())
            
            logger.info("✅ Мидлвари зарегистрированы")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка регистрации мидлварей: {e}")
            logger.info("⚠️ Продолжаю без мидлварей...")
        
        logger.info("4. Инициализирую базу данных...")
        try:
            from database import init_db
            init_db()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
        
        logger.info("5. Регистрирую обработчики...")
        try:
            from handlers import register_all_handlers
            register_all_handlers(dp)
            
            logger.info(f"✅ Все обработчики зарегистрированы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации обработчиков: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        logger.info("6. Запускаю планировщик...")
        try:
            from services import SchedulerManager
            scheduler_manager = SchedulerManager(bot)
            scheduler_manager.start()
            logger.info("✅ Планировщик запущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска планировщика: {e}")
            logger.info("⚠️ Продолжаю без планировщика...")
        
        logger.info("7. Запускаю планировщик сообщений...")
        try:
            message_scheduler = TimezoneMessageScheduler(bot)
            asyncio.create_task(message_scheduler.start())
            logger.info("✅ Планировщик сообщений запущен")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика сообщений: {e}")
            logger.info("⚠️ Продолжаю без планировщика сообщений...")

        logger.info("8. Запускаю планировщик челленджей...")
        try:
            # Здесь запускаем обновленную версию
            asyncio.create_task(check_and_send_scheduled_challenges(bot))
            logger.info("✅ Планировщик челленджей запущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска планировщика челленджей: {e}")
            logger.info("⚠️ Продолжаю без планировщика челленджей...")

        logger.info("9. Запускаю очистку устаревших данных...")
        try:
            asyncio.create_task(cleanup_pending_challenges(bot))
            logger.info("✅ Очистка устаревших данных запущена")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска очистки: {e}")
        
        logger.info("10. Инициализирую шрифты для PDF отчетов...")
        try:
            def init_dejavu_fonts():
                """Инициализация DejaVu шрифтов (поддерживают кириллицу)"""
                try:
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    from reportlab.lib.fonts import addMapping
                    import os
                    
                    fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
                    dejavu_regular = os.path.join(fonts_dir, "DejaVuSans.ttf")
                    dejavu_bold = os.path.join(fonts_dir, "DejaVuSans-Bold.ttf")
                    
                    if os.path.exists(dejavu_regular):
                        pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_regular))
                        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', dejavu_bold))
                        
                        addMapping('DejaVuSans', 0, 0, 'DejaVuSans')       
                        addMapping('DejaVuSans', 1, 0, 'DejaVuSans-Bold')   
                        
                        logger.info("✅ Шрифты DejaVu загружены (поддержка кириллицы)")
                        return True
                    else:
                        logger.warning("⚠️ Шрифты DejaVu не найдены. Использую Helvetica.")
                        return False
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка загрузки шрифтов: {e}")
                    return False
            
            fonts_loaded = init_dejavu_fonts()
            
            if fonts_loaded:
                from services.report_formatter import set_fallback_font
                set_fallback_font('DejaVuSans')
                logger.info("✅ Шрифт DejaVuSans установлен для PDF отчетов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации шрифтов: {e}")

        logger.info("11. Проверяю доступные шрифты...")
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            registered_fonts = pdfmetrics.getRegisteredFontNames()
            logger.info(f"📝 Зарегистрированные шрифты: {registered_fonts}")
            
            if 'DejaVuSans' in registered_fonts:
                logger.info("✅ DejaVuSans доступен")
            else:
                logger.warning("⚠️ DejaVuSans НЕ зарегистрирован!")
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки шрифтов: {e}")
        
        logger.info("🎉 Все системы готовы! Запускаю опрос сообщений...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        logger.info("✅ Бот остановлен")

async def main():
    """Основная функция - запускает Flask сервер и бота"""
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"✅ Flask сервер запущен на порту {os.getenv('PORT', 8080)}")
    
    # Запускаем бота
    await bot_main()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
