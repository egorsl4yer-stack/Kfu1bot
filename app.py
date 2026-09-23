def get_schedule_data_for_day(target_day_name: str, target_date=None):
  if not os.path.exists(EXCEL_FILE):
    return [], f"❌ **Ошибка:** файл `{EXCEL_FILE}` не найден на сервере!"

  try:
    df = pd.read_excel(EXCEL_FILE, sheet_name="2 курс ", header=None)

    # 1. Находим точную колонку группы 14.6-515
    col_idx = None
    for c in range(df.shape[1]):
      if "14.6-515" in str(df.iloc[7, c]):
        col_idx = c
        break

    if col_idx is None:
      return [], "⚠️ Не удалось найти группу 14.6-515 в таблице."

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
        # Ищем предмет в колонке группы ИЛИ в соседней колонке лекций (чуть левее/правее от группы)
        subj_val = None
        for check_col in [
            col_idx,
            col_idx - 1,
            col_idx - 2,
            col_idx + 1,
        ]:  # Проверяем группу и колонки рядом
          if 0 <= check_col < df.shape[1]:
            val = df.iloc[r, check_col]
            if (
                pd.notna(val)
                and str(val).strip() != "nan"
                and str(val).strip() != ""
            ):
              v_str = str(val).strip()
              # Если это чужой семинар другой группы — жестко пропускаем
              if (
                  "14.6-" in v_str
                  and "14.6-515" not in v_str
                  and "лекция" not in v_str.lower()
              ):
                continue
              # Если это лекция или наш семинар — берем
              if (
                  "лекция" in v_str.lower()
                  or check_col == col_idx
                  or "14.6-515" in v_str
              ):
                subj_val = val
                break

        if subj_val is not None:
          subj_str = str(subj_val)
          if is_subject_active(subj_str, current_week):
            clean_subj = clean_subject_text(subj_str)
            if is_valid_subject(clean_subj):
              weeks_left = get_weeks_left(subj_str, current_week)
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
                  l["time"] == time_str and l["subject"] == clean_subj
                  for l in lessons
              ):
                lessons.append(lesson_info)

    return lessons, None
  except Exception as e:
    return [], f"⚠️ Ошибка при обработке расписания: {e}"
