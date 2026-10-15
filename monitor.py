import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

API = "https://async.api.zenrows.com/v1"
HEADERS = {"X-API-Key": os.environ["ZENROWS_API_KEY"]}

# Scraping settings per retailer. Most stores work with Adaptive Stealth Mode
# alone; the extras say how to read the price there. Stores not listed get AUTO
# and come back as HTML, where the price is read from schema.org JSON-LD.
AUTO = {"mode": "auto"}


def css(selector):
    return {**AUTO, "css_extractor": json.dumps({"price": selector})}


RETAILERS = {
    "www.bestbuy.com": {**AUTO, "extract": "auto"},
    "www.walmart.com": {**AUTO, "extract": "auto"},
    "www.ebay.com": {**AUTO, "extract": "auto"},
    "www.amazon.com": css("#corePrice_feature_div .a-offscreen"),
    "www.newegg.com": css(".product-buy-box .price-current_2026"),
    "www.abt.com": css(".pricing-item-price"),
    "www.adorama.com": {**AUTO, "wait_for": "[data-test-id='product-price-container']"},
    "www.qvc.com": {"js_render": "true", "premium_proxy": "true"},
}


def load_watchlist(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build_tasks(watchlist):
    tasks = []
    for row in watchlist:
        domain = urlparse(row["url"]).netloc
        # external_id allows letters, digits, ".", "_" and "-" (128 chars max)
        task = {"url": row["url"], "external_id": f'{row["sku"]}__{domain}'}
        task["zenrows_params"] = RETAILERS.get(domain, AUTO)
        tasks.append(task)
    return tasks


def submit(tasks, name="price-watch"):
    job = {
        "type": "regular",
        "status": "closed",
        "name": name,
        "zenrows_params": {"proxy_country": "us"},  # US prices, in dollars
        "tasks": tasks,
    }
    r = requests.post(f"{API}/jobs", headers=HEADERS, json=job, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"{r.status_code}: {r.text}")
    return r.json()["job_id"]


def latest_run(job_id):
    return requests.get(f"{API}/jobs/{job_id}", headers=HEADERS, timeout=60).json()["latest_run"]


def wait(job_id, after=0, every=15):
    """Waits for a run newer than run number `after` to finish, and returns it."""
    while True:
        run = latest_run(job_id)
        if run["run_sequence"] > after and run["status"] in ("completed", "failed", "stopped"):
            return run
        time.sleep(every)


def results(job_id):
    """All results of the job's latest run, following the pagination cursor."""
    rows, cursor = [], None
    while True:
        params = {"status": "all", "cursor": cursor} if cursor else {"status": "all"}
        page = requests.get(f"{API}/jobs/{job_id}/results",
                            headers=HEADERS, params=params, timeout=60).json()
        rows += page["results"]
        cursor = page.get("next_cursor")
        if not cursor:
            return rows


class JsonLd(HTMLParser):
    """Collects every <script type="application/ld+json"> block on a page."""

    def __init__(self):
        super().__init__()
        self.blocks, self._inside = [], False

    def handle_starttag(self, tag, attrs):
        self._inside = tag == "script" and ("type", "application/ld+json") in attrs

    def handle_endtag(self, tag):
        self._inside = False

    def handle_data(self, data):
        if self._inside and data.strip():
            try:
                self.blocks.append(json.loads(data))
            except ValueError:
                pass


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def price_from_jsonld(page, color):
    parser = JsonLd()
    parser.feed(page)
    offers = []
    for node in walk(parser.blocks):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Product" in types and node.get("offers"):
            found = node["offers"]
            offers += found if isinstance(found, list) else [found]
    # A product page can list one offer per variant. Prefer the one in our color.
    for offer in offers:
        item = offer.get("itemOffered") or {}
        if isinstance(item, dict) and str(item.get("color", "")).lower() == color.lower():
            return offer.get("price"), offer.get("priceCurrency")
    for offer in offers:
        if offer.get("price") is not None:
            return offer.get("price"), offer.get("priceCurrency")
    return None, None


def parse_price(value):
    """'$1,299.99', 'Your Price: $242.89', 228 or '298.00' -> 1299.99, 242.89, 228.0, 298.0"""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    return float(match.group().replace(",", "")) if match else None


def read_price(row, body, color):
    """Returns (price, currency, method, note) for one successful result."""
    try:
        data = json.loads(body)
    except ValueError:
        price, currency = price_from_jsonld(body, color)
        return parse_price(price), currency, "json-ld", None
    if "parsed" in data:  # Zenrows Extract
        parsed = data["parsed"]
        pricing = parsed.get("pricing") or {}
        title = json.dumps(parsed.get("item") or parsed.get("product") or {}).lower()
        note = "refurbished listing" if "refurbished" in title else None
        currency = pricing.get("currency")
        if not currency or len(currency) != 3:  # some sites give "$228.00" here
            currency = "USD"
        return parse_price(pricing.get("current_price")), currency, "extract", note
    return parse_price(data.get("price")), "USD", "css", None


def collect(job_id, run, watchlist):
    color = {r["url"]: r["color"] for r in watchlist}
    out = []
    for row in results(job_id):
        sku, domain = row["external_id"].split("__")
        record = {"run_id": run["run_id"], "run_sequence": run["run_sequence"],
                  "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "sku": sku, "retailer": domain, "status": row["status"],
                  "price": None, "currency": None, "method": None, "note": None}
        if row["status"] == "successful":
            body = requests.get(row["result_url"], timeout=120).text
            price, currency, method, note = read_price(row, body, color[row["url"]])
            record.update(price=price, currency=currency, method=method, note=note)
            if price is None:
                record["note"] = "no price found on the page"
        else:
            error = row.get("error") or {}
            record["note"] = f'{error.get("code")} (HTTP {error.get("status")})'
        out.append(record)
    return out


def save(records, path="prices.csv"):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        if new:
            writer.writeheader()
        writer.writerows(records)


def rerun(job_id):
    r = requests.post(f"{API}/jobs/{job_id}/rerun", headers=HEADERS, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"{r.status_code}: {r.text}")


if __name__ == "__main__":
    # First time: python monitor.py           -> creates the job
    # After that: python monitor.py JOB_ID    -> runs the same job again
    watchlist = load_watchlist("watchlist.csv")
    if len(sys.argv) > 1:
        job_id = sys.argv[1]
        previous = latest_run(job_id)["run_sequence"]
        rerun(job_id)
        run = wait(job_id, after=previous)
    else:
        job_id = submit(build_tasks(watchlist))
        run = wait(job_id)
    print(f'job {job_id}, run {run["run_sequence"]}: {run["stats"]}')
    records = collect(job_id, run, watchlist)
    save(records)
    for r in sorted(records, key=lambda r: (r["price"] is None, r["price"] or 0)):
        price = f'{r["price"]:.2f} {r["currency"]}' if r["price"] is not None else "-"
        print(f'{r["retailer"]:<26} {r["status"]:<11} {price:<12} {r["method"] or "":<8} {r["note"] or ""}')
