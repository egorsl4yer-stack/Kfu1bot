import asyncio
import datetime
import os
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from fastapi import FastAPI
import pandas as pd
import uvicorn

TOKEN = "8961619027:AAGRDD1Ik0uousmP43uT5ezmybbWOVp74_o"

bot = Bot(token=TOKEN)
dp = Dispatcher()

EXCEL_FILE = "Расписание_Менеджмент_1_семестр_2026_2027_21_08_2026.xlsx"

DAYS_MAP = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def get_current_academic_week(target_date=None) -> int:
  """Считает учебную неделю строго по календарным неделям (с понедельника).

  1 сентября 2026 года — вторник. Понедельник этой недели — 31 августа 2026 г.
  """
  if target_date is None:
    target_date = datetime.date.today()

  sem_start_monday = datetime.date(2026, 8, 31)
  delta_days = (target_date - sem_start_monday).days
  if delta_days < 0:
    return 1
  return (delta_days // 7) + 1


def get_weeks_left(subject_str: str, current_week: int) -> int:
  """Считает, сколько всего учебных недель (занятий) осталось до конца предмета"""
  match = re.search(r"(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\s*нед", subject_str)
  if not match:
    return 17 - current_week + 1  # Если без ограничений, до конца семестра (17 нед)

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
  """Убирает из текста упоминания недель и лишний мусор"""
  cleaned = re.sub(
      r"\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*\s*(?:\(\d+\)\s*)?нед\.?",
      "",
      subject_str,
  )
  cleaned = cleaned.split("14.6-")[0]
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned


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
      target_date = datetime.date.today()

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

    if not schedule_list:
      return (
          f"🏖 *{target_day_name}* — пар у группы **14.6-515** нет (выходной"
          f" день)!"
      )

    result = [
        f"✨ **Расписание • Группа 14.6-515**\n📌 День: **{target_day_name}**"
        f" (`{current_week}-я учебная неделя`)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    result.extend(schedule_list)
    return "\n".join(result)

  except Exception as e:
    return f"⚠️ Ошибка при обработке расписания: {e}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "👋 **Привет! Это твой личный бот расписания группы 14.6-515.**\n\n"
      "🤖 *Я автоматически считаю учебные недели, отслеживаю актуальные пары"
      " и подсказываю, сколько занятий осталось до конца каждого"
      " предмета.*\n\n"
      "📌 **Доступные команды:**\n"
      "• /today — расписание на сегодня ☀️\n"
      "• /tomorrow — расписание на завтра 🌙\n"
      "• /week — расписание на всю неделю 📅",
      parse_mode="Markdown",
  )


@dp.message(Command("today"))
async def cmd_today(message: Message):
  today = datetime.date.today()
  today_name = DAYS_MAP[today.weekday()]
  text = get_schedule_for_day(today_name, today)
  await message.answer(text, parse_mode="Markdown")


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
  tomorrow = datetime.date.today() + datetime.timedelta(days=1)
  tomorrow_name = DAYS_MAP[tomorrow.weekday()]
  text = get_schedule_for_day(tomorrow_name, tomorrow)
  await message.answer(text, parse_mode="Markdown")


@dp.message(Command("week"))
async def cmd_week(message: Message):
  days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
  today = datetime.date.today()
  current_week = get_current_academic_week(today)

  await message.answer(
      f"📚 **Расписание на всю неделю для группы 14.6-515**\n🗓 *Текущая"
      f" учебная неделя: {current_week}-я*\n━━━━━━━━━━━━━━━━━━━━━━",
      parse_mode="Markdown",
  )

  for day in days:
    res = get_schedule_for_day(day, today)
    # Отправляем каждый день отдельным красивым сообщением
    await message.answer(res, parse_mode="Markdown")
    await asyncio.sleep(0.3)  # Небольшая пауза для порядка


# Веб-сервер для Render
app = FastAPI()


@app.get("/")
def index():
  return "Bot is alive!"


async def run_bot():
  await dp.start_polling(bot)


@app.on_event("startup")
async def startup_event():
  asyncio.create_task(run_bot())


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))
  uvicorn.run(app, host="0.0.0.0", port=port)
