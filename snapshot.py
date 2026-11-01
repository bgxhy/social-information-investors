"""Amazon product snapshot (run LOCALLY, once a day, low frequency).
Parsing is fragile: Amazon changes page layout and may show a captcha."""
import re, time, random, datetime as dt
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "snapshots.csv"
H = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
     "Accept-Language": "en-US,en;q=0.9"}


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    if "validateCaptcha" in html or "Enter the characters you see" in html:
        return None

    def t(sel):
        el = soup.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    text = soup.get_text(" ", strip=True)
    m = re.search(r"Best Sellers Rank:?\s*#?([\d,]+)\s+in\s+([^#(]+)", text)
    return {"title": t("#productTitle")[:80],
            "price": t("span.a-price span.a-offscreen"),
            "rating": t("#acrPopover"),
            "reviews": t("#acrCustomerReviewText"),
            "availability": t("#availability")[:60],
            "rank": m.group(1).replace(",", "") if m else "",
            "rank_cat": m.group(2).strip() if m else ""}


def main():
    items = pd.read_csv(ROOT / "asins.csv")
    rows, blocked = [], 0
    for r in items.itertuples():
        time.sleep(random.uniform(8, 20))
        try:
            resp = requests.get(f"https://www.amazon.com/dp/{r.asin}", headers=H, timeout=20)
            d = parse(resp.text) if resp.status_code == 200 else None
        except Exception:
            d = None
        row = {"date": dt.date.today().isoformat(), "brand": r.brand, "asin": r.asin}
        if d is None:
            row["status"] = "blocked"
            blocked += 1
        else:
            row.update(d)
            row["status"] = "ok"
        rows.append(row)
        print(r.brand, r.asin, row["status"])
        if blocked >= 3:
            print("3 blocks in a row-ish, stopping; fall back to manual weekly records")
            break
    pd.DataFrame(rows).to_csv(OUT, mode="a", header=not OUT.exists(), index=False)


if __name__ == "__main__":
    main()
