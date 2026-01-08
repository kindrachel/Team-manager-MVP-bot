import os
import sys
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

def setup_fonts():
    """Настройка шрифтов для ReportLab"""
    try:
        # Список возможных путей к шрифтам Arial
        font_paths = [
            # Windows
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\ariali.ttf",
            r"C:\Windows\Fonts\arialbi.ttf",
            
            # Linux
            "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            
            # MacOS
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
            
            # Текущая директория
            "fonts/arial.ttf",
        ]
        
        found_fonts = []
        
        # Ищем Arial Regular
        for path in font_paths:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('Arial', path))
                    found_fonts.append(('Arial', path))
                    print(f"✅ Шрифт Arial загружен: {path}")
                    break
                except Exception as e:
                    continue
        
        # Ищем Arial Bold
        for path in font_paths:
            if 'bd' in path.lower() or 'bold' in path.lower():
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('Arial-Bold', path))
                        found_fonts.append(('Arial-Bold', path))
                        print(f"✅ Шрифт Arial-Bold загружен: {path}")
                        break
                    except:
                        continue
        
        if found_fonts:
            # Настраиваем маппинг
            for font_name, _ in found_fonts:
                if 'Bold' in font_name:
                    addMapping('Arial', 1, 0, font_name)  # bold
                else:
                    addMapping('Arial', 0, 0, font_name)  # normal
            
            print("✅ Шрифты настроены успешно")
            return True
        
        print("⚠️ Шрифты Arial не найдены")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка настройки шрифтов: {e}")
        return False

# Запускаем настройку
if __name__ == "__main__":
    setup_fonts()