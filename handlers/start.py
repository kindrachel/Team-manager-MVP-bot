from aiogram import Router, types, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from database import User, get_session
from keyboards import main_menu_keyboard
from utils.states import RegistrationStates
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
import asyncio

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    welcome_caption = (
        f'🚀 <b>Добро пожаловать в vadirss.ru!</b> 🚀\n\n'
        f'Первым делом небольшой, но важный пункт:\n\n'
        f'Нажимая кнопку согласия, Вы подтверждаете'
        f' <a href="https://docs.google.com/document/d/1_tdSQB5NT3d6jtMCiZK0f9xYfeOtI2fOsFT7oJGwxRA/edit?tab=t.0">своё согласие на обработку персональных данных</a>'  
        f' в соответствии с нашей <a href="https://docs.google.com/document/d/1HaA_KzljAyr3h43hCFIt1Q_yrN-sMFjxsoqQSpkwz0s/edit?tab=t.0">Политикой конфиденциальности</a>.\n\n'
        f'📌 Помните: без согласия функционал будет доступен частично.\n\n'
        f'Жмите «Даю согласие» 👇 и продолжим регистрацию!'
    )
    try:
        user_id = message.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        
        if user:
            await message.answer(
                f"👋 С возвращением, {user.name}!\n\nВыбери действие:",
                reply_markup=main_menu_keyboard()
            )
        else:
            # УБРАЛ ОТПРАВКУ ФОТО - только текст
            await message.answer(
                text=welcome_caption, 
                parse_mode=ParseMode.HTML, 
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='Даю согласие', callback_data='acceptpolicy')]
                ])
            )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == 'acceptpolicy')
async def startreg(call: types.CallbackQuery, state: FSMContext) -> None:
    """Начало регистрации"""
    
    await call.answer(cache_time=1)
    
    try:
        await call.message.edit_text(
            'Пожалуйста, укажите ваше ФИО:',
            parse_mode=ParseMode.HTML
        )
        
        await state.update_data(registration_message_id=call.message.message_id)
        
    except TelegramBadRequest:
        new_message = await call.message.answer(
            'Пожалуйста, укажите ваше ФИО:',
            parse_mode=ParseMode.HTML,
        )
        
        await state.update_data(registration_message_id=new_message.message_id)
    
    await state.set_state(RegistrationStates.waiting_for_name)

def validate_fio(fio: str) -> tuple[bool, str]:
    """Проверка ФИО, возвращает (is_valid, error_message)"""
    fio = fio.strip()
    
    # Проверка длины
    if len(fio) < 5:
        return False, "❌ ФИО слишком короткое (минимум 5 символов)"
    if len(fio) > 100:
        return False, "❌ ФИО слишком длинное (максимум 100 символов)"
    
    # Проверка на только буквы и пробелы
    if not all(c.isalpha() or c.isspace() for c in fio):
        return False, "❌ ФИО должно содержать только буквы и пробелы"
    
    # Проверка что минимум 2 слова
    parts = fio.split()
    if len(parts) < 2:
        return False, "❌ Введите и Фамилию, и Имя (минимум 2 слова)"
    
    # Проверка что каждое слово начинается с заглавной
    for part in parts:
        if not part[0].isupper():
            return False, f"❌ Слово '{part}' должно начинаться с заглавной буквы"
    
    return True, ""

@router.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext) -> None:
    """Обработка имени с проверкой ФИО"""
    name = message.text.strip()
    
    is_valid, error_msg = validate_fio(name)
    if not is_valid:
        error_msg_obj = await message.answer(error_msg)
        
        try:
            await message.delete()
        except:
            pass
        
        await asyncio.sleep(2)
        try:
            await error_msg_obj.delete()
        except:
            pass
        
        return

    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(name=name)
    
    data = await state.get_data()
    reg_message_id = data.get('registration_message_id')
    
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, все верно", callback_data="confirm_name")],
        [InlineKeyboardButton(text="❌ Нет, исправить", callback_data="edit_name")]
    ])
    
    if reg_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=reg_message_id,
                text=(
                    f"🔍 <b>Проверьте правильность ФИО:</b>\n\n"
                    f"👤 <b>{name}</b>\n\n"
                    f"Если все верно, нажмите кнопку ниже ⬇️"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=confirm_keyboard
            )
        except Exception as e:
            print(f"Ошибка редактирования: {e}")
            await send_confirmation_step(message.bot, message.chat.id, name, confirm_keyboard) 
    else:
        await send_confirmation_step(message.bot, message.chat.id, name, confirm_keyboard)
    
    await state.set_state(RegistrationStates.waiting_for_name_confirmation)

async def send_confirmation_step(bot, chat_id: int, name: str, keyboard: InlineKeyboardMarkup):
    """Отправка шага подтверждения (если не удалось редактировать)"""
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔍 <b>Проверьте правильность ФИО:</b>\n\n"
            f"👤 <b>{name}</b>\n\n"
            f"Если все верно, нажмите кнопку ниже ⬇️"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

def register_start_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков из этого файла"""
    dp.include_router(router)



