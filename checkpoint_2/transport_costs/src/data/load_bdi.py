"""Загрузка Baltic Dry Index (BDI) по месяцам и сохранение в parquet.

Что нужно в data/raw/:
    bdi_barchart.csv      — barchart.com, BDI.BI → Price History → Monthly → Download (основной ряд, 2015 – сейчас)
    bdi_monthly_asub.csv  — pxweb.asub.ax, таблица SJ102 (2011–2025, для проверки)

Запуск из корня репозитория:
    python src/data/load_bdi.py

BDI — общий индекс фрахта сухогрузов (1985 = 1000). Карбамид возят на Supramax/Handysize,
их индексы платные, поэтому BDI используем как прокси и калибруем по CIF − FOB из Comtrade.
"""
from pathlib import Path
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed/bdi_monthly.parquet")


def load_barchart(path=RAW / "bdi_barchart.csv"):
    # последняя строка файла — подпись «Downloaded from Barchart...», её пропускаем
    df = pd.read_csv(path, skipfooter=1, engine="python", parse_dates=["Time"])
    df = df.set_index("Time").sort_index()
    df.index.name = "date"
    df = df.rename(columns={"Open": "bdi_open", "High": "bdi_high", "Low": "bdi_low", "Latest": "bdi"})
    # bdi = значение на конец месяца: оно известно в месяце t, поэтому в признаках нет «заглядывания в будущее»
    # bdi_avg = оценка среднего за месяц как (open + close) / 2. Дневных данных у нас нет, только месячные свечи,
    # поэтому это приближение, а не настоящее среднее. Если появится дневной ряд — заменить на df.resample("MS").mean()
    df["bdi_avg"] = (df["bdi_open"] + df["bdi"]) / 2
    df = df[["bdi", "bdi_avg", "bdi_open", "bdi_high", "bdi_low"]]
    # текущий месяц ещё не закончился — выбрасываем
    current = pd.Timestamp.today().to_period("M").to_timestamp()
    return df[df.index < current]


def load_asub(path=RAW / "bdi_monthly_asub.csv"):
    # формат: годы в строках, месяцы в столбцах; значение на первый рабочий день месяца
    df = pd.read_csv(path, skiprows=2)
    df = df.melt(id_vars="year", var_name="month", value_name="bdi_asub")
    df["date"] = pd.to_datetime(df["year"].astype(str) + "-" + df["month"], format="%Y-%B")
    return df.set_index("date")["bdi_asub"].sort_index()


if __name__ == "__main__":
    bdi = load_barchart()
    asub = load_asub()

    # проверка: Open у Barchart = значение ÅSUB (оба — начало месяца)
    both = pd.concat([bdi["bdi_open"], asub], axis=1).dropna()
    same = (both["bdi_open"] == both["bdi_asub"]).mean()
    print(f"Сверка с ÅSUB: совпадает {same:.0%} из {len(both)} общих месяцев")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bdi.to_parquet(OUT)
    print(f"Сохранено: {OUT}  ({len(bdi)} месяцев, {bdi.index.min():%Y-%m} — {bdi.index.max():%Y-%m})")
    print(bdi.tail(3))
