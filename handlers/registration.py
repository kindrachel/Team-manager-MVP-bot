from aiogram import Router, F, types, Dispatcher, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto
from datetime import datetime, timezone as tz
from database import User, Organization, UserRole, get_session
from keyboards import org_type_keyboard, main_menu_keyboard
from utils.time import get_user_timezone, format_datetime, get_current_org_time
from utils.states import RegistrationStates
from utils.validators import validate_phone_number
from aiogram.enums import ParseMode
import pytz
import asyncio
import logging


logger = logging.getLogger(__name__)
router = Router()

registartion_pic = FSInputFile('pictures/register.png')
sucсefulreg_pic = FSInputFile('pictures/succeful_register.png')

# Карта команд и организаций
TEAM_MAP = {
    "team_proffloyd": "ФК \"ПроффЛойд\"",
    "team_footbutsproff": "FootБутсProff",
    "team_proffloyd_a": "ПроффЛойд-А",
    "team_factor": "ОП «Фактор-Гарант»",
    "team_unisoft": "Юнисофт",
    "team_fitservice": "FIT SERVICE",
    "org_ecoproff": "ЭкоПроффЛойд"
}

POSITION_MAP = {
    "gk": "Вратарь (ВРТ)",
    "cb": "Центральный защитник (ЦЗ)",
    "fb": "Крайний защитник (ЛЗ/ПЗ)",
    "cdm": "Центральный опорный полузащитник (ЦОП)",
    "cm": "Центральный полузащитник (ЦП)",
    "wm": "Фланговый полузащитник (ЛП/ПП)",
    "cam": "Атакующий полузащитник (ЦАП)",
    "wf": "Фланговый атакующий (ЛФА/ПФА)",
    "fw": "Нападающий (форвард)"
}

def get_team_map_from_db():
    """Получает организации из базы данных"""
    session = get_session()
    try:
        organizations = session.query(Organization).all()
        team_map = {}
        
        for org in organizations:
            # Создаем ключи на основе ID или имени
            key = f"org_{org.id}"
            team_map[key] = org.name
            
        return team_map
    finally:
        session.close()

async def _save_user_to_db(callback, state: FSMContext, data=None):
    """Универсальная функция сохранения пользователя в БД"""
    if data is None:
        data = await state.get_data()
    
    session = get_session()
    
    try:
        chat_id = callback.message.chat.id
        user_id = callback.from_user.id
        
        from config import load_config
        config = load_config()
        
        # Получаем данные из состояния
        org_id = data.get("org_id")
        org_name = data.get("team_name", "Default")
        direction = data.get("direction", "sport")
        sport_type = data.get("sport_type", "football")
        
        # Находим организацию по ID или названию
        if org_id:
            org = session.query(Organization).filter(Organization.id == org_id).first()
        else:
            # Запасной вариант - поиск по названию
            org = session.query(Organization).filter(
                Organization.name == org_name,
                Organization.org_type == sport_type
            ).first()
        
        if not org:
            # Если организация не найдена, создаем новую
            org = Organization(
                name=org_name,
                org_type=sport_type,
                admin_id=user_id,
                created_at=datetime.now(tz.utc)
            )
            session.add(org)
            session.flush()
        
        # Определяем роль пользователя
        if user_id in config.admin_ids:
            user_role = UserRole.SUPER_ADMIN.value
            role_display = "👑 Суперадмин системы"
            trainer_verified = True
            verification_requested_at = None
        else:
            user_role = data.get("user_role", UserRole.MEMBER.value)
            role_display = data.get("role_text", "👤 Участник")
            trainer_verified = data.get("trainer_verified", True)
            
            # Если тренер, ставим дату запроса на верификацию
            verification_requested_at = None
            if user_role == UserRole.TRAINER.value and not trainer_verified:
                verification_requested_at = datetime.now(tz.utc)
        
        # Проверяем существующего пользователя
        existing_user = session.query(User).filter(User.user_id == user_id).first()
        
        if existing_user:
            # Обновляем существующего пользователя
            existing_user.name = data["name"]
            existing_user.phone = data["phone"]
            existing_user.direction = direction
            existing_user.sport_type = sport_type
            existing_user.position = data["position"]
            existing_user.role = user_role
            existing_user.trainer_verified = trainer_verified
            existing_user.verification_requested_at = verification_requested_at
            existing_user.org_id = org.id
            existing_user.last_active = datetime.now()
            session.commit()
            user = existing_user
        else:
            # Создаем нового пользователя
            user = User(
                user_id=user_id,
                chat_id=chat_id,
                org_id=org.id,
                name=data["name"],
                phone=data["phone"],
                direction=direction,
                sport_type=sport_type,
                position=data["position"],
                role=user_role,
                trainer_verified=trainer_verified,
                verification_requested_at=verification_requested_at,
                points=0,
                level=1,
                registered_at=datetime.now(tz.utc), 
                last_active=datetime.now(tz.utc) 
            )
            session.add(user)
            session.commit()
        
        # Формируем сообщение об успехе
        sport_emojis = {
            "football": "⚽",
            "basketball": "🏀", 
            "volleyball": "🏐",
            "taekwondo": "🥋",
            "dance": "🔥"
        }
        
        sport_emoji = sport_emojis.get(sport_type, "🏢")
        
        success_text = (
            f"✅ Регистрация успешна!\n\n"
            f"👤 {user.name}\n"
            f"📲 {user.phone}\n"
            f"🎯 {user.position}\n"
            f"{sport_emoji} {org.name}\n"
            f"👨‍💼 Роль: {role_display}\n\n"
        )
        
        # Добавляем информацию о верификации для тренеров
        if user_role == UserRole.TRAINER.value and not trainer_verified:
            success_text += "⏳ Ваша роль тренера ожидает подтверждения администратором.\n"
            success_text += "До подтверждения у вас будут права обычного участника.\n\n"
            
            # Отправляем уведомление админам организации
            await notify_admins_about_trainer_request(callback.bot, user, org)
        
        success_text += f"{'🎖️ Вы суперадмин! Доступна админ-панель.' if user_id in config.admin_ids else '🎊 Добро пожаловать!'}\n"
        success_text += "Ваш путь к мастерству начинается! 💪"
        
        await callback.message.edit_text(
            success_text
            )
        )
        
        # Показываем соответствующее меню
        if user_id in config.admin_ids:
            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="show_admin_menu")],
                [InlineKeyboardButton(text="👤 Профиль", callback_data="profile_view")]
            ])
            await callback.message.answer("Выберите действие:", reply_markup=admin_kb)
        else:
            await callback.message.answer("Выбери действие:", reply_markup=main_menu_keyboard())
        
        await state.clear()
    
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользователя: {e}")
        await callback.message.edit_text(f"❌ Ошибка при регистрации: {str(e)}")
    finally:
        session.close()

async def notify_admins_about_trainer_request(bot, trainer: User, org: Organization):
    """Отправить уведомление админам о запросе на тренера"""
    session = get_session()
    try:
        # Находим всех админов организации
        admins = session.query(User).filter(
            User.org_id == org.id,
            User.role.in_([UserRole.ORG_ADMIN.value, UserRole.SUPER_ADMIN.value])
        ).all()
        
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.chat_id,
                    text=f"👨‍🏫 Новый запрос на роль тренера!\n\n"
                         f"Пользователь: {trainer.name}\n"
                         f"Телефон: {trainer.phone or 'Не указан'}\n"
                         f"Позиция: {trainer.position or 'Не указана'}\n"
                         f"Организация: {org.name}\n\n"
                         f"Для подтверждения перейдите в админ-панель → Управление ролями",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text="📋 Перейти к запросам",
                            callback_data="admin_manage_roles"
                        )]
                    ])
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление админу {admin.user_id}: {e}")
    finally:
        session.close()

@router.callback_query(F.data == "confirm_name")
async def confirm_name_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Подтверждение ФИО и переход к выбору направления"""
    data = await state.get_data()
    name = data.get('name')
    
    # Редактируем сообщение с подтверждением
    try:
        await callback.message.edit_media(
                f"✅ <b>Имя: {name}</b>\n\nВыберите направление:",
                parse_mode=ParseMode.HTML
            ),
            reply_markup=org_type_keyboard()
        )
    except:
        # Если не получилось редактировать, отправляем новое
        await callback.message.answer(
            f"✅ <b>Имя: {name}</b>\n\nВыберите направление:",
            parse_mode=ParseMode.HTML,
            reply_markup=org_type_keyboard()
        )
    
    # Переходим к выбору направления
    await state.set_state(RegistrationStates.waiting_for_direction)
    await callback.answer()

@router.callback_query(F.data == "edit_name")
async def edit_name_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Исправление ФИО"""
    try:
        await callback.edit_text(
                "Пожалуйста, укажите ваше ФИО еще раз:",
                parse_mode=ParseMode.HTML
            ),
            reply_markup=None  # Убираем клавиатуру
        )
    except:
        await callback.message.answer(
            "Пожалуйста, укажите ваше ФИО еще раз:",
            parse_mode=ParseMode.HTML
        )
    
    # Возвращаем к вводу ФИО
    await state.set_state(RegistrationStates.waiting_for_name)
    await callback.answer("Введите ФИО заново")

async def send_new_registration_step(message: types.Message, state: FSMContext, name: str):
    """Отправить новый шаг регистрации"""
    new_msg = await message.answer(
        f"✅ <b>Имя: {name}</b>\n\nВыберите направление:",
        parse_mode=ParseMode.HTML,
        reply_markup=org_type_keyboard()
    )
    await state.update_data(registration_message_id=new_msg.message_id)

@router.callback_query(RegistrationStates.waiting_for_direction)
async def process_direction(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка направления - ТОЛЬКО СПОРТ"""
    direction = callback.data.replace("dir_", "")
    
    if direction != "sport":
        # Показываем сообщение, что только спорт доступен
        await callback.answer(
            "⏳ Направление временно недоступно.\n"
            "В настоящее время доступна регистрация только для спортивных организаций.",
            show_alert=True
        )
        return
    
    await state.update_data(direction=direction)
    
    # Показываем выбор вида спорта
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚽ Футбол", callback_data="sport_football")],
        [InlineKeyboardButton(text="🏀 Баскетбол", callback_data="sport_basketball")],
        [InlineKeyboardButton(text="🏐 Волейбол", callback_data="sport_volleyball")],
        [InlineKeyboardButton(text="🥋 Тхэквондо", callback_data="sport_taekwondo")],
        [InlineKeyboardButton(text="🔥 Танцы", callback_data="sport_dance")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_name_confirmation")]
    ])
    
    await callback.message.delete()
    await callback.message.answer("Выберите вид спорта:", reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_sport_type)

async def back_to_name_confirmation(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Возврат к подтверждению имени"""
    data = await state.get_data()
    name = data.get('name', '')
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, верно", callback_data="confirm_name"),
            InlineKeyboardButton(text="❌ Нет, исправить", callback_data="edit_name")
        ]
    ])
    
    await callback.message.edit_text(
        f"✅ <b>Имя: {name}</b>\n\n",
        "Если все верно, нажмите кнопку ниже ⬇️",
            parse_mode=ParseMode.HTML
        ),
        reply_markup=confirm_kb
    )

@router.callback_query(RegistrationStates.waiting_for_sport_type)
async def process_sport_type(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка вида спорта"""
    sport_type = callback.data.replace("sport_", "")
    await state.update_data(sport_type=sport_type)
    
    # Получаем организации из базы данных для этого вида спорта
    session = get_session()
    try:
        organizations = session.query(Organization).filter(
            Organization.org_type == sport_type
        ).order_by(Organization.name).all()
        
        if not organizations:
            # Если нет организаций, показываем сообщение
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к выбору спорта", 
                                    callback_data="back_to_direction")]
            ])
            
            await callback.message.edit_text(
                f"Пока нет организаций для {sport_type}.\n"
                "Обратитесь к администратору для создания организации.",
                reply_markup=kb
            )
            return
        
        # Создаем клавиатуру с организациями из базы
        buttons = []
        row = []
        
        for i, org in enumerate(organizations, 1):
            # Определяем эмодзи в зависимости от вида спорта
            emoji = {
                "football": "⚽",
                "basketball": "🏀",
                "volleyball": "🏐",
                "taekwondo": "🥋",
                "dance": "🔥"
            }.get(sport_type, "🏢")
            
            button_text = f"{emoji} {org.name}"
            
            # Добавляем кнопку в ряд (по 1 кнопке в ряд для лучшей читаемости)
            buttons.append([InlineKeyboardButton(
                text=button_text,
                callback_data=f"org_{org.id}"  # Используем ID организации
            )])
        
        # Добавляем кнопку "Назад"
        buttons.append([
            InlineKeyboardButton(text="🔙 Назад к выбору спорта", 
                               callback_data="back_to_direction")
        ])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(
            f"Выберите вашу команду/организацию ({sport_type}):",
            reply_markup=kb
        )
        await state.set_state(RegistrationStates.waiting_for_org_selection)
        
    except Exception as e:
        logger.error(f"Ошибка при получении организаций: {e}")
        await callback.answer("❌ Ошибка при загрузке организаций", show_alert=True)
    finally:
        session.close()

@router.callback_query(RegistrationStates.waiting_for_org_selection, F.data.startswith("org_"))
async def process_org_selection(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора организации из базы данных"""
    try:
        org_id = int(callback.data.replace("org_", ""))
        
        session = get_session()
        try:
            org = session.query(Organization).filter(Organization.id == org_id).first()
            
            if not org:
                await callback.answer("❌ Организация не найдена", show_alert=True)
                return
            
            # Сохраняем данные организации
            await state.update_data(
                team_name=org.name,
                org_id=org.id,
                direction="sport",  # Всегда спорт
                sport_type=org.org_type  # Сохраняем вид спорта
            )
            
            # Переходим к вводу телефона
            await callback.message.edit_text(
                    f"✅ Вы выбрали: {org.name}\n\n"
                           "Укажите ваш номер телефона в формате +7 (XXX) XXX-XX-XX:"
                )
            )
            await state.set_state(RegistrationStates.waiting_for_phone)
            
        finally:
            session.close()
            
    except ValueError:
        await callback.answer("❌ Неверный формат организации", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка выбора организации: {e}")
        await callback.answer("❌ Ошибка выбора организации", show_alert=True)

from aiogram.exceptions import TelegramBadRequest


@router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext) -> None:
    """Обработка телефона с валидацией и подтверждением"""
    phone = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass
    
    is_valid, result = validate_phone_number(phone)
    
    if not is_valid:
        error_msg = await message.answer(result)
        await asyncio.sleep(3)
        try:
            await error_msg.delete()
        except:
            pass
        return
    
    await state.update_data(phone=result, phone_raw=phone)
    
    data = await state.get_data()
    name = data.get('name', '')
    
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, верно", callback_data="confirm_phone"),
            InlineKeyboardButton(text="❌ Нет, исправить", callback_data="edit_phone")
        ]
    ])
    
    try:
        await message.bot.edit_message_media(
            chat_id=message.chat.id,
            message_id=message.message_id - 1,
            media=InputMediaPhoto(
                media=registartion_pic,
                caption=(
                    f"🔍 <b>Проверьте правильность номера:</b>\n\n"
                    f"👤 <b>{name}</b>\n"
                    f"📱 <b>{result}</b>\n\n"
                    f"Если все верно, нажмите кнопку ниже ⬇️"
                ),
                parse_mode=ParseMode.HTML
            ),
            reply_markup=confirm_keyboard
        )
    except (TelegramBadRequest, ValueError):
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id - 1
            )
        except:
            pass
        
        await message.answer((
                f"🔍 <b>Проверьте правильность номера:</b>\n\n"
                f"👤 <b>{name}</b>\n"
                f"📱 <b>{result}</b>\n\n"
                f"Если все верно, нажмите кнопку ниже ⬇️"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_keyboard
        )
    
    await state.set_state(RegistrationStates.waiting_for_phone_confirmation)

@router.callback_query(RegistrationStates.waiting_for_phone_confirmation, F.data == "confirm_phone")
async def confirm_phone_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Подтверждение номера телефона"""
    data = await state.get_data()
    phone = data.get('phone')

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤴 Вратарь (ВРТ)", callback_data="pos_gk")],
        [InlineKeyboardButton(text="⚪ Центральный защитник (ЦЗ)", callback_data="pos_cb")],
        [InlineKeyboardButton(text="🔲 Крайний защитник (ЛЗ/ПЗ)", callback_data="pos_fb")],
        [InlineKeyboardButton(text="🟡 Центральный опорный полузащитник (ЦОП)", callback_data="pos_cdm")],
        [InlineKeyboardButton(text="⚽ Центральный полузащитник (ЦП)", callback_data="pos_cm")],
        [InlineKeyboardButton(text="🟠 Фланговый полузащитник (ЛП/ПП)", callback_data="pos_wm")],
        [InlineKeyboardButton(text="🟢 Атакующий полузащитник (ЦАП)", callback_data="pos_cam")],
        [InlineKeyboardButton(text="📍 Фланговый атакующий (ЛФА/ПФА)", callback_data="pos_wf")],
        [InlineKeyboardButton(text="💥 Нападающий (форвард)", callback_data="pos_fw")],
        [InlineKeyboardButton(text="➕ Смежная позиция", callback_data="pos_custom")]
    ])
    text = "Укажите свое амплуа:"

    try:
        await callback.message.edit_text(
                f"✅ <b>Номер подтвержден: {phone}</b>\n\n{text}",
                parse_mode=ParseMode.HTML
            ),
            reply_markup=kb
        )
    except TelegramBadRequest:
        await callback.message.answer(
            f"✅ <b>Номер подтвержден: {phone}</b>\n\n{text}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

    await state.set_state(RegistrationStates.waiting_for_position)
    await callback.answer()

@router.callback_query(RegistrationStates.waiting_for_phone_confirmation, F.data == "edit_phone")
async def edit_phone_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Исправление номера телефона"""
    try:
        await callback.message.edit_text(
                "Пожалуйста, укажите ваш номер телефона еще раз:\n\nПример: +7 (912) 345-67-89",
                parse_mode=ParseMode.HTML
            ),
            reply_markup=None 
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "Пожалуйста, укажите ваш номер телефона еще раз:\n\nПример: +7 (912) 345-67-89",
            parse_mode=ParseMode.HTML
        )
    
    await state.set_state(RegistrationStates.waiting_for_phone)
    await callback.answer("Введите номер заново")

@router.callback_query(RegistrationStates.waiting_for_position)
async def process_position(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Завершение регистрации или запрос кастомной должности"""
    pos_code = callback.data.replace("pos_", "")

    if pos_code == "custom":
        try:
            await callback.message.edit_caption(
                caption="Введите вашу должность/позицию вручную:",
                reply_markup=None
            )
        except TelegramBadRequest:
            await callback.message.answer("Введите вашу должность/позицию вручную:")
            try:
                await callback.message.delete()
            except:
                pass

        await state.set_state(RegistrationStates.waiting_for_custom_position)
        return

    position = POSITION_MAP.get(pos_code, "Участник")
    await state.update_data(position=position)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Тренер", callback_data="role_trainer")],
        [InlineKeyboardButton(text="⚽ Игрок", callback_data="role_member")]
    ])
    role_text = "Выберите вашу роль в команде:"

    try:
        await callback.message.edit_caption(
            caption=role_text,
            reply_markup=kb
        )
    except TelegramBadRequest:
        try:
            await callback.message.edit_text(
                role_text
                ),
                reply_markup=kb
            )
        except TelegramBadRequest:
            await callback.message.answer(role_text, reply_markup=kb)
            try:
                await callback.message.delete()
            except:
                pass

    await state.set_state(RegistrationStates.waiting_for_role)

@router.message(RegistrationStates.waiting_for_custom_position)
async def process_custom_position(message: types.Message, state: FSMContext) -> None:
    """Обработка кастомной должности"""
    position = message.text
    await state.update_data(position=position)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍🏫 Тренер", callback_data="role_trainer")],
        [InlineKeyboardButton(text="⚽ Игрок", callback_data="role_member")]
    ])
    role_text = "Выберите вашу роль в команде:"

    await message.delete()
    await message.answer(role_text, reply_markup=kb)
    await state.set_state(RegistrationStates.waiting_for_role)

@router.callback_query(RegistrationStates.waiting_for_role)
async def process_role(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора роли"""
    from config import load_config

    config = load_config()
    user_telegram_id = callback.from_user.id

    if user_telegram_id in config.admin_ids:
        user_role = UserRole.SUPER_ADMIN.value
        role_text = "👑 Суперадмин системы"
        trainer_verified = True  # Суперадмины сразу верифицированы
    else:
        if callback.data == "role_trainer":
            user_role = UserRole.TRAINER.value
            trainer_verified = False  # Тренеры требуют верификации
            role_text = "👨‍🏫 Тренер команды (требует подтверждения)"
        else:
            user_role = UserRole.MEMBER.value
            role_text = "👤 Участник"
            trainer_verified = True  # Участники не требуют верификации

    await state.update_data(
        user_role=user_role,
        trainer_verified=trainer_verified,
        role_text=role_text
    )

    data = await state.get_data()
    await _save_user_to_db(callback, state, data)

def register_registration_handlers(dp: Dispatcher):

    dp.include_router(router)
