import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

class ProductivityModel:
    def __init__(self, data_path="model/data.csv"):
        # Получаем абсолютный путь к CSV, чтобы не было ошибок при запуске из разных папок
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_path = os.path.join(current_dir, "data.csv")
        
        # Инициализируем Случайный Лес
        # n_estimators=100 - создаем 100 деревьев принятия решений
        # max_depth=5 - ограничиваем глубину, чтобы модель не зазубривала данные (защита от переобучения)
        self.model = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
        self.is_trained = False
        
        # Обучаем модель при запуске
        self.train_model()

    def train_model(self):
        """Обучает модель на CSV. Если данных нет, использует синтетическую базу."""
        if os.path.exists(self.data_path) and os.path.getsize(self.data_path) > 0:
            try:
                df = pd.read_csv(self.data_path)
                # Если в таблице есть колонка efficiency, учимся на реальных данных
                if 'efficiency_score' in df.columns:
                    X = df[['classes', 'study', 'sports', 'shorts', 'youtube', 'games', 'chores', 'sleep', 'has_job']]
                    y = df['efficiency_score']
                    self.model.fit(X, y)
                    self.is_trained = True
                    print("Модель успешно обучена на реальных данных из CSV!")
                    return
            except Exception as e:
                print(f"Ошибка при чтении CSV: {e}. Переход на синтетические данные.")

        # Если файла нет или данных мало, загружаем в модель "базовую логику"
        self._train_on_synthetic_data()

    def _train_on_synthetic_data(self):
        """Зашиваем в модель понимание нелинейности (золотой середины)"""
        # Колонки: classes, study, sports, shorts, youtube, games, chores, sleep, has_job
        X_synthetic = [
            [6, 2, 1.5, 0.5, 1, 0, 1, 8, 0],  # Идеальный студент (Сон 8ч, мало шортсов, есть спорт)
            [4, 0, 0, 4.0, 3, 4, 0, 5, 0],    # Лентяй-геймер с недосыпом
            [8, 4, 0, 0.0, 0, 0, 0, 4, 1],    # Трудоголик на грани выгорания (очень мало сна, много работы)
            [2, 1, 0, 3.0, 3, 3, 1, 12, 0],   # Слишком много сна и прокрастинации
            [5, 2, 1.0, 1.0, 1, 1, 1, 7.5, 1] # Хороший баланс с работой
        ]
        # Оценки эффективности для этих архетипов (от 0 до 100)
        y_synthetic = [95, 15, 55, 30, 88] 
        
        self.model.fit(X_synthetic, y_synthetic)
        self.is_trained = True
        print("CSV не найден или пуст. Модель Random Forest обучена на синтетических архетипах.")

    def predict_efficiency(self, time_data: dict) -> int:
        """Предсказывает эффективность на основе словаря с часами от телеграм-бота."""
        if not self.is_trained:
            return 0
            
        # Строго соблюдаем порядок признаков (фичей)
        features = [
            time_data.get('classes', 0),
            time_data.get('study', 0),
            time_data.get('sports', 0),
            time_data.get('shorts', 0),
            time_data.get('youtube', 0),
            time_data.get('games', 0),
            time_data.get('chores', 0),
            time_data.get('sleep', 0),
            time_data.get('has_job', 0)
        ]
        
        # Модель ожидает двумерный массив (список списков)
        prediction = self.model.predict([features])[0]
        
        # Гарантируем, что процент не выйдет за пределы 0-100
        return int(np.clip(prediction, 0, 100))

    def get_recommendations(self, time_data: dict) -> str:
        """Классические рекомендации на основе эвристики (правил)"""
        recs = []
        sleep = time_data.get('sleep', 0)
        procrastination = time_data.get('shorts', 0) + time_data.get('games', 0)
        
        if sleep < 6:
            recs.append("🔴 Твой сон критически мал! Модель сильно штрафует за недосып, так как это ведет к выгоранию. Старайся спать 7-8 часов.")
        elif sleep > 10:
            recs.append("🟡 Ты спишь больше нормы. Слишком долгий сон может вызывать чувство вялости.")
            
        if procrastination > 4:
            recs.append("🔴 У тебя уходит больше 4 часов в день на 'дешевый дофамин' (рилсы, игры). Попробуй сократить это время хотя бы на час.")
            
        if time_data.get('study', 0) == 0 and time_data.get('classes', 0) > 0:
            recs.append("🟡 Пары — это хорошо, но без самостоятельной учебы материал забудется. Добавь хотя бы 30 минут на повторение.")

        if not recs:
            recs.append("🟢 У тебя идеальный баланс! Ты держишь отличную пропорцию между учебой, отдыхом и сном. Так держать!")
            
        return "\n".join(recs)