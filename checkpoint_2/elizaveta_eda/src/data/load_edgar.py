"""Оборотный капитал производителей азотных удобрений из отчётности SEC (EDGAR).

Считаем по кварталам, сколько дней деньги «заморожены» в цикле:
  DSO — дни до оплаты покупателем   = дебиторская задолженность / выручка за квартал × 91
  DIO — дни хранения запасов        = запасы / себестоимость за квартал × 91
  DPO — дни отсрочки поставщикам    = кредиторская задолженность / себестоимость за квартал × 91
  цикл = DSO + DIO − DPO

Запуск из корня репозитория:
    python src/data/load_edgar.py
SEC требует, чтобы в запросе были имя и email того, кто скачивает:
впишите свои данные в USER_AGENT ниже перед запуском.
Если SEC отказывает (ошибка 403), скачайте файлы в браузере и положите в data/raw/edgar/:
  https://data.sec.gov/api/xbrl/companyfacts/CIK0001324404.json  (CF Industries)
  https://data.sec.gov/api/xbrl/companyfacts/CIK0001425292.json  (CVR Partners)
  https://data.sec.gov/api/xbrl/companyfacts/CIK0000060714.json  (LSB Industries)
Скрипт сначала ищет эти файлы и берёт данные из них.
Результат: data/processed/working_capital_quarterly.csv
"""
import json
from pathlib import Path
import time

import pandas as pd
import requests

USER_AGENT = "Имя Фамилия your_email@example.com"   # <- впишите своё имя и email
OUT = Path("data/processed/working_capital_quarterly.csv")

COMPANIES = {
    "CF Industries": 1324404,     # крупнейший производитель азотных удобрений в США
    "CVR Partners": 1425292,      # производитель аммиака и UAN в США
    "LSB Industries": 60714,      # производитель аммиака и азотных удобрений в США
}

# в отчётах компании пишут одно и то же под разными тегами — пробуем по очереди
TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "receivables": ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
    "inventory": ["InventoryNet"],
    "payables": ["AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"],
    # авансы покупателей (предоплата за удобрения)
    "advances": ["DeferredRevenue", "ContractWithCustomerLiabilityCurrent", "ContractWithCustomerLiability"],
    # процентные расходы и долг — чтобы посчитать реальную ставку, по которой компания занимает
    "interest": ["InterestExpense", "InterestExpenseDebt", "InterestPaidNet"],
    "debt": ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
}
FLOWS = {"revenue", "cogs", "interest"}   # показатели за период; остальные — на дату баланса


def quarterly(facts, tag, is_flow):
    """Ряд по кварталам из фактов XBRL: ключ — конец квартала."""
    units = facts.get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
    if not units:
        return None
    df = pd.DataFrame(units)
    df = df[df["form"].isin(["10-Q", "10-K"])].copy()
    df["end"] = pd.to_datetime(df["end"])
    if is_flow:
        df["start"] = pd.to_datetime(df["start"])
        df["days"] = (df["end"] - df["start"]).dt.days
        q = df[df["days"].between(80, 100)].drop_duplicates("end", keep="last").set_index("end")["val"]
        # квартал из нарастающего итога: (9 мес.) − (6 мес.), (год) − (9 мес.) и т. д.
        ytd = df[df["days"] > 100].drop_duplicates(["start", "end"], keep="last")
        for start, part in ytd.groupby("start"):
            part = part.sort_values("end")
            prev_end, prev_val = start - pd.Timedelta(days=1), 0.0
            first_q = q[(q.index > start) & (q.index <= start + pd.Timedelta(days=100))]
            if len(first_q):
                prev_end, prev_val = first_q.index[0], first_q.iloc[0]
            for end, val in zip(part["end"], part["val"]):
                if 80 <= (end - prev_end).days <= 100 and end not in q.index:
                    q.loc[end] = val - prev_val
                if 80 <= (end - prev_end).days <= 100 or (end - start).days <= 100:
                    prev_end, prev_val = end, val
        return q.sort_index()
    return df.drop_duplicates("end", keep="last").set_index("end")["val"].sort_index()


rows = []
for company, cik in COMPANIES.items():
    local = Path(f"data/raw/edgar/CIK{cik:010d}.json")
    if local.exists():
        facts = json.loads(local.read_text())["facts"]
        print(company, "- из файла", local)
    else:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate", "Host": "data.sec.gov"}
        response = requests.get(url, headers=headers, timeout=60)
        if response.status_code != 200:
            print(company, "ошибка", response.status_code, "- скачайте файл вручную в", local)
            continue
        facts = response.json()["facts"]
    series = {}
    for name, tags in TAGS.items():
        # основной тег — тот, где больше всего кварталов с 2014 года;
        # пропущенные кварталы дополняем из остальных тегов
        found = {}
        for tag in tags:
            s = quarterly(facts, tag, name in FLOWS)
            if s is not None:
                found[tag] = s[s.index >= "2014-01-01"]
        if not found:
            continue
        order = sorted(found, key=lambda t: len(found[t]), reverse=True)
        combined = found[order[0]]
        for tag in order[1:]:
            combined = combined.combine_first(found[tag])
        series[name] = combined
        print(f"{company:15s} {name:12s} <- {' + '.join(order)} ({len(combined)} кварталов)")
    table = pd.DataFrame(series)
    table = table[table.index >= "2014-01-01"]
    table = table.reindex(columns=list(TAGS))
    table["dso_days"] = table["receivables"] / table["revenue"] * 91
    table["dio_days"] = table["inventory"] / table["cogs"] * 91
    if True:
        table["dpo_days"] = table["payables"] / table["cogs"] * 91
        table["cycle_days"] = table["dso_days"] + table["dio_days"] - table["dpo_days"]
    table["advance_days"] = table["advances"] / table["revenue"] * 91
    table["working_capital_usd"] = table["receivables"] + table["inventory"] - table["payables"] - table["advances"].fillna(0)
    table["gross_margin_pct"] = (table["revenue"] - table["cogs"]) / table["revenue"] * 100
    table["debt_rate_pct"] = table["interest"] * 4 / table["debt"] * 100
    table["company"] = company
    rows.append(table)
    time.sleep(1)

if not rows:
    raise SystemExit("Ни одна компания не скачалась — пришлите текст ответа сервера выше")
result = pd.concat(rows)
result.index.name = "quarter_end"
OUT.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(OUT)
print(f"\nСохранено: {OUT}")
print(result.groupby("company")[["dso_days", "dio_days", "dpo_days", "advance_days", "gross_margin_pct", "debt_rate_pct"]].median().round(1))
