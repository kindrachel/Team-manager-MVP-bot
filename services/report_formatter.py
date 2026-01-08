import json
import csv
from datetime import datetime
from io import StringIO, BytesIO
from typing import Dict, List
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont  # Добавлен импорт
import matplotlib.pyplot as plt
import logging
import os

logger = logging.getLogger(__name__)

_PDF_FONT_NAME = None

def get_available_fonts():
    """Получить список доступных шрифтов"""
    try:
        return pdfmetrics.getRegisteredFontNames()
    except:
        return []

def get_best_font():
    """Выбрать лучший доступный шрифт (с поддержкой кириллицы)"""
    global _PDF_FONT_NAME

    # Если шрифт уже установлен - используем его
    if _PDF_FONT_NAME is not None:
        return _PDF_FONT_NAME

    available_fonts = get_available_fonts()
    logger.info(f"Доступные шрифты: {available_fonts}")
    
    # Приоритет: DejaVuSans -> Helvetica
    font_priority = ['DejaVuSans', 'Helvetica']
    
    for font in font_priority:
        if font in available_fonts:
            logger.info(f"✅ Выбран шрифт: {font}")
            _PDF_FONT_NAME = font
            return font
    
    # Fallback на Helvetica
    logger.warning("⚠️ Шрифты с кириллицей не найдены, использую Helvetica")
    _PDF_FONT_NAME = 'Helvetica'
    return _PDF_FONT_NAME

def set_fallback_font(font_name: str):
    """Установить fallback шрифт (вызывается из main.py)"""
    global _PDF_FONT_NAME
    _PDF_FONT_NAME = font_name
    logger.info(f"📝 Установлен шрифт для PDF: {font_name}")

def get_pdf_font_name():
    """Получить имя шрифта для использования в PDF"""
    # Если шрифт еще не определен, определяем его
    if _PDF_FONT_NAME is None:
        get_best_font()
    
    return _PDF_FONT_NAME

class ReportFormatter:
    """Форматирование отчетов в различные форматы"""
    
    @staticmethod
    def create_daily_report_pdf(report_data: Dict) -> BytesIO:
        """Создание PDF отчета за день"""
        buffer = BytesIO()
        
        
        try:
            # Получаем корректное имя шрифта
            font_name = get_pdf_font_name()
            logger.info(f"📝 Использую шрифт: {font_name} для создания отчета")
            
            # Проверяем доступные жирные шрифты
            bold_font_name = f'{font_name}-Bold'
            available_fonts = get_available_fonts()
            
            if bold_font_name not in available_fonts:
                logger.warning(f"⚠️ Жирный шрифт {bold_font_name} не найден, использую {font_name}")
                bold_font_name = font_name
            
            logger.info(f"📝 Использую жирный шрифт: {bold_font_name}")
            
            # Создаем PDF документ
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            
            # Используем стили со шрифтами, поддерживающими кириллицу
            styles = getSampleStyleSheet()
            
            # Стили с указанием шрифтов
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontName=font_name,  
                fontSize=16,
                spaceAfter=20,
                textColor=colors.HexColor('#2E86C1')
            )
            
            heading_style = ParagraphStyle(
                'Heading2',
                parent=styles['Heading2'],
                fontName=font_name,
                fontSize=14,
                spaceAfter=10,
                textColor=colors.HexColor('#34495E')
            )
            
            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                spaceAfter=5,
                encoding='utf-8'
            )
            
            bold_style = ParagraphStyle(
                'Bold',
                parent=styles['Normal'],
                fontName=bold_font_name,
                fontSize=10,
                spaceAfter=5,
                encoding='utf-8'
            )
            
            story.append(Paragraph("■ ЕЖЕДНЕВНЫЙ ОТЧЕТ", title_style))
            story.append(Paragraph(f"Команда: {report_data.get('org_name', 'Неизвестно')}", heading_style))
            story.append(Paragraph(f"Дата: {report_data.get('date', datetime.now().strftime('%d.%m.%Y'))}", heading_style))
            story.append(Spacer(1, 20))
            
            stats = report_data.get('daily_stats', {})
            stats_table_data = [
                [Paragraph('Метрика', bold_style), Paragraph('Значение', bold_style)],
                [Paragraph('Всего участников', normal_style), 
                Paragraph(str(stats.get('total_members', 0)), normal_style)],
                [Paragraph('Активных сегодня', normal_style), 
                Paragraph(str(stats.get('active_today', 0)), normal_style)],
                [Paragraph('Выполнено челленджей', normal_style), 
                Paragraph(str(stats.get('completed_challenges_today', 0)), normal_style)],
                [Paragraph('Пройдено опросов', normal_style), 
                Paragraph(str(stats.get('submitted_surveys_today', 0)), normal_style)],
                [Paragraph('Заработано очков', normal_style), 
                Paragraph(str(stats.get('total_points_earned', 0)), normal_style)]
            ]
            
            stats_table = Table(stats_table_data, colWidths=[3*inch, 2*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), bold_font_name),  # ВАЖНО: используем bold_font_name
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(Paragraph("▼ Статистика за день", heading_style))
            story.append(stats_table)
            story.append(Spacer(1, 20))
            
            # AI анализ
            ai_analysis = report_data.get('ai_analysis', {})
            if ai_analysis:
                story.append(Paragraph("▶ AI-АНАЛИЗ", heading_style))
                story.append(Paragraph(f"<b>Краткое резюме:</b> {ai_analysis.get('executive_summary', 'Нет данных')}", normal_style))
                story.append(Paragraph(f"<b>Настроение команды:</b> {ai_analysis.get('team_mood', 'Неизвестно')}", normal_style))
                story.append(Spacer(1, 10))
                
                # Ключевые достижения
                if 'key_achievements' in ai_analysis:
                    story.append(Paragraph("<b>★ Ключевые достижения:</b>", normal_style))
                    for achievement in ai_analysis['key_achievements']:
                        story.append(Paragraph(f"• {achievement}", normal_style))
                
                story.append(Spacer(1, 10))
                
                # Рекомендации
                if 'ai_recommendations' in ai_analysis:
                    story.append(Paragraph("<b>→ Рекомендации на завтра:</b>", normal_style))
                    for rec in ai_analysis['ai_recommendations']:
                        priority_emoji = {"high": "●", "medium": "○", "low": "△"}.get(rec.get('priority', 'medium'), '○')
                        story.append(Paragraph(f"{priority_emoji} {rec.get('action', '')}: {rec.get('reason', '')}", normal_style))
                
                story.append(Spacer(1, 10))
                story.append(Paragraph(f"<b>💫 Мотивация:</b> {ai_analysis.get('motivational_message', '')}", normal_style))
            
            # Лучшие игроки
            top_performers = report_data.get('top_performers', [])
            if top_performers:
                story.append(Spacer(1, 20))
                story.append(Paragraph("★ ЛУЧШИЕ ИГРОКИ СЕГОДНЯ", heading_style))
                
                performers_data = [
                    [Paragraph('Имя', normal_style), 
                    Paragraph('Очки', normal_style), 
                    Paragraph('Челленджи', normal_style), 
                    Paragraph('Опросы', normal_style)]
                ]
                for player in top_performers[:5]:
                    performers_data.append([
                        Paragraph(player.get('name', 'Неизвестно'), normal_style),
                        Paragraph(str(player.get('points_today', 0)), normal_style),
                        Paragraph(str(player.get('challenges_today', 0)), normal_style),
                        Paragraph(str(player.get('surveys_today', 0)), normal_style)
                    ])
                
                performers_table = Table(performers_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch])
                performers_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27AE60')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), bold_font_name),  # ВАЖНО: используем bold_font_name
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EAFAF1')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                
                story.append(performers_table)
            
            # Футер
            story.append(Spacer(1, 30))
            story.append(Paragraph(f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}", normal_style))
            story.append(Paragraph(" ПроффПомощник | vadirss.ru", normal_style))
            
            # Собираем документ
            doc.build(story)
            buffer.seek(0)
            
            logger.info("✅ Ежедневный отчет успешно создан")
            return buffer
            
        except Exception as e:
            logger.error(f"Ошибка создания PDF отчета: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: создаем простой текстовый отчет
            return ReportFormatter.create_text_report(report_data)
    
    @staticmethod
    def create_members_report_pdf(report_data: Dict) -> BytesIO:
        """Создание PDF отчета по игрокам"""
        buffer = BytesIO()
        
        try:
            # Получаем корректное имя шрифта
            font_name = get_pdf_font_name()
            logger.info(f"📝 Использую шрифт: {font_name} для отчета по игрокам")
            
            # Проверяем доступные жирные шрифты
            bold_font_name = f'{font_name}-Bold'
            available_fonts = get_available_fonts()
            if bold_font_name not in available_fonts:
                logger.warning(f"⚠️ Жирный шрифт {bold_font_name} не найден, использую {font_name}")
                bold_font_name = font_name
            
            logger.info(f"📝 Использую жирный шрифт: {bold_font_name}")
            
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            styles = getSampleStyleSheet()
            
            # Стили
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontName=font_name,
                fontSize=16,
                spaceAfter=20,
                textColor=colors.HexColor('#2E86C1')
            )
            
            heading_style = ParagraphStyle(
                'Heading2',
                parent=styles['Heading2'],
                fontName=font_name,
                fontSize=14,
                spaceAfter=10,
                textColor=colors.HexColor('#34495E')
            )
            
            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=9,
                spaceAfter=3
            )
            
            bold_style = ParagraphStyle(
                'Bold',
                parent=styles['Normal'],
                fontName=bold_font_name,
                fontSize=10,
                spaceAfter=5,
                encoding='utf-8'
            )

            # Заголовок
            story.append(Paragraph(f"👥 ОТЧЕТ ПО ИГРОКАМ", title_style))
            team_analysis = report_data.get('team_analysis', {})
            story.append(Paragraph(f"Команда: {team_analysis.get('team_assessment', 'Общая оценка')}", heading_style))
            story.append(Paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}", heading_style))
            story.append(Spacer(1, 20))
            
            # Общие рекомендации
            story.append(Paragraph("♦ ОБЩИЕ РЕКОМЕНДАЦИИ ДЛЯ КОМАНДЫ", heading_style))
            
            if 'training_recommendations' in team_analysis:
                story.append(Paragraph("<b>Тренировочный процесс:</b>", normal_style))
                for rec in team_analysis['training_recommendations'][:3]:
                    story.append(Paragraph(f"• {rec}", normal_style))
            
            if 'motivation_strategies' in team_analysis:
                story.append(Spacer(1, 5))
                story.append(Paragraph("<b>Мотивационные стратегии:</b>", normal_style))
                for strat in team_analysis['motivation_strategies'][:3]:
                    story.append(Paragraph(f"• {strat}", normal_style))
            
            story.append(Spacer(1, 10))
            story.append(Paragraph(f"<b>Заметки для тренера:</b> {team_analysis.get('coach_notes', '')}", normal_style))
            
            story.append(Spacer(1, 20))
            
            # Отчет по каждому игроку
            member_reports = report_data.get('member_reports', [])
            if member_reports:
                story.append(Paragraph("👤 ДЕТАЛЬНЫЙ АНАЛИЗ ИГРОКОВ", heading_style))
                
                for idx, member_report in enumerate(member_reports, 1):
                    user_data = member_report.get('user_data', {})
                    analysis = member_report.get('ai_analysis', {})
                    
                    # Заголовок игрока
                    story.append(Paragraph(
                        f"<b>{idx}. {user_data.get('name', 'Неизвестно')} | Уровень: {user_data.get('level', 1)} | Очки: {user_data.get('points', 0)}</b>",
                        heading_style
                    ))
                    
                    # Статистика в таблице
                    stats_data = [
                        [Paragraph('Метрика', bold_style), Paragraph('Значение', bold_style)],
                        [Paragraph('Всего челленджей', normal_style), 
                        Paragraph(str(user_data.get('total_challenges', 0)), normal_style)],
                        [Paragraph('Выполнено', normal_style), 
                        Paragraph(str(user_data.get('completed_challenges', 0)), normal_style)],
                        [Paragraph('Процент выполнения', normal_style), 
                        Paragraph(f"{user_data.get('completion_rate', 0):.1f}%", normal_style)],
                        [Paragraph('Последние опросы', normal_style), 
                        Paragraph(str(user_data.get('recent_surveys', 0)), normal_style)],
                        [Paragraph('Средняя энергия', normal_style), 
                        Paragraph(f"{user_data.get('avg_energy', 0):.1f}/10", normal_style)]
                    ]
                    
                    stats_table = Table(stats_data, colWidths=[2*inch, 1.5*inch])
                    stats_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7D3C98')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (-1, 0), bold_font_name),  # ВАЖНО: используем bold_font_name
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F4ECF7')),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey)
                    ]))
                    
                    story.append(stats_table)
                    story.append(Spacer(1, 5))
                    
                    # AI анализ
                    story.append(Paragraph(f"<b>Характеристика:</b> {analysis.get('player_summary', '')}", normal_style))
                    
                    if 'strengths' in analysis:
                        story.append(Paragraph("<b>Сильные стороны:</b>", normal_style))
                        for strength in analysis['strengths'][:3]:
                            story.append(Paragraph(f"✓ {strength}", normal_style))
                    
                    if 'improvement_areas' in analysis:
                        story.append(Paragraph("<b>Области для улучшения:</b>", normal_style))
                        for area in analysis['improvement_areas'][:3]:
                            story.append(Paragraph(f"→ {area}", normal_style))
                    
                    if 'personal_recommendations' in analysis:
                        story.append(Paragraph("<b>Персональные рекомендации:</b>", normal_style))
                        for rec in analysis['personal_recommendations'][:3]:
                            story.append(Paragraph(f"♦ {rec}", normal_style))

                    if 'metrics_based_recommendations' in analysis:
                        story.append(Paragraph("<b>Рекомендации по метрикам:</b>", normal_style))
                        for rec in analysis['metrics_based_recommendations'][:2]:
                            story.append(Paragraph(f"📊 {rec}", normal_style))

                    story.append(Paragraph(f"<b>Мотивация:</b> {analysis.get('motivational_note', '')}", normal_style))
                    
                    story.append(Spacer(1, 15))
            
            # Футер
            story.append(Spacer(1, 20))
            story.append(Paragraph(f"Всего проанализировано игроков: {report_data.get('total_members', 0)}", normal_style))
            story.append(Paragraph(f"Сгенерировано: {report_data.get('generated_at', datetime.now().isoformat())}", normal_style))
            story.append(Paragraph("ПроффПомощник | vadirss.ru", normal_style))
            
            doc.build(story)
            buffer.seek(0)
            
            logger.info("✅ Отчет по игрокам успешно создан")
            return buffer
            
        except Exception as e:
            logger.error(f"Ошибка создания PDF отчета по игрокам: {e}")
            import traceback
            traceback.print_exc()
            return ReportFormatter.create_text_report(report_data)
    
    @staticmethod
    def create_text_report(report_data: Dict) -> BytesIO:
        """Создание простого текстового отчета (fallback)"""
        try:
            text_content = "♦ ОТЧЕТ\n\n"
            
            if 'org_name' in report_data:
                text_content += f"Команда: {report_data['org_name']}\n"
            
            if 'date' in report_data:
                text_content += f"Дата: {report_data['date']}\n"
            
            text_content += f"\nСгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            
            buffer = BytesIO()
            buffer.write(text_content.encode('utf-8'))
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logger.error(f"Ошибка создания текстового отчета: {e}")
            # Минимальный fallback
            buffer = BytesIO()
            buffer.write("Отчет временно недоступен".encode('utf-8'))
            buffer.seek(0)
            return buffer
    
    @staticmethod
    def create_csv_report(report_data: Dict, report_type: str = "daily") -> BytesIO:
        """Создание CSV отчета"""
        buffer = StringIO()
        writer = csv.writer(buffer)
        
        try:
            if report_type == "daily":
                # Заголовок
                writer.writerow(["Ежедневный отчет", report_data.get('org_name', ''), report_data.get('date', '')])
                writer.writerow([])
                
                # Статистика
                stats = report_data.get('daily_stats', {})
                writer.writerow(["Статистика за день"])
                writer.writerow(["Метрика", "Значение"])
                writer.writerow(["Всего участников", stats.get('total_members', 0)])
                writer.writerow(["Активных сегодня", stats.get('active_today', 0)])
                writer.writerow(["Выполнено челленджей", stats.get('completed_challenges_today', 0)])
                writer.writerow(["Пройдено опросов", stats.get('submitted_surveys_today', 0)])
                writer.writerow(["Заработано очков", stats.get('total_points_earned', 0)])
                
            elif report_type == "members":
                # Отчет по игрокам
                writer.writerow(["Отчет по игрокам", datetime.now().strftime('%d.%m.%Y')])
                writer.writerow([])
                writer.writerow(["Имя", "Уровень", "Очки", "Челленджи", "Выполнено", "Процент", "Опросы", "Энергия"])
                
                for member in report_data.get('member_reports', []):
                    user_data = member.get('user_data', {})
                    writer.writerow([
                        user_data.get('name', ''),
                        user_data.get('level', 0),
                        user_data.get('points', 0),
                        user_data.get('total_challenges', 0),
                        user_data.get('completed_challenges', 0),
                        f"{user_data.get('completion_rate', 0):.1f}%",
                        user_data.get('recent_surveys', 0),
                        f"{user_data.get('avg_energy', 0):.1f}"
                    ])
            
            # Конвертируем в BytesIO
            csv_bytes = BytesIO()
            csv_bytes.write(buffer.getvalue().encode('utf-8-sig'))  # utf-8-sig для Excel
            csv_bytes.seek(0)
            return csv_bytes
            
        except Exception as e:
            logger.error(f"Ошибка создания CSV: {e}")
            return BytesIO()
        
    @staticmethod
    def create_personal_report_pdf(report_data: Dict) -> BytesIO:
        """Создание PDF личного отчета"""
        buffer = BytesIO()

        try:
            # Получаем корректное имя шрифта
            font_name = get_pdf_font_name()
            logger.info(f"📝 Использую шрифт: {font_name} для личного отчета")

            # Проверяем доступные жирные шрифты
            bold_font_name = f'{font_name}-Bold'
            available_fonts = get_available_fonts()
            if bold_font_name not in available_fonts:
                logger.warning(f"⚠️ Жирный шрифт {bold_font_name} не найден, использую {font_name}")
                bold_font_name = font_name

            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            styles = getSampleStyleSheet()

            # Стили
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontName=font_name,
                fontSize=18,
                spaceAfter=20,
                textColor=colors.HexColor('#2E86C1')
            )

            heading_style = ParagraphStyle(
                'Heading2',
                parent=styles['Heading2'],
                fontName=font_name,
                fontSize=14,
                spaceAfter=10,
                textColor=colors.HexColor('#34495E')
            )

            normal_style = ParagraphStyle(
                'Normal',
                parent=styles['Normal'],
                fontName=font_name,
                fontSize=10,
                spaceAfter=5
            )

            bold_style = ParagraphStyle(
                'Bold',
                parent=styles['Normal'],
                fontName=bold_font_name,
                fontSize=10,
                spaceAfter=5
            )

            # Заголовок
            story.append(Paragraph("📊 ЛИЧНЫЙ МЕСЯЧНЫЙ ОТЧЕТ", title_style))
            story.append(Paragraph(f"Пользователь: {report_data.get('user_name', 'Неизвестно')}", heading_style))
            story.append(Paragraph(f"Период: {report_data.get('period', 'Месячный отчет')}", heading_style))
            story.append(Spacer(1, 20))

            # Статистика в таблице
            stats = report_data.get('stats', {})
            stats_table_data = [
                [Paragraph('Показатель', bold_style), Paragraph('Значение', bold_style)],
                [Paragraph('Выполнено челленджей', normal_style), Paragraph(str(stats.get('total_challenges', 0)), normal_style)],
                [Paragraph('Пройдено опросов', normal_style), Paragraph(str(stats.get('surveys_completed', 0)), normal_style)],
                [Paragraph('Заработано очков', normal_style), Paragraph(str(stats.get('total_points', 0)), normal_style)],
                [Paragraph('Процент выполнения', normal_style), Paragraph(f"{stats.get('completion_rate', 0):.1f}%", normal_style)],
                [Paragraph('Активных дней', normal_style), Paragraph(str(stats.get('active_days', 0)), normal_style)],
                [Paragraph('Средняя энергия', normal_style), Paragraph(f"{stats.get('avg_energy', 0):.1f}/10", normal_style)]
            ]

            stats_table = Table(stats_table_data, colWidths=[3*inch, 2*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498DB')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8F9FA')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))

            story.append(Paragraph("📈 СТАТИСТИКА ЗА МЕСЯЦ", heading_style))
            story.append(stats_table)
            story.append(Spacer(1, 20))

            # Прогресс
            progress = report_data.get('progress', {})
            if progress:
                story.append(Paragraph("🎯 ПРОГРЕСС", heading_style))
                progress_table_data = [
                    [Paragraph('Показатель', bold_style), Paragraph('Значение', bold_style)],
                    [Paragraph('Текущий уровень', normal_style), Paragraph(str(progress.get('level', 1)), normal_style)],
                    [Paragraph('Общие очки', normal_style), Paragraph(str(progress.get('current_points', 0)), normal_style)],
                    [Paragraph('Челленджи за месяц', normal_style), Paragraph(str(progress.get('challenges_this_month', 0)), normal_style)],
                    [Paragraph('Опросы за месяц', normal_style), Paragraph(str(progress.get('surveys_this_month', 0)), normal_style)],
                    [Paragraph('Тренд энергии', normal_style), Paragraph(progress.get('avg_energy_trend', 'Не определен'), normal_style)]
                ]

                progress_table = Table(progress_table_data, colWidths=[3*inch, 2*inch])
                progress_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#27AE60')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), bold_font_name),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#EAFAF1')),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))

                story.append(progress_table)
                story.append(Spacer(1, 20))

            # AI анализ и рекомендации
            ai_analysis = report_data.get('ai_analysis', {})
            if ai_analysis:
                story.append(Paragraph("🤖 АНАЛИЗ И РЕКОМЕНДАЦИИ", heading_style))
                story.append(Paragraph(f"<b>Резюме:</b> {ai_analysis.get('executive_summary', 'Нет данных')}", normal_style))
                story.append(Paragraph(f"<b>Настроение:</b> {ai_analysis.get('team_mood', 'Не определено')}", normal_style))
                story.append(Spacer(1, 10))

                # Ключевые достижения
                if 'key_achievements' in ai_analysis:
                    story.append(Paragraph("<b>🏆 Ключевые достижения:</b>", normal_style))
                    for achievement in ai_analysis['key_achievements']:
                        story.append(Paragraph(f"• {achievement}", normal_style))

                story.append(Spacer(1, 10))

                # Персональные рекомендации
                if 'personal_recommendations' in ai_analysis:
                    story.append(Paragraph("<b>💡 Рекомендации для вас:</b>", normal_style))
                    for rec in ai_analysis['personal_recommendations']:
                        story.append(Paragraph(f"• {rec}", normal_style))

                story.append(Spacer(1, 10))
                story.append(Paragraph(f"<b>💫 Мотивация:</b> {ai_analysis.get('motivational_message', '')}", normal_style))

            # Футер
            story.append(Spacer(1, 30))
            story.append(Paragraph(f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}", normal_style))
            story.append(Paragraph("ПроффПомощник | vadirss.ru", normal_style))

            doc.build(story)
            buffer.seek(0)

            logger.info("✅ Личный отчет успешно создан")
            return buffer

        except Exception as e:
            logger.error(f"Ошибка создания личного отчета PDF: {e}")
            import traceback
            traceback.print_exc()
            return ReportFormatter.create_fallback_pdf("Личный отчет", report_data)
    
    @staticmethod
    def create_trainer_report_pdf(report_data: Dict) -> BytesIO:
        """Создание PDF отчета тренера"""
        try:
            # Используем существующий метод create_members_report_pdf с модификациями
            modified_report = {
                "team_analysis": report_data.get("team_analysis", {}),
                "member_reports": report_data.get("member_reports", []),
                "total_members": report_data.get("total_members", 0)
            }

            return ReportFormatter.create_members_report_pdf(modified_report)

        except Exception as e:
            logger.error(f"Ошибка создания отчета тренера PDF: {e}")
            return ReportFormatter.create_fallback_pdf("Отчет тренера", report_data)
    
    @staticmethod
    def create_fallback_pdf(title: str, data: Dict) -> BytesIO:
        """Создать простой PDF как fallback"""
        buffer = BytesIO()
        
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            styles = getSampleStyleSheet()
            
            story.append(Paragraph(f"Отчет: {title}", styles['Heading1']))
            story.append(Spacer(1, 20))
            
            # Добавляем базовую информацию
            if "stats" in data:
                story.append(Paragraph("Статистика:", styles['Heading2']))
                for key, value in data["stats"].items():
                    story.append(Paragraph(f"{key}: {value}", styles['Normal']))
            
            doc.build(story)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            logger.error(f"Ошибка fallback PDF: {e}")
            # Минимальный fallback
            buffer.write("PDF отчет временно недоступен")
            buffer.seek(0)
            return buffer