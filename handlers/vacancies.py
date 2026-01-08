from aiogram import Router, F, types, Dispatcher
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
import json
import random

router = Router()
search_job_pic = FSInputFile('pictures/searchjob.png')

user_vacancy_state = {}

@router.message(F.text == "🔍 ПОИСК ЛЮБИМОЙ РАБОТЫ")
async def show_vacancies_intro(message: types.Message) -> None:
    """Показать интро вакансий"""
    try:
        from database import User, get_session
        
        user_id = message.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Напиши /start")
            return
        
        intro_text = (
            "🔍 ПОИСК ЛЮБИМОЙ РАБОТЫ\n\n"
            "Здесь собраны ТОЛЬКО ПРОВЕРЕННЫЕ РАБОТОДАТЕЛИ 💚\n\n"
            "Компании которые видят в вас личность, человека.\n"
            "Компании которые мыслят будущим.\n\n"
            "Они будут оказывать вам поддержку в развитии:\n"
            "• Как личности\n"
            "• Как профессионала\n\n"
            "В будущем будет больше вакансий проверенных партнеров"
        )
        
        from keyboards import vacancies_menu_keyboard
        await message.answer(=intro_text, reply_markup=vacancies_menu_keyboard())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "view_vacancies")
async def show_random_vacancy(callback: types.CallbackQuery) -> None:
    """Показать случайную вакансию"""
    try:
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        if not vacancies:
            # Используем answer для алерта вместо edit_text
            await callback.answer("❌ Нет доступных вакансий", show_alert=True)
            return
        
        random_index = random.randint(0, len(vacancies) - 1)
        user_vacancy_state[callback.from_user.id] = random_index
        vacancy = vacancies[random_index]
        
        # СНАЧАЛА отвечаем на callback, чтобы убрать "часики"
        await callback.answer()
        
        # ПОТОМ отправляем новое сообщение с вакансией
        vacancy_text = (
            f"💼 {vacancy['title']}\n"
            f"🏢 {vacancy['company']}\n"
            f"📍 {vacancy.get('type', 'N/A')}\n\n"
            f"📌 {vacancy.get('description', 'Нет описания')}\n\n"
            f"Заинтересовало?\n"
            f"Пишите нам: {vacancy.get('contact', 'N/A')}"
        )
        
        from keyboards import vacancy_navigation_keyboard
        await callback.message.answer(
            vacancy_text,
            reply_markup=vacancy_navigation_keyboard(random_index, len(vacancies)),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("vac_prev_") | F.data.startswith("vac_next_"))
async def navigate_vacancies(callback: types.CallbackQuery) -> None:
    """Навигация по вакансиям"""
    try:
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        total_vacancies = len(vacancies)
        
        if callback.data.startswith("vac_prev_"):
            current_index = int(callback.data.replace("vac_prev_", ""))
            new_index = max(0, current_index - 1)
        else: 
            current_index = int(callback.data.replace("vac_next_", ""))
            new_index = min(total_vacancies - 1, current_index + 1)
        
        user_vacancy_state[callback.from_user.id] = new_index
        vacancy = vacancies[new_index]
        
        vacancy_text = (
            f"💼 {vacancy['title']}\n"
            f"🏢 {vacancy['company']}\n"
            f"📍 {vacancy.get('type', 'N/A')}\n\n"
            f"📌 {vacancy.get('description', 'Нет описания')}\n\n"
            f"Заинтересовало?\n"
            f"Пишите нам: {vacancy.get('contact', 'N/A')}"
        )
        
        from keyboards import vacancy_navigation_keyboard
        await callback.message.edit_text(
            vacancy_text,
            reply_markup=vacancy_navigation_keyboard(new_index, total_vacancies),
            disable_web_page_preview=True
        )
        
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("vac_details_"))
async def show_vacancy_details(callback: types.CallbackQuery) -> None:
    """Показать детали вакансии с ссылкой"""
    try:
        vacancy_id = int(callback.data.replace("vac_details_", ""))
        
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if vacancy_id >= len(data["vacancies"]):
            await callback.answer("❌ Вакансия не найдена", show_alert=True)
            return
        
        vacancy = data["vacancies"][vacancy_id]
        
        vacancy_text = (
            f"💼 {vacancy['title']}\n\n"
            f"🏢 {vacancy['company']}\n"
            f"📍 {vacancy.get('type', 'N/A')}\n\n"
            f"📌 {vacancy.get('description', 'Нет описания')}\n\n"
        )
        
        if vacancy.get('details_url'):
            vacancy_text += f"📖 Подробности: {vacancy['details_url']}\n\n"
        
        vacancy_text += f"Заинтересовало?\nПишите нам: {vacancy.get('contact', 'N/A')}"
        
        from keyboards import vacancy_navigation_keyboard
        await callback.message.edit_text(
            vacancy_text,
            reply_markup=vacancy_navigation_keyboard(vacancy_id, len(data["vacancies"])),
            disable_web_page_preview=False
        )
        
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == 'back_to_vacancies_list')
async def back_to_vacancies_list(callback: types.CallbackQuery) -> None:
    """Вернуться к просмотру вакансий"""
    try:
        user_id = callback.from_user.id
        
        with open("assets/vacancies.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        vacancies = data["vacancies"]
        
        if user_id not in user_vacancy_state or user_vacancy_state[user_id] >= len(vacancies):
            current_index = random.randint(0, len(vacancies) - 1)
            user_vacancy_state[user_id] = current_index
        else:
            current_index = user_vacancy_state[user_id]
        
        vacancy = vacancies[current_index]
        
        vacancy_text = (
            f"💼 {vacancy['title']}\n"
            f"🏢 {vacancy['company']}\n"
            f"📍 {vacancy.get('type', 'N/A')}\n\n"
            f"📌 {vacancy.get('description', 'Нет описания')}\n\n"
            f"Заинтересовало?\n"
            f"Пишите нам: {vacancy.get('contact', 'N/A')}"
        )
        
        from keyboards import vacancy_navigation_keyboard
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.message.answer(
            vacancy_text,
            reply_markup=vacancy_navigation_keyboard(current_index, len(vacancies)),
            disable_web_page_preview=True
        )
        
        await callback.answer()
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == 'no_action')
async def no_action(callback: types.CallbackQuery) -> None:
    """Заглушка для кнопок без действия"""
    await callback.answer()

def register_vacancies_handlers(dp: Dispatcher):

    dp.include_router(router)
