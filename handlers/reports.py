# handlers/user_reports.py
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from services.monthly_report import generate_user_monthly_report
from services.report_formatter import ReportFormatter
from database import get_session, User
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query (F.data == 'profile_monthly_report')
async def user_monthly_report(call: types.CallbackQuery):
    """Месячный отчет для пользователя - ТОЛЬКО PDF файл"""
    try:
        # Отправляем сообщение о начале генерации
        status_msg = await call.message.answer("📊 Генерирую ваш месячный отчет...")
        
        # Генерируем отчет
        report = await generate_user_monthly_report(call.from_user.id)
        
        if "error" in report:
            await status_msg.edit_text(f"❌ {report['error']}")
            return
        
        await status_msg.edit_text("📝 Формирую PDF файл...")
        
        # Создаем PDF
        pdf_buffer = ReportFormatter.create_personal_report_pdf(report)
        
        if pdf_buffer is None:
            await status_msg.edit_text("❌ Не удалось создать PDF отчет")
            return
        
        await status_msg.edit_text("📤 Отправляю отчет...")
        
        # Создаем файл для отправки
        pdf_bytes = pdf_buffer.getvalue()
        input_file = BufferedInputFile(
            file=pdf_bytes,
            filename=f"my_report_{datetime.now().strftime('%Y%m')}.pdf"
        )
        
        # Отправляем файл
        await call.message.bot.send_document(
            chat_id=call.message.chat.id,
            document=input_file,
            caption=(
                f"📊 *Ваш месячный отчет*\n\n"
                f"*Период:* {report.get('period', 'Не указан')}\n"
                f"*Челленджи выполнено:* {report.get('stats', {}).get('total_challenges', 0)}\n"
                f"*Очков заработано:* {report.get('stats', {}).get('total_points', 0)}\n"
                f"*Текущий уровень:* {report.get('user_level', 1)}\n\n"
                f"📈 Отчет содержит детальную статистику"
            ),
            parse_mode="Markdown"
        )
        
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета: {e}")
        await call.message.answer(f"❌ Не удалось сгенерировать отчет: {str(e)[:100]}")
