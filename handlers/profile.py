from aiogram import Router, F, types, Dispatcher
from aiogram.fsm.context import FSMContext
from database import User, Organization, get_session, UserRole
from keyboards import profile_menu_keyboard, back_button_to_profile
from services import MetricsCollector
from utils import get_level_name, format_user_full_profile
from utils.states import RegistrationStates
from datetime import datetime, timezone
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import os
from pathlib import Path
from middlewares import ClearStateMiddleware
from config import load_config

PROFILE_PHOTOS_DIR = "profile_photos"
Path(PROFILE_PHOTOS_DIR).mkdir(exist_ok=True)

STANDARD_PROFILE_PIC = FSInputFile('pictures/meprofile.png')
stat_pic = FSInputFile('pictures/Statistic.png')
awards_pic = FSInputFile('pictures/Awards.png')


router = Router()

@router.message (F.text == '👤 Профиль')
async def profile (message: types.Message):
    """"Кнопка профиля"""

    try:
        user_id = message.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
        session.close()
        
        if not user:
            await message.answer(
                "❌ Ошибка: пользователь не найден\n\n"
                "Введите /start для регистрации")
            return

        profile_text = '👤 Выбери раздел профиля:'
        profile_keyboard = profile_menu_keyboard

        await message.delete()
        await message.answer_photo(
                photo = STANDARD_PROFILE_PIC,
                caption=profile_text,
                reply_markup= profile_keyboard())
    
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.callback_query(F.data == "profile_view")
async def show_profile_details(callback: types.CallbackQuery) -> None:
    """Показать детали профиля"""
    try:
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
        session.close()
        
        if not user:
            await callback.message.answer(
                "❌ Ошибка: пользователь не найден\n\n"
                "Введите /start для регистрации")
            return
        
        profile_text = format_user_full_profile(user, org)
        
        user_photo = await get_profile_photo_for_user(user_id)
        
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=user_photo,
            caption=profile_text,
            parse_mode='Markdown',
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                    [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                ]
            )
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")

def get_user_profile_photo_path(user_id: int) -> str:
    """Получить путь к фото профиля пользователя"""
    return os.path.join(PROFILE_PHOTOS_DIR, f"user_{user_id}_profile.jpg")

def user_has_custom_photo(user_id: int) -> bool:
    """Проверить, есть ли у пользователя кастомное фото"""
    photo_path = get_user_profile_photo_path(user_id)
    return os.path.exists(photo_path) and os.path.getsize(photo_path) > 0

async def get_profile_photo_for_user(user_id: int) -> FSInputFile:
    """Получить фото профиля для пользователя (кастомное или стандартное)"""
    photo_path = get_user_profile_photo_path(user_id)
    
    if user_has_custom_photo(user_id):
        return FSInputFile(photo_path)
    else:
        return STANDARD_PROFILE_PIC

async def save_profile_photo(user_id: int, photo_file_id: str, bot) -> bool:
    """Скачать и сохранить фото профиля"""
    try:
        photo = await bot.get_file(photo_file_id)
        
        photo_path = get_user_profile_photo_path(user_id)
        await bot.download_file(photo.file_path, photo_path)
        
        session = get_session()
        try:
            user = session.query(User).filter(User.user_id == user_id).first()
            if user:
                user.profile_photo_path = photo_path
                user.has_custom_photo = True  
                session.commit()
        finally:
            session.close()
            
        return True
    except Exception as e:
        print(f"Ошибка сохранения фото: {e}")
        return False

async def delete_custom_photo(user_id: int) -> bool:
    """Удалить кастомное фото пользователя"""
    try:
        photo_path = get_user_profile_photo_path(user_id)
        
        if os.path.exists(photo_path):
            os.remove(photo_path)
            
            session = get_session()
            try:
                user = session.query(User).filter(User.user_id == user_id).first()
                if user:
                    user.profile_photo_path = None
                    user.has_custom_photo = False
                    session.commit()
            finally:
                session.close()
            
            return True
        return False
    except Exception as e:
        print(f"Ошибка удаления фото: {e}")
        return False
    
@router.callback_query(F.data == "change_profile_photo")
async def request_profile_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Запрос новой фотографии профиля с кнопкой Назад"""
    user_id = callback.from_user.id
    has_custom_photo = user_has_custom_photo(user_id)
    
    keyboard_buttons = []
    
    if has_custom_photo:
        keyboard_buttons.append(
            [types.InlineKeyboardButton(text="🔄 Вернуть стандартную фотографию", callback_data="reset_to_default_photo")]
        )
    
    keyboard_buttons.append(
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_from_photo_change")]
    )
    
    try:
        await callback.message.edit_caption(
            caption="📸 Отправьте новую фотографию для профиля:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=keyboard_buttons
            )
        )
    except Exception as e:
        print(f"Ошибка редактирования caption: {e}")
        await callback.message.answer(
            "📸 Отправьте новую фотографию для профиля:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=keyboard_buttons
            )
        )
    
    await state.set_state(RegistrationStates.waiting_for_profile_photo)
    await callback.answer()

@router.callback_query(F.data == "back_from_photo_change")
async def back_from_photo_change(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Вернуться из изменения фото в профиль (универсальный)"""
    try:
        await state.clear()
        
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
        session.close()
        
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        profile_text = format_user_full_profile(user, org)
        
        user_photo = await get_profile_photo_for_user(user_id)
        
        try:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=user_photo,
                    caption=profile_text
                ),
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                        [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                    ]
                )
            )
        except:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=user_photo,
                caption=profile_text,
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                        [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                    ]
                )
            )
        
        await callback.answer()
        
    except Exception as e:
        print(f"Ошибка в back_from_photo_change: {e}")
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=STANDARD_PROFILE_PIC,
            caption="👤 Выбери раздел профиля:",
            reply_markup=profile_menu_keyboard()
        )

@router.message(RegistrationStates.waiting_for_profile_photo)
async def handle_profile_photo(message: types.Message, state: FSMContext) -> None:
    """Обработка загруженной фотографии профиля с возможностью вернуться"""
    if not message.photo:
        if message.text == "◀️ Назад":
            await back_from_photo_change(message, state)
            return
        
        await message.answer("❌ Пожалуйста, отправьте фотографию или нажмите 'Назад'")
        return
    
    try:
        try:
            await message.delete()
        except:
            pass
        
        photo_file_id = message.photo[-1].file_id
        user_id = message.from_user.id
        
        success = await save_profile_photo(user_id, photo_file_id, message.bot)
        
        if success:
            session = get_session()
            try:
                user = session.query(User).filter(User.user_id == user_id).first()
                org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
                
                if not user:
                    await message.answer("❌ Пользователь не найден")
                    return
                
                profile_text = format_user_full_profile(user, org)
                
                user_photo = await get_profile_photo_for_user(user_id)
                
                await message.bot.edit_message_caption(
                    chat_id=message.chat.id,
                    message_id=message.message_id - 1,  
                    caption=profile_text + "\n\n✅ Фотография профиля успешно обновлена!",
                    reply_markup=types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                            [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                        ]
                    )
                )
                
                await message.answer("✅ Фотография профиля успешно обновлена!",
                                            reply_markup=types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                        ]
                    ))
                
            finally:
                session.close()
        else:
            await message.answer("❌ Ошибка при сохранении фотографии")
            
    except Exception as e:
        print(f"Ошибка обработки фото: {e}")
        await message.answer(f"❌ Ошибка: {str(e)[:100]}")
    
    finally:
        await state.clear()

@router.callback_query(F.data == "reset_to_default_photo")
async def reset_to_default_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Вернуть стандартную фотографию профиля"""
    user_id = callback.from_user.id
    
    try:
        deleted = await delete_custom_photo(user_id)
        
        if deleted:
            session = get_session()
            try:
                user = session.query(User).filter(User.user_id == user_id).first()
                org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
                
                if not user:
                    await callback.message.edit_text("❌ Пользователь не найден")
                    return
                
                profile_text = format_user_full_profile(user, org)
                
                await callback.message.edit_media(
                    media=InputMediaPhoto(
                        media=STANDARD_PROFILE_PIC,
                        caption=profile_text + "\n\n✅ Стандартная фотография восстановлена"
                    ),
                    reply_markup=types.InlineKeyboardMarkup(
                        inline_keyboard=[
                            [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                            [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_button_to_profile')]
                        ]
                    )
                )
                
                await callback.answer("✅ Фотография восстановлена до стандартной")
                
            finally:
                session.close()
        else:
            await callback.message.edit_text("❌ Не удалось восстановить стандартную фотографию")
            
    except Exception as e:
        print(f"Ошибка восстановления фото: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_photo_change")
async def cancel_photo_change(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Отмена изменения фото - вернуться в профиль"""
    try:
        await state.clear()
        
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
        session.close()
        
        if user:
            profile_text = format_user_full_profile(user, org)
            
            user_photo = await get_profile_photo_for_user(user_id)
            
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=user_photo,
                    caption=profile_text
                ),
                reply_markup=types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                        [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                    ]
                )
            )
        else:
            await callback.message.edit_text("❌ Пользователь не найден")
            
    except Exception as e:
        print(f"Ошибка в cancel_photo_change: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}")
    
    await callback.answer()

@router.callback_query(F.data == "profile_stats")
async def show_profile_stats(callback: types.CallbackQuery) -> None:
    """Показать статистику"""
    try:
        user_id = callback.from_user.id
        stats = MetricsCollector.get_user_stats(user_id)
        
        if not stats:
            await callback.message.delete()
            await callback.message.answer("❌ Статистика не найдена", reply_markup=back_button_to_profile())
            return
        
        stats_text = (
            f"📈 *ВАША СТАТИСТИКА*\n\n"
            f"📊 *Всего опросов:* {stats['total_surveys']}\n"
            f"✅ *Выполнено челленджей:* {stats['completed_challenges']}\n"
            f"*⏳ Активных челленджей:* {stats['pending_challenges']}\n"
            f"📅 *Cегодня:* {stats['today_surveys']} опросов, {stats['today_completed_challenges']} челленджей\n\n"
            f"📊 *Средние показатели:*\n"
            f"  ⚡ *Энергия:* {stats['avg_energy']}/10\n"
            f"  😴 *Сон:* {stats['avg_sleep']}/10\n"
            f"  🎯 *Готовность:* {stats['avg_readiness']}/10\n\n"
            f"📈 *Посещаемость:* {stats['attendance_percent']}%"
        )

        await callback.message.delete()
        await callback.message.answer_photo(photo=stat_pic, caption= stats_text, reply_markup=back_button_to_profile())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_button_to_profile())

@router.callback_query(F.data == "profile_awards")
async def show_profile_awards(callback: types.CallbackQuery) -> None:
    """Показать награды"""
    try:
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        session.close()
        
        if not user:
            await callback.message.delete()
            await callback.message.answer("❌ Пользователь не найден", reply_markup=back_button_to_profile())
            return
        
        registered_at = user.registered_at
        if registered_at.tzinfo is None:
            registered_at = registered_at.replace(tzinfo=timezone.utc)
        
        days_on_platform = (datetime.now(timezone.utc) - registered_at).days + 1
        
        awards_text = (
            f"🏆 *ВАШИ НАГРАДЫ И ДОСТИЖЕНИЯ*\n\n"
            f"💎 *Опыт:* {get_level_name(user.level)}\n"
            f"🎯 *Баллы:* {user.points}\n"
            f"📅 *На платформе:* {days_on_platform} дней\n\n"
        )
        
        if user.points >= 100:
            awards_text += "✅ Достижение: Первые 100 очков! 🎉\n"
        if user.points >= 500:
            awards_text += "✅ Достижение: Масштабист! 500 очков! 🔥\n"
        if user.points >= 1000:
            awards_text += "✅ Достижение: Мастер! 1000 очков! 🏆\n"
        
        if user.level >= 3:
            awards_text += f"✅ Достижение: {get_level_name(user.level)} 👑\n"
        await callback.message.delete()
        await callback.message.answer_photo(photo=awards_pic, caption=awards_text, reply_markup=back_button_to_profile())
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_button_to_profile())


@router.callback_query(F.data == "back_button_to_profile")
async def back_to_profile_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработчик кнопки Назад в профиле"""
    try:
        await state.clear()
        
        user_id = callback.from_user.id
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            session.close()
            return
        
        org = session.query(Organization).filter(Organization.id == user.org_id).first() if user else None
        session.close()
        
        profile_text = format_user_full_profile(user, org)
        
        user_photo = await get_profile_photo_for_user(user_id)
        
        await callback.message.edit_media(
            media=InputMediaPhoto(
                media=user_photo,
                caption=profile_text
            ),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text='📸 Изменить фотографию профиля', callback_data='change_profile_photo')],
                    [types.InlineKeyboardButton(text='◀️ Назад', callback_data='back_to_profile')]
                ]
            )
        )
        
    except Exception as e:
        print(f"Ошибка в back_to_profile_handler: {e}")
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=STANDARD_PROFILE_PIC,
                caption="👤 Выбери раздел профиля:",
                reply_markup=profile_menu_keyboard()
            )
        except:
            await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == 'back_to_profile')
async def back_to_profile_menu(call: types.CallbackQuery) -> None:
    """Показать меню профиля, обработчик кнопки назад"""
    try:
        
        await call.message.delete()
        await call.message.answer_photo(
            photo=STANDARD_PROFILE_PIC, 
            caption="👤 Выбери раздел профиля:",
            reply_markup=profile_menu_keyboard()
        )
        
    except Exception as e:
        print(f"Ошибка в back_to_profile_menu: {e}")
        await call.answer(f"❌ Ошибка: {e}", show_alert=True)


def register_profile_handlers(dp: Dispatcher):
    dp.include_router(router)