from dataclasses import dataclass
from typing import Dict, List

@dataclass
class NutritionRecommendations:
    protein_daily: int = 5  # порций
    vegetables_daily: int = 5  # порций
    fats_daily: int = 3  # порций
    fruits_daily: int = 4  # порций
    dairy_daily: int = 3  # порций
    grains_daily: int = 6  # порций

    def update_recommendations(self, new_values: Dict[str, int]):
        """Обновляет нормы на основе входящих данных."""
        for nutrient, value in new_values.items():
            if hasattr(self, f"{nutrient}_daily"):
                setattr(self, f"{nutrient}_daily", value)

class NutritionAnalyzer:
    def __init__(self, user_norms: Dict[str, int] = None):
        if user_norms:
            self.recommendations = NutritionRecommendations(**user_norms)
        else:
            self.recommendations = NutritionRecommendations()

    def analyze_daily_intake(self, totals: Dict[str, int]) -> List[str]:
        """Анализирует дневное потребление и выдает рекомендации"""
        recommendations = []
        
        # Проверяем белки
        protein_percent = (totals['protein'] / self.recommendations.protein_daily) * 100 
        if protein_percent < 80:
            recommendations.append("⚠️ Недостаточное потребление белка. Добавьте в рацион мясо, рыбу, яйца или бобовые.")
        elif protein_percent > 120:
            recommendations.append("⚠️ Избыточное потребление белка. Уменьшите порции белковых продуктов.")

        # Проверяем овощи
        if totals['vegetables'] < self.recommendations.vegetables_daily:
            recommendations.append("🥗 Рекомендуется увеличить потребление овощей для лучшего здоровья.")

        # Проверяем жиры
        fat_percent = (totals['fats'] / self.recommendations.fats_daily) * 100
        if fat_percent > 110:
            recommendations.append("⚠️ Высокое потребление жиров. Обратите внимание на размер порций.")

        # Проверяем фрукты
        if totals['fruits'] < self.recommendations.fruits_daily:
            recommendations.append("🍎 Добавьте больше фруктов в свой рацион.")

        # Общие рекомендации
        if not recommendations:
            recommendations.append("👍 Ваш рацион сбалансирован. Продолжайте в том же духе!")

        return recommendations 