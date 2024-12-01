from datetime import datetime, time
from typing import Dict

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
                job = context.job
                
                # Создаем красивое сообщение с напоминанием
                message = (
                    f"⏰ *Время для приема пищи!*\n\n"
                    f"🍽️ *{meal}*\n\n"
                    f"Рекомендации:\n"
                    f"• Не торопитесь во время еды\n"
                    f"• Пейте достаточно воды\n"
                    f"• Старайтесь есть разнообразную пищу\n\n"
                    f"📝 Не забудьте записать прием пищи в дневник: /add"
                )
                
                await context.bot.send_message(
                    job.chat_id,
                    message,
                    parse_mode='Markdown'
                ) 