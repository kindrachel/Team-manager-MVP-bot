import os
import asyncio
import logging
import sys
import signal
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Глобальные переменные
logger = None
http_runner = None

# Обработка SIGTERM от Render
def handle_sigterm(signum, frame):
    logger.info(f"🛑 Received SIGTERM signal ({signum}), shutting down gracefully...")
    sys.exit(0)

# Создаем aiohttp сервер для Render
async def handle_root(request):
    return web.Response(text="✅ Bot is running on Render")

async def handle_health(request):
    return web.Response(text="OK")

async def start_http_server():
    """Запуск HTTP сервера для Render"""
    global http_runner
    
    app = web.Application()
    app.router.add_get('/', handle_root)
    app.router.add_get('/health', handle_health)
    
    port = int(os.getenv("PORT", 10000))  # Render использует 10000
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    http_runner = runner
    logger.info(f"✅ HTTP сервер запущен на порту {port}")
    return runner

async def stop_http_server():
    """Остановка HTTP сервера"""
    global http_runner
    if http_runner:
        await http_runner.cleanup()
        logger.info("✅ HTTP сервер остановлен")

# Инициализация логгера
def setup_logging():
    global logger
    
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
    
    # Регистрируем обработчик SIGTERM
    signal.signal(signal.SIGTERM, handle_sigterm)
    
    return logger

# Создание временных директорий
def create_temp_dirs():
    TEMP_DIRS = ["temp_reports", "temp_data", "logs"]
    for dir_name in TEMP_DIRS:
        os.makedirs(dir_name, exist_ok=True)
        logger.info(f"✅ Создана директория: {dir_name}")

# Фоновая задача для очистки устаревших записей
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

# Фоновая задача для проверки запланированных челленджей
async def check_and_send_scheduled_challenges(bot: Bot):
    """Фоновая задача для проверки и отправки запланированных челленджей"""
    logger.info("Запуск задачи проверки запланированных челленджей...")
    
    try:
        from services.challenge_sheduler import ChallengeScheduler
        
        scheduler = ChallengeScheduler(bot)
        await scheduler.start()
        
        logger.info("✅ Задача проверки запланированных челленджей запущена")
        
    except Exception as e:
        logger.error(f"Ошибка запуска задачи проверки челленджей: {e}")

# Инициализация шрифтов для PDF
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

# Основная функция бота
async def bot_main():
    """Главная функция бота"""
    try:
        logger.info("🚀 Запуск бота...")
        
        # 1. Проверяем супер-админа
        try:
            from middlewares.autoregister import ensure_super_admin_exists
            await ensure_super_admin_exists()
            logger.info("✅ Супер-админ проверен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки супер-админа: {e}")
        
        # 2. Загружаем конфигурацию
        logger.info("Загружаю конфигурацию...")
        try:
            from config import load_config
            config = load_config()
            logger.info("✅ Конфигурация загружена")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфигурации: {e}")
            raise
        
        # 3. Инициализируем бота
        logger.info("Инициализирую бота...")
        try:
            storage = MemoryStorage()
            bot = Bot(token=config.token) 
            dp = Dispatcher(storage=storage)
            logger.info("✅ Бот и диспетчер инициализированы")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации бота: {e}")
            raise
        
        # 4. Регистрируем мидлвари
        logger.info("Регистрирую мидлвари...")
        try:
            from middlewares import (
                ClearStateMiddleware,
                AutoRegisterUserMiddleware,
                LoggingMiddleware,
                AntiFloodMiddleware
            )
            from middlewares.middlewares import CacheMiddleware
            
            dp.update.middleware(LoggingMiddleware())
            dp.update.middleware(AntiFloodMiddleware(delay=0.3))
            dp.update.middleware(ClearStateMiddleware())
            dp.update.middleware(AutoRegisterUserMiddleware())
            dp.update.middleware(CacheMiddleware())
            
            logger.info("✅ Мидлвари зарегистрированы")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка регистрации мидлварей: {e}")
            logger.info("⚠️ Продолжаю без мидлварей...")
        
        # 5. Инициализируем базу данных
        logger.info("Инициализирую базу данных...")
        try:
            from database import init_db
            init_db()
            logger.info("✅ База данных инициализирована")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            raise
        
        # 6. Регистрируем обработчики
        logger.info("Регистрирую обработчики...")
        try:
            from handlers import register_all_handlers
            register_all_handlers(dp)
            logger.info("✅ Все обработчики зарегистрированы")
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации обработчиков: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # 7. Запускаем планировщики
        logger.info("Запускаю планировщик...")
        try:
            from services import SchedulerManager
            scheduler_manager = SchedulerManager(bot)
            scheduler_manager.start()
            logger.info("✅ Планировщик запущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска планировщика: {e}")
        
        # 8. Запускаем планировщик сообщений
        logger.info("Запускаю планировщик сообщений...")
        try:
            from services.timezone_scheduler import TimezoneMessageScheduler
            message_scheduler = TimezoneMessageScheduler(bot)
            asyncio.create_task(message_scheduler.start())
            logger.info("✅ Планировщик сообщений запущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска планировщика сообщений: {e}")
        
        # 9. Запускаем планировщик челленджей
        logger.info("Запускаю планировщик челленджей...")
        asyncio.create_task(check_and_send_scheduled_challenges(bot))
        logger.info("✅ Планировщик челленджей запущен")
        
        # 10. Запускаем очистку устаревших данных
        logger.info("Запускаю очистку устаревших данных...")
        asyncio.create_task(cleanup_pending_challenges(bot))
        logger.info("✅ Очистка устаревших данных запущена")
        
        # 11. Инициализируем шрифты для PDF
        logger.info("Инициализирую шрифты для PDF отчетов...")
        fonts_loaded = init_dejavu_fonts()
        if fonts_loaded:
            try:
                from services.report_formatter import set_fallback_font
                set_fallback_font('DejaVuSans')
                logger.info("✅ Шрифт DejaVuSans установлен для PDF отчетов")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось установить шрифт: {e}")
        
        # 12. Запускаем бота
        logger.info("🎉 Все системы готовы! Запускаю опрос сообщений...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        raise

# Основная функция
async def main():
    """Основная функция - запускает всё"""
    try:
        # Настройка логирования
        setup_logging()
        
        # Создание временных директорий
        create_temp_dirs()
        
        # Запуск HTTP сервера
        await start_http_server()
        
        # Запуск бота
        await bot_main()
        
    except SystemExit:
        # Корректный выход по SIGTERM
        logger.info("✅ Завершение работы по сигналу")
    except KeyboardInterrupt:
        logger.info("⚠️ Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Останавливаем HTTP сервер
        await stop_http_server()
        logger.info("✅ Бот полностью остановлен")

if __name__ == '__main__':
    # Запуск асинхронного приложения
    asyncio.run(main())
