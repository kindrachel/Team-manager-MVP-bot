from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_session
from utils.states import VacancyStates
import json
from datetime import datetime
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "admin_manage_vacancies")
async def admin_manage_vacancies_menu(callback: types.CallbackQuery):
    """Меню управления вакансиями"""
    user_id = callback.from_user.id
    
    # Импорт тут, чтобы избежать циклических импортов
    from .members import is_admin
    if not is_admin(user_id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="admin_add_vacancy")],
        [InlineKeyboardButton(text="📋 Список вакансий", callback_data="admin_list_vacancies")],
        [InlineKeyboardButton(text="🗑️ Удалить вакансию", callback_data="admin_delete_vacancy_menu")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
    ])
    
    await callback.message.edit_text(
        "💼 УПРАВЛЕНИЕ ВАКАНСИЯМИ\n\n"
        "Выберите действие:",
        reply_markup=kb
    )

@router.callback_query(F.data == "admin_add_vacancy")
async def admin_add_vacancy_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления вакансии"""
    user_id = callback.from_user.id
    
    from .members import is_admin
    if not is_admin(user_id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📝 ДОБАВЛЕНИЕ НОВОЙ ВАКАНСИИ\n\n"
        "Введите название вакансии:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_vacancy")]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_title)
    await callback.answer()

@router.message(VacancyStates.waiting_for_vacancy_title)
async def process_vacancy_title(message: types.Message, state: FSMContext):
    """Обработка названия вакансии"""
    await state.update_data(title=message.text)
    
    await message.answer(
        "🏢 Введите название компании:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_vacancy")]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_company)
    await message.delete()

@router.message(VacancyStates.waiting_for_vacancy_company)
async def process_vacancy_company(message: types.Message, state: FSMContext):
    """Обработка названия компании"""
    await state.update_data(company=message.text)
    
    await message.answer(
        "📍 Введите тип работы (офис/удаленно/гибрид):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_vacancy")]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_type)
    await message.delete()

@router.message(VacancyStates.waiting_for_vacancy_type)
async def process_vacancy_type(message: types.Message, state: FSMContext):
    """Обработка типа работы"""
    await state.update_data(type=message.text)
    
    await message.answer(
        "📌 Введите описание вакансии:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_vacancy")]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_description)
    await message.delete()

@router.message(VacancyStates.waiting_for_vacancy_description)
async def process_vacancy_description(message: types.Message, state: FSMContext):
    """Обработка описания вакансии"""
    await state.update_data(description=message.text)
    
    await message.answer(
        "📞 Введите контакт для отклика (телефон/email/telegram):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="admin_cancel_vacancy")]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_contact)
    await message.delete()

@router.message(VacancyStates.waiting_for_vacancy_contact)
async def process_vacancy_contact(message: types.Message, state: FSMContext):
    """Обработка контакта и подтверждение"""
    await state.update_data(contact=message.text)
    
    data = await state.get_data()
    
    preview_text = (
        "📋 ПРЕДПРОСМОТР ВАКАНСИИ:\n\n"
        f"💼 Название: {data['title']}\n"
        f"🏢 Компания: {data['company']}\n"
        f"📍 Тип: {data['type']}\n"
        f"📌 Описание: {data['description'][:200]}...\n"
        f"📞 Контакт: {data['contact']}\n\n"
        "✅ Добавить эту вакансию?"
    )
    
    await message.answer(
        preview_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, добавить", callback_data="vacancy_confirm_yes"),
                InlineKeyboardButton(text="❌ Нет, отменить", callback_data="vacancy_confirm_no")
            ]
        ])
    )
    await state.set_state(VacancyStates.waiting_for_vacancy_confirm)
    await message.delete()

@router.callback_query(VacancyStates.waiting_for_vacancy_confirm, F.data == "vacancy_confirm_yes")
async def confirm_vacancy_add(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение добавления вакансии"""
    try:
        data = await state.get_data()
        
        # Читаем существующие вакансии
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            vacancies_data = json.load(f)
        
        # Добавляем новую вакансию
        new_vacancy = {
            "id": len(vacancies_data["vacancies"]) + 1,
            "title": data["title"],
            "company": data["company"],
            "type": data["type"],
            "description": data["description"],
            "contact": data["contact"],
            "created_at": datetime.now().isoformat(),
            "created_by": callback.from_user.id
        }
        
        vacancies_data["vacancies"].append(new_vacancy)
        
        # Сохраняем
        with open("assets/vacancies.json", "w", encoding="utf-8") as f:
            json.dump(vacancies_data, f, ensure_ascii=False, indent=2)
        
        await callback.message.edit_text(
            f"✅ Вакансия добавлена!\n\n"
            f"💼 {data['title']}\n"
            f"🏢 {data['company']}\n\n"
            f"Всего вакансий: {len(vacancies_data['vacancies'])}"
        )
        
        await callback.message.answer(
            "Что дальше?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить еще", callback_data="admin_add_vacancy")],
                [InlineKeyboardButton(text="📋 Список вакансий", callback_data="admin_list_vacancies")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
            ])
        )
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при сохранении: {e}")
    finally:
        await state.clear()

@router.callback_query(VacancyStates.waiting_for_vacancy_confirm, F.data == "vacancy_confirm_no")
async def cancel_vacancy_add(callback: types.CallbackQuery, state: FSMContext):
    """Отмена добавления вакансии"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Добавление вакансии отменено",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="admin_add_vacancy")],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="back_to_admin_panel")]
        ])
    )

@router.callback_query(F.data == "admin_cancel_vacancy")
async def admin_cancel_vacancy(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания вакансии"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Добавление вакансии отменено",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="admin_add_vacancy")],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="back_to_admin_panel")]
        ])
    )

@router.callback_query(F.data == "admin_list_vacancies")
async def admin_list_vacancies(callback: types.CallbackQuery):
    """Показать список вакансий для админа"""
    user_id = callback.from_user.id
    
    from .members import is_admin
    if not is_admin(user_id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    try:
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        
        if not vacancies:
            await callback.message.edit_text(
                "📋 Нет доступных вакансий",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Добавить вакансию", callback_data="admin_add_vacancy")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
                ])
            )
            return
        
        # Показываем первую вакансию
        await show_admin_vacancy_detail(callback, 0, vacancies)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}")

async def show_admin_vacancy_detail(callback: types.CallbackQuery, index: int, vacancies: list):
    """Показать детали вакансии для админа"""
    vacancy = vacancies[index]
    
    # Форматируем дату создания
    created_at_str = ""
    if "created_at" in vacancy:
        try:
            created_at = datetime.fromisoformat(vacancy["created_at"].replace('Z', '+00:00'))
            created_at_str = created_at.strftime('%d.%m.%Y %H:%M')
        except:
            created_at_str = "неизвестно"
    
    vacancy_text = (
        f"📋 ВАКАНСИЯ {index + 1}/{len(vacancies)}\n\n"
        f"💼 *{vacancy['title']}*\n"
        f"🏢 {vacancy['company']}\n"
        f"📍 {vacancy.get('type', 'N/A')}\n\n"
        f"📌 *Описание:*\n{vacancy.get('description', 'Нет описания')}\n\n"
        f"📞 *Контакт:* {vacancy.get('contact', 'N/A')}\n"
        f"📅 *Добавлена:* {created_at_str}\n"
        f"👤 *ID создателя:* {vacancy.get('created_by', 'неизвестно')}"
    )
    
    # Создаем клавиатуру
    keyboard = []
    
    # Навигационные кнопки
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="⬅️ Назад", 
            callback_data=f"admin_vac_prev_{index}"
        ))
    
    nav_buttons.append(InlineKeyboardButton(
        text=f"{index + 1}/{len(vacancies)}", 
        callback_data="no_action"
    ))
    
    if index < len(vacancies) - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="Вперед ➡️", 
            callback_data=f"admin_vac_next_{index}"
        ))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки действий
    keyboard.append([
        InlineKeyboardButton(
            text="🗑️ Удалить", 
            callback_data=f"admin_vac_delete_{index}"
        ),
        InlineKeyboardButton(
            text="◀️ К списку", 
            callback_data="admin_list_vacancies"
        )
    ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="➕ Добавить новую", 
            callback_data="admin_add_vacancy"
        ),
        InlineKeyboardButton(
            text="◀️ В админку", 
            callback_data="back_to_admin_panel"
        )
    ])
    
    await callback.message.edit_text(
        vacancy_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

@router.callback_query(F.data == "no_action")
async def handle_no_action(callback: types.CallbackQuery):
    """Обработчик для кнопок без действия"""
    await callback.answer()  

@router.callback_query(F.data.startswith("admin_vac_prev_") | F.data.startswith("admin_vac_next_"))
async def admin_navigate_vacancies(callback: types.CallbackQuery):
    """Навигация по вакансиям в админке"""
    try:
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        
        if callback.data.startswith("admin_vac_prev_"):
            current_index = int(callback.data.replace("admin_vac_prev_", ""))
            new_index = max(0, current_index - 1)
        else:
            current_index = int(callback.data.replace("admin_vac_next_", ""))
            new_index = min(len(vacancies) - 1, current_index + 1)
        
        await show_admin_vacancy_detail(callback, new_index, vacancies)
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("admin_vac_delete_"))
async def admin_delete_vacancy(callback: types.CallbackQuery):
    """Удаление вакансии (упрощенная версия)"""
    try:
        parts = callback.data.split('_')
        if len(parts) < 4:
            await callback.answer("❌ Неверный формат команды", show_alert=True)
            return
        
        vacancy_index = int(parts[-1]) 
        
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        
        if vacancy_index >= len(vacancies):
            await callback.answer("❌ Вакансия не найдена", show_alert=True)
            return
        
        deleted_vacancy = vacancies[vacancy_index]
        
        vacancies.pop(vacancy_index)
        
        for i, vac in enumerate(vacancies):
            vac["id"] = i + 1
        
        with open("assets/vacancies.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        await callback.message.edit_text(
            f"✅ *Вакансия удалена*\n\n"
            f"💼 {deleted_vacancy['title']}\n"
            f"🏢 {deleted_vacancy['company']}\n\n"
            f"📊 Осталось вакансий: {len(vacancies)}",
            parse_mode="Markdown"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 К списку вакансий", callback_data="admin_list_vacancies")],
            [InlineKeyboardButton(text="◀️ В админку", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.answer("Что дальше?", reply_markup=kb)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка удаления вакансии: {e}")
        await callback.answer(f"❌ Ошибка удаления: {str(e)[:100]}", show_alert=True)
