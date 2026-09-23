import asyncio
import datetime
import os
import random
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message
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

current_group_note = None
note_date = None


def get_current_msk_time():
  return datetime.datetime.now(MSK_TZ)


def get_current_academic_week(target_date=None) -> int:
  if target_date is None:
    target_date = get_current_msk_time().date()

  sem_start_monday = datetime.date(2026, 8, 31)
  delta_days = (target_date - sem_start_monday).days
  if delta_days < 0:
    return 1
  return (delta_days // 7) + 1


def is_even_week(week_num: int) -> bool:
  return week_num % 2 == 0


def get_weeks_left(subject_str: str, current_week: int) -> int:
  match = re.search(
      r"(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\s*(?:\(\d+\)\s*)?нед",
      subject_str,
  )
  if not match:
    return max(0, 17 - current_week + 1)

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
  match = re.search(
      r"(\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*)\s*(?:\(\d+\)\s*)?нед",
      subject_str,
  )
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
  cleaned = re.sub(
      r"\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*\s*(?:\(\d+\)\s*)?нед\.?",
      "",
      subject_str,
  )
  cleaned = re.split(r"14\.6-\d+", cleaned)[0]
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned


def is_valid_subject(subject_str: str) -> bool:
  if not subject_str or subject_str.lower() in ["nan", "none", "", "-"]:
    return False
  if re.match(r"^[\d:\-\.\s]+$", subject_str):
    return False
  if len(subject_str) < 3:
    return False
  return True


def parse_time_str(time_str: str):
  try:
    parts = time_str.replace(" ", "").split("-")
    if len(parts) != 2:
      return None
    start_h, start_m = map(int, parts[0].split(":"))
    end_h, end_m = map(int, parts[1].split(":"))
    return (start_h * 60 + start_m, end_h * 60 + end_m)
  except:
    return None


def get_motivational_quote(lessons_count: int, is_weekend: bool) -> str:
  if is_weekend:
    quotes = [
        "🌴 Наконец-то выходные! Выспись за всю неделю и забудь про пары.",
        "☕️ Отдыхай, набирайся сил. Понедельник придет быстрее, чем хотелось бы!",
        "🎉 Никаких пар! Самое время погулять или поиграть в любимые игры.",
    ]
  elif lessons_count == 0:
    quotes = [
        "🍀 Халява! Сегодня пар нет, отличный день для отдыха.",
        "🧘 День без пар — повод заняться своими делами или закрыть долги.",
    ]
  elif lessons_count <= 2:
    quotes = [
        "⚡️ Легкий день! Всего пара пар, пролетит незаметно.",
        "🚀 Быстрый забег: отучился и свободен!",
        "😎 На релаксе: сегодня пар совсем немного.",
    ]
  elif lessons_count >= 4:
    quotes = [
        "🔥 Настоящий марафон! Держись, ты справишься с этим днем.",
        "☕️ Запасись кофе — день будет долгим, но ты сильнее!",
        "💪 Тяжело в учебе — зато потом легче. Жми до победного!",
    ]
  else:
    quotes = [
        "🎯 Отличный рабочий ритм. Продуктивного дня!",
        "⭐️ Хороший баланс пар. Сделай этот день крутым!",
        "🧠 Включаем режим продуктивности — всё получится!",
    ]
  return random.choice(quotes)


def get_main_keyboard():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(text="☀️ Сегодня", callback_data="btn_today"),
              InlineKeyboardButton(text="🌙 Завтра", callback_data="btn_tomorrow"),
          ],
          [
              InlineKeyboardButton(text="📚 Вся неделя", callback_data="btn_week"),
              InlineKeyboardButton(
                  text="📅 Выбрать дату", callback_data="btn_pick_date"
              ),
          ],
      ]
  )


async def set_bot_commands(bot_instance: Bot):
  commands = [
      BotCommand(command="today", description="☀️ Расписание на сегодня"),
      BotCommand(command="tomorrow", description="🌙 Расписание на завтра"),
      BotCommand(command="week", description="📚 Расписание на всю неделю"),
      BotCommand(
          command="note", description="📢 Опубликовать объявление (/note текст)"
      ),
      BotCommand(command="start", description="🔄 Перезапустить бота"),
  ]
  await bot_instance.set_my_commands(commands)


def get_schedule_data_for_day(target_day_name: str, target_date=None):
  if not os.path.exists(EXCEL_FILE):
    return [], f"❌ **Ошибка:** файл `{EXCEL_FILE}` не найден на сервере!"

  try:
    df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ", header=None)

    col_idx = None
    # Ищем точное вхождение нашей группы 14.6-515 в шапке таблицы (строки 0-11)
    for r in range(min(12, len(df))):
      for c in range(df.shape[1]):
        val = str(df.iloc[r, c])
        if "14.6-515" in val and "516" not in val:
          col_idx = c
          break
      if col_idx is not None:
        break

    if col_idx is None:
      col_idx = 9  # Безопасный фоллбек на правильную колонку

    if target_date is None:
      target_date = get_current_msk_time().date()

    current_week = get_current_academic_week(target_date)

    lessons = []
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

      if day_val is not None and not str(day_val).startswith("Дни"):
        current_day = str(day_val).strip()

      if current_day.lower().startswith(target_day_name.lower()):
        cell_val = df.iloc[r, col_idx] if col_idx < df.shape[1] else None

        if (
            pd.notna(cell_val)
            and str(cell_val).strip() != "nan"
            and str(cell_val).strip() != ""
        ):
          cell_str = str(cell_val).strip()
          parts = re.split(r"\n|\s{10,}", cell_str)

          for part in parts:
            part = part.strip()
            if not part:
              continue
            if "14.6-516" in part and "14.6-515" not in part:
              continue

            if is_subject_active(part, current_week):
              clean_subj = clean_subject_text(part)
              if is_valid_subject(clean_subj):
                weeks_left = get_weeks_left(part, current_week)
                time_str = (
                    str(time_val).strip() if time_val else "Время уточняется"
                )

                lesson_info = {
                    "time": time_str,
                    "subject": clean_subj,
                    "weeks_left": weeks_left,
                    "parsed_time": parse_time_str(time_str),
                }

                if not any(
                    l["time"] == time_str
                    and l["subject"].lower() == clean_subj.lower()
                    for l in lessons
                ):
                  lessons.append(lesson_info)

    return lessons, None
  except Exception as e:
    return [], f"⚠️ Ошибка при обработке расписания: {e}"


def build_schedule_text(target_day_name: str, target_date=None) -> str:
  if target_date is None:
    target_date = get_current_msk_time().date()

  current_week = get_current_academic_week(target_date)
  week_type = (
      "Знаменатель (четная)"
      if is_even_week(current_week)
      else "Числитель (нечетная)"
  )

  lessons, err = get_schedule_data_for_day(target_day_name, target_date)
  if err:
    return err

  global current_group_note, note_date
  note_text = ""
  today_iso = get_current_msk_time().date().isoformat()
  if (
      current_group_note
      and note_date == today_iso
      and target_date == get_current_msk_time().date()
  ):
    note_text = (
        f"📢 **ВАЖНОЕ ОБЪЯВЛЕНИЕ:**\n_{current_group_note}_\n━━━━━━━━━━━━━━━━━━━━━━\n"
    )

  is_weekend = target_day_name in ["Суббота", "Воскресенье"]

  if not lessons:
    quote = get_motivational_quote(0, is_weekend)
    return (
        f"{note_text}🏖 *{target_day_name}* (`{target_date.strftime('%d.%m.%Y')}`)"
        f" — пар у группы **14.6-515** нет!\n\n_{quote}_"
    )

  valid_times = [
      l["parsed_time"] for l in lessons if l["parsed_time"] is not None
  ]
  summary_line = ""
  if valid_times:
    start_day_mins = valid_times[0][0]
    end_day_mins = valid_times[-1][1]

    start_str = f"{start_day_mins // 60:02d}:{start_day_mins % 60:02d}"
    end_str = f"{end_day_mins // 60:02d}:{end_day_mins % 60:02d}"

    total_span_mins = end_day_mins - start_day_mins

    # Правильный расчет окон: окно — это если перерыв между парами > 90 минут
    window_hours_list = []
    for i in range(len(valid_times) - 1):
      gap = valid_times[i + 1][0] - valid_times[i][1]
      if gap > 90:
        window_hours_list.append(gap / 60)

    hours = total_span_mins // 60
    mins = total_span_mins % 60
    duration_str = f"{hours} ч {mins} мин" if mins > 0 else f"{hours} ч"

    if not window_hours_list:
      windows_str = "без окон"
    else:
      windows_str = (
          f"есть окно (-а) ~{', '.join([f'{h:.1f}' for h in window_hours_list])}"
          " ч"
      )

    summary_line = f"📋 **Сводка:** учеба с **{start_str}** до **{end_str}** ({duration_str}, {windows_str})\n"

  status_line = ""
  now_dt = get_current_msk_time()
  if target_date == now_dt.date():
    now_mins = now_dt.hour * 60 + now_dt.minute
    for l in lessons:
      pt = l["parsed_time"]
      if pt:
        s_m, e_m = pt
        if s_m <= now_mins <= e_m:
          rem = e_m - now_mins
          status_line = (
              f"⏳ *Сейчас идет пара! До конца осталось ~{rem} мин.*\n"
          )
          break
        elif now_mins < s_m:
          diff = s_m - now_mins
          h = diff // 60
          m = diff % 60
          time_to = f"{h} ч {m} мин" if h > 0 else f"{m} мин"
          status_line = f"⏳ *До первой/следующей пары осталось {time_to}*\n"
          break

  quote = get_motivational_quote(len(lessons), is_weekend)

  result = [
      f"{note_text}"
      f"✨ **Расписание • Группа 14.6-515**\n"
      f"📌 День: **{target_day_name}** (`{target_date.strftime('%d.%m.%Y')}`)\n"
      f"📊 Неделя: **{current_week}-я** ({week_type})\n"
      f"{summary_line}"
      f"{status_line}"
      f"━━━━━━━━━━━━━━━━━━━━━━\n"
  ]

  for l in lessons:
    result.append(
        f"🕒 **{l['time']}**\n📚 {l['subject']}\n⏳ *Осталось занятий:"
        f" {l['weeks_left']}*\n"
    )

  result.append(f"💡 *{quote}*")
  return "\n".join(result)


@dp.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "👋 **Привет! Я бот расписания группы 14.6-515.**\n\n"
      "Расписание идеальное: только наши пары, лекции и никакой путаницы!\n"
      "Нажми кнопку **Menu** слева от ввода или пользуйся кнопками ниже 👇",
      parse_mode="Markdown",
      reply_markup=get_main_keyboard(),
  )


@dp.message(Command("note"))
async def cmd_note(message: Message):
  global current_group_note, note_date
  args = message.text.split(maxsplit=1)
  if len(args) < 2:
    await message.answer(
        "⚠️ Напиши текст объявления сразу после команды, например:\n`/note"
        " Завтра встречаемся около ауд. А401`",
        parse_mode="Markdown",
    )
    return

  current_group_note = args[1]
  note_date = get_current_msk_time().date().isoformat()

  await message.answer(
      f"📢 **Внимание! Опубликовано новое объявление для группы"
      f" 14.6-515:**\n\n_{current_group_note}_",
      parse_mode="Markdown",
  )


@dp.message(Command("today"))
async def cmd_today(message: Message):
  now_msk = get_current_msk_time()
  today_name = DAYS_MAP[now_msk.weekday()]
  text = build_schedule_text(today_name, now_msk.date())
  await message.answer(
      text, parse_mode="Markdown", reply_markup=get_main_keyboard()
  )


@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message):
  tomorrow_msk = get_current_msk_time() + datetime.timedelta(days=1)
  tomorrow_name = DAYS_MAP[tomorrow_msk.weekday()]
  text = build_schedule_text(tomorrow_name, tomorrow_msk.date())
  await message.answer(
      text, parse_mode="Markdown", reply_markup=get_main_keyboard()
  )


@dp.message(Command("week"))
async def cmd_week(message: Message):
  days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
  now_msk = get_current_msk_time()
  current_week = get_current_academic_week(now_msk.date())
  week_type = "Знаменатель" if is_even_week(current_week) else "Числитель"

  await message.answer(
      f"📚 **Расписание на всю неделю для группы 14.6-515**\n🗓 *{current_week}-я"
      f" учебная неделя ({week_type})*\n━━━━━━━━━━━━━━━━━━━━━━",
      parse_mode="Markdown",
  )

  for day in days:
    res = build_schedule_text(day, now_msk.date())
    markup = get_main_keyboard() if day == "Суббота" else None
    await message.answer(res, parse_mode="Markdown", reply_markup=markup)
    await asyncio.sleep(0.3)


def generate_calendar_keyboard(year: int, month: int):
  keyboard = []
  months_ru = [
      "Январь",
      "Февраль",
      "Март",
      "Апрель",
      "Май",
      "Июнь",
      "Июль",
      "Август",
      "Сентябрь",
      "Октябрь",
      "Ноябрь",
      "Декабрь",
  ]
  keyboard.append([
      InlineKeyboardButton(
          text=f"📅 {months_ru[month-1]} {year}", callback_data="ignore"
      )
  ])

  keyboard.append([
      InlineKeyboardButton(text="Пн", callback_data="ignore"),
      InlineKeyboardButton(text="Вт", callback_data="ignore"),
      InlineKeyboardButton(text="Ср", callback_data="ignore"),
      InlineKeyboardButton(text="Чт", callback_data="ignore"),
      InlineKeyboardButton(text="Пт", callback_data="ignore"),
      InlineKeyboardButton(text="Сб", callback_data="ignore"),
      InlineKeyboardButton(text="Вс", callback_data="ignore"),
  ])

  import calendar

  cal = calendar.monthcalendar(year, month)
  for week in cal:
    row = []
    for day in week:
      if day == 0:
        row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
      else:
        row.append(
            InlineKeyboardButton(
                text=str(day), callback_data=f"cal_date_{year}_{month}_{day}"
            )
        )
    keyboard.append(row)

  keyboard.append(
      [InlineKeyboardButton(text="« Вернуться в меню", callback_data="btn_today")]
  )
  return InlineKeyboardMarkup(inline_keyboard=keyboard)


@dp.callback_query(F.data == "btn_pick_date")
async def process_pick_date(callback: types.CallbackQuery):
  now = get_current_msk_time()
  kb = generate_calendar_keyboard(now.year, now.month)
  await callback.message.edit_text(
      "🗓 **Выберите дату в календаре:**",
      parse_mode="Markdown",
      reply_markup=kb,
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("cal_date_"))
async def process_calendar_click(callback: types.CallbackQuery):
  parts = callback.data.split("_")
  y, m, d = int(parts[2]), int(parts[3]), int(parts[4])
  selected_date = datetime.date(y, m, d)
  day_name = DAYS_MAP[selected_date.weekday()]

  text = build_schedule_text(day_name, selected_date)
  await callback.message.delete()
  await callback.message.answer(
      text, parse_mode="Markdown", reply_markup=get_main_keyboard()
  )
  await callback.answer()


@dp.callback_query(F.data.in_(["btn_today", "btn_tomorrow", "btn_week", "ignore"]))
async def process_callbacks(callback: types.CallbackQuery):
  if callback.data == "ignore":
    await callback.answer()
    return

  if callback.message:
    try:
      await callback.message.delete()
    except:
      pass

  now_msk = get_current_msk_time()
  if callback.data == "btn_today":
    today_name = DAYS_MAP[now_msk.weekday()]
    text = build_schedule_text(today_name, now_msk.date())
    await callback.message.answer(
        text, parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

  elif callback.data == "btn_tomorrow":
    tomorrow_msk = now_msk + datetime.timedelta(days=1)
    tomorrow_name = DAYS_MAP[tomorrow_msk.weekday()]
    text = build_schedule_text(tomorrow_name, tomorrow_msk.date())
    await callback.message.answer(
        text, parse_mode="Markdown", reply_markup=get_main_keyboard()
    )

  elif callback.data == "btn_week":
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
    current_week = get_current_academic_week(now_msk.date())
    week_type = "Знаменатель" if is_even_week(current_week) else "Числитель"
    await callback.message.answer(
        f"📚 **Расписание на всю неделю**\n🗓 *{current_week}-я неделя"
        f" ({week_type})*,\nгруппа 14.6-515\n━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for day in days:
      res = build_schedule_text(day, now_msk.date())
      markup = get_main_keyboard() if day == "Суббота" else None
      await callback.message.answer(res, parse_mode="Markdown", reply_markup=markup)
      await asyncio.sleep(0.3)

  await callback.answer()


app = FastAPI()


@app.get("/")
def index():
  return "Bot is running with precise group parsing!"


async def run_bot():
  await set_bot_commands(bot)
  await dp.start_polling(bot)


@app.on_event("startup")
async def startup_event():
  asyncio.create_task(run_bot())


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 10000))
  uvicorn.run(app, host="0.0.0.0", port=port)
