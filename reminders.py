from datetime import datetime, time
from telegram.ext import ContextTypes

class MealReminder:
    def __init__(self):
        self.default_times = {
            "Завтрак": time(8, 0),
            "Утренний перекус": time(11, 0),
            "Обед": time(14, 0),
            "Обеденный перекус": time(16, 0),
            "Полдник": time(17, 0),
            "Ужин": time(19, 0)
        }

    async def check_and_remind(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверяет время и отправляет напоминания"""
        now = datetime.now().time()
        
        for meal, meal_time in self.default_times.items():
            if now.hour == meal_time.hour and now.minute == meal_time.minute:
                await context.bot.send_message(
                    chat_id=context.job.chat_id,
                    text=f"Время для {meal}! Не забудьте записать прием пищи в дневник.",
                ) 