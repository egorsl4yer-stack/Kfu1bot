import asyncio
import datetime
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from fastapi import FastAPI
import pandas as pd
import pytz
import uvicorn

TOKEN = "8961619027:AAGRDD1Ik0uousmP43uT5ezmybbWOVp74_o"

bot = Bot(token=TOKEN)
dp = Dispatcher()

EXCEL_FILE = "Расписание_Менеджмент_1_семестр_2026_2027_21_08_2026.xlsx"
MSK_TZ = pytz.timezone("Europe/Moscow")

DAYS_MAP = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}

# Глобальные переменные для объявлений группы
current_group_note = None
note_date = None


def get_current_msk_time():
  """Возвращает точное текущее время по Москве (МСК)"""
  return datetime.datetime.now(MSK_TZ)


def get_current_academic_week(target_date=None) -> int:
  """Строгий расчет учебных недель по календарным неделям (с понедельника).

  1 сентября 2026 — вторник. Понедельник этой недели — 31 августа 2026.
  """
  if target_date is None:
    target_date = get_current_msk_time().date()

  sem_start_monday = datetime.date(2026, 8, 31)
  delta_days = (target_date - sem_start_monday).days
  if delta_days < 0:
    return 1
  return (delta_days // 7) + 1


def get_weeks_left(subject_str: str, current_week: int) -> int:
  """Считает, сколько учебных недель (занятий) осталось до конца предмета"""
  match = re.search(r"(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\s*нед", subject_str)
  if not match:
    return 17 - current_week + 1

  week_part = match.group(1)
  ranges = week_part.split(",")
  left_count = 0
  for r in ranges:
    r = r.strip()
    if "-" in r:
      start, end = map(int, r.split("-"))
      s_w = max(current_week, start)
      if s_w <= end:
        left_count += end - s_w + 1
    else:
      w = int(r)
      if w >= current_week:
        left_count += 1
  return left_count


def is_subject_active(subject_str: str, current_week: int) -> bool:
  """Проверяет, идет ли предмет на текущей учебной неделе"""
  match = re.search(r"(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\s*нед", subject_str)
  if not match:
    return True

  week_part = match.group(1)
  ranges = week_part.split(",")
  for r in ranges:
    r = r.strip()
    if "-" in r:
      start, end = map(int, r.split("-"))
      if start <= current_week <= end:
        return True
    else:
      if int(r) == current_week:
        return True
  return False


def clean_subject_text(subject_str: str) -> str:
  """Очищает текст предмета от номеров недель и лишнего мусора"""
  cleaned = re.sub(
      r"\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*\s*(?:\(\d+\)\s*)?нед\.?",
      "",
      subject_str,
  )
  cleaned = cleaned.split("14.6-")[0]
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned


def get_main_keyboard():
  """Инлайн-клавиатура под сообщениями"""
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="☀️ Сегодня", callback_data="btn_today"),
              InlineKeyboardButton(text="🌙 Завтра", callback_data="btn_tomorrow"),
          ],
          [InlineKeyboardButton(text="📚 Вся неделя", callback_data="btn_week")],
      ]
  )


def get_schedule_for_day(target_day_name: str, target_date=None) -> str:
  if not os.path.exists(EXCEL_FILE):
    return "❌ **Ошибка:** файл расписания не найден на сервере!"

  try:
    df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ", header=None)

    col_idx = None
    for c in range(df.shape[1]):
      if "14.6-515" in str(df.iloc[7, c]):
        col_idx = c
        break

    if col_idx is None:
      return "⚠️ Не удалось найти группу 14.6-515 в таблице."

    if target_date is None:
      target_date = get_current_msk_time().date()

    current_week = get_current_academic_week(target_date)

    schedule_list = []
    current_day = ""

    for r in range(8, len(df)):
      day_val = (
          df.iloc[r, 0]
          if pd.notna(df.iloc[r, 0])
          else (df.iloc[r, 7] if pd.notna(df.iloc[r, 7]) else None)
      )
      time_val = (
          df.iloc[r, 1]
          if pd.notna(df.iloc[r, 1])
          else (df.iloc[r, 8] if pd.notna(df.iloc[r, 8]) else None)
      )
      subj_val = df.iloc[r, col_idx]

      if day_val is not None and not str(day_val).startswith("Дни"):
        current_day = str(day_val).strip()

      if (
          current_day.lower().startswith(target_day_name.lower())
          and pd.notna(subj_val)
          and str(subj_val).strip() != "nan"
          and str(subj_val).strip() != ""
      ):
        if is_subject_active(str(subj_val), current_week):
          clean_subj = clean_subject_text(str(subj_val))
          weeks_left = get_weeks_left(str(subj_val), current_week)
          if clean_subj:
            schedule_list.append(
                f"🕒 **{time_val}**\n📚 {clean_subj}\n⏳ *Осталось занятий:"
                f" {weeks_left}*\n"
            )

    global current_group_note, note_date
    note_text = ""
    if (
        current_group_note
        and note_date == get_current_msk_time().date().isoformat()
    ):
      note_text = (
          f"\n📢 **ВАЖНОЕ ОБЪЯВЛЕНИЕ:**\n_{current_group_note}_\n━━━━━━━━━━━━━━━━━━━━━━\n"
      )

    if not schedule_list:
      return (
          f"{note_text}🏖 *{target_day_name}* — пар у группы **14.6-515** нет"
          " (выходной день)!"
      )

    result = [
        f"{note_text}✨ **Расписание • Группа 14.6-515**\n📌 День:"
        f" **{target_day_name}** (`{current_week}-я учебная неделя`)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    result.extend(schedule_list)
    return "\n".join(result)

  except Exception as e:
    return f"⚠️ Ошибка при обработке расписания: {e}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "👋 **Привет! Твой бот расписания группы 14.6-515 (по МСК).**\n\n"
      "🤖 *Все недели считаются строго по понедельникам, таймеры и кнопки"
      " активны!* Выбирай действие ниже 👇",
      parse_mode="Markdown",
      reply_markup=get_main_keyboard(),
  )


@dp.message(Command("note"))
async def cmd_note(message: Message):
  """Команда для создания объявления: /note Текст"""
  global current_group_note, note_date
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.answer(
        "⚠️ Напиши текст объявления после команды, например:\n`/note Завтра"
        " встречаемся у 401 аудитории в 9:50`",
        parse_mode="Markdown",
    )
    return

  current_group_note = args[1]
  note_date = get_current_msk_time().date().isoformat()
  await message.answer(
      "✅ Объявление успешно опубликовано на сегодня!", parse_mode="Markdown"
  )


@dp.message(Command("today"))
async def cmd_today(message: Message):
  now_msk = get_current_msk_time()
  today_name = DAYS_MAP[now_msk.weekday()]
  text = get_schedule_for_day(today_name, now_msk.date())

  try:
    df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ", header=None)
    col_idx = None
    for c in range(df.shape[1]):
      if "14.6-515" in str(df.iloc[7, c]):
        col_idx = c
        break

    current_day = ""
    current_time = now_msk.time()
    next_class_info = None

    for r in range(8, len(df)):
      day_val = (
          df.iloc[r, 0]
          if pd.notna(df.iloc[r, 0])
          else (df.iloc[r, 7] if pd.notna(df.iloc[r, 7]) else None)
      )
      time_val = (
          df.iloc[r, 1]
          if pd.notna(df.iloc[r, 1])
          else (df.iloc[r, 8] if pd.notna(df.iloc[r, 8]) else None)
      )
      subj_val = df.iloc[r, col_idx]

      if day_val is not None and not str(day_val).startswith("Дни"):
        current_day = str(day_val).strip()

      if (
          current_day.lower().startswith(today_name.lower())
          and pd.notna(subj_val)
          and str(subj_val).strip() != "nan"
          and str(subj_val).strip() != ""
      ):
        if time_val and "-" in str(time_val):
          start_t_str = str(time_val).split("-")[0].strip()
          h, m = map(int, start_t_str.split(":"))
          lesson_time = datetime.time(h, m)

          if current_time < lesson_time:
            d1 = datetime.datetime.combine(now_msk.date(), current_time)
            d2 = datetime.datetime.combine(now_msk.date(), lesson_time)
            diff = d2 - d1
            hrs = diff.seconds // 3600
            mins = (diff.seconds % 3600) // 60
            clean_subj = clean_subject_text(str(subj_val))
            next_class_info = (
                f"\n⏰ *До след. пары* «{clean_subj[:25]}...» ({time_val})"
                f" осталось: **{hrs} ч. {mins} мин.**"
            )
            break

    if next_class_info:
      text += f"\n━━━━━━━━━━━━━━━━━━━━━━{next_class_info}"
    else:
      text += (
          "\n━━━━━━━━━━━━━━━━━━━━━━\n🏁 *Все пары на сегодня уже прошли или не"
          " ожидаются!*"
      )
  except Exception:
    pass

  await message.answer(
      text, parse_mode="Markdown", reply_markup=get_main_keyboard()
  )


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
  tomorrow_msk = get_current_msk_time() + datetime.timedelta(days=1)
  tomorrow_name = DAYS_MAP[tomorrow_msk.weekday()]
  text = get_schedule_for_day(tomorrow_name, tomorrow_msk.date())
  await message.answer(
      text, parse_mode="Markdown", reply_markup=get_main_keyboard()
  )


@dp.message(Command("week"))
async def cmd_week(message: Message):
  days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
  now_msk = get_current_msk_time()
  current_week = get_current_academic_week(now_msk.date())

  await message.answer(
      f"📚 **Расписание на всю неделю для группы 14.6-515**\n🗓 *Текущая"
      f" учебная неделя: {current_week}-я (МСК)*\n━━━━━━━━━━━━━━━━━━━━━━",
      parse_mode="Markdown",
  )

  for i, day in enumerate(days):
    res = get_schedule_for_day(day, now_msk.date())
    # Кнопки отправляем только под последним сообщением недели (субботой)
    markup = get_main_keyboard() if day == "Суббота" else None
    await message.answer(res, parse_mode="Markdown", reply_markup=markup)
    await asyncio.sleep(0.3)


@dp.callback_query(
    F.data.in_(["btn_today", "btn_tomorrow", "btn_week", "btn_menu"])
)
async def process_callbacks(callback: types.CallbackQuery):
  if callback.data == "btn_today":
    await callback.message.delete()
    now_msk = get_current_msk_time()
    today_name = DAYS_MAP[now_msk.weekday()]
    text = get_schedule_for_day(today_name, now_msk.date())
    await callback.message.answer(
        text, parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

  elif callback.data == "btn_tomorrow":
    await callback.message.delete()
    tomorrow_msk = get_current_msk_time() + datetime.timedelta(days=1)
    tomorrow_name = DAYS_MAP[tomorrow_msk.weekday()]
    text = get_schedule_for_day(tomorrow_name, tomorrow_msk.date())
    await callback.message.answer(
        text, parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

  elif callback.data == "btn_week":
    await callback.message.delete()
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
    now_msk = get_current_msk_time()
    current_week = get_current_academic_week(now_msk.date())
    await callback.message.answer(
        f"📚 **Расписание на всю неделю**\n🗓 *{current_week}-я неделя*,"
        f" группа 14.6-515\n━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for day in days:
      res = get_schedule_for_day(day, now_msk.date())
      markup = get_main_keyboard() if day == "Суббота" else None
      await callback.message.answer(res, parse_mode="Markdown", reply_markup=markup)
      await asyncio.sleep(0.3)

  await callback.answer()


# Веб-сервер для Render
app = FastAPI()


@app.get("/")
def index():
  return "Bot is alive and configured!"


async def run_bot():
  await dp.start_polling(bot)


@app.on_event("startup")
async def startup_event():
  asyncio.create_task(run_bot())


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))
  uvicorn.run(app, host="0.0.0.0", port=port)
