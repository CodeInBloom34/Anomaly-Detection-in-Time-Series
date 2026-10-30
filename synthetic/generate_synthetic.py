"""
profile.json'dan taxid x tarih panel yapisinda sentetik veri uretir.

Model (Gaussian copula + panel zaman serisi):
  z[id, t, j] = sqrt(icc_j) * b[id, j]                 # firmaya ozgu kalici seviye
              + sqrt(1 - icc_j) * x[id, t, j]          # AR(1) zaman dinamigi
              + mevsim_j(ay, gun) + trend_j * t
  b ve x'in inovasyonlari kolonlar arasi korelasyon matrisiyle (Cholesky) uretilir.
  Son adimda her kolon siralama ile kantil dagilimina esletirilir; boylece
  marjinal dagilimlar (sifir yigilmasi, carpiklik, tam sayilik dahil) korunur.

Opsiyonel: anomali enjeksiyonu (spike, seviye kaymasi, drift, sifirlanma) ve
etiket kolonlari - anomali tespit modellerini test etmek icin.

Kullanim:
    python generate_synthetic.py profile.json -o synthetic.csv --n-ids 5000 --anomaly-rate 0.03
"""
import argparse
import json

import numpy as np
import pandas as pd


def nearest_psd_corr(c):
    c = (np.asarray(c, float) + np.asarray(c, float).T) / 2
    w, v = np.linalg.eigh(c)
    c = v @ np.diag(np.clip(w, 1e-6, None)) @ v.T
    d = np.sqrt(np.diag(c))
    return c / np.outer(d, d)


def sample_from_quantiles(qs, size, rng):
    qs = np.asarray(qs, float)
    return np.interp(rng.uniform(size=size), np.linspace(0, 1, len(qs)), qs)


def to_uniform(v):
    """Siralama ile (0,1) araligina tasir - marjinali kantillere birebir esler."""
    # Esit degerler ayni ranki alir -> firma sabiti kolonlar firma icinde degismez
    return pd.Series(v).rank(method="average").to_numpy() / (len(v) + 1)


def generate(profile, n_ids=None, start=None, seed=42):
    rng = np.random.default_rng(seed)
    P, cols = profile["panel"], profile["columns"]
    names = profile["corr_columns"]
    p = len(names)
    n_ids = n_ids or P["n_ids"]
    T = P["n_periods"]
    grid = pd.date_range(start or P["start"], periods=T, freq=P["freq"])

    # Her firmanin baslangic donemi ve gozlem sayisi
    s_idx = np.clip(np.round(sample_from_quantiles(P["start_idx_quantiles"], n_ids, rng)), 0, T - 1).astype(int)
    e_idx = np.clip(np.round(sample_from_quantiles(P["end_idx_quantiles"], n_ids, rng)), 0, T - 1).astype(int)
    s_idx, e_idx = np.minimum(s_idx, e_idx), np.maximum(s_idx, e_idx)
    length = e_idx - s_idx + 1

    L = np.linalg.cholesky(nearest_psd_corr(profile["corr"]))
    static = np.array([cols[c].get("static", False) for c in names])
    icc = np.where(static, 1.0, [cols[c]["icc"] for c in names])
    phi = np.array([cols[c]["ar1"] for c in names])
    trend = np.where(static, 0.0, [cols[c].get("trend_per_period", 0.0) for c in names])

    B = rng.standard_normal((n_ids, p)) @ L.T
    X = np.empty((n_ids, T, p))
    X[:, 0] = rng.standard_normal((n_ids, p)) @ L.T
    scale = np.sqrt(1 - phi ** 2)
    for t in range(1, T):
        X[:, t] = phi * X[:, t - 1] + scale * (rng.standard_normal((n_ids, p)) @ L.T)

    # Sadece gozlenen (id, t) hucrelerini al
    id_ix = np.repeat(np.arange(n_ids), length)
    t_ix = np.concatenate([np.arange(s, s + n) for s, n in zip(s_idx, length)])
    keep = rng.uniform(size=len(t_ix)) < P.get("fill_rate", 1.0)
    id_ix, t_ix = id_ix[keep], t_ix[keep]
    dates = grid[t_ix]
    Z = np.sqrt(icc) * B[id_ix] + np.sqrt(1 - icc) * X[id_ix, t_ix] + trend * t_ix[:, None]
    month = dates.month.values - 1
    for j, c in enumerate(names):
        if static[j]:
            continue
        if "month_effect" in cols[c]:
            Z[:, j] += np.asarray(cols[c]["month_effect"])[month]
        if "dow_effect" in cols[c]:
            Z[:, j] += np.asarray(cols[c]["dow_effect"])[dates.dayofweek.values]

    taxids = np.array([f"SYN{i:07d}" for i in rng.permutation(n_ids) + 1])
    out = {"taxid": taxids[id_ix], "tarih": dates}
    for j, c in enumerate(names):
        info, u = cols[c], to_uniform(Z[:, j])
        if info["type"] == "numeric":
            qs = np.asarray(info["quantiles"])
            v = np.interp(u, np.linspace(0, 1, len(qs)), qs)
            v = np.round(v) if info["is_integer"] else np.round(v, 2)
        elif info["type"] == "discrete":
            vals = np.asarray(info["values"])
            v = vals[np.minimum(np.searchsorted(np.cumsum(info["probs"]), u), len(vals) - 1)]
        elif info["type"] == "binary":
            lv = info["levels"] or [0.0]
            v = np.where(u > 1 - info["p_high"], lv[-1], lv[0])
        else:
            cats = np.asarray(info["categories"], dtype=object)
            v = cats[np.minimum(np.searchsorted(np.cumsum(info["probs"]), u), len(cats) - 1)]
        v = pd.Series(v)
        if info["missing_rate"] > 0:
            r = rng.uniform(size=n_ids)[id_ix] if info.get("static") else rng.uniform(size=len(v))
            v[r < info["missing_rate"]] = np.nan
        out[c] = v.values
    return pd.DataFrame(out)


def inject_anomalies(df, profile, rate, seed=42):
    """Firma bazinda anomali ekler; satir bazinda etiket kolonlari dondurur."""
    rng = np.random.default_rng(seed + 1)
    num = [c for c, i in profile["columns"].items() if i["type"] == "numeric" and c in df]
    df = df.copy()
    df["is_anomaly"] = 0
    df["anomaly_type"] = ""
    df["anomaly_cols"] = ""
    groups = df.groupby("taxid").indices
    ids = rng.choice(list(groups), size=int(len(groups) * rate), replace=False)
    kinds = ["spike", "level_shift", "drift", "zero_out"]
    for tid in ids:
        rows = np.sort(groups[tid])
        if len(rows) < 4:
            continue
        kind = rng.choice(kinds)
        k = rng.integers(1, min(4, len(num)) + 1)
        targets = list(rng.choice(num, size=k, replace=False))
        if kind == "spike":
            hit = rows[rng.integers(len(rows), size=rng.integers(1, 3))]
        else:
            hit = rows[rng.integers(len(rows) // 3, len(rows) - 1):]
        for c in targets:
            qs = np.asarray(profile["columns"][c]["quantiles"])
            iqr = max(qs[75] - qs[25], abs(qs[50]) * 0.1, 1e-9)
            x = df.loc[hit, c].astype(float)
            if kind == "spike":
                x = x + rng.choice([-1, 1]) * rng.uniform(5, 15) * iqr
            elif kind == "level_shift":
                x = x + rng.choice([-1, 1]) * rng.uniform(2, 5) * iqr
            elif kind == "drift":
                x = x + np.linspace(0, rng.uniform(3, 8), len(hit)) * iqr
            else:
                x = x * 0
            if profile["columns"][c]["is_integer"]:
                x = x.round()
            df.loc[hit, c] = x
        df.loc[hit, "is_anomaly"] = 1
        df.loc[hit, "anomaly_type"] = kind
        df.loc[hit, "anomaly_cols"] = ",".join(targets)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("-o", "--out", default="synthetic.csv")
    ap.add_argument("--n-ids", type=int, help="Uretilecek firma sayisi (varsayilan: profildeki)")
    ap.add_argument("--start", help="Baslangic tarihi (varsayilan: profildeki)")
    ap.add_argument("--anomaly-rate", type=float, default=0.0, help="Anomali eklenecek firma orani, or. 0.03")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    with open(args.profile, encoding="utf-8") as f:
        profile = json.load(f)
    df = generate(profile, args.n_ids, args.start, args.seed)
    if args.anomaly_rate > 0:
        df = inject_anomalies(df, profile, args.anomaly_rate, args.seed)
    if args.out.endswith(".parquet"):
        df.to_parquet(args.out, index=False)
    else:
        df.to_csv(args.out, index=False)
    print(f"{len(df)} satir, {df['taxid'].nunique()} firma, {df.shape[1]} kolon -> {args.out}")
    if "is_anomaly" in df:
        print(f"  Anomalili satir orani: {df['is_anomaly'].mean():.2%}")


if __name__ == "__main__":
    main()
