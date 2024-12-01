import logging
import os
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, HRFlowable
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

from database import add_entry, get_entries, get_entries_for_period
from config import TELEGRAM_BOT_TOKEN, FONT_PATH
from constants import ConversationState, NUTRIENT_LIMITS, MESSAGES, NUTRIENT_EMOJI, MEAL_TIMES
from nutrition_analyzer import NutritionAnalyzer, NutritionRecommendations

import pytz

# Определяем московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger('bot')

# Состояния для ConversationHandler
SET_PROTEIN, SET_VEGETABLES, SET_FATS, SET_FRUITS, SET_DAIRY, SET_GRAINS = range(6)

def register_cyrillic_font():
    """
    Регистрирует шрифт, поддерживающий кириллицу.
    Возвращает True при успешной регистрации, иначе False.
    """
    if not os.path.exists(FONT_PATH):
        logger.error(f"Шрифт не найден по пути: {FONT_PATH}")
        return False

    try:
        # Регистрация обычного шрифта
        pdfmetrics.registerFont(TTFont('CustomCyrillicFont', FONT_PATH))

        # Попытка регистрации жирного шрифта
        bold_font_path = FONT_PATH.replace('.ttf', '-Bold.ttf')  # Пример, измените при необходимости
        if os.path.exists(bold_font_path):
            pdfmetrics.registerFont(TTFont('CustomCyrillicFont-Bold', bold_font_path))
            logger.info("Жирный шрифт успешно зарегистрирован.")
        else:
            # Если жирный шрифт не найден, используем обычный
            pdfmetrics.registerFont(TTFont('CustomCyrillicFont-Bold', FONT_PATH))
            logger.warning("Жирный шрифт не найден. Используется обычный шрифт для жирного текста.")

        logger.info("Шрифт успешно зарегистрирован.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при регистрации шрифта: {e}")
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start. Отправляет приветственное сообщение и отображает клавиатуру с основными командами.
    """
    logger.debug("Вызван обработчик /start")
    user = update.effective_user
    # Создаем клавиатуру с кнопками
    keyboard = [
        [KeyboardButton('/add'), KeyboardButton('/view')],
        [KeyboardButton('/stats'), KeyboardButton('/set_norms')],
        [KeyboardButton('/reminders'), KeyboardButton('/cancel')]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(MESSAGES['welcome'], reply_markup=reply_markup)
    logger.info(f"Пользователь {user.id} начал взаимодействие с ботом.")

async def add_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Начинает процесс добавления новой записи о приёме пищи.
    Предлагает выбрать приём пищи из доступных вариантов.
    """
    # Разбиваем MEAL_TIMES на строки по 2 элемента
    reply_keyboard = [MEAL_TIMES[i:i + 2] for i in range(0, len(MEAL_TIMES), 2)]
    await update.message.reply_text(
        MESSAGES['choose_meal'],
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        )
    )
    logger.info(f"Пользователь {update.effective_user.id} начал добавление записи.")
    return ConversationState.CHOOSE_MEAL.value

async def choose_meal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает выбор приёма пищи пользователем.
    """
    meal_time = update.message.text
    if meal_time not in MEAL_TIMES:
        await update.message.reply_text(MESSAGES['invalid_meal'])
        logger.warning(f"Пользователь {update.effective_user.id} выбрал некорректный приём пищи: {meal_time}")
        return ConversationState.CHOOSE_MEAL.value

    context.user_data['meal_time'] = meal_time
    context.user_data['current_state'] = ConversationState.UPLOAD_PHOTO.value
    await update.message.reply_text(
        MESSAGES['send_photo'],
        reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"Пользователь {update.effective_user.id} выбрал приём пищи: {meal_time}")
    return ConversationState.UPLOAD_PHOTO.value

async def upload_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает загрузку фотографий пользователем. Пользователь может отправить несколько фотографий.
    """
    # Обработка команды /done
    if update.message.text and update.message.text.lower() == '/done':
        context.user_data['current_state'] = ConversationState.ENTER_PROTEIN.value
        await update.message.reply_text("Введите количество Белков (в порциях):")
        return ConversationState.ENTER_PROTEIN.value

    # Обработка фотографии
    elif update.message.photo:
        photo = update.message.photo[-1]
        try:
            file = await photo.get_file()
            file_bytes = BytesIO()
            await file.download_to_memory(out=file_bytes)
            file_bytes.seek(0)
        except Exception as e:
            logger.error(f"Ошибка при получении файла фотографии: {e}")
            await update.message.reply_text("Произошла ошибка при получении фотографии. Попробуйте снова.")
            return ConversationState.UPLOAD_PHOTO.value

        # Сохранение изображения локально
        user_id = update.effective_user.id
        timestamp = datetime.now(MOSCOW_TZ).strftime("%Y%m%d%H%M%S")
        image_path = f"images/{user_id}_{timestamp}.jpg"
        try:
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            with open(image_path, 'wb') as f:
                f.write(file_bytes.read())
            context.user_data.setdefault('image_paths', []).append(image_path)
            logger.info(f"Фотография сохранена по пути: {image_path}")
            await update.message.reply_text(
                "📷 Фотография сохранена. Вы можете отправить ещё фотографию или введите /done, чтобы продолжить."
            )
        except Exception as e:
            logger.error(f"Ошибка при сохранении фотографии: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении фотографии.")
            return ConversationState.UPLOAD_PHOTO.value

        return ConversationState.UPLOAD_PHOTO.value

    else:
        await update.message.reply_text("Пожалуйста, отправьте фотографию или введите /done, чтобы продолжить.")
        return ConversationState.UPLOAD_PHOTO.value

class NutrientInputHandler:
    """
    Класс для обработки ввода количества порций пищевых групп.
    """
    def __init__(self):
        self.nutrients = {
            ConversationState.ENTER_PROTEIN: ('protein', "Белков"),
            ConversationState.ENTER_VEGETABLES: ('vegetables', "Овощей"),
            ConversationState.ENTER_FATS: ('fats', "Жиров"),
            ConversationState.ENTER_FRUITS: ('fruits', "Фруктов"),
            ConversationState.ENTER_DAIRY: ('dairy', "Молочных продуктов"),
            ConversationState.ENTER_GRAINS: ('grains', "Злаков")
        }

    def validate_nutrient(self, value: str, nutrient_type: str) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Проверяет корректность введенного значения для пищевой группы.
        """
        try:
            value = int(value)
            min_val, max_val = NUTRIENT_LIMITS[nutrient_type]
            
            if not (min_val <= value <= max_val):
                return False, None, f"Значение должно быть между {min_val} и {max_val} порций"
                
            return True, value, None
        except ValueError:
            return False, None, "Пожалуйста, введите целое число"

    async def handle_input(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
    ) -> int:
        """
        Обрабатывает ввод пользователя для текущего состояния и переходит к следующему.
        """
        current_state = ConversationState(context.user_data['current_state'])
        nutrient_key, nutrient_name = self.nutrients[current_state]
        
        is_valid, value, error_message = self.validate_nutrient(
            update.message.text, 
            nutrient_key
        )
        
        if not is_valid:
            await update.message.reply_text(f"{error_message} для {nutrient_name} (порций):")
            return current_state.value
            
        context.user_data[nutrient_key] = value
        logger.info(f"Пользователь {update.effective_user.id} ввёл {nutrient_name}: {value} порций")
        
        # Определяем следующее состояние
        states = list(self.nutrients.keys())
        current_idx = states.index(current_state)
        
        if current_idx == len(states) - 1:
            # Если это последний nutrient, сохраняем запись
            await self._save_entry(update, context)
            return ConversationHandler.END
            
        # Иначе переходим к следующему nutrient
        next_state = states[current_idx + 1]
        context.user_data['current_state'] = next_state.value
        _, next_nutrient_name = self.nutrients[next_state]
        await update.message.reply_text(
            MESSAGES['enter_amount'].format(nutrient_name=next_nutrient_name)
        )
        return next_state.value

    async def _save_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Сохраняет запись в базу данных после ввода всех данных.
        """
        user_id = update.effective_user.id
        date = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d")
        timestamp = datetime.now(MOSCOW_TZ).strftime("%Y-%m-%d %H:%M:%S")

        image_paths = context.user_data.get('image_paths', [])
        
        add_entry(
            user_id=user_id,
            date=date,
            meal_time=context.user_data['meal_time'],
            protein=context.user_data.get('protein', 0),
            vegetables=context.user_data.get('vegetables', 0),
            fats=context.user_data.get('fats', 0),
            fruits=context.user_data.get('fruits', 0),
            dairy=context.user_data.get('dairy', 0),
            grains=context.user_data.get('grains', 0),
            image_paths=image_paths,
            timestamp=timestamp
        )

        await update.message.reply_text(
            MESSAGES['entry_added'].format(meal_time=context.user_data['meal_time'])
        )
        logger.info(f"Запись успешно сохранена для пользователя {user_id}.")

        # Очистка image_paths для следующего входа
        context.user_data.pop('image_paths', None)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет текущий процесс добавления записи.
    """
    await update.message.reply_text(
        "Добавление записи отменено.", reply_markup=ReplyKeyboardRemove()
    )
    logger.info(f"Пользователь {update.effective_user.id} отменил добавление записи.")
    return ConversationHandler.END

@dataclass
class DiaryEntry:
    """
    Класс для хранения данных одной записи дневника.
    """
    meal_time: str
    protein: int
    vegetables: int
    fats: int
    fruits: int
    dairy: int
    grains: int
    image_paths: List[str]
    timestamp: datetime

class PDFReportGenerator:
    """
    Класс для генерации PDF-отчёта на основе записей дневника.
    """
    def __init__(self, user_id: int, date: str, user_norms: Dict[str, int] = None):
        self.user_id = user_id
        self.date = date
        self.pdf_path = f"reports/{user_id}_{date}.pdf"
        # Регистрируем шрифт перед созданием стилей
        if not register_cyrillic_font():
            logger.error("Ошибка при регистрации шрифта.")
        self.styles = self._create_styles()
        self.nutrition_analyzer = NutritionAnalyzer(user_norms)

    def _create_styles(self) -> dict:
        """
        Создаёт и возвращает стили для PDF-документа.
        """
        styles = getSampleStyleSheet()
        
        # Обновляем заголовок отчёта
        styles.add(ParagraphStyle(
            name='CenterTitle',
            alignment=1,
            fontName='CustomCyrillicFont-Bold',
            fontSize=26,
            spaceAfter=20,
            textColor=colors.HexColor('#1F618D'),  # Более насыщенный синий
        ))
        
        # Нормы потребления
        styles.add(ParagraphStyle(
            name='Norms',
            alignment=0,  # Выравнивание по левому краю
            fontName='CustomCyrillicFont-Bold',
            fontSize=14,
            spaceAfter=10,
            textColor=colors.HexColor('#2C3E50'),  # Тёмно-синий
            wordWrap='CJK'  # Добавлено свойство переноса
        ))
        
        # Подзаголовки
        styles.add(ParagraphStyle(
            name='SubTitle',
            fontName='CustomCyrillicFont-Bold',
            fontSize=16,
            spaceAfter=10,
            textColor=colors.HexColor('#34495E'),  # Серовато-синий
            wordWrap='CJK'  # Добавлено свойство переноса
        ))
        
        # Стиль для текста в ячейках таблицы
        styles.add(ParagraphStyle(
            name='TableCell',
            fontName='CustomCyrillicFont',
            fontSize=10,
            alignment=0,  # Выравнивание по левому краю
            leading=12,
            wordWrap='CJK',
            splitLongWords=True,
            hyphenationLang='ru'  # Язык для переноса слов
        ))
        
        # Стиль для заголовков таблицы
        styles.add(ParagraphStyle(
            name='TableHeader',
            fontName='CustomCyrillicFont-Bold',
            fontSize=11,
            alignment=1,  # Центрирование
            textColor=colors.white,
            wordWrap='CJK'  # Добавлено свойство переноса
        ))
        
        # Стиль для подписей к фото
        styles.add(ParagraphStyle(
            name='PhotoCaption',
            fontName='CustomCyrillicFont',
            fontSize=12,
            alignment=1,  # Центрирование
            spaceAfter=5,
            textColor=colors.HexColor('#2980B9'),  # Синий
            wordWrap='CJK'  # Добавлено свойство переноса
        ))
        
        # Стиль для рекомендаций
        styles.add(ParagraphStyle(
            name='Recommendation',
            fontName='CustomCyrillicFont',
            fontSize=12,
            spaceAfter=10,
            leftIndent=20,
            bulletIndent=10,
            textColor=colors.HexColor('#7F8C8D'),  # Серый
            wordWrap='CJK'  # Добавлено свойство переноса
        ))
        
        return styles

    def _create_table_style(self) -> TableStyle:
        """
        Создаёт и возвращает стиль для таблицы в отчёте.
        """
        return TableStyle([
            # Общие настройки
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#BDC3C7')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495E')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            # Выравнивание и шрифты
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'CustomCyrillicFont'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            # Отступы
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            # Цвет фона для чётных строк
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ECF0F1')),
            ('BACKGROUND', (0, 2), (-1, -1), colors.white),
        ])

    def _create_table_data(self, entries: List[DiaryEntry]) -> Tuple[List[List[str]], dict]:
        """
        Создаёт данные для таблицы и считает итоги потребления.
        """
        # Заголовки столбцов
        data = [[
            Paragraph('Приём пищи', self.styles['TableHeader']),
            Paragraph('Белки', self.styles['TableHeader']),
            Paragraph('Овощи', self.styles['TableHeader']),
            Paragraph('Жиры', self.styles['TableHeader']),
            Paragraph('Фрукты', self.styles['TableHeader']),
            Paragraph('Молочка', self.styles['TableHeader']),
            Paragraph('Злаки', self.styles['TableHeader']),
            Paragraph('Время', self.styles['TableHeader']),
        ]]
        
        totals = {
            'protein': 0, 'vegetables': 0, 'fats': 0,
            'fruits': 0, 'dairy': 0, 'grains': 0
        }
        
        for entry in entries:
            # Конвертируем время в московский часовой пояс
            time_str = entry.timestamp.astimezone(MOSCOW_TZ).strftime("%H:%M")
            data.append([
                Paragraph(entry.meal_time, self.styles['TableCell']),
                Paragraph(str(entry.protein), self.styles['TableCell']),
                Paragraph(str(entry.vegetables), self.styles['TableCell']),
                Paragraph(str(entry.fats), self.styles['TableCell']),
                Paragraph(str(entry.fruits), self.styles['TableCell']),
                Paragraph(str(entry.dairy), self.styles['TableCell']),
                Paragraph(str(entry.grains), self.styles['TableCell']),
                Paragraph(time_str, self.styles['TableCell']),
            ])
            
            # Суммируем значения
            totals['protein'] += entry.protein
            totals['vegetables'] += entry.vegetables
            totals['fats'] += entry.fats
            totals['fruits'] += entry.fruits
            totals['dairy'] += entry.dairy
            totals['grains'] += entry.grains
            
        # Добавляем строку с итогами
        data.append([
            Paragraph('Сумма', self.styles['TableHeader']),
            Paragraph(str(totals['protein']), self.styles['TableHeader']),
            Paragraph(str(totals['vegetables']), self.styles['TableHeader']),
            Paragraph(str(totals['fats']), self.styles['TableHeader']),
            Paragraph(str(totals['fruits']), self.styles['TableHeader']),
            Paragraph(str(totals['dairy']), self.styles['TableHeader']),
            Paragraph(str(totals['grains']), self.styles['TableHeader']),
            ''
        ])
        
        return data, totals

    def _create_recommendations(self, totals: dict, user_norms: Dict[str, int]) -> List[Paragraph]:
        """
        Создаёт список рекомендаций на основе анализа потребления.
        """
        recommendations = self.nutrition_analyzer.analyze_daily_intake(totals)
        elements = []
        elements.append(Paragraph("Рекомендации:", self.styles['SubTitle']))
        elements.append(Spacer(1, 10))
        
        for rec in recommendations:
            elements.append(Paragraph(f"• {rec}", self.styles['Recommendation']))
            elements.append(Spacer(1, 5))
            
        return elements

    def _add_image(self, meal_time: str, image_path: str, timestamp: datetime) -> List:
        """
        Добавляет изображение в отчёт с подписью к нему.
        """
        elements = []
        try:
            img = Image.open(image_path)
            img_width, img_height = img.size
            aspect = img_height / float(img_width)
            img_width = 400  # Ширина изображения
            img_height = img_width * aspect

            img.thumbnail((img_width, img_height))
            img_io = BytesIO()
            img.save(img_io, format='PNG')
            img_io.seek(0)

            # Форматирование времени
            time_str = timestamp.astimezone(MOSCOW_TZ).strftime("%H:%M")

            # Добавляем подпись к фото с временем
            caption_text = f"📷 {meal_time} в {time_str}"
            elements.append(Paragraph(caption_text, self.styles['PhotoCaption']))
            elements.append(Spacer(1, 5))

            # Добавляем изображение
            from reportlab.platypus import Image as PlatypusImage
            platypus_image = PlatypusImage(img_io, width=img_width, height=img_height)
            elements.append(platypus_image)
            elements.append(PageBreak())

        except Exception as e:
            logger.error(f"Ошибка при добавлении изображения: {e}")

        return elements

    async def generate(self, entries: List[DiaryEntry]) -> Optional[str]:
        """
        Генерирует PDF-отчёт и возвращает путь к файлу.
        """
        try:
            os.makedirs(os.path.dirname(self.pdf_path), exist_ok=True)
            
            # Создаем шаблон документа с номерами страниц
            doc = BaseDocTemplate(
                self.pdf_path,
                pagesize=A4,
                rightMargin=20,
                leftMargin=20,
                topMargin=20,
                bottomMargin=20
            )

            frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
            template = PageTemplate(id='test', frames=frame, onPage=self._add_page_number)
            doc.addPageTemplates([template])

            elements = []

            # Заголовок отчёта
            title = Paragraph(f"Пищевой дневник за {self.date}", self.styles['CenterTitle'])
            elements.append(title)
            
            # Отображение норм или вопросительных знаков
            if self.nutrition_analyzer.recommendations:
                norms_text = "Ваши ежедневные нормы потребления:\n"
                norms_text += f"• Белки: {self.nutrition_analyzer.recommendations.protein_daily} порций\n"
                norms_text += f"• Овощи: {self.nutrition_analyzer.recommendations.vegetables_daily} порций\n"
                norms_text += f"• Жиры: {self.nutrition_analyzer.recommendations.fats_daily} порций\n"
                norms_text += f"• Фрукты: {self.nutrition_analyzer.recommendations.fruits_daily} порций\n"
                norms_text += f"• Молочные продукты: {self.nutrition_analyzer.recommendations.dairy_daily} порций\n"
                norms_text += f"• Злаки: {self.nutrition_analyzer.recommendations.grains_daily} порций\n"
            else:
                norms_text = "Ваши ежедневные нормы потребления:\n"
                norms_text += "• Белки: ? порций\n"
                norms_text += "• Овощи: ? порций\n"
                norms_text += "• Жиры: ? порций\n"
                norms_text += "• Фрукты: ? порций\n"
                norms_text += "• Молочные продукты: ? порций\n"
                norms_text += "• Злаки: ? порций\n"
            
            norms = Paragraph(norms_text, self.styles['Norms'])
            elements.append(norms)
            elements.append(Spacer(1, 10))

            # Создаём таблицу
            table_data, totals = self._create_table_data(entries)
            
            # Рассчитываем общую ширину страницы
            page_width = A4[0] - doc.leftMargin - doc.rightMargin

            # Определяем ширины столбцов пропорционально
            col_ratios = [1.5, 1, 1, 1, 1, 1.2, 1, 1.2]
            total_ratio = sum(col_ratios)
            col_widths = [(ratio / total_ratio) * page_width for ratio in col_ratios]

            # Устанавливаем минимальную ширину столбцов
            min_col_width = 100  # Минимальная ширина столбца
            col_widths = [max(width, min_col_width) for width in col_widths]
            
            table = Table(table_data, colWidths=col_widths)
            
            # Добавляем стиль к таблице
            table.setStyle(self._create_table_style())

            elements.append(table)
            elements.append(Spacer(1, 20))

            # Добавляем разделительную линию
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#BDC3C7')))
            elements.append(Spacer(1, 10))

            # Добавляем рекомендации
            recommendations_elements = self._create_recommendations(totals, self.nutrition_analyzer.recommendations.__dict__ if self.nutrition_analyzer.recommendations else None)
            elements.extend(recommendations_elements)

            # Добавляем фотографии (по одной на страницу)
            for entry in entries:
                if entry.image_paths:
                    for image_path in entry.image_paths:
                        if os.path.exists(image_path):
                            elements.extend(self._add_image(entry.meal_time, image_path, entry.timestamp))

            doc.build(elements)
            logger.info(f"PDF отчёт успешно создан: {self.pdf_path}")
            return self.pdf_path

        except Exception as e:
            logger.error(f"Ошибка при создании PDF: {e}")
            return None

    def _add_page_number(self, canvas, doc):
        """
        Добавляет номер страницы внизу каждой страницы.
        """
        page_num = canvas.getPageNumber()
        text = f"Страница {page_num}"
        canvas.setFont('CustomCyrillicFont', 9)
        canvas.drawCentredString(A4[0] / 2, 15 * mm, text)

def main():
    """Запускает бота и ин��циализирует обработчики."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Создание обработчиков команд
    application.add_handler(CommandHandler("start", start))

    # Создание экземпляра NutrientInputHandler
    nutrient_input_handler = NutrientInputHandler()

    # Определение состояний для ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_entry_start)],
        states={
            ConversationState.CHOOSE_MEAL.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_meal)
            ],
            ConversationState.UPLOAD_PHOTO.value: [
                MessageHandler(
                    filters.PHOTO | filters.Regex('^/done$') | (filters.TEXT & ~filters.COMMAND),
                    upload_photos
                )
            ],
            ConversationState.ENTER_PROTEIN.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
            ConversationState.ENTER_VEGETABLES.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
            ConversationState.ENTER_FATS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
            ConversationState.ENTER_FRUITS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
            ConversationState.ENTER_DAIRY.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
            ConversationState.ENTER_GRAINS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, nutrient_input_handler.handle_input)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()