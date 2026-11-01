"""Event study on weekly Trends (web+shop both abnormal) vs forward excess return over SPY.
Run locally (needs access to Google). Pool must be fixed BEFORE running."""
import time, random, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from pytrends.request import TrendReq

ROOT = Path(__file__).parent
Z_T, RECENT, BASE, MIN_GAP_WEEKS = 2.5, 2, 26, 8
HORIZONS = (20, 60)   # trading days


def weekly(pt, kw, gprop):
    for i in range(4):
        try:
            pt.build_payload([kw], timeframe="today 5-y", geo="US", gprop=gprop)
            df = pt.interest_over_time()
            return df[kw] if not df.empty else None
        except Exception:
            time.sleep(30 * (i + 1))
    return None


def rolling_z(s):
    """Point-in-time: uses only the BASE weeks before the RECENT window."""
    out = pd.Series(index=s.index, dtype=float)
    for i in range(RECENT + BASE, len(s) + 1):
        rec = s.iloc[i - RECENT:i]
        b = s.iloc[i - RECENT - BASE:i - RECENT]
        if (b > 0).mean() < 0.7:
            continue
        out.iloc[i - 1] = (rec.mean() - b.mean()) / max(b.std(ddof=1), 1.0)
    return out


def px(t, start):
    p = yf.download(t, start=start, progress=False, auto_adjust=True)["Close"]
    return p.iloc[:, 0] if isinstance(p, pd.DataFrame) else p


def fwd(p, spy, d, h):
    p, spy = p[p.index > d], spy[spy.index > d]
    if len(p) <= h or len(spy) <= h:
        return np.nan
    return p.iloc[h] / p.iloc[0] - spy.iloc[h] / spy.iloc[0]


def main():
    pool = pd.read_csv(ROOT / "monitor_pool.csv").dropna(subset=["ticker"])
    pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
    start = (dt.date.today() - dt.timedelta(days=365 * 5 + 30)).isoformat()
    spy = px("SPY", start)
    ev, base = [], []
    for r in pool.itertuples():
        w, s = weekly(pt, r.brand, ""), None
        time.sleep(random.uniform(6, 12))
        s = weekly(pt, r.brand, "froogle")
        time.sleep(random.uniform(6, 12))
        if w is None or s is None:
            print("skip", r.brand); continue
        p = px(r.ticker, start)
        zw, zs = rolling_z(w), rolling_z(s)
        # weekly index = week START; data complete only after week ends -> +7d (no look-ahead)
        avail = zw.index + pd.Timedelta(days=7)
        hit = ((zw >= Z_T) & (zs >= Z_T)).values
        last = None
        for d, h in zip(avail, hit):
            row = {h_: fwd(p, spy, d, h_) for h_ in HORIZONS}
            base.append(row)                      # every week = unconditional baseline
            if h and (last is None or (d - last).days > MIN_GAP_WEEKS * 7):
                ev.append({"brand": r.brand, "ticker": r.ticker, "date": d.date(), **row})
                last = d
    ev, base = pd.DataFrame(ev), pd.DataFrame(base)
    ev.to_csv(ROOT / "data" / "backtest_events.csv", index=False)
    print(f"events: {len(ev)}")
    for h in HORIZONS:
        if len(ev):
            e = ev[h].dropna()
            print(f"{h}d excess vs SPY | n={len(e)} mean={e.mean():.2%} median={e.median():.2%} "
                  f"hit={(e > 0).mean():.0%} | all-weeks baseline mean={base[h].mean():.2%}")
    print("n is small -> treat as exploratory, not proof.")


if __name__ == "__main__":
    main()
