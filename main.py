import logging

from bot import main as bot_main
from database import init_db

def setup_logging():
    """Настраивает конфигурацию логирования"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

def main():
    """Инициализирует и запускает бота"""
    # Инициализация базы данных
    init_db()
    logging.info("База данных инициализирована.")

    # Запуск бота
    bot_main()

if __name__ == '__main__':
    setup_logging()
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен пользователем.") 