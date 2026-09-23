import asyncio
import datetime
import os
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


def get_schedule_for_day(target_day_name: str) -> str:
  if not os.path.exists(EXCEL_FILE):
    return "❌ Файл расписания не найден на сервере!"

  try:
    df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ", header=None)

    col_idx = None
    for c in range(df.shape[1]):
      if "14.6-515" in str(df.iloc[7, c]):
        col_idx = c
        break

    if col_idx is None:
      return "⚠️ Не удалось найти группу 14.6-515 в таблице."

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
        clean_subj = str(subj_val).split("14.6-")[0].strip()
        schedule_list.append(f"⏰ *{time_val}*:\n{clean_subj}\n")

    if not schedule_list:
      return f"🎉 На день ({target_day_name}) у группы 14.6-515 пар нет (выходной)!"

    result = [f"📅 **Расписание для группы 14.6-515 на {target_day_name}:**\n"]
    result.extend(schedule_list)
    return "\n".join(result)

  except Exception as e:
    return f"⚠️ Ошибка при обработке расписания: {e}"


@dp.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "Привет! Я бот расписания группы 14.6-515.\n\nКоманды:\n/today — пары на"
      " сегодня\n/tomorrow — пары на завтра\n/week — на всю неделю"
  )


@dp.message(Command("today"))
async def cmd_today(message: Message):
  today_index = datetime.datetime.now().weekday()
  today_name = DAYS_MAP[today_index]
  text = get_schedule_for_day(today_name)
  await message.answer(text, parse_mode="Markdown")


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
  tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
  tomorrow_name = DAYS_MAP[tomorrow.weekday()]
  text = get_schedule_for_day(tomorrow_name)
  await message.answer(text, parse_mode="Markdown")


@dp.message(Command("week"))
async def cmd_week(message: Message):
  days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
  full_schedule = ["📚 **Расписание группы 14.6-515 на всю неделю:**\n"]
  for day in days:
    res = get_schedule_for_day(day)
    full_schedule.append(res + "\n" + "—" * 20 + "\n")
  await message.answer("\n".join(full_schedule), parse_mode="Markdown")


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
