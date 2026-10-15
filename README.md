# Price Scraping: Track Prices Across Retailers

## Description

This repo is the companion code for the tutorial [Price scraping: track prices across retailers](https://www.zenrows.com/blog/price-scraping). It sends the same product's pages at twelve US retailers to [Zenrows Batch](https://docs.zenrows.com/batch/introduction) as one job, reads each price the best way for that store, checks every result, and keeps a price history you can diff run to run.

## Features

- One Batch job across a mixed list of retailer domains, with per-store settings
- Three ways to read a price: [Zenrows Extract](https://docs.zenrows.com/extract/introduction) (`extract=auto`), the page's schema.org JSON-LD, and `css_extractor`. Mixing them is for demonstration: Zenrows Extract handles any site, so you can use `extract=auto` for every store
- Variant matching in JSON-LD, so a page that lists several colors returns the one you watch
- US prices pinned with `proxy_country`
- A validation step that flags any page that loads without a price
- A CSV price history and a diff between the latest two runs
- Retrying only the URLs that failed, keeping the rest of the run

## Prerequisites

- Python 3.9+
- A Zenrows API key: [create a Zenrows account](https://app.zenrows.com/register)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/ZenRows/price-scraping-zenrows-batch.git
   cd price-scraping-zenrows-batch
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The scripts read your key from the `ZENROWS_API_KEY` environment variable:

```bash
export ZENROWS_API_KEY=your_api_key   # Windows (PowerShell): $env:ZENROWS_API_KEY="your_api_key"
```

Edit `watchlist.csv` to watch your own products: one row per product page, with your product ID, the variant (color) and the URL.

## Usage

```bash
python monitor.py                # first run: creates the job, prints every store's price, writes prices.csv
python monitor.py JOB_ID         # later runs: runs the same job again and appends to prices.csv
python changes.py                # compares the latest two runs in prices.csv
python retry_failed.py JOB_ID    # retries only the URLs that failed in the latest run
```

## Project structure

```
.
├── watchlist.csv     # The product pages to watch
├── monitor.py        # Submit or rerun the job, read and validate every price, save the run
├── changes.py        # Diff the latest two runs
├── retry_failed.py   # POST /jobs/{id}/rerun?status=failed
├── requirements.txt
├── .gitignore
└── LICENSE
```

## Learn more

- [Build a price monitor](https://docs.zenrows.com/academy/build-price-monitoring)
- [Use different settings for each URL in one job](https://docs.zenrows.com/academy/batch/per-task-settings)
- [Schedule web scraping without a cron server](https://www.zenrows.com/blog/schedule-web-scraping)
