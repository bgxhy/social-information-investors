"""Alt-data radar V1: Google Trends (web + shopping) anomaly -> WeCom push."""
import os, time, random, datetime as dt
from pathlib import Path
from urllib.parse import quote
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
Z_T = float(os.getenv("Z_THRESHOLD", "2.5"))
RECENT, BASE = 7, 90
COOLDOWN_DAYS = 7


def zscore(s: pd.Series, recent=RECENT, base=BASE):
    """Point-in-time z: recent mean vs the baseline window BEFORE it."""
    s = s.dropna()
    if len(s) < recent + int(base * 0.8):
        return None
    rec = s.iloc[-recent:]
    b = s.iloc[-(recent + base):-recent]
    if (b > 0).mean() < 0.7:          # too little search volume -> unreliable
        return None
    sd = max(b.std(ddof=1), 1.0)      # floor: values are 0-100 integers
    return {"z": float((rec.mean() - b.mean()) / sd),
            "ma7": float(rec.mean()), "base": float(b.mean())}


def classify(web, shop, t=Z_T):
    w = web is not None and web["z"] >= t
    s = shop is not None and shop["z"] >= t
    return "strong" if (w and s) else "watch" if (w or s) else "none"


def fetch(pt, kw, gprop):
    end = dt.date.today()
    tf = f"{end - dt.timedelta(days=125)} {end}"   # <270 days -> daily data
    for i in range(4):
        try:
            pt.build_payload([kw], timeframe=tf, geo="US", gprop=gprop)
            df = pt.interest_over_time()
            if df.empty:
                return None
            if "isPartial" in df:
                df = df[~df["isPartial"].astype(bool)]
            return df[kw]
        except Exception as e:
            wait = 30 * (i + 1) + random.uniform(0, 10)
            print(f"  retry {i+1} for '{kw}' ({e.__class__.__name__}), wait {wait:.0f}s")
            time.sleep(wait)
    return None


def push(text):
    url = os.getenv("WECOM_WEBHOOK")
    if not url:
        print("[no webhook, print only]\n" + text)
        return
    r = requests.post(url, json={"msgtype": "markdown",
                                 "markdown": {"content": text[:3800]}}, timeout=15)
    print("wecom:", r.status_code, r.text[:100])


def days_to(d):
    try:
        return (pd.to_datetime(d).date() - dt.date.today()).days
    except Exception:
        return None


def recently_pushed(brand):
    f = DATA / "pushed.csv"
    if not f.exists():
        return False
    p = pd.read_csv(f)
    p = p[p["brand"] == brand]
    if p.empty:
        return False
    return (dt.date.today() - pd.to_datetime(p["date"]).max().date()).days < COOLDOWN_DAYS


def fmt(r):
    return f"Z={r['z']:.1f}（7日均值{r['ma7']:.0f} vs 基线{r['base']:.0f}）" if r else "无有效数据"


def main():
    from pytrends.request import TrendReq
    (DATA / "trends").mkdir(parents=True, exist_ok=True)
    pool = pd.read_csv(ROOT / "monitor_pool.csv")
    pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
    today = dt.date.today().isoformat()
    log, fails, total = [], 0, 0

    for r in pool.itertuples():
        slug = "".join(c if c.isalnum() else "_" for c in r.brand)
        res = {}
        for ch, gp in (("web", ""), ("shop", "froogle")):
            total += 1
            s = fetch(pt, r.brand, gp)
            time.sleep(random.uniform(6, 12))
            if s is None:
                fails += 1
                continue
            s.to_csv(DATA / "trends" / f"{slug}_{ch}.csv")   # latest window, overwritten
            res[ch] = zscore(s)
        status = classify(res.get("web"), res.get("shop"))
        log.append({"date": today, "brand": r.brand, "ticker": r.ticker,
                    "web_z": res["web"]["z"] if res.get("web") else None,
                    "shop_z": res["shop"]["z"] if res.get("shop") else None,
                    "status": status})
        zw = round(res["web"]["z"], 1) if res.get("web") else None
        zs = round(res["shop"]["z"], 1) if res.get("shop") else None
        print(r.brand, status, "web_z=", zw, "shop_z=", zs)

        if status == "strong" and not recently_pushed(r.brand):
            d = days_to(getattr(r, "next_earnings", None))
            link = f"https://trends.google.com/trends/explore?q={quote(r.brand)}&geo=US"
            msg = (f"## 【异动】{r.ticker if isinstance(r.ticker, str) else '-'}｜{r.brand}\n"
                   f"> 普通搜索：{fmt(res['web'])}\n"
                   f"> 购物搜索：{fmt(res['shop'])}\n"
                   f"> 距财报：{d if d is not None else '未填'} 天\n"
                   f"[查看Trends]({link})\n"
                   f"请人工核实：真需求 / 新闻事件 / 水军")
            push(msg)
            pd.DataFrame([{"date": today, "brand": r.brand}]).to_csv(
                DATA / "pushed.csv", mode="a", header=not (DATA / "pushed.csv").exists(),
                index=False)

    f = DATA / "signals.csv"
    pd.DataFrame(log).to_csv(f, mode="a", header=not f.exists(), index=False)

    if total and fails / total > 0.5:
        push(f"## 【运行异常】\n> {fails}/{total} 次Trends请求失败，可能被限流，请检查。")

    if dt.date.today().weekday() == 0 and f.exists():      # Monday digest
        h = pd.read_csv(f)
        h = h[(pd.to_datetime(h["date"]) >= pd.Timestamp.today() - pd.Timedelta(days=7))
              & (h["status"] == "watch")]
        if not h.empty:
            cnt = h.groupby("brand").size().sort_values(ascending=False)
            push("## 【周报】观察名单（单通道异常）\n" +
                 "\n".join(f"> {b}：{n} 天" for b, n in cnt.items()))


if __name__ == "__main__":
    main()
