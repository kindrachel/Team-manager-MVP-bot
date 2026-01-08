# handlers/admins/modules/statistics.py
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from database import User, get_session
from services import MetricsCollector
from services.report_formatter import ReportFormatter
from services.ai_report_analyzer import AIReportAnalyzer
from services.monthly_report import generate_trainer_monthly_report
import logging
from datetime import datetime
import asyncio

router = Router()
logger = logging.getLogger(__name__)
report_analyzer = AIReportAnalyzer()


@router.callback_query(F.data == "admin_view_stats")
async def admin_view_stats(callback: types.CallbackQuery) -> None:
    """Показать статистику команды"""
    user_id = callback.from_user.id
    
    session = get_session()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        stats = MetricsCollector.get_organization_stats(user.org_id)
        daily = MetricsCollector.get_daily_report(user.org_id)
        
        stats_text = (
            f"📊 СТАТИСТИКА КОМАНДЫ\n\n"
            f"🏢 {stats['org_name']}\n"
            f"👥 Всего членов: {stats['total_members']}\n"
            f"📝 Всего опросов: {stats['total_surveys']}\n"
            f"⚡ Выполнено челленджей: {stats['completed_challenges']}\n"
            f"🎯 Средний уровень: {stats['avg_level']}\n"
            f"💎 Всего очков в команде: {stats['total_points']}\n\n"
            f"📈 СЕГОДНЯ ({daily['date']}):\n"
            f"✅ Активно членов: {daily['active_users']}/{stats['total_members']}\n"
            f"📝 Опросов пройдено: {daily['total_surveys_today']}\n"
            f"⚡ Челленджей выполнено: {daily['completed_challenges']}\n"
            f"📊 Процент ответивших: {daily['survey_response_rate']}%\n"
            f"⚡ Средняя энергия: {daily['avg_energy']}/10"
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_admin_panel")]
        ])
        
        await callback.message.edit_text(stats_text, reply_markup=kb)
    finally:
        session.close()

@router.callback_query(F.data == "admin_detailed_report")
async def admin_detailed_report(callback: types.CallbackQuery):
    """Подробный отчет по игрокам с AI-анализом"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        await callback.message.edit_text("👥 Генерирую подробный AI-отчет по игрокам...")
        
        # Генерируем детальный отчет
        report = await report_analyzer.generate_detailed_member_report(user.org_id)
        
        if "error" in report:
            await callback.message.edit_text(f"❌ {report['error']}")
            return
        
        # Общий анализ команды
        team_analysis = report.get("team_analysis", {})
        
        team_text = f"""
🏆 *ОБЩИЙ AI-АНАЛИЗ КОМАНДЫ*

{team_analysis.get('team_assessment', 'Анализ команды')}

🎯 *Рекомендации по тренировкам:*
{chr(10).join(f"• {rec}" for rec in team_analysis.get('training_recommendations', []))}

💡 *Стратегии мотивации:*
{chr(10).join(f"• {strat}" for strat in team_analysis.get('motivation_strategies', []))}

📝 *Заметки для тренера:*
{team_analysis.get('coach_notes', 'Продолжайте работу')}
"""
        
        await callback.message.edit_text(team_text, parse_mode="Markdown")
        
        # Отправляем анализ по каждому игроку
        for idx, member_report in enumerate(report.get("member_reports", []), 1):
            user_data = member_report["user_data"]
            analysis = member_report["ai_analysis"]
            
            member_text = f"""
👤 *ИГРОК {idx}: {user_data['name']}*
*Уровень:* {user_data['level']} | *Очки:* {user_data['points']}

📊 *Статистика:*
• Выполнено челленджей: {user_data['completed_challenges']}/{user_data['total_challenges']}
• Процент выполнения: {user_data['completion_rate']:.1f}%
• Опросов: {user_data['recent_surveys']}

🤖 *AI-АНАЛИЗ:*
{analysis.get('player_summary', 'Нет анализа')}

🌟 *Сильные стороны:*
{chr(10).join(f"• {strength}" for strength in analysis.get('strengths', []))}

🎯 *Над чем работать:*
{chr(10).join(f"• {area}" for area in analysis.get('improvement_areas', []))}

💡 *Рекомендации:*
{chr(10).join(f"• {rec}" for rec in analysis.get('personal_recommendations', []))}

💫 *Мотивация:* {analysis.get('motivational_note', 'Продолжай в том же духе!')}
"""
            
            await callback.message.answer(member_text, parse_mode="Markdown")
            await asyncio.sleep(0.5)
        
        # Итог
        await callback.message.answer(
            f"✅ *Отчет сгенерирован!*\n\n"
            f"Всего проанализировано: {report['total_members']} игроков\n"
            f"Время генерации: {report['generated_at']}",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Ошибка детального отчета: {e}")
        await callback.message.edit_text("❌ Ошибка генерации отчета")
    finally:
        session.close()

@router.callback_query(F.data == "admin_monthly_report")
async def admin_monthly_report(callback: types.CallbackQuery):
    """Месячный отчет для тренера - ТОЛЬКО PDF файл"""
    try:
        user_id = callback.from_user.id
        
        session = get_session()
        user = session.query(User).filter(User.user_id == user_id).first()
        
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        await callback.message.edit_text("📊 Генерирую месячный отчет команды...")
        
        # Генерируем отчет
        report = await generate_trainer_monthly_report(user.org_id)
        
        if "error" in report:
            await callback.message.edit_text(f"❌ {report['error']}")
            return
        
        await callback.message.edit_text("📝 Формирую PDF файл...")
        
        # Создаем PDF
        pdf_buffer = ReportFormatter.create_trainer_report_pdf(report)
        
        if pdf_buffer is None:
            await callback.message.edit_text("❌ Не удалось создать PDF отчет")
            return
        
        await callback.message.edit_text("📤 Отправляю отчет...")
        
        # Создаем файл для отправки
        pdf_bytes = pdf_buffer.getvalue()
        input_file = BufferedInputFile(
            file=pdf_bytes,
            filename=f"team_report_{datetime.now().strftime('%Y%m')}.pdf"
        )
        
        # Отправляем файл
        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=input_file,
            caption=(
                f"🏢 *Месячный отчет команды*\n\n"
                f"*Команда:* {report.get('team_analysis', {}).get('team_assessment', 'Неизвестно')}\n"
                f"*Период:* Месячный отчет\n"
                f"*Участников:* {report.get('total_members', 0)}\n"
                f"*Челленджей выполнено:* {sum(m['user_data'].get('completed_challenges', 0) for m in report.get('member_reports', []))}\n"
                f"*Очков заработано:* {sum(m['user_data'].get('points', 0) for m in report.get('member_reports', [])):,}\n\n"
                f"📈 Отчет содержит статистику команды"
            ),
            parse_mode="Markdown"
        )
        
        # Удаляем сообщение о статусе
        await callback.message.delete()
        
        # Показываем краткое уведомление
        await callback.message.answer(
            "✅ Отчет отправлен! Проверьте файл выше.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_admin_panel")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)[:100]}")
    finally:
        session.close()

@router.callback_query(F.data == "admin_members_report")
async def admin_members_report(callback: types.CallbackQuery):
    """Подробный отчет по игрокам в виде файла"""
    user_id = callback.from_user.id
    session = get_session()
    
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user or not user.org_id:
            await callback.message.edit_text("❌ Вы не администратор команды")
            return
        
        await callback.message.edit_text("👥 Генерирую детальный отчет по игрокам...")
        
        pdf_buffer = await report_analyzer.generate_members_report_pdf(user.org_id)
        
        pdf_bytes = pdf_buffer.getvalue()
        
        input_file = BufferedInputFile(
            file=pdf_bytes,
            filename=f"members_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
        
        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=input_file,
            caption=f"👥 Детальный отчет по игрокам\nДата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await callback.message.answer("✅ Отчет по игрокам готов!")
        
        pdf_buffer.close()
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета по игрокам: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка генерации отчета: {str(e)[:100]}")
    finally:
        session.close()