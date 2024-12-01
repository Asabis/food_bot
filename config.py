# config.py

import os
import platform

# Токен вашего Telegram-бота, полученный от @BotFather
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в переменных окружения.")

# Определение пути к шрифту в зависимости от операционной системы
system = platform.system()
if system == 'Windows':
    FONT_PATH = "C:\\Windows\\Fonts\\Arial.ttf"
elif system == 'Darwin':  # macOS
    FONT_PATH = "/Library/Fonts/Arial.ttf"
else:
    FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
