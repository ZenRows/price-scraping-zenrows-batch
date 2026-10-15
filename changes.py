import csv
from collections import defaultdict

rows = list(csv.DictReader(open("prices.csv")))
runs = sorted({int(r["run_sequence"]) for r in rows})
if len(runs) < 2:
    raise SystemExit("need at least two runs")
before, after = runs[-2], runs[-1]

price = defaultdict(dict)
for r in rows:
    if r["price"]:
        price[int(r["run_sequence"])][(r["sku"], r["retailer"])] = float(r["price"])

for key in sorted(set(price[before]) | set(price[after])):
    old, new = price[before].get(key), price[after].get(key)
    if old is None or new is None:
        print(f"{key[1]:<26} {old} -> {new}  (missing in one run, check before alerting)")
    elif abs(new - old) >= 0.01:
        print(f"{key[1]:<26} {old:.2f} -> {new:.2f}  ({(new - old) / old:+.1%})")
print(f"compared run {before} with run {after}: {len(price[after])} prices in the latest run")
