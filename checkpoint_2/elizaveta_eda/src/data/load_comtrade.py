# Шаг 5. Загрузка месячной торговли карбамидом (HS 310210) из UN Comtrade
# Запуск из корня репозитория:
#   python src/data/load_comtrade.py
# Работает без ключа (бесплатный preview). В одном запросе — все 8 стран за один месяц.
# Каждый скачанный месяц сразу сохраняется в data/raw/comtrade_months/,
# поэтому если скрипт прервётся, при повторном запуске он продолжит с того же места.
import json
import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
CACHE = Path("data/raw/comtrade_months")
CACHE.mkdir(parents=True, exist_ok=True)

countries = {
    682: "Саудовская Аравия",
    634: "Катар",
    512: "Оман",
    818: "Египет",
    156: "Китай",
    699: "Индия",
    76: "Бразилия",
    842: "США",
}
all_codes = ",".join(str(c) for c in countries)


def ask(period, flow):
    params = {"reporterCode": all_codes, "period": period, "cmdCode": "310210",
              "flowCode": flow, "partnerCode": 0}
    for attempt in range(5):
        try:
            response = requests.get(URL, params=params, timeout=60)
        except requests.exceptions.RequestException:
            print("   обрыв связи, повтор через 15 сек.", flush=True)
            time.sleep(15)
            continue
        if response.status_code == 200:
            return response.json().get("data", [])
        print("   сервер ответил", response.status_code, "- повтор через 15 сек.", flush=True)
        time.sleep(15)
    return None


months = [f"{y}{m:02d}" for y in range(2015, 2027) for m in range(1, 13) if f"{y}{m:02d}" <= "202609"]
for month in months:
    for flow in ["X", "M"]:
        file = CACHE / f"{month}_{flow}.json"
        if file.exists():
            continue
        data = ask(month, flow)
        if data is None:
            print(month, flow, "не скачалось - запустите скрипт ещё раз позже", flush=True)
            continue
        file.write_text(json.dumps(data))
        time.sleep(1)
    print(month, "готово", flush=True)

rows = []
for file in sorted(CACHE.glob("*.json")):
    rows.extend(json.loads(file.read_text()))

trade = pd.DataFrame(rows)
trade["country"] = trade["reporterCode"].map(countries)
keep = ["country", "reporterCode", "period", "flowCode", "netWgt", "qty", "qtyUnitCode",
        "altQty", "altQtyUnitCode", "isNetWgtEstimated", "primaryValue", "cifvalue", "fobvalue"]
trade = trade[[c for c in keep if c in trade.columns]]
trade["date"] = pd.to_datetime(trade["period"].astype(str), format="%Y%m")
# вес в кг: netWgt, а если страна его не указала (0 или пусто) — qty в кг (код единицы 8)
weight_kg = trade["netWgt"].where(trade["netWgt"] > 0)
qty_kg = trade["qty"].where((trade["qtyUnitCode"] == 8) & (trade["qty"] > 0))
trade["tonnes"] = weight_kg.fillna(qty_kg) / 1000
trade["usd_per_tonne"] = trade["primaryValue"] / trade["tonnes"]
trade.to_csv("data/raw/comtrade_urea_monthly.csv", index=False)
print("\nСохранено: data/raw/comtrade_urea_monthly.csv,", len(trade), "строк")
print(trade.groupby(["country", "flowCode"])["date"].agg(["min", "max", "count"]))
