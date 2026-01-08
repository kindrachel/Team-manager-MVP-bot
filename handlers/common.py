from aiogram import Router, F, types, Dispatcher
from keyboards import main_menu_keyboard
from aiogram.types import FSInputFile

help_pic = FSInputFile('pictures/help.png')
mm_pic = FSInputFile('pictures/main_menu.png')

router = Router()

@router.callback_query(F.data == "back_to_menu")
async def go_back(callback: types.CallbackQuery) -> None:
    """Вернуться в главное меню"""
    try:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo = mm_pic,
            caption = "👋 Главное меню",
            reply_markup=main_menu_keyboard()
        )
        await callback.answer()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        await callback.answer("⚠️ Ошибка!", show_alert=True)

@router.message(F.text == "❔ Справка")
async def show_help(message: types.Message) -> None:
    """Показать справку"""
    help_text = (
        "❔ СПРАВКА\n\n"
        "👤 Профиль - информация о вас и ваши награды\n"
        "⚡ Челленджи - выполняй задания и получай очки\n"
        "📈 Активность - опросы, статистика, лидерборд\n"
        "🔍 Работа - вакансии от проверенных партнеров\n\n"
        "💎 Система очков:\n"
        "• Опрос = +5 очков\n"
        "• Челлендж = зависит от сложности\n"
        "• Каждые 100 очков = новый уровень\n\n"
        "🏆 Уровни:\n"
        "1️⃣ Новичок\n"
        "2️⃣ Развивающийся\n"
        "3️⃣ Профи\n"
        "4️⃣ Лидер\n"
        "5️⃣ Капитан\n\n"
        "Вопросы? Пишите нам! @proffmanagers 💬"
    )
    
    await message.answer_photo(photo=help_pic, caption=help_text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]))

def register_common_handlers(dp: Dispatcher):
    dp.include_router(router)