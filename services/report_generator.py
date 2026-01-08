import pandas as pd
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import datetime 
import logging

logger = logging.getLogger(__name__)

class ReportGenerator:
    @staticmethod
    async def create_personal_report(user, ai_analysis):
        """Создание PDF отчета с AI-анализом"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # Заголовок
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2E86C1')
        )
        
        story.append(Paragraph(f"Отчет по развитию: {user.name}", title_style))
        story.append(Spacer(1, 20))
        
        # AI-анализ
        story.append(Paragraph("🤖 AI-анализ вашего прогресса:", styles['Heading2']))
        story.append(Paragraph(ai_analysis.get('progress_summary', ''), styles['BodyText']))
        
        # Сильные стороны
        story.append(Paragraph("🌟 Сильные стороны:", styles['Heading3']))
        for strength in ai_analysis.get('strengths', []):
            story.append(Paragraph(f"• {strength}", styles['BodyText']))
        
        # График прогресса
        chart_image = await ReportGenerator._create_progress_chart(user)
        story.append(chart_image)
        
        doc.build(story)
        buffer.seek(0)
        
        # Сохранение файла
        filename = f"reports/personal_{user.user_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        with open(filename, 'wb') as f:
            f.write(buffer.read())
        
        return filename
    
    @staticmethod
    async def _create_progress_chart(user):
        """Создание графика прогресса"""
        # Собираем данные для графика
        surveys = user.surveys[-10:]  # Последние 10 опросов
        
        if len(surveys) > 1:
            dates = [s.created_at for s in surveys]
            energies = [s.energy for s in surveys]
            
            plt.figure(figsize=(10, 4))
            plt.plot(dates, energies, marker='o', linewidth=2, color='#2E86C1')
            plt.fill_between(dates, energies, alpha=0.3, color='#2E86C1')
            plt.title('Динамика энергии и вовлеченности', fontsize=14)
            plt.grid(True, alpha=0.3)
            
            # Сохраняем в буфер
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            plt.close()
            buf.seek(0)
            
            return Image(buf, width=6*inch, height=2.5*inch)
        
        return Spacer(1, 20)