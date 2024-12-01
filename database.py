import sqlite3
from typing import List
from datetime import datetime
import pytz
import logging

DB_NAME = 'food_diary.db'
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
logger = logging.getLogger(__name__)

def init_db():
    """
    Инициализирует базу данных, создавая необходимые таблицы, если они не существуют.
    """
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    meal_time TEXT NOT NULL,
                    protein INTEGER,
                    vegetables INTEGER,
                    fats INTEGER,
                    fruits INTEGER,
                    dairy INTEGER,
                    grains INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS meal_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meal_id INTEGER NOT NULL,
                    image_path TEXT,
                    FOREIGN KEY(meal_id) REFERENCES meals(id)
                )
            ''')
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")

def add_entry(user_id, date, meal_time, protein, vegetables, fats, fruits, dairy, grains, image_paths, timestamp):
    """
    Добавляет новую запись о приёме пищи в базу данных.

    Args:
        user_id (int): Идентификатор пользователя.
        date (str): Дата записи в формате YYYY-MM-DD.
        meal_time (str): Наименование приёма пищи.
        protein (int): Количество порций белков.
        vegetables (int): Количество порций овощей.
        fats (int): Количество порций жиров.
        fruits (int): Количество порций фруктов.
        dairy (int): Количество порций молочных продуктов.
        grains (int): Количество порций злаков.
        image_paths (list): Список путей к фотографиям блюд.
        timestamp (str): Время создания записи.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO meals (user_id, date, meal_time, protein, vegetables, fats, fruits, dairy, grains, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, date, meal_time, protein, vegetables, fats, fruits, dairy, grains, timestamp))
    meal_id = cursor.lastrowid
    for image_path in image_paths:
        cursor.execute('''
            INSERT INTO meal_photos (meal_id, image_path)
            VALUES (?, ?)
        ''', (meal_id, image_path))
    conn.commit()
    conn.close()

def get_entries(user_id, date):
    """
    Получает все записи о приёмах пищи пользователя за указанную дату.

    Args:
        user_id (int): Идентификатор пользователя.
        date (str): Дата в формате YYYY-MM-DD.

    Returns:
        list: Список записей с прикреплёнными фотографиями.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT meals.id, meal_time, protein, vegetables, fats, fruits, dairy, grains, timestamp
        FROM meals
        WHERE user_id = ? AND date = ?
        ORDER BY timestamp ASC
    ''', (user_id, date))
    meal_rows = cursor.fetchall()

    entries = []
    for meal_row in meal_rows:
        meal_id = meal_row[0]
        cursor.execute('''
            SELECT image_path
            FROM meal_photos
            WHERE meal_id = ?
        ''', (meal_id,))
        photos = [row[0] for row in cursor.fetchall()]
        timestamp = datetime.strptime(meal_row[-1], '%Y-%m-%d %H:%M:%S')
        timestamp = MOSCOW_TZ.localize(timestamp)
        entries.append(meal_row[1:-1] + (photos, timestamp))

    conn.close()
    return entries

def get_entries_for_period(user_id: int, start_date: str, end_date: str) -> List[tuple]:
    """
    Получает записи за указанный период.

    Args:
        user_id (int): Идентификатор пользователя.
        start_date (str): Начальная дата в формате YYYY-MM-DD.
        end_date (str): Конечная дата в формате YYYY-MM-DD.

    Returns:
        List[tuple]: Список записей за период.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, meal_time, protein, vegetables, fats, fruits, dairy, grains, timestamp
        FROM meals
        WHERE user_id = ? AND date BETWEEN ? AND ?
        ORDER BY date ASC, timestamp ASC
    ''', (user_id, start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return rows
