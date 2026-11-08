"""Общий код проверки моделей: деление трейн/тест и прогноз со скользящим началом.

Положить в репозиторий как src/models/backtest.py.
Каждая модель — функция fit_predict(train, now), где
  train — строки, ответ для которых уже известен в момент прогноза (признаки + колонка "y"),
  now   — одна строка признаков на месяц прогноза.
Функция возвращает прогноз цены карбамида через h месяцев.
Вся предобработка (масштабирование, заполнение пропусков) делается ВНУТРИ fit_predict
и обучается только на train — так на каждом шаге модель не видит будущего.
"""
import numpy as np
import pandas as pd
from scipy import stats

TEST_START = pd.Timestamp("2023-10-01")
CRISIS = ("2021-07", "2022-12")


def make_table(df, h):
    """Признаки на месяц t и ответ: цена через h месяцев."""
    table = pd.DataFrame(index=df.index)
    table["price"] = df["urea_price"]
    table["gas"] = df["gas_europe"]
    table["gas_change"] = df["gas_europe"].diff()
    table["gas_change_lag1"] = table["gas_change"].shift(1)
    table["price_change"] = df["urea_price"].diff()
    table["y"] = df["urea_price"].shift(-h)
    return table


def split_train_test(table):
    """Делим только по времени: всё до октября 2023 — трейн, дальше — тест."""
    train = table.loc[table.index < TEST_START]
    test = table.loc[table.index >= TEST_START]
    return train, test


def rolling_backtest(table, h, fit_predict, origins, window=None):
    """Прогноз со скользящим началом.

    window=None — расширяющееся окно (учимся на всей истории),
    window=60   — скользящее окно (учимся на последних 60 месяцах).
    """
    rows = []
    for origin in origins:
        if pd.isna(table.loc[origin, "y"]):
            continue
        known = table.loc[: origin - pd.DateOffset(months=h)].dropna()
        if window is not None:
            known = known.iloc[-window:]
        now = table.loc[[origin]]
        forecast = fit_predict(known, now)
        rows.append({
            "origin": origin,
            "fact": table.loc[origin, "y"],
            "naive": table.loc[origin, "price"],
            "forecast": forecast,
        })
    return pd.DataFrame(rows).set_index("origin")


def score(results):
    """Ошибки модели и наивного прогноза; отношение MSE < 1 — модель лучше."""
    out = {}
    calm = (results.index < CRISIS[0]) | (results.index > CRISIS[1])
    for name, part in [("все", results), ("без кризиса", results[calm]), ("кризис", results[~calm])]:
        if len(part) == 0:
            continue
        e_model = part["fact"] - part["forecast"]
        e_naive = part["fact"] - part["naive"]
        out[name] = {
            "прогнозов": len(part),
            "RMSE модели": round(np.sqrt((e_model ** 2).mean()), 1),
            "RMSE наивного": round(np.sqrt((e_naive ** 2).mean()), 1),
            "MSE модель / наивный": round((e_model ** 2).mean() / (e_naive ** 2).mean(), 2),
        }
    return pd.DataFrame(out).T


# ---------- Строгая проверка: k и отбор признаков внутри каждого шага ----------

def make_table_full(prices, h):
    """Таблица для строгой проверки: цена, газ, ответ через h месяцев
    и месячные лог-изменения всех рядов (колонки d_<ряд>) как кандидаты в признаки."""
    table = pd.DataFrame(index=prices.index)
    table["price"] = prices["urea_price"]
    table["gas"] = prices["gas_europe"]
    for col in prices.columns:
        if col != "urea_price":
            table["d_" + col] = np.log(prices[col]).diff()
    table["d_urea_price"] = np.log(prices["urea_price"]).diff()
    table["y"] = prices["urea_price"].shift(-h)
    return table


def estimate_k(known):
    """k = наклон цены карбамида по газу, только по известным строкам."""
    return stats.linregress(known["gas"], known["price"]).slope


def select_features(known, candidates, redundant=0.75):
    """Отбор признаков только по известным строкам:
    1) |корреляция с изменением цены через h месяцев| >= порога случайности 1,96/sqrt(n);
    2) из пары признаков с |r| > redundant оставляем тот, что сильнее связан с целью."""
    target = np.log(known["y"] / known["price"])
    threshold = 1.96 / np.sqrt(len(known) - 2)
    link = known[candidates].corrwith(target)
    passed = link[link.abs() >= threshold].sort_values(key=abs, ascending=False)
    corr = known[passed.index].corr()
    selected = []
    for feature in passed.index:
        if all(abs(corr.loc[feature, s]) <= redundant for s in selected):
            selected.append(feature)
    return selected
