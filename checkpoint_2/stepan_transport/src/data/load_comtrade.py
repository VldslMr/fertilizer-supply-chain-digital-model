"""Загрузка UN Comtrade (карбамид, HS 310210) и сборка таблицы торговых потоков.

Что нужно в data/raw/ (выгрузка comtradeplus.un.org, Annual, HS 310210, 2015–2025,
Reporters = All, Partners = All):
    comtrade_urea_exports.csv   — Trade flow = Export
    comtrade_urea_imports.csv   — Trade flow = Import

Запуск из корня репозитория:
    python src/data/load_comtrade.py

На выходе (data/processed/):
    trade_flows.parquet        — потоки «страна-экспортёр -> страна-импортёр -> год»
    exports_by_origin.parquet  — экспорт каждой страны за год: по своим данным и по зеркальным
    freight_gap.parquet        — медиана (CIF − FOB) по маршрутам за год, $/т — оценка стоимости доставки
"""
from pathlib import Path
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")


def read(name):
    # index_col=False — в файлах Comtrade лишняя запятая в конце строки, без этого колонки сдвигаются
    df = pd.read_csv(RAW / name, encoding="utf-8-sig", index_col=False)
    df = df[df["partnerDesc"] != "World"]                    # итог «весь мир» посчитаем сами
    df["t"] = df["netWgt"] / 1000                            # кг -> тонны
    return df


def build():
    ex = read("comtrade_urea_exports.csv")
    im = read("comtrade_urea_imports.csv")

    # Экспорт: отчитывается страна-отправитель, партнёр — получатель. Стоимость FOB (без доставки).
    ex = ex.rename(columns={"reporterDesc": "origin", "partnerDesc": "dest", "refYear": "year"})
    ex = ex.groupby(["year", "origin", "dest"], as_index=False).agg(t_exp=("t", "sum"), fob_usd=("fobvalue", "sum"))

    # Импорт: отчитывается страна-получатель, партнёр — отправитель. Стоимость CIF (с доставкой и страховкой).
    im = im.rename(columns={"reporterDesc": "dest", "partnerDesc": "origin", "refYear": "year"})
    im = im.groupby(["year", "origin", "dest"], as_index=False).agg(t_imp=("t", "sum"), cif_usd=("cifvalue", "sum"))

    # Один поток видят обе стороны. Склеиваем.
    flows = ex.merge(im, on=["year", "origin", "dest"], how="outer")
    # Лучший объём: по данным импортёра (Катар, Россия с 2022, Иран сами не отчитываются), иначе экспортёра
    flows["t"] = flows["t_imp"].where(flows["t_imp"] > 0, flows["t_exp"])
    flows["fob_per_t"] = flows["fob_usd"] / flows["t_exp"]
    flows["cif_per_t"] = flows["cif_usd"] / flows["t_imp"]

    # Разница CIF − FOB ≈ фрахт + страховка. Берём только надёжные пары:
    # поток > 20 тыс. т и веса у двух сторон расходятся не больше чем на 30 %.
    ok = (flows["t_imp"] > 20_000) & ((flows["t_exp"] / flows["t_imp"] - 1).abs() < 0.3) \
         & (flows["fob_usd"] > 0) & (flows["cif_usd"] > 0)
    flows["freight_gap"] = (flows["cif_per_t"] - flows["fob_per_t"]).where(ok)

    # Экспорт по странам: своя отчётность против зеркальной (сумма импорта партнёров)
    by_origin = flows.groupby(["year", "origin"]).agg(
        reported_t=("t_exp", "sum"), mirror_t=("t_imp", "sum")).reset_index()

    # Медиана по маршрутам — отдельные маршруты шумные (поставка в декабре приходит в январе и т. п.)
    gap = flows.groupby("year")["freight_gap"].agg(["median", "count"]).rename(
        columns={"median": "freight_gap_median", "count": "n_routes"})
    return flows, by_origin, gap


if __name__ == "__main__":
    flows, by_origin, gap = build()
    OUT.mkdir(parents=True, exist_ok=True)
    flows.to_parquet(OUT / "trade_flows.parquet", index=False)
    by_origin.to_parquet(OUT / "exports_by_origin.parquet", index=False)
    gap.to_parquet(OUT / "freight_gap.parquet")
    print(f"trade_flows: {len(flows)} строк, {flows['year'].min()}–{flows['year'].max()}")
    print("\nМедиана CIF − FOB по маршрутам, $/т:")
    print(gap.round(1))
