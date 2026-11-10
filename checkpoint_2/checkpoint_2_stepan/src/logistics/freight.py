"""Калькулятор морской доставки карбамида: сколько стоит рейс, сколько нужно судов.

Модель одного маршрута (один завод -> один порт назначения, тайм-чартер):

    T (дни рейса) = погрузка + путь с грузом + выгрузка + путь порожняком + ожидание
    аренда        = T × ставка_в_день
    топливо       = (дни_с_грузом × расход_гружёным + дни_балласт × расход_балласт + дни_в_порту × расход_в_порту) × цена_бункера
    сборы         = 2 захода в порт + Суэц (гружёным полная ставка, балластом — доля)
    страховка     = стоимость_судна × ставка военной страховки (Персидский залив, Красное море)
    $/т           = (аренда + топливо + сборы + страховка) / размер_партии

    судов нужно   S = (Q / партия) × T / 365

Ставка аренды выводится из BDI, цена топлива — из Brent (см. DEFAULTS).
Все параметры по умолчанию взяты из data/reference/ и помечены там источником.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

REF = Path("data/reference")

DEFAULTS = dict(
    # ставка аренды Supramax, $/день = tc_a + tc_b × BDI  (data/reference/charter_rates.csv, 3 точки — грубо)
    tc_a=3790.0,
    tc_b=6.09,
    # цена судового топлива VLSFO, $/т ≈ bunker_k × Brent $/барр. (ОЦЕНКА: 1 т ≈ 7,3 барр. + наценка переработки)
    bunker_k=7.8,
    port_dues=65_000.0,        # $ за заход (оценка, fees.csv)
    load_rate=12_500.0,        # т/сут (оценка)
    discharge_rate=6_500.0,    # т/сут (оценка)
    port_wait_days=3.0,        # дней на рейде (оценка)
    suez_toll=200_000.0,       # $ за проход гружёным (оценка, $150–250 тыс.)
    suez_ballast_share=0.5,    # балластом платят меньше — доля от гружёной ставки (оценка)
    hull_value=20e6,           # $, Supramax ~15 лет (сделка Ipsea Colossus, окт. 2026)
)


@dataclass
class Vessel:
    name: str
    parcel_t: float
    speed_kn: float
    fuel_laden_tpd: float
    fuel_ballast_tpd: float
    fuel_port_tpd: float


def load_vessel(name: str = "Supramax") -> Vessel:
    v = pd.read_csv(REF / "vessel_classes.csv").set_index("vessel_class").loc[name]
    return Vessel(name, v.parcel_t, v.speed_kn, v.fuel_laden_tpd, v.fuel_ballast_tpd, v.fuel_port_tpd)


def load_routes() -> pd.DataFrame:
    return pd.read_csv(REF / "routes.csv")


def tc_rate(bdi: float, p: dict = DEFAULTS) -> float:
    """Ставка тайм-чартера Supramax, $/день, из BDI."""
    return p["tc_a"] + p["tc_b"] * bdi


def bunker_price(brent: float, p: dict = DEFAULTS) -> float:
    """Цена VLSFO, $/т, из Brent $/барр."""
    return p["bunker_k"] * brent


def voyage_cost(distance_nm: float, vessel: Vessel, tc: float, bunker: float,
                via_suez: bool = False, war_gulf_pct: float = 0.0, war_red_sea_pct: float = 0.0,
                extra_wait_days: float = 0.0, p: dict = DEFAULTS) -> dict:
    """Стоимость одного рейса туда-обратно в $/т груза и его длительность.

    war_gulf_pct / war_red_sea_pct — ставка военной страховки в % стоимости судна за рейс
    (передавать только для маршрутов, которые реально проходят эти зоны).
    """
    sea_days = distance_nm / (vessel.speed_kn * 24)                 # в одну сторону
    port_days = (vessel.parcel_t / p["load_rate"] + vessel.parcel_t / p["discharge_rate"]
                 + p["port_wait_days"] + extra_wait_days)
    T = 2 * sea_days + port_days

    hire = T * tc
    fuel = (sea_days * vessel.fuel_laden_tpd + sea_days * vessel.fuel_ballast_tpd
            + port_days * vessel.fuel_port_tpd) * bunker
    fees = 2 * p["port_dues"]
    if via_suez:
        fees += p["suez_toll"] * (1 + p["suez_ballast_share"])
    war = p["hull_value"] * (war_gulf_pct + war_red_sea_pct) / 100

    q = vessel.parcel_t
    return dict(T_days=T, hire=hire / q, fuel=fuel / q, fees=fees / q, war=war / q,
                total=(hire + fuel + fees + war) / q)


def fleet_needed(annual_t: float, T_days: float, vessel: Vessel) -> float:
    """Сколько судов должно постоянно работать на маршруте, чтобы вывезти annual_t за год."""
    return annual_t / vessel.parcel_t * T_days / 365
