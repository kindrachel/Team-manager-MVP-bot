from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from database import User, Organization, Challenge, get_session, UserRole, ChallengeStatus
from services import MESSAGE_TEMPLATES
from services.ai_challenge_planer import AIChallengePlanner
from services.challenge_storage import challenge_storage
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional
from utils.states import ScheduleEditStates
import logging
import random
import asyncio

router = Router()
logger = logging.getLogger(__name__)
challenge_planner = AIChallengePlanner()

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, time
import asyncio

from database import get_session
from database.models import MessageSchedule, User, UserRole, MessageScheduleStatus
from services.shedule_manager import ScheduleManager
from .members import is_admin

router = Router()

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, time
import asyncio
import logging
import re

from database import get_session
from database.models import User, UserRole, MessageSchedule, MessageScheduleStatus, Organization
from services.shedule_manager import ScheduleManager
from services.scheduler_service import MESSAGE_TEMPLATES
from .members import is_admin

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

router = Router()
logger = logging.getLogger(__name__)

# Константы
PAGE_SIZE = 5  # Количество сообщений на странице

class BotScheduler:
    """Планировщик задач бота"""
    
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        
    def start(self):
        """Запуск планировщика"""
        
        # 1. Основная проверка - каждый час
        self.scheduler.add_job(
            self._check_and_send_reminders,
            CronTrigger(minute=0, timezone="UTC"),  # Каждый час в 00 минут
            id="hourly_reminders",
            name="Напоминания каждый час",
            replace_existing=True
        )
        
        # 2. Для теста - каждые 10 минут
        self.scheduler.add_job(
            self._check_and_send_reminders,
            CronTrigger(minute="*/10", timezone="UTC"),
            id="test_reminders",
            name="Тест напоминаний каждые 10 мин",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("✅ Планировщик задач запущен")
        logger.info("⏰ Напоминания будут проверяться каждый час (в 18:00 по времени организации)")
    
    async def _check_and_send_reminders(self):
        """Проверяем и отправляем напоминания"""
        logger.info("⏰ Проверка напоминаний...")
        
        try:
            from services.reminder import SimpleReminderService
            service = SimpleReminderService(self.bot)
            await service.send_daily_reminders()
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминаний: {e}")
    
    def shutdown(self):
        """Остановка планировщика"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("🛑 Планировщик остановлен")


@router.callback_query(F.data == "admin_schedule_preview")
async def admin_schedule_preview(callback: types.CallbackQuery) -> None:
    """Главное меню управления расписанием"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Получаем часовой пояс организации
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        timezone = org.timezone if org else "Asia/Novosibirsk"
        
        # Получаем первую страницу расписаний
        schedules, current_page, total_pages = ScheduleManager.get_schedules_page(
            user.org_id, page=0, page_size=PAGE_SIZE
        )
        
        if not schedules:
            # Создаем расписания по умолчанию
            await callback.message.edit_text(
                "📅 Настройка расписания сообщений\n\n"
                "У вас еще нет настроенных сообщений.\n"
                "Создаем расписание по умолчанию..."
            )
            
            ScheduleManager.create_default_schedules(user.org_id)
            
            # Получаем обновленный список
            schedules, current_page, total_pages = ScheduleManager.get_schedules_page(
                user.org_id, page=0, page_size=PAGE_SIZE
            )
        
        # Формируем текст
        schedule_text = f"📅 УПРАВЛЕНИЕ РАСПИСАНИЕМ\n\n"
        schedule_text += f"🏢 Организация: {org.name if org else 'Неизвестно'}\n"
        schedule_text += f"🌍 Часовой пояс: {timezone}\n"
        schedule_text += f"📊 Сообщений: {len(schedules)} (стр. {current_page + 1}/{max(1, total_pages)})\n\n"
        
        for schedule in schedules:
            status = "✅" if schedule.status == MessageScheduleStatus.ACTIVE.value else "⏸️"
            time_str = schedule.scheduled_time.strftime("%H:%M")
            short_content = schedule.content[:60] + "..." if len(schedule.content) > 60 else schedule.content
            
            schedule_text += (
                f"{status} ⏰ {time_str} - {schedule.title}\n"
                f"   📝 {short_content}\n"
                f"   🆔 ID: {schedule.id}\n\n"
            )
        
        # Создаем клавиатуру
        keyboard_buttons = []
        
        # Кнопки навигации, если есть несколько страниц
        if total_pages > 1:
            nav_buttons = []
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data=f"schedule_page_{current_page - 1}"
                ))
            
            nav_buttons.append(InlineKeyboardButton(
                text=f"{current_page + 1}/{total_pages}", 
                callback_data="schedule_page_info"
            ))
            
            if current_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="Вперед ▶️", 
                    callback_data=f"schedule_page_{current_page + 1}"
                ))
            
            keyboard_buttons.append(nav_buttons)
        
        # Кнопки управления
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(text="✏️ Выбрать для редактирования", callback_data="schedule_select_edit"),
                InlineKeyboardButton(text="➕ Добавить сообщение", callback_data="schedule_add_new")
            ],
            [
                InlineKeyboardButton(text="📤 Отправить все сейчас", callback_data="schedule_send_all"),
                InlineKeyboardButton(text="⚙️ Часовой пояс", callback_data="admin_change_timezone")
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_admin_panel")
            ]
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(schedule_text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка показа расписания: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")
    finally:
        session.close()

@router.callback_query(F.data.startswith("schedule_page_"))
async def schedule_pagination(callback: types.CallbackQuery) -> None:
    """Пагинация расписания"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    try:
        # Получаем номер страницы
        data = callback.data
        if data == "schedule_page_info":
            await callback.answer("Текущая страница")
            return
        
        page_num = int(data.split("_")[2])
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Получаем часовой пояс
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        timezone = org.timezone if org else "Asia/Novosibirsk"
        
        # Получаем страницу
        schedules, current_page, total_pages = ScheduleManager.get_schedules_page(
            user.org_id, page=page_num, page_size=PAGE_SIZE
        )
        
        if not schedules:
            await callback.message.edit_text(
                "📭 Нет сообщений на этой странице",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ К первой странице", callback_data="schedule_page_0")
                ]])
            )
            return
        
        # Формируем текст
        schedule_text = f"📅 УПРАВЛЕНИЕ РАСПИСАНИЕМ\n\n"
        schedule_text += f"🏢 Организация: {org.name if org else 'Неизвестно'}\n"
        schedule_text += f"🌍 Часовой пояс: {timezone}\n"
        schedule_text += f"📊 Сообщений: {len(schedules)} (стр. {current_page + 1}/{max(1, total_pages)})\n\n"
        
        for schedule in schedules:
            status = "✅" if schedule.status == MessageScheduleStatus.ACTIVE.value else "⏸️"
            time_str = schedule.scheduled_time.strftime("%H:%M")
            short_content = schedule.content[:60] + "..." if len(schedule.content) > 60 else schedule.content
            
            schedule_text += (
                f"{status} ⏰ {time_str} - {schedule.title}\n"
                f"   📝 {short_content}\n"
                f"   🆔 ID: {schedule.id}\n\n"
            )
        
        # Создаем клавиатуру с пагинацией
        keyboard_buttons = []
        
        # Кнопки навигации
        if total_pages > 1:
            nav_buttons = []
            if current_page > 0:
                nav_buttons.append(InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data=f"schedule_page_{current_page - 1}"
                ))
            
            nav_buttons.append(InlineKeyboardButton(
                text=f"{current_page + 1}/{total_pages}", 
                callback_data="schedule_page_info"
            ))
            
            if current_page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton(
                    text="Вперед ▶️", 
                    callback_data=f"schedule_page_{current_page + 1}"
                ))
            
            keyboard_buttons.append(nav_buttons)
        
        # Кнопки управления
        keyboard_buttons.extend([
            [
                InlineKeyboardButton(text="✏️ Выбрать для редактирования", callback_data="schedule_select_edit"),
                InlineKeyboardButton(text="➕ Добавить", callback_data="schedule_add_new")
            ],
            [
                InlineKeyboardButton(text="📤 Отправить все", callback_data="schedule_send_all"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_schedule_preview")
            ]
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(schedule_text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка пагинации: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке страницы")
    finally:
        if 'session' in locals():
            session.close()

@router.callback_query(F.data == "schedule_select_edit")
async def schedule_select_edit(callback: types.CallbackQuery) -> None:
    """Выбор сообщения для редактирования"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Получаем все расписания
        schedules = session.query(MessageSchedule).filter(
            MessageSchedule.org_id == user.org_id
        ).order_by(
            MessageSchedule.order_index,
            MessageSchedule.scheduled_time
        ).all()
        
        if not schedules:
            await callback.message.edit_text(
                "📭 Нет сообщений для редактирования",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview")
                ]])
            )
            return
        
        # Создаем клавиатуру с кнопками для каждого сообщения
        keyboard_buttons = []
        
        for schedule in schedules:
            status = "✅" if schedule.status == MessageScheduleStatus.ACTIVE.value else "⏸️"
            time_str = schedule.scheduled_time.strftime("%H:%M")
            btn_text = f"{status} {time_str} - {schedule.title[:20]}..."
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"schedule_edit_{schedule.id}"
                )
            ])
        
        # Кнопки навигации
        keyboard_buttons.append([
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview"),
            InlineKeyboardButton(text="➕ Новое", callback_data="schedule_add_new")
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            "✏️ ВЫБЕРИТЕ СООБЩЕНИЕ ДЛЯ РЕДАКТИРОВАНИЯ\n\n"
            "Нажмите на сообщение, которое хотите изменить:",
            reply_markup=kb
        )
        
    except Exception as e:
        logger.error(f"Ошибка выбора редактирования: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке")
    finally:
        session.close()

@router.callback_query(F.data.startswith("schedule_edit_"))
async def schedule_edit_detail(callback: types.CallbackQuery) -> None:
    """Детальное редактирование сообщения"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    try:
        schedule_id = int(callback.data.split("_")[2])
        
        schedule = ScheduleManager.get_schedule_by_id(schedule_id)
        if not schedule:
            await callback.message.edit_text("❌ Сообщение не найдено")
            return
        
        # Проверяем права на организацию
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or user.org_id != schedule.org_id:
            await callback.message.edit_text("❌ Нет прав на редактирование")
            return
        
        # Получаем часовой пояс
        org = session.query(Organization).filter(Organization.id == schedule.org_id).first()
        timezone = org.timezone if org else "Asia/Novosibirsk"
        
        # Форматируем время
        time_str = schedule.scheduled_time.strftime("%H:%M")
        status_text = "✅ Активно" if schedule.status == MessageScheduleStatus.ACTIVE.value else "⏸️ Приостановлено"
        
        # Показываем больше текста
        content_preview = schedule.content[:300] + "..." if len(schedule.content) > 300 else schedule.content
        
        message_text = (
            f"✏️ РЕДАКТИРОВАНИЕ СООБЩЕНИЯ\n\n"
            f"🆔 ID: {schedule.id}\n"
            f"⏰ Время отправки: {time_str} (пояс: {timezone})\n"
            f"📌 Заголовок: {schedule.title}\n"
            f"📝 Содержание:\n{content_preview}\n\n"
            f"📊 Статус: {status_text}\n"
            f"📅 Режим: {'Ежедневно' if schedule.is_daily else f'День недели: {schedule.day_of_week}'}"
        )
        
        # Создаем клавиатуру действий
        keyboard_buttons = [
            [
                InlineKeyboardButton(text="📝 Изменить текст", callback_data=f"schedule_change_text_{schedule.id}"),
                InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"schedule_change_time_{schedule.id}")
            ],
            [
                InlineKeyboardButton(
                    text="🔄 " + ("Приостановить" if schedule.status == MessageScheduleStatus.ACTIVE.value else "Активировать"),
                    callback_data=f"schedule_toggle_{schedule.id}"
                ),
                InlineKeyboardButton(text="📤 Отправить сейчас", callback_data=f"schedule_send_now_{schedule.id}")
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"schedule_delete_{schedule.id}"),
                InlineKeyboardButton(text="◀️ Назад", callback_data="schedule_select_edit")
            ]
        ]
        
        kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(message_text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка редактирования: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке")
    finally:
        if 'session' in locals():
            session.close()

@router.callback_query(F.data.startswith("schedule_change_time_"))
async def schedule_change_time_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Начало изменения времени - устанавливаем состояние"""
    user_id = callback.from_user.id
    
    try:
        schedule_id = int(callback.data.split("_")[3])
        
        # Получаем расписание для проверки
        schedule = ScheduleManager.get_schedule_by_id(schedule_id)
        if not schedule:
            await callback.answer("❌ Сообщение не найдено", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            schedule_id=schedule_id,
            current_time=schedule.scheduled_time.strftime("%H:%M"),
            title=schedule.title
        )
        await state.set_state(ScheduleEditStates.waiting_for_time)
        
        # Показываем инструкцию
        message_text = (
            f"⏰ ИЗМЕНЕНИЕ ВРЕМЕНИ ОТПРАВКИ\n\n"
            f"Сообщение: {schedule.title}\n"
            f"Текущее время: {schedule.scheduled_time.strftime('%H:%M')}\n\n"
            f"Введите новое время в формате *ЧЧ:ММ* (24 часа):\n"
            f"Примеры: 09:30, 14:00, 18:45\n\n"
            f"Для отмены нажмите /cancel"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Отмена", callback_data=f"schedule_edit_{schedule_id}")
        ]])
        
        await callback.message.edit_text(message_text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка начала изменения времени: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке")

@router.message(ScheduleEditStates.waiting_for_time, F.text)
async def process_time_input(message: Message, state: FSMContext) -> None:
    """Обработка введенного времени"""
    try:
        time_str = message.text.strip()
        
        # Проверяем формат времени
        time_pattern = r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$'
        if not re.match(time_pattern, time_str):
            await message.answer(
                "❌ *Неверный формат времени!*\n\n"
                "Пожалуйста, введите время в формате *ЧЧ:ММ* (24 часа):\n"
                "• Часы: от 00 до 23\n"
                "• Минуты: от 00 до 59\n\n"
                "Примеры: 09:30, 14:00, 18:45\n\n"
                "Для отмены нажмите /cancel",
                parse_mode="Markdown"
            )
            return
        
        # Парсим время
        hours, minutes = map(int, time_str.split(':'))
        new_time = time(hours, minutes)
        
        # Получаем данные из состояния
        data = await state.get_data()
        schedule_id = data.get('schedule_id')
        
        if not schedule_id:
            await message.answer("❌ Ошибка: данные сессии утеряны")
            await state.clear()
            return
        
        # Обновляем время в базе данных
        success = ScheduleManager.update_schedule_time(schedule_id, new_time)
        
        if success:
            schedule = ScheduleManager.get_schedule_by_id(schedule_id)
            
            await message.answer(
                f"✅ *Время успешно обновлено!*\n\n"
                f"📝 Сообщение: {schedule.title}\n"
                f"⏰ Новое время: {new_time.strftime('%H:%M')}\n\n"
                f"Сообщение будет отправляться ежедневно в указанное время.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✏️ Вернуться к редактированию", 
                                       callback_data=f"schedule_edit_{schedule_id}")
                ]])
            )
        else:
            await message.answer("❌ Ошибка при обновлении времени")
        
        await state.clear()
        
    except ValueError as e:
        await message.answer(
            "❌ *Неверный формат времени!*\n\n"
            "Используйте только цифры и двоеточие.\n"
            "Пример: 14:30",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка обработки времени: {e}")
        await message.answer("❌ Ошибка при обновлении времени")
        await state.clear()

@router.callback_query(F.data.startswith("schedule_change_text_"))
async def schedule_change_text_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Начало изменения текста - устанавливаем состояние"""
    user_id = callback.from_user.id
    
    try:
        schedule_id = int(callback.data.split("_")[3])
        
        # Получаем расписание
        schedule = ScheduleManager.get_schedule_by_id(schedule_id)
        if not schedule:
            await callback.answer("❌ Сообщение не найдено", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            schedule_id=schedule_id,
            current_title=schedule.title,
            current_content=schedule.content[:500]
        )
        await state.set_state(ScheduleEditStates.waiting_for_text)
        
        # Показываем инструкцию
        content_preview = schedule.content[:300] + "..." if len(schedule.content) > 300 else schedule.content
        
        message_text = (
            f"📝 ИЗМЕНЕНИЕ ТЕКСТА СООБЩЕНИЯ\n\n"
            f"Сообщение: {schedule.title}\n"
            f"Текущее время: {schedule.scheduled_time.strftime('%H:%M')}\n\n"
            f"*Текущий текст:*\n{content_preview}\n\n"
            f"*Отправьте новый текст сообщения.*\n\n"
            f"Поддерживается форматирование Markdown:\n"
            f"• *жирный текст*\n"
            f"• _курсив_\n"
            f"• [ссылка](https://example.com)\n\n"
            f"Для отмены нажмите /cancel"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Отмена", callback_data=f"schedule_edit_{schedule_id}")
        ]])
        
        await callback.message.edit_text(message_text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка начала изменения текста: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке")

@router.message(ScheduleEditStates.waiting_for_text, F.text)
async def process_text_input(message: Message, state: FSMContext) -> None:
    """Обработка введенного текста"""
    try:
        new_text = message.text.strip()
        
        if len(new_text) < 3:
            await message.answer(
                "❌ *Текст слишком короткий!*\n\n"
                "Минимальная длина сообщения - 3 символа.\n"
                "Пожалуйста, введите более содержательный текст.",
                parse_mode="Markdown"
            )
            return
        
        if len(new_text) > 4000:
            await message.answer(
                "❌ *Текст слишком длинный!*\n\n"
                "Максимальная длина сообщения - 4000 символов.\n"
                "Сократите текст и попробуйте снова.",
                parse_mode="Markdown"
            )
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        schedule_id = data.get('schedule_id')
        
        if not schedule_id:
            await message.answer("❌ Ошибка: данные сессии утеряны")
            await state.clear()
            return
        
        # Обновляем текст в базе данных
        success = ScheduleManager.update_schedule_content(schedule_id, new_text)
        
        if success:
            schedule = ScheduleManager.get_schedule_by_id(schedule_id)
            
            # Показываем превью нового текста
            preview = new_text[:200] + "..." if len(new_text) > 200 else new_text
            
            await message.answer(
                f"✅ *Текст успешно обновлен!*\n\n"
                f"📝 Сообщение: {schedule.title}\n"
                f"⏰ Время: {schedule.scheduled_time.strftime('%H:%M')}\n\n"
                f"*Превью нового текста:*\n{preview}\n\n"
                f"Сообщение будет отправлено с этим текстом.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📝 Изменить еще раз", 
                                       callback_data=f"schedule_change_text_{schedule_id}"),
                    InlineKeyboardButton(text="✏️ К редактированию", 
                                       callback_data=f"schedule_edit_{schedule_id}")
                ]])
            )
        else:
            await message.answer("❌ Ошибка при обновлении текста")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста: {e}")
        await message.answer("❌ Ошибка при обновлении текста")
        await state.clear()

@router.callback_query(F.data.startswith("schedule_toggle_"))
async def schedule_toggle_status(callback: types.CallbackQuery) -> None:
    """Переключение статуса сообщения"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    try:
        schedule_id = int(callback.data.split("_")[2])
        
        success = ScheduleManager.toggle_schedule_status(schedule_id)
        
        if success:
            schedule = ScheduleManager.get_schedule_by_id(schedule_id)
            new_status = "активировано" if schedule.status == MessageScheduleStatus.ACTIVE.value else "приостановлено"
            await callback.answer(f"✅ Сообщение {new_status}", show_alert=True)
            
            # Обновляем сообщение
            await schedule_edit_detail(callback)
        else:
            await callback.answer("❌ Ошибка при изменении статуса", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка переключения статуса: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data == "schedule_add_new")
async def schedule_add_new(callback: types.CallbackQuery) -> None:
    """Добавление нового сообщения"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    # Показываем шаблоны
    templates_text = "➕ ДОБАВЛЕНИЕ НОВОГО СООБЩЕНИЯ\n\n"
    templates_text += "Выберите тип сообщения:\n\n"
    
    # Группируем шаблоны
    template_groups = [
        ("🎯 Приветствия", ["morning_greeting"]),
        ("🏟️ Тренировки", ["training_reminder"]),
        ("⚡ Челленджи", ["challenge_1", "challenge_2", "challenge_3"]),
        ("📋 Итоги", ["evening_summary"]),
        ("💬 Обратная связь", ["feedback_request"])
    ]
    
    keyboard_buttons = []
    
    for group_name, template_keys in template_groups:
        for key in template_keys:
            if key in MESSAGE_TEMPLATES:
                display_name = key.replace('_', ' ').title()
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📝 {display_name}",
                        callback_data=f"schedule_new_from_{key}"
                    )
                ])
    
    # Кнопка для пустого сообщения
    keyboard_buttons.append([
        InlineKeyboardButton(text="✏️ Пустое сообщение", callback_data="schedule_new_empty")
    ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text(templates_text, reply_markup=kb)

@router.callback_query(F.data.startswith("schedule_new_from_"))
async def schedule_new_from_template(callback: types.CallbackQuery) -> None:
    """Создание сообщения из шаблона"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    try:
        template_key = callback.data.split("_")[3]
        template_content = MESSAGE_TEMPLATES.get(template_key, "")
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Создаем новое сообщение
        new_schedule = MessageSchedule(
            org_id=user.org_id,
            title=template_key.replace('_', ' ').title(),
            content=template_content,
            scheduled_time=time(12, 0),  # Время по умолчанию
            message_type=template_key,
            status=MessageScheduleStatus.DRAFT.value,
            is_daily=True,
            order_index=0
        )
        
        session.add(new_schedule)
        session.commit()
        
        await callback.message.edit_text(
            f"✅ Сообщение создано из шаблона '{template_key}'!\n\n"
            f"Теперь настройте время отправки и проверьте текст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚙️ Настроить", callback_data=f"schedule_edit_{new_schedule.id}"),
                InlineKeyboardButton(text="◀️ Назад", callback_data="schedule_add_new")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания сообщения: {e}")
        await callback.message.edit_text("❌ Ошибка при создании")
    finally:
        session.close()

@router.callback_query(F.data == "schedule_new_empty")
async def schedule_new_empty_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Начало создания пустого сообщения"""
    user_id = callback.from_user.id
    
    try:
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Сохраняем org_id в состоянии
        await state.update_data(org_id=user.org_id)
        await state.set_state(ScheduleEditStates.waiting_for_title)
        
        await callback.message.edit_text(
            "📝 СОЗДАНИЕ НОВОГО СООБЩЕНИЯ\n\n"
            "1️⃣ *Введите заголовок сообщения:*\n"
            "Например: '🎯 Утреннее приветствие'\n\n"
            "Для отмены нажмите /cancel",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="◀️ Отмена", callback_data="schedule_add_new")
            ]])
        )
        
    except Exception as e:
        logger.error(f"Ошибка начала создания: {e}")
        await callback.message.edit_text("❌ Ошибка при создании")
    finally:
        if 'session' in locals():
            session.close()

@router.message(ScheduleEditStates.waiting_for_title, F.text)
async def process_title_input(message: Message, state: FSMContext) -> None:
    """Обработка введенного заголовка"""
    try:
        title = message.text.strip()
        
        if len(title) < 2:
            await message.answer("❌ Заголовок слишком короткий!")
            return
        
        # Сохраняем заголовок и переходим к тексту
        await state.update_data(title=title)
        await state.set_state(ScheduleEditStates.waiting_for_new_schedule)  # Исправлено!
        
        await message.answer(
            f"✅ Заголовок сохранен: {title}\n\n"
            f"2️⃣ Теперь введите текст сообщения:\n\n"
            f"Для отмены нажмите /cancel"
        )
        
    except Exception as e:
        logger.error(f"Ошибка обработки заголовка: {e}")
        await message.answer("❌ Ошибка при обработке заголовка")
        await state.clear()

@router.message(ScheduleEditStates.waiting_for_new_schedule, F.text)
async def process_new_schedule_text(message: Message, state: FSMContext) -> None:
    """Обработка текста для нового сообщения"""
    try:
        content = message.text.strip()
        
        if len(content) < 3:
            await message.answer(
                "❌ *Текст слишком короткий!*\n\n"
                "Минимальная длина сообщения - 3 символа.",
                parse_mode="Markdown"
            )
            return
        
        # Получаем данные из состояния
        data = await state.get_data()
        org_id = data.get('org_id')
        title = data.get('title')
        
        if not org_id or not title:
            await message.answer("❌ Ошибка: данные сессии утеряны")
            await state.clear()
            return
        
        # Создаем новое сообщение
        session = get_session()
        try:
            new_schedule = MessageSchedule(
                org_id=org_id,
                title=title,
                content=content,
                scheduled_time=time(12, 0),  # Время по умолчанию
                message_type="custom",
                status=MessageScheduleStatus.DRAFT.value,
                is_daily=True,
                order_index=0
            )
            
            session.add(new_schedule)
            session.commit()
            
            await message.answer(
                f"✅ *Новое сообщение создано!*\n\n"
                f"📝 Заголовок: {title}\n"
                f"📊 Статус: Черновик\n"
                f"⏰ Время по умолчанию: 12:00\n\n"
                f"Теперь настройте время отправки и активируйте сообщение.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⚙️ Настроить", 
                                       callback_data=f"schedule_edit_{new_schedule.id}"),
                    InlineKeyboardButton(text="📋 В список", 
                                       callback_data="admin_schedule_preview")
                ]])
            )
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка создания сообщения: {e}")
            await message.answer("❌ Ошибка при создании сообщения")
        finally:
            session.close()
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки текста: {e}")
        await message.answer("❌ Ошибка при создании сообщения")
        await state.clear()

@router.callback_query(F.data == "schedule_send_all")
async def schedule_send_all_now(callback: types.CallbackQuery) -> None:
    """Отправка всех сообщений сейчас"""
    user_id = callback.from_user.id
    
    if not is_admin(user_id):
        await callback.message.edit_text("❌ Нет прав")
        return
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не привязаны к организации")
            return
        
        # Получаем активные сообщения
        schedules = session.query(MessageSchedule).filter(
            MessageSchedule.org_id == user.org_id,
            MessageSchedule.status == MessageScheduleStatus.ACTIVE.value
        ).all()
        
        if not schedules:
            await callback.message.edit_text(
                "📭 Нет активных сообщений для отправки",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview")
                ]])
            )
            return
        
        # Получаем пользователей организации
        users = session.query(User).filter(
            User.org_id == user.org_id,
            User.chat_id.isnot(None)
        ).all()
        
        if not users:
            await callback.message.edit_text(
                "👥 Нет активных пользователей в организации",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview")
                ]])
            )
            return
        
        bot = callback.bot
        total_sent = 0
        total_failed = 0
        
        # Отправляем прогресс
        progress_msg = await callback.message.edit_text(
            "📤 Начинаю рассылку всех сообщений...\n"
            f"⏳ 0/{len(schedules)} сообщений\n"
            f"👥 Пользователей: {len(users)}"
        )
        
        for i, schedule in enumerate(schedules):
            # Обновляем прогресс
            await progress_msg.edit_text(
                f"📤 Рассылка всех сообщений...\n"
                f"⏳ {i}/{len(schedules)} сообщений\n"
                f"📝 Текущее: {schedule.title}\n"
                f"👥 Пользователей: {len(users)}"
            )
            
            for u in users:
                try:
                    await bot.send_message(
                        u.chat_id,
                        f"{schedule.title}\n\n{schedule.content}"
                    )
                    total_sent += 1
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    total_failed += 1
                    logger.warning(f"Ошибка отправки пользователю {u.user_id}: {e}")
        
        result_text = (
            f"✅ Рассылка завершена!\n\n"
            f"📊 Результаты:\n"
            f"📤 Успешно отправлено: {total_sent} сообщений\n"
            f"❌ Ошибок отправки: {total_failed}\n"
            f"📝 Сообщений: {len(schedules)}\n"
            f"👥 Пользователей: {len(users)}\n\n"
            f"Проверьте чаты участников! 🚀"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data="schedule_send_all")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_schedule_preview")]
        ])
        
        await progress_msg.edit_text(result_text, reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка массовой отправки: {e}")
        await callback.message.edit_text(f"❌ Ошибка при отправке: {str(e)[:200]}")
    finally:
        session.close()

@router.callback_query(F.data.startswith("schedule_delete_"))
async def schedule_delete_confirmation(callback: types.CallbackQuery) -> None:
    """Подтверждение удаления сообщения"""
    user_id = callback.from_user.id
    
    try:
        schedule_id = int(callback.data.split("_")[2])
        
        schedule = ScheduleManager.get_schedule_by_id(schedule_id)
        if not schedule:
            await callback.answer("❌ Сообщение не найдено", show_alert=True)
            return
        
        # Показываем подтверждение
        message_text = (
            f"🗑️ ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ\n\n"
            f"Вы уверены, что хотите удалить сообщение?\n\n"
            f"📝 *{schedule.title}*\n"
            f"⏰ Время: {schedule.scheduled_time.strftime('%H:%M')}\n\n"
            f"*Это действие нельзя отменить!*"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", 
                                   callback_data=f"schedule_confirm_delete_{schedule_id}"),
                InlineKeyboardButton(text="❌ Нет, отменить", 
                                   callback_data=f"schedule_edit_{schedule_id}")
            ]
        ])
        
        await callback.message.edit_text(message_text, parse_mode="Markdown", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения удаления: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("schedule_confirm_delete_"))
async def schedule_delete_execute(callback: types.CallbackQuery) -> None:
    """Выполнение удаления сообщения"""
    user_id = callback.from_user.id
    
    try:
        schedule_id = int(callback.data.split("_")[3])
        
        session = get_session()
        try:
            schedule = session.query(MessageSchedule).filter(
                MessageSchedule.id == schedule_id
            ).first()
            
            if not schedule:
                await callback.answer("❌ Сообщение не найдено", show_alert=True)
                return
            
            title = schedule.title
            session.delete(schedule)
            session.commit()
            
            await callback.message.edit_text(
                f"✅ Сообщение успешно удалено!\n\n"
                f"📝 Удалено: {title}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="📋 К списку сообщений", 
                                       callback_data="admin_schedule_preview")
                ]])
            )
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления: {e}")
            await callback.answer("❌ Ошибка при удалении", show_alert=True)
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Ошибка выполнения удаления: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.callback_query(F.data.startswith("schedule_send_now_"))
async def schedule_send_now(callback: types.CallbackQuery) -> None:
    """Отправка конкретного сообщения сейчас"""
    user_id = callback.from_user.id
    
    try:
        schedule_id = int(callback.data.split("_")[3])
        
        schedule = ScheduleManager.get_schedule_by_id(schedule_id)
        if not schedule:
            await callback.answer("❌ Сообщение не найдено", show_alert=True)
            return
        
        session = get_session()
        try:
            # Получаем пользователей организации
            users = session.query(User).filter(
                User.org_id == schedule.org_id,
                User.chat_id.isnot(None)
            ).all()
            
            if not users:
                await callback.answer("❌ Нет пользователей для отправки", show_alert=True)
                return
            
            bot = callback.bot
            sent_count = 0
            failed_count = 0
            
            # Показываем прогресс
            progress_msg = await callback.message.edit_text(
                f"📤 Отправка сообщения...\n"
                f"📝 {schedule.title}\n"
                f"👥 Пользователей: {len(users)}\n"
                f"⏳ Отправлено: 0/{len(users)}"
            )
            
            for i, user in enumerate(users, 1):
                try:
                    await bot.send_message(
                        user.chat_id,
                        f"{schedule.title}\n\n{schedule.content}"
                    )
                    sent_count += 1
                    
                    # Обновляем прогресс каждые 5 пользователей
                    if i % 5 == 0 or i == len(users):
                        await progress_msg.edit_text(
                            f"📤 Отправка сообщения...\n"
                            f"📝 {schedule.title}\n"
                            f"👥 Пользователей: {len(users)}\n"
                            f"✅ Отправлено: {sent_count}/{len(users)}"
                        )
                    
                    await asyncio.sleep(0.05)
                    
                except Exception as e:
                    failed_count += 1
                    logger.warning(f"Ошибка отправки пользователю {user.user_id}: {e}")
            
            result_text = (
                f"✅ Сообщение отправлено!\n\n"
                f"📝 {schedule.title}\n\n"
                f"📊 Результаты:\n"
                f"✅ Успешно: {sent_count} пользователей\n"
                f"❌ Ошибок: {failed_count}\n"
                f"👥 Всего: {len(users)}"
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Отправить еще раз", 
                                       callback_data=f"schedule_send_now_{schedule_id}"),
                    InlineKeyboardButton(text="✏️ К редактированию", 
                                       callback_data=f"schedule_edit_{schedule_id}")
                ]
            ])
            
            await progress_msg.edit_text(result_text, reply_markup=kb)
            
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            await callback.answer(f"❌ Ошибка при отправке: {str(e)[:100]}", show_alert=True)
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Ошибка подготовки отправки: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)

@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """Отмена текущего действия"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer("❌ Нет активных действий для отмены")
        return
    
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📋 К расписанию", callback_data="admin_schedule_preview")
        ]])
    )

@router.message(F.text.lower().in_(["отмена", "/отмена"]))
async def cancel_text_handler(message: Message, state: FSMContext) -> None:
    """Отмена по тексту 'отмена'"""
    await cancel_handler(message, state)

@router.callback_query(F.data == "admin_generate_challenges")
async def admin_generate_challenges(callback: types.CallbackQuery):
    """Генерация AI-челленджей для команды"""
    user_id = callback.from_user.id
    session = get_session()
    
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        await callback.message.edit_text("🎯 Анализирую команду и генерирую челленджи...")
        
        # Генерируем челленджи через AI
        challenges = await challenge_planner.generate_daily_challenges(user.org_id)
        
        if not challenges:
            await callback.message.edit_text("❌ Не удалось сгенерировать челленджи")
            return
        
        # ✅ ОБЯЗАТЕЛЬНО СОХРАНЯЕМ В БД (PendingChallenge)
        try:
            record_id = await challenge_storage.save_challenges(
                user_id=user_id,
                chat_id=callback.message.chat.id,
                org_id=user.org_id,
                challenges=challenges,
                ttl_hours=24
            )
            
            logger.info(f"✅ Челленджи сохранены в PendingChallenge, ID={record_id}")
            
            # ДЕБАГ: проверяем, что сохранилось
            check_data = await challenge_storage.get_challenges(user_id)
            if check_data:
                logger.info(f"✅ Проверка БД: найдено {len(check_data.get('challenges', []))} челленджей")
            else:
                logger.error("❌ Проверка БД: данные не найдены!")
            
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ошибка сохранения в БД: {e}")
            await callback.message.edit_text(
                f"❌ Ошибка сохранения данных: {str(e)[:100]}\n"
                f"Попробуйте снова или обратитесь к разработчику."
            )
            return
        
        # Показываем челленджи
        await show_generated_challenges(
            callback=callback,
            challenges=challenges,
            record_id=record_id
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации челленджей: {e}")
        await callback.message.edit_text("❌ Ошибка генерации челленджей")
    finally:
        session.close()

async def show_generated_challenges(
    callback: types.CallbackQuery,
    challenges: List[Dict],
    record_id: int 
):
    """Показать сгенерированные челленджи с кнопкой планирования"""
    report_text = "🎯 *AI-ЧЕЛЛЕНДЖИ НА ДЕНЬ*\n\n"
    
    for challenge in challenges:
        time_emoji = {
            "morning": "🌅",
            "afternoon": "☀️", 
            "evening": "🌙"
        }.get(challenge.get("time", ""), "⏰")
        
        difficulty_emoji = {
            "easy": "🟢",
            "medium": "🟡",
            "hard": "🔴"
        }.get(challenge.get("difficulty", ""), "🟡")
        
        report_text += f"""
{time_emoji} *{challenge.get('title', 'Челлендж').upper()}* ({challenge.get('time', 'N/A')})
{difficulty_emoji} Сложность: {challenge.get('difficulty', 'medium')} | ⭐ Очки: {challenge.get('points', 10)}
⏰ Время: {challenge.get('duration', '15-20 минут')} | 🎯 Фокус: {challenge.get('focus', 'тренировка')}

📝 *Описание:*
{challenge.get('description', 'Нет описания')}

✅ *Критерии успеха:*
{challenge.get('success_criteria', 'Выполнение всех пунктов')}
"""
    
    await callback.message.edit_text(report_text, parse_mode="Markdown")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Запланировать отправку", 
                callback_data=f"schedule_challenges_{record_id}" 
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Сгенерировать заново", 
                callback_data="admin_generate_challenges"
            )
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")
        ]
    ])
    
    await callback.message.answer(
        f"✅ Челленджи сохранены (ID: {record_id}). Хотите запланировать отправку?",
        reply_markup=kb
    )

@router.callback_query(F.data.startswith("schedule_challenges_"))
async def schedule_challenges_handler(callback: types.CallbackQuery):
    """Обработка планирования с record_id из callback_data"""
    user_id = callback.from_user.id
    
    try:
        # Извлекаем record_id из callback_data
        record_id = int(callback.data.replace("schedule_challenges_", ""))
        
        # Получаем данные из БД
        data = await challenge_storage.get_challenges(user_id)
        
        if not data:
            await callback.answer("❌ Данные не найдены в БД", show_alert=True)
            return
        
        if data["id"] != record_id:
            await callback.answer("❌ ID не совпадает", show_alert=True)
            return
        
        # Получаем пользователя
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        # Планируем
        await process_challenge_scheduling(
            callback=callback,
            user_id=user_id,
            org_id=user.org_id,
            challenges=data["challenges"],
            record_id=record_id
        )
        
    except ValueError:
        await callback.answer("❌ Неверный формат ID", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка планирования: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:200]}")

async def process_challenge_scheduling(
    callback: types.CallbackQuery,
    user_id: int,
    org_id: int,
    challenges: List[Dict],
    record_id: int
):
    """Обработка планирования челленджей с учетом часового пояса"""
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        # Получаем организацию для часового пояса
        org = session.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            await callback.message.edit_text("❌ Организация не найдена")
            return
        
        org_timezone = org.timezone if hasattr(org, 'timezone') else "Asia/Novosibirsk"
        
        await callback.message.edit_text(f"📅 Планирую отправку челленджей (часовой пояс: {org_timezone})...")
        
        members = session.query(User).filter(
            User.org_id == org_id,
            User.role.in_([UserRole.MEMBER.value, UserRole.TRAINER.value]),  
            User.chat_id.isnot(None)
        ).all()
        
        logger.info(f"Найдено участников: {len(members)}")
        
        if not members:
            await callback.message.edit_text("❌ В команде нет активных участников")
            await challenge_storage.update_status(record_id, "CANCELLED")
            return
        
        saved_count = 0
        
        # Время отправки для каждого типа челленджей (в часовом поясе организации)
        time_slots = {
            "morning": time(9, 0),    # 09:00 утра
            "afternoon": time(14, 0), # 14:00 дня
            "evening": time(19, 0)    # 19:00 вечера
        }
        
        import pytz
        from datetime import datetime, timezone as tz
        
        # Получаем объект часового пояса организации
        try:
            org_tz = pytz.timezone(org_timezone)
        except:
            logger.warning(f"Неверный часовой пояс {org_timezone}, используем Asia/Novosibirsk")
            org_tz = pytz.timezone("Asia/Novosibirsk")
        
        # Текущее время в UTC
        now_utc = datetime.now(tz.utc)
        # Текущее время в часовом поясе организации
        now_org = now_utc.astimezone(org_tz)
        
        for challenge_data in challenges:
            challenge_time = challenge_data.get("time", "morning")
            send_time_local = time_slots.get(challenge_time)
            
            if not send_time_local:
                logger.warning(f"Unknown time slot: {challenge_time}, using default")
                send_time_local = time(12, 0)
            
            # Создаем datetime в часовом поясе организации
            send_datetime_local = org_tz.localize(datetime.combine(now_org.date(), send_time_local))
            
            # Если время уже прошло сегодня, планируем на завтра
            if send_datetime_local < now_org:
                send_datetime_local += timedelta(days=1)
                logger.info(f"Challenge '{challenge_time}' moved to tomorrow in {org_timezone}")
            
            # Конвертируем в UTC для хранения в базе
            send_datetime_utc = send_datetime_local.astimezone(tz.utc)
            
            for member in members:
                # Создаем челлендж со статусом SCHEDULED
                challenge = Challenge(
                    user_id=member.user_id,
                    text=(
                        f"{challenge_data.get('title', 'Челлендж')}\n\n"
                        f"{challenge_data.get('description', '')}"
                    ),
                    points=challenge_data.get("points", 10),
                    status=ChallengeStatus.SCHEDULED.value,
                    created_by=user_id,
                    created_at=datetime.now(tz.utc),
                    scheduled_for=send_datetime_utc,  # Время в UTC
                    is_custom=True,
                    challenge_time=challenge_time,
                    difficulty=challenge_data.get("difficulty", "medium"),
                    duration=challenge_data.get("duration", "15-20 минут"),
                    focus_area=challenge_data.get("focus", "тренировка")
                )
                session.add(challenge)
                saved_count += 1
        
        session.commit()
        
        # Форматируем время для отображения пользователю
        time_display = {}
        for challenge in challenges:
            time_key = challenge.get("time", "morning")
            send_time_local = time_slots.get(time_key, time(12, 0))
            send_datetime_local = org_tz.localize(datetime.combine(now_org.date(), send_time_local))
            
            # Если прошло сегодня, показываем завтра
            if send_datetime_local < now_org:
                send_datetime_local += timedelta(days=1)
            
            time_display[time_key] = send_datetime_local.strftime("%H:%M")
        
        await challenge_storage.update_status(
            record_id,
            "SCHEDULED",
            metadata={
                "scheduled_at": datetime.now(tz.utc).isoformat(),
                "org_timezone": org_timezone,
                "member_count": len(members),
                "challenge_count": len(challenges),
                "send_times_local": time_display
            }
        )
        
        # Обновляем функцию форматирования сообщения
        success_text = format_success_message_with_timezone(
            challenges, members, saved_count, org_timezone, time_display
        )
        await callback.message.edit_text(success_text, parse_mode="Markdown")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Просмотреть расписание", 
                    callback_data="admin_view_schedule"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Сгенерировать новые", 
                    callback_data="admin_generate_challenges"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад", 
                    callback_data="back_to_admin_panel"
                )
            ]
        ])
        
        await callback.message.answer("Что дальше?", reply_markup=kb)
        
    except Exception as e:
        session.rollback()
        await challenge_storage.update_status(record_id, "ERROR")
        
        logger.error(f"Ошибка планирования челленджей: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка планирования: {str(e)[:200]}")
    finally:
        session.close()

def format_success_message_with_timezone(challenges, members, saved_count, org_timezone, time_display):
    """Форматирование сообщения об успехе с учетом часового пояса"""
    time_texts = {
        "morning": "🌅 Утро",
        "afternoon": "☀️ День", 
        "evening": "🌙 Вечер"
    }
    
    success_text = (
        f"✅ Челленджи запланированы!\n\n"
        f"📊 Статистика:\n"
        f"• Часовой пояс: {org_timezone}\n"
        f"• Всего челленджей: {len(challenges)}\n"
        f"• Участников: {len(members)}\n"
        f"• Запланировано отправок: {saved_count}\n\n"
        f"📅 Расписание отправки (время местное):\n"
    )
    
    for challenge in challenges:
        time_slot = challenge.get("time", "")
        time_display_value = time_display.get(time_slot, "??:??")
        time_emoji = time_texts.get(time_slot, "⏰")
        success_text += f"• {time_emoji} {time_display_value}: {challenge.get('title', 'Челлендж')}\n"
    
    success_text += f"\n📢 Челленджи будут автоматически отправлены {len(members)} участникам в указанное время."
    
    return success_text

def get_send_time(challenge_time: str) -> Optional[time]:
    """Получить время отправки на основе типа челленджа"""
    time_map = {
        "morning": time(9, 0),    # 09:00
        "afternoon": time(14, 0), # 14:00
        "evening": time(19, 0)    # 19:00
    }
    return time_map.get(challenge_time)

def format_success_message(challenges, members, saved_count, send_date):
    """Форматирование сообщения об успехе"""
    time_texts = {
        "morning": "🌅 Утро (09:00)",
        "afternoon": "☀️ День (14:00)", 
        "evening": "🌙 Вечер (19:00)"
    }
    
    success_text = (
        f"✅ Челленджи запланированы!\n\n"
        f"📊 Статистика:\n"
        f"• Всего челленджей: {len(challenges)}\n"
        f"• Участников: {len(members)}\n"
        f"• Запланировано отправок: {saved_count}\n"
        f"• Дата отправки: {send_date.strftime('%d.%m.%Y')}\n\n"
        f"📅 Расписание отправки:\n"
    )
    
    for challenge in challenges:
        time_slot = challenge.get("time", "")
        time_display = time_texts.get(time_slot, "⏰")
        success_text += f"• {time_display}: {challenge.get('title', 'Челлендж')}\n"
    
    success_text += f"\n📢 Челленджи будут автоматически отправлены {len(members)} участникам в указанное время."
    
    return success_text


@router.callback_query(F.data == "admin_view_schedule")
async def admin_view_schedule(callback: types.CallbackQuery):
    """Просмотр запланированных челленджей с учетом часового пояса"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        # Получаем организацию для часового пояса
        org = session.query(Organization).filter(Organization.id == user.org_id).first()
        org_timezone = org.timezone if hasattr(org, 'timezone') else "Asia/Novosibirsk"
        
        import pytz
        from datetime import datetime, timezone as tz
        
        try:
            org_tz = pytz.timezone(org_timezone)
        except:
            org_tz = pytz.timezone("Asia/Novosibirsk")
        
        # Получаем запланированные челленджи
        scheduled_challenges = session.query(Challenge).filter(
            Challenge.created_by == user_id,
            Challenge.scheduled_for.isnot(None),
            Challenge.status == "SCHEDULED"
        ).order_by(Challenge.scheduled_for).all()
        
        if not scheduled_challenges:
            await callback.message.edit_text(
                f"📅 Нет запланированных челленджей\n\n"
                f"Часовой пояс: {org_timezone}\n"
                f"Сгенерируйте и запланируйте челленджи через меню.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Сгенерировать", callback_data="admin_generate_challenges")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
                ])
            )
            return
        
        # Группируем по времени (в местном времени)
        challenges_by_time = {"morning": [], "afternoon": [], "evening": []}
        
        for challenge in scheduled_challenges:
            if challenge.scheduled_for:
                # Конвертируем из UTC в местное время
                challenge_local_time = challenge.scheduled_for.replace(tzinfo=tz.utc).astimezone(org_tz)
                
                # Определяем временной слот
                hour = challenge_local_time.hour
                if 5 <= hour < 12:
                    time_slot = "morning"
                elif 12 <= hour < 17:
                    time_slot = "afternoon"
                else:
                    time_slot = "evening"
                    
                challenges_by_time[time_slot].append((challenge, challenge_local_time))
        
        schedule_text = f"📅 ЗАПЛАНИРОВАННЫЕ ЧЕЛЛЕНДЖИ\n\n"
        schedule_text += f"🌍 Часовой пояс: {org_timezone}\n\n"
        
        for time_slot, challenges in challenges_by_time.items():
            if challenges:
                time_emoji = {
                    "morning": "🌅 УТРО",
                    "afternoon": "☀️ ДЕНЬ",
                    "evening": "🌙 ВЕЧЕР"
                }.get(time_slot, "⏰")
                
                # Берем первое время как пример
                first_time = challenges[0][1] if challenges else None
                time_str = first_time.strftime("%H:%M") if first_time else "??:??"
                
                schedule_text += f"{time_emoji} ({time_str}):\n"
                
                # Группируем по участникам
                challenge_titles = {}
                for challenge, local_time in challenges:
                    title = challenge.text.split('\n')[0][:30] + "..."
                    if title not in challenge_titles:
                        challenge_titles[title] = 1
                    else:
                        challenge_titles[title] += 1
                
                for title, count in list(challenge_titles.items())[:3]:  # Показываем максимум 3
                    schedule_text += f"• {title}\n"
                    schedule_text += f"  👥 Участников: {count}\n"
                    schedule_text += f"  ⭐ Очки: {challenge.points}\n"
                
                if len(challenge_titles) > 3:
                    schedule_text += f"  ... и еще {len(challenge_titles) - 3} челленджей\n"
                
                schedule_text += "\n"
        
        schedule_text += f"\n📊 Всего запланировано: {len(scheduled_challenges)} отправок"
        
        await callback.message.edit_text(schedule_text)
        
        # Кнопки управления
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить все", callback_data="admin_cancel_schedule")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_view_schedule")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.answer("Управление расписанием:", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка просмотра расписания: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        session.close()

@router.callback_query(F.data == "admin_cancel_schedule")
async def admin_cancel_schedule(callback: types.CallbackQuery):
    """Отмена всех запланированных челленджей"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, отменить все", callback_data="confirm_cancel_schedule")],
            [InlineKeyboardButton(text="❌ Нет, оставить", callback_data="admin_view_schedule")]
        ])
        
        await callback.message.edit_text(
            "⚠️ ВЫ УВЕРЕНЫ?\n\n"
            "Это действие отменит ВСЕ запланированные челленджи.\n"
            "Восстановление будет невозможно.",
            reply_markup=confirm_kb
        )
        
    except Exception as e:
        logger.error(f"Ошибка подтверждения отмены: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")
    finally:
        session.close()

@router.callback_query(F.data == "confirm_cancel_schedule")
async def confirm_cancel_schedule(callback: types.CallbackQuery):
    """Подтверждение отмены расписания"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        deleted_count = session.query(Challenge).filter(
            Challenge.created_by == user_id,
            Challenge.scheduled_for.isnot(None),
            Challenge.status == "PENDING"
        ).delete()
        
        session.commit()
        
        await callback.message.edit_text(
            f"✅ Расписание отменено!\n\n"
            f"Удалено запланированных челленджей: {deleted_count}\n\n"
            f"Теперь можно создать новое расписание."
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Сгенерировать новые", callback_data="admin_generate_challenges")],
            [InlineKeyboardButton(text="◀️ Назад в админку", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.answer("Что дальше?", reply_markup=kb)
        
    except Exception as e:
        logger.error(f"Ошибка отмены расписания: {e}")
        await callback.message.edit_text(f"❌ Ошибка отмены: {str(e)}")
    finally:
        session.close()