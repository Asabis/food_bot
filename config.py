# config.py

import os

# Токен вашего Telegram-бота, полученный от @BotFather
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Не задан TELEGRAM_BOT_TOKEN в переменных окружения.")

# Путь к шрифту, поддерживающему кириллицу
# Замените путь в соответствии с вашей ОС и установленными шрифтами

# Примеры путей для разных ОС:
# Windows
# FONT_PATH = "C:\\Windows\\Fonts\\arial.ttf"

# macOS
# FONT_PATH = "/Library/Fonts/Arial.ttf"

# Linux
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
