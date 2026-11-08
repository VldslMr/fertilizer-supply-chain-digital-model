"""Загрузка цен World Bank Pink Sheet и сохранение в parquet.

Запуск из корня репозитория:
    python src/data/load_pink_sheet.py
"""
from pathlib import Path                     # удобная работа с путями
import pandas as pd                          # таблицы

RAW = Path("data/raw/CMO-Historical-Data-Monthly.xlsx")      # откуда читаем
OUT = Path("data/processed/prices_monthly.parquet")          # куда сохраняем

# наше имя -> начало заголовка колонки в файле (в нижнем регистре)
COLUMNS = {
    "urea_price": "urea",                    # карбамид, $/т
    "gas_europe": "natural gas, europe",     # газ Европа (TTF с апреля 2015), $/млн БТЕ
    "gas_us": "natural gas, us",             # газ США (Henry Hub), $/млн БТЕ
    "lng_japan": "liquefied natural gas",    # СПГ Японии, $/млн БТЕ
    "brent": "crude oil, brent",             # нефть Brent, $/баррель
    "coal_aus": "coal, australian",          # уголь Newcastle, $/т
    "maize": "maize",                        # кукуруза US Gulf, $/т
}


def load(raw_path=RAW):
    # 1. Читаем лист целиком, без заголовков: строку с названиями найдём сами
    raw = pd.read_excel(raw_path, sheet_name="Monthly Prices", header=None)

    # 2. Строка с названиями товаров — та, где есть слово "Urea"
    is_header = raw.apply(lambda row: row.astype(str).str.contains("Urea", case=False).any(), axis=1)
    header_row = raw.index[is_header][0]
    names = raw.iloc[header_row].fillna("").astype(str).str.strip().str.lower()

    # 3. Находим номер колонки для каждого нашего имени и печатаем для проверки
    col_index = {}
    for our_name, start in COLUMNS.items():
        found = [i for i, n in enumerate(names) if n.startswith(start)]
        if not found:
            raise ValueError(f"Не нашла колонку для {our_name}: проверьте заголовки в файле")
        col_index[our_name] = found[0]
        print(f"{our_name:11s} <- {raw.iloc[header_row, found[0]]!r}")

    # 4. Данные начинаются через строку после названий (следующая строка — единицы измерения)
    data = raw.iloc[header_row + 1:]

    # 5. Даты вида "2020M01" -> 2020-01-01; строка единиц станет пустой датой (NaT)
    dates = pd.to_datetime(data[0].fillna("").astype(str).str.replace("M", "-"),
                           format="%Y-%m", errors="coerce")

    # 6. Числа; пропуски в файле обозначены "…" — они станут NaN
    df = pd.DataFrame({name: pd.to_numeric(data[i], errors="coerce")
                       for name, i in col_index.items()})
    df.index = dates
    df = df[df.index.notna()].sort_index()   # убираем строки без даты, сортируем по времени
    df.index.name = "date"
    return df


if __name__ == "__main__":
    df = load()
    OUT.parent.mkdir(parents=True, exist_ok=True)    # создаём data/processed, если её нет
    df.to_parquet(OUT)
    print(f"\nСохранено: {OUT}  ({len(df)} месяцев, {df.index.min():%Y-%m} — {df.index.max():%Y-%m})")
    print(df.tail(3))                                 # последние месяцы — сверить с Excel
