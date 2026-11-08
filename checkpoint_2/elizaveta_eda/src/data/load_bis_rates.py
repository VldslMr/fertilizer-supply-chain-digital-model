"""Ключевые ставки центробанков из выгрузок BIS (data.bis.org → Central bank policy rates).

Файлы CSV, скачанные с сайта BIS, лежат в data/raw/bis_policy_rates/ (по одному на страну).
Запуск из корня репозитория:
    python src/data/load_bis_rates.py
Результат: data/processed/policy_rates_monthly.csv — одна строка на месяц, колонка на страну, % годовых.
"""
from pathlib import Path
import pandas as pd

RAW = Path("data/raw/bis_policy_rates")
OUT = Path("data/processed/policy_rates_monthly.csv")

columns = {}
for file in sorted(RAW.glob("*.csv")):
    data = pd.read_csv(file, skiprows=3)
    country = data["REF_AREA:Reference area"].iloc[0].split(":")[1]
    dates = pd.to_datetime(data["TIME_PERIOD:Period"]).dt.to_period("M").dt.to_timestamp()
    values = pd.to_numeric(data["OBS_VALUE:Value"], errors="coerce")
    columns["rate_" + country.lower().replace(" ", "_")] = pd.Series(values.values, index=dates)
    print(f"{country:15s} {dates.min():%Y-%m} — {dates.max():%Y-%m}")

rates = pd.DataFrame(columns).loc["2010-01":]
rates.index.name = "date"
OUT.parent.mkdir(parents=True, exist_ok=True)
rates.to_csv(OUT)
print(f"\nСохранено: {OUT}, {len(rates)} месяцев")
print(rates.loc["2015":].describe().loc[["min", "50%", "max"]].round(2))
