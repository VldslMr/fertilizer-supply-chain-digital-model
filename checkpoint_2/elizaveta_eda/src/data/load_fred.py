"""Ставки, спреды и валютные курсы из FRED (Федеральный резервный банк Сент-Луиса).

Запуск из корня репозитория:
    python src/data/load_fred.py
Ключ не нужен. Результат: data/processed/fred_monthly.csv — одна строка на месяц.
"""
from pathlib import Path
import pandas as pd

OUT = Path("data/processed/fred_monthly.csv")

SERIES = {
    "fed_rate": "FEDFUNDS",              # ставка ФРС, % годовых (месячная)
    "sofr": "SOFR",                      # рыночная ставка долларового фондирования, % (дневная, с 2018)
    "spread_us_bbb": "BAMLC0A4CBBB",     # спред облигаций компаний США рейтинга BBB, п.п. (дневной)
    "spread_em_corp": "BAMLEMCBPIOAS",   # спред облигаций компаний развивающихся стран, п.п. (дневной)
    "usd_index": "TWEXBGSMTH",           # индекс доллара к широкой корзине валют (месячный)
    "inr_per_usd": "EXINUS",             # рупий за доллар (месячный)
    "brl_per_usd": "EXBZUS",             # реалов за доллар (месячный)
}

columns = {}
for name, code in SERIES.items():
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
    raw = pd.read_csv(url, index_col=0, parse_dates=True)
    values = pd.to_numeric(raw.iloc[:, 0], errors="coerce")
    columns[name] = values.resample("MS").mean()
    print(f"{name:15s} {code:15s} {values.first_valid_index():%Y-%m} — {values.last_valid_index():%Y-%m}")

fred = pd.DataFrame(columns).loc["2010-01":]
fred.index.name = "date"
OUT.parent.mkdir(parents=True, exist_ok=True)
fred.to_csv(OUT)
print(f"\nСохранено: {OUT}, {len(fred)} месяцев")
print(fred.tail(3).round(2))
