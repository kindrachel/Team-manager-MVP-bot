import re

def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Валидация телефонного номера с поддержкой разных форматов
    
    Возвращает: (is_valid, error_message)
    """
    phone_clean = re.sub(r'[^\d\+]', '', phone)
    
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) < 10:
        return False, "❌ Номер слишком короткий (минимум 10 цифр)"
    if len(digits_only) > 15:
        return False, "❌ Номер слишком длинный (максимум 15 цифр)"
    
    russian_patterns = [
        r'^\+7\d{10}$',             
        r'^\+7\s?\(?\d{3}\)?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$',
        r'^8\d{10}$',                     
        r'^8\s?\(?\d{3}\)?\s?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}$',    
    ]
    
    company_patterns = [
        r'^\+?\d{1,3}\s?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}$',  
        r'^\+?\d{1,3}[\s\-]?\d{2,}[\s\-]?\d{2,}[\s\-]?\d{2,}$',  
    ]
    
    all_patterns = russian_patterns + company_patterns
    
    for pattern in all_patterns:
        if re.match(pattern, phone.strip()):
            if any(re.match(p, phone.strip()) for p in russian_patterns):
                normalized = re.sub(r'\D', '', phone_clean)
                if normalized.startswith('8'):
                    normalized = '+7' + normalized[1:]
                elif normalized.startswith('7'):
                    normalized = '+' + normalized
                elif not normalized.startswith('+7'):
                    normalized = '+7' + normalized
                    
                if len(normalized) != 12:  
                    return False, "❌ Российский номер должен содержать 10 цифр после +7"
                    
                return True, normalized
            
            return True, phone_clean
    
    return False, (
        "❌ Неверный формат номера.\n\n"
        "✅ Примеры правильных форматов:\n"
        "• +79123456789\n"
        "• +7 (912) 345-67-89\n"
        "• 8 (912) 345-67-89\n"
        "• +1 (234) 567-8900 (для компаний)\n\n"
        "Введите номер еще раз:"
    )