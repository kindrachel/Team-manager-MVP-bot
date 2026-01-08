import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.rl_config import defaultPageSize

def register_fonts():
    """Регистрация шрифтов для ReportLab"""
    try:
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",  
            "C:/Windows/Fonts/ariali.ttf",   
            "C:/Windows/Fonts/arialbi.ttf", 
        ]
        
        registered_fonts = []
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_name = os.path.basename(font_path).split('.')[0]
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    registered_fonts.append(font_name)
                    print(f"✅ Шрифт зарегистрирован: {font_name}")
                except Exception as e:
                    print(f"⚠️ Не удалось зарегистрировать {font_path}: {e}")
        
        if registered_fonts:
            from reportlab.lib.fonts import addMapping
            if 'arial' in registered_fonts:
                addMapping('Arial', 0, 0, 'arial')  
            if 'arialbd' in registered_fonts:
                addMapping('Arial', 1, 0, 'arialbd')  
            if 'ariali' in registered_fonts:
                addMapping('Arial', 0, 1, 'ariali')  
            if 'arialbi' in registered_fonts:
                addMapping('Arial', 1, 1, 'arialbi') 
            
            return True
        
        print("⚠️ Шрифты Arial не найдены, использую стандартные")
        return False
        
    except Exception as e:
        print(f"❌ Ошибка регистрации шрифтов: {e}")
        return False

fonts_initialized = register_fonts()