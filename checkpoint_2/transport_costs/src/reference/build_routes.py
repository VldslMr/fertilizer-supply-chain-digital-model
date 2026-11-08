"""Справочник маршрутов: морские расстояния между портами экспорта и импорта карбамида.

Расстояния считает библиотека searoute (морская сеть Eurostat MARNET), поэтому их можно пересчитать.
Запуск из корня репозитория:
    pip install searoute
    python src/reference/build_routes.py

Сценарии:
    normal      — кратчайший путь (через Суэц и Баб-эль-Мандеб, если так короче)
    no_red_sea  — Суэц и Баб-эль-Мандеб закрыты (2024: хуситы) -> путь вокруг мыса Доброй Надежды
Закрытие Ормуза обходом не решается: порты Катара и Восточной Аравии внутри залива,
поэтому для них флаг via_hormuz = True означает «поток блокируется» (2026).
"""
from pathlib import Path
import pandas as pd
import searoute as sr

OUT = Path("data/reference/routes.csv")
KNOTS = 12.5   # эксплуатационная скорость Supramax, узлов (см. vessel_classes.csv)

PORTS = {  # (долгота, широта)
    "Mesaieed (QA)": (51.57, 24.99),     # QAFCO
    "Jubail (SA)": (49.66, 27.02),       # SABIC Agri-Nutrients
    "Sur (OM)": (59.53, 22.57),          # OMIFCO — снаружи Ормуза!
    "Damietta (EG)": (31.77, 31.47),
    "Ust-Luga (RU)": (28.40, 59.68),
    "Paranagua (BR)": (-48.51, -25.50),
    "Kandla (IN)": (70.22, 23.00),
    "New Orleans (US)": (-89.40, 28.90),
    "Geelong (AU)": (144.36, -38.14),
    "Antwerp (BE)": (4.40, 51.23),
    "Laem Chabang (TH)": (100.88, 13.08),
}
GULF = ["Mesaieed (QA)", "Jubail (SA)", "Sur (OM)"]
DEST = ["Paranagua (BR)", "Kandla (IN)", "New Orleans (US)", "Geelong (AU)", "Antwerp (BE)", "Laem Chabang (TH)"]
PAIRS = [(o, d) for o in GULF for d in DEST] \
      + [("Damietta (EG)", d) for d in ["Antwerp (BE)", "New Orleans (US)", "Paranagua (BR)", "Kandla (IN)"]] \
      + [("Ust-Luga (RU)", d) for d in ["Antwerp (BE)", "New Orleans (US)", "Paranagua (BR)", "Kandla (IN)"]]
SCENARIOS = {"normal": ["northwest"], "no_red_sea": ["northwest", "suez", "babalmandab"]}

rows = []
for o, d in PAIRS:
    for scen, restr in SCENARIOS.items():
        f = sr.searoute(PORTS[o], PORTS[d], units="naut", restrictions=restr, return_passages=True)
        ps = f.properties.get("traversed_passages", [])
        nm = round(f.properties["length"])
        rows.append(dict(origin=o, dest=d, scenario=scen, distance_nm=nm,
                         sea_days_one_way=round(nm / (KNOTS * 24), 1),
                         via_hormuz="ormuz" in ps, via_suez="suez" in ps,
                         via_bab_el_mandeb="babalmandab" in ps, via_cape="south_africa" in ps,
                         passages=";".join(ps)))

df = pd.DataFrame(rows)
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
print(f"Сохранено: {OUT} ({len(df)} строк)")
print(df.pivot_table(index=["origin", "dest"], columns="scenario", values="distance_nm").to_string())
