import os
import sys
import time
import asyncio
import aiosqlite
from typing import Any, Awaitable, Callable, Dict
from decouple import config
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.dispatcher.middlewares.base import BaseMiddleware

# Автоматически добавляем родительскую директорию в пути, чтобы импортировать модель
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from model.model import ProductivityModel

# --- Абсолютные пути, чтобы бот не падал при запуске из разных папок ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(CURRENT_DIR, "database.db")

# --- Инициализация ---
BOT_TOKEN = config('BOT_TOKEN')
session = AiohttpSession(timeout=60)  # Оптимальный таймаут для стабильного соединения
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
ml_model = ProductivityModel()


# --- МИДЛВАРЬ ДЛЯ ЗАЩИТЫ ОТ DDOS (ANTI-FLOOD) ---
class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.7):
        self.limit = limit
        self.users: Dict[int, float] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[types.Message, Dict[str, Any]], Awaitable[Any]],
        event: types.Message,
        data: Dict[str, Any]
    ) -> Any:
        if not event.from_user:
            return await handler(event, data)
            
        user_id = event.from_user.id
        current_time = time.time()
        
        if user_id in self.users:
            last_time = self.users[user_id]
            if current_time - last_time < self.limit:
                # Если пользователь спамит слишком часто, просто молча игнорируем запрос
                return 
                
        self.users[user_id] = current_time
        return await handler(event, data)


# Подключаем защиту от спама ко всем входящим сообщениям
dp.message.outer_middleware(AntiFloodMiddleware(limit=0.7))


# --- FSM Классы ---
class RegState(StatesGroup):
    university = State()
    course = State()
    group_name = State()
    has_job = State()

class TimeState(StatesGroup):
    classes = State()
    study = State()
    sports = State()
    shorts = State()
    youtube = State()
    games = State()
    chores = State()
    sleep = State()


# --- Хелпер для валидации времени ---
def validate_hours(input_text: str, current_data: dict) -> tuple[bool, float, str]:
    """Проверяет корректность ввода времени и лимит в 24 часа + защита от сверхбольших чисел."""
    # Защита от слишком длинного ввода (строка > 10 символов не может быть адекватным числом часов)
    if len(input_text.strip()) > 10:
        return False, 0.0, "❌ Введено слишком длинное число! Пожалуйста, укажите реальное количество часов."

    try:
        val = float(input_text.replace(',', '.'))
    except (ValueError, OverflowError):  # Теперь ловим и неформат, и переполнение памяти
        return False, 0.0, "❌ Пожалуйста, введи корректное число (например: 2 или 1.5)."
        
    if val < 0:
        return False, 0.0, "❌ Количество часов не может быть отрицательным!"
    if val > 24:
        return False, 0.0, "❌ В сутках всего 24 часа. Нельзя ввести число больше 24!"
        
    # Считаем сумму уже заполненных часов
    time_keys = ['classes', 'study', 'sports', 'shorts', 'youtube', 'games', 'chores', 'sleep']
    already_spent = sum(float(current_data.get(k, 0.0)) for k in time_keys)
    
    if already_spent + val > 24:
        available = round(24.0 - already_spent, 2)
        return False, 0.0, f"❌ Ошибка! Сумма часов превышает 24.\nУ тебя уже распределено: {already_spent} ч.\nДоступно максимум: {available} ч."
        
    return True, round(val, 2), ""


# --- База Данных (Используем безопасный DB_PATH) ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            university TEXT,
            course INTEGER,
            group_name TEXT,
            has_job BOOLEAN
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS time_stats (
            user_id INTEGER PRIMARY KEY,
            classes REAL,
            study REAL,
            sports REAL,
            shorts REAL,
            youtube REAL,
            games REAL,
            chores REAL,
            sleep REAL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )''')
        await db.commit()


# --- Клавиатуры ---
# --- Клавиатуры ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Ввести/Изменить время ⏱")],
        [KeyboardButton(text="Моя продуктивность 📊"), KeyboardButton(text="Сравнение 📈")],
        [KeyboardButton(text="Мой профиль 👤")]
    ],
    resize_keyboard=True
)

compare_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="С группой 👥"), KeyboardButton(text="С курсом 📚")],
        [KeyboardButton(text="С универом 🏫"), KeyboardButton(text="Со всеми 🌍")],
        [KeyboardButton(text="Назад в меню ⬅️")]
    ],
    resize_keyboard=True
)

# --- Хэндлеры Регистрации ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        # Защищено от SQL-инъекций через кортеж параметров (?,)
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (message.from_user.id,))
        user = await cursor.fetchone()
        
        if user:
            await message.answer("С возвращением! Выбери действие в меню.", reply_markup=main_kb)
        else:
            await message.answer("Привет! Давай зарегистрируемся.\nВведи название своего университета:")
            await state.set_state(RegState.university)

@dp.message(RegState.university)
async def process_uni(message: types.Message, state: FSMContext):
    if len(message.text) > 100:
        return await message.answer("❌ Название слишком длинное. Введи покороче (до 100 символов).")
    await state.update_data(university=message.text.strip())
    await message.answer("На каком ты курсе? (введи цифру)")
    await state.set_state(RegState.course)

@dp.message(RegState.course)
async def process_course(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 6):
        return await message.answer("❌ Пожалуйста, введи реальный номер курса цифрой (от 1 до 6).")
    await state.update_data(course=int(message.text))
    await message.answer("Введи номер своей группы:")
    await state.set_state(RegState.group_name)

@dp.message(RegState.group_name)
async def process_group(message: types.Message, state: FSMContext):
    if len(message.text) > 30:
        return await message.answer("❌ Слишком длинное название группы.")
    await state.update_data(group_name=message.text.strip())
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("Ты совмещаешь учебу с работой?", reply_markup=kb)
    await state.set_state(RegState.has_job)

@dp.message(RegState.has_job, F.text.in_(["Да", "Нет"]))
async def process_job(message: types.Message, state: FSMContext):
    has_job = True if message.text == "Да" else False
    data = await state.get_data()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Все параметры строго разделены, инъекции невозможны
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, university, course, group_name, has_job) VALUES (?, ?, ?, ?, ?)",
            (message.from_user.id, data['university'], data['course'], data['group_name'], has_job)
        )
        await db.commit()
        
    await state.clear()
    await message.answer("Регистрация успешна! Теперь введи свое распределение времени.", reply_markup=main_kb)


# --- Хэндлеры Ввода Времени с валидацией ---
@dp.message(F.text == "Ввести/Изменить время ⏱")
async def start_time_input(message: types.Message, state: FSMContext):
    await state.clear()  # Сбрасываем старые черновики ввода
    await message.answer("Сколько часов в день уходит на пары в среднем?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(TimeState.classes)

@dp.message(TimeState.classes)
async def process_classes(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(classes=val)
    await message.answer("Сколько часов уходит на самостоятельную учебу после пар?")
    await state.set_state(TimeState.study)

@dp.message(TimeState.study)
async def process_study(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(study=val)
    await message.answer("Сколько часов занимает спорт (секции, зал)?")
    await state.set_state(TimeState.sports)

@dp.message(TimeState.sports)
async def process_sports(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(sports=val)
    await message.answer("Сколько часов в день ты листаешь TikTok/Reels/Shorts/VK клипы?")
    await state.set_state(TimeState.shorts)

@dp.message(TimeState.shorts)
async def process_shorts(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(shorts=val)
    await message.answer("Сколько часов уходит на YouTube?")
    await state.set_state(TimeState.youtube)

@dp.message(TimeState.youtube)
async def process_youtube(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(youtube=val)
    await message.answer("Сколько часов в день ты играешь в игры?")
    await state.set_state(TimeState.games)

@dp.message(TimeState.games)
async def process_games(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(games=val)
    await message.answer("Сколько часов занимают домашние дела (уборка, готовка)?")
    await state.set_state(TimeState.chores)

@dp.message(TimeState.chores)
async def process_chores(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    await state.update_data(chores=val)
    await message.answer("И последнее: сколько часов ты спишь в сутки?")
    await state.set_state(TimeState.sleep)

@dp.message(TimeState.sleep)
async def finish_time_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    is_valid, val, err_msg = validate_hours(message.text, data)
    if not is_valid:
        return await message.answer(err_msg)
        
    data['sleep'] = val
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO time_stats (user_id, classes, study, sports, shorts, youtube, games, chores, sleep)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            classes=excluded.classes, study=excluded.study, sports=excluded.sports,
            shorts=excluded.shorts, youtube=excluded.youtube, games=excluded.games, 
            chores=excluded.chores, sleep=excluded.sleep
        ''', (
            message.from_user.id, data['classes'], data['study'], data['sports'],
            data['shorts'], data['youtube'], data['games'], data['chores'], data['sleep']
        ))
        await db.commit()
        
    await state.clear()
    await message.answer("Данные о времени успешно сохранены и обновлены!", reply_markup=main_kb)


# --- Анализ и Меню ---
@dp.message(F.text == "Моя продуктивность 📊")
async def analyze_productivity(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        u_cursor = await db.execute("SELECT has_job FROM users WHERE user_id = ?", (message.from_user.id,))
        user_row = await u_cursor.fetchone()
        
        t_cursor = await db.execute("SELECT * FROM time_stats WHERE user_id = ?", (message.from_user.id,))
        stats_row = await t_cursor.fetchone()
        
    if not stats_row or not user_row:
        return await message.answer("Сначала введи данные о времени через меню!")
        
    time_data = dict(stats_row)
    del time_data['user_id']
    time_data['has_job'] = 1 if user_row['has_job'] else 0
    
    score = ml_model.predict_efficiency(time_data)
    recs = ml_model.get_recommendations(time_data)
    
    await message.answer(
        f"🧠 Расчетная эффективность по ML-модели: **{score}%**\n\n**Рекомендации:**\n{recs}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "Сравнение 📈")
async def show_compare_menu(message: types.Message):
    await message.answer("С кем ты хочешь сравнить свои результаты?", reply_markup=compare_kb)

@dp.message(F.text == "Назад в меню ⬅️")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_kb)

@dp.message(F.text.in_(["С группой 👥", "С курсом 📚", "С универом 🏫", "Со всеми 🌍"]))
async def process_comparison(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        # Достаем данные пользователя для формирования условий поиска
        cursor = await db.execute("SELECT university, course, group_name FROM users WHERE user_id = ?", (message.from_user.id,))
        user_info = await cursor.fetchone()
        
        if not user_info:
            return await message.answer("Профиль не найден. Перезапусти бота через /start")
            
        uni, course, group = user_info
        
        # Базовый запрос
        query = """
            SELECT AVG(t.study), AVG(t.shorts), AVG(t.games), AVG(t.sleep)
            FROM time_stats t 
            JOIN users u ON t.user_id = u.user_id 
        """
        params = []
        title = ""
        
        # Динамически добавляем фильтры (WHERE) в зависимости от кнопки
        if message.text == "С группой 👥":
            query += "WHERE u.university = ? AND u.course = ? AND u.group_name = ?"
            params = [uni, course, group]
            title = f"со студентами группы {group} ({course} курс, {uni})"
        elif message.text == "С курсом 📚":
            query += "WHERE u.university = ? AND u.course = ?"
            params = [uni, course]
            title = f"со студентами {course} курса ({uni})"
        elif message.text == "С универом 🏫":
            query += "WHERE u.university = ?"
            params = [uni]
            title = f"со студентами {uni}"
        elif message.text == "Со всеми 🌍":
            title = "со всеми пользователями бота"
            
        cursor = await db.execute(query, params)
        avg_stats = await cursor.fetchone()
        
        cursor = await db.execute("SELECT study, shorts, games, sleep FROM time_stats WHERE user_id = ?", (message.from_user.id,))
        my_stats = await cursor.fetchone()
        
    if not my_stats:
        return await message.answer("Сначала введи свои данные о времени через меню!")
        
    if not avg_stats or avg_stats[0] is None:
        return await message.answer(f"Пока недостаточно данных для сравнения {title}.")
        
    avg_study, avg_shorts, avg_games, avg_sleep = [round(x, 1) for x in avg_stats]
    my_study, my_shorts, my_games, my_sleep = my_stats
    
    text = f"📊 **Сравнение {title}:**\n\n"
    text += f"📚 Учеба вне пар:\nТы: {my_study} ч. | В среднем: {avg_study} ч.\n\n"
    text += f"📱 Короткие видео:\nТы: {my_shorts} ч. | В среднем: {avg_shorts} ч.\n\n"
    text += f"🎮 Игры:\nТы: {my_games} ч. | В среднем: {avg_games} ч.\n\n"
    text += f"😴 Сон:\nТы: {my_sleep} ч. | В среднем: {avg_sleep} ч."
    
    await message.answer(text, parse_mode="Markdown")
@dp.message(F.text == "Мой профиль 👤")
async def show_profile(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT university, course, group_name, has_job FROM users WHERE user_id = ?", (message.from_user.id,))
        user_info = await cursor.fetchone()
        
    if user_info:
        uni, course, group, has_job = user_info
        job_text = "Да" if has_job else "Нет"
        text = f"👤 **Твой профиль:**\n\n🏫 Университет: {uni}\n📈 Курс: {course}\n👥 Группа: {group}\n💼 Работа: {job_text}\n\n_Чтобы изменить профиль, отправь команду /start заново_"
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("Профиль не найден. Отправь /start")


# --- Запуск ---
async def main():
    await init_db()
    print("Бот успешно запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())