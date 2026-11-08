# PortWatch: Ормуз и Баб-эль-Мандеб — пакет к чекпоинту 2

## Состав пакета

- `notebooks/03_eda_portwatch_checkpoint2.ipynb` — анализ PortWatch, включая статистики, пропуски, выбросы, корреляции, pairplot и выводы; **только train (2019–2024)**.
- `scripts/download_portwatch.py` — загрузчик данных PortWatch (отдельный скрипт, не обязателен для просмотра готового EDA).
- `data/raw/portwatch_hormuz_bab_daily.csv` — ежедневные данные по двум проливам до 2026-11-01.
- `data/processed/portwatch_hormuz_bab_monthly.csv` — 138 месяцев с 2015-04 по 2026-09, со всеми типами судов.
- `data/processed/portwatch_transport_features_monthly.csv` — компактная версия ключевых признаков.
- `reports/portwatch/EDA_REVIEW.md` — итоговый текст и графики; CSV-таблицы проверок рядом.

## Проверка соответствия чекпоинту

| Требование | Наша реализация |
|---|---|
| Описательные статистики | `statistics_train.csv` + ноутбук |
| Пропуски, нули и ошибки | таблицы `quality_checks`, `missing_values`, `zero_values`, `suspicious_zero_capacity` |
| Выбросы | IQR, даты и пороги в CSV |
| Распределения и сегменты | `distributions_train.png`, `ship_types_share_train.png` |
| Корреляционные матрицы | Pearson/Spearman, график и CSV |
| Pairplot | `pairplot_train.png` |
| Тренды и сезонность | `traffic_trends_train.png`, `seasonality_train.png` |
| Выводы | `reports/portwatch/EDA_REVIEW.md` |
| Признаки для объединения с Pink Sheet | `data/processed/` |
| Целевая переменная карбамида | отсутствует в PortWatch; нужна итоговая объединённая таблица |


