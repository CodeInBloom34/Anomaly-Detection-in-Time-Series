"""
Gizli veriden sadece TOPLULASTIRILMIS istatistik cikaran profil araci.

Bu script senin ortaminda, gercek veri uzerinde calisir ve `profile.json`
uretir. JSON icinde hicbir satir, hicbir taxid ve hicbir uc deger (min/max)
yoktur; sadece dagilim kantilleri, eksik oranlari, korelasyonlar ve zaman
yapisi (otokorelasyon, mevsimsellik, firma-ici benzerlik) bulunur.
Paylasmadan once JSON'u acip gozle kontrol etmen onerilir.

Kullanim:
    python profile_data.py veri.csv --date-col tarih --id-col taxid -o profile.json
"""
import argparse
import json
import sys
from statistics import NormalDist

import numpy as np
import pandas as pd

N_QUANTILES = 101
_INV_GRID = np.linspace(1e-4, 1 - 1e-4, 10001)
_INV_VALS = np.array([NormalDist().inv_cdf(p) for p in _INV_GRID])


def normal_scores(s: pd.Series) -> pd.Series:
    """Siralamaya dayali normal skor (Gaussian copula donusumu). NaN korunur."""
    r = s.rank(method="average")
    n = s.notna().sum()
    u = r / (n + 1)
    return pd.Series(np.interp(u, _INV_GRID, _INV_VALS), index=s.index).where(s.notna())


def round_sig(x, sig):
    x = np.asarray(x, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        mag = np.where(x == 0, 0, np.floor(np.log10(np.abs(x))))
    factor = 10 ** (sig - 1 - mag)
    return np.round(x * factor) / factor


def infer_freq(dates: pd.Series) -> str:
    u = pd.Series(np.sort(dates.dropna().unique()))
    f = pd.infer_freq(u) if len(u) >= 3 else None
    if f:
        return f
    d = u.diff().dt.days.median()
    if d <= 1.5:
        return "D"
    if d <= 8:
        return "W"
    if d <= 32:
        return "MS" if (u.dt.day == 1).all() else "ME"
    if d <= 95:
        return "QS"
    return "YS"


def build_profile(df, date_col, id_col, exclude=(), min_cat_count=10, max_cat_levels=50,
                  tail_clip=0.005, sig_digits=4, max_discrete_levels=30):
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values([id_col, date_col]).reset_index(drop=True)
    freq = infer_freq(df[date_col])

    # ---- Panel yapisi: kac firma, her firma kac donem, ne zaman basliyor ----
    grid = pd.date_range(df[date_col].min(), df[date_col].max(), freq=freq)
    per_id = df.groupby(id_col)[date_col].agg(["min", "max", "count"])
    start_idx = np.searchsorted(grid.values, per_id["min"].values)
    end_idx = np.searchsorted(grid.values, per_id["max"].values)
    span = end_idx - start_idx + 1
    q = np.linspace(0, 1, 21)
    panel = {
        "n_ids": int(len(per_id)),
        "n_rows": int(len(df)),
        "freq": freq,
        "n_periods": int(len(grid)),
        # Tarih araligi gizli sayilirsa uretim sirasinda --start ile degistirilebilir
        "start": str(grid[0].date()),
        "start_idx_quantiles": np.quantile(start_idx, q).round(1).tolist(),
        "end_idx_quantiles": np.quantile(end_idx, q).round(1).tolist(),
        # Firma aktif oldugu donemlerin ne kadarinda kayit var (ara bosluklar)
        "fill_rate": round(float(per_id["count"].sum() / span.sum()), 4),
    }

    feature_cols = [c for c in df.columns if c not in (date_col, id_col, *exclude)]
    columns, z = {}, {}
    skipped = []
    for c in feature_cols:
        s = df[c]
        info = {"missing_rate": round(float(s.isna().mean()), 4)}
        if pd.api.types.is_bool_dtype(s) or (pd.api.types.is_numeric_dtype(s) and s.dropna().nunique() <= 2):
            vals = s.dropna().astype(float)
            levels = sorted(vals.unique().tolist())
            info.update(type="binary", levels=levels,
                        p_high=round(float((vals == levels[-1]).mean()), 4) if levels else 0.0)
            z[c] = normal_scores(s.astype(float))
        elif (pd.api.types.is_numeric_dtype(s) and s.dropna().nunique() <= max_discrete_levels
              and np.all(np.mod(s.dropna(), 1) == 0)):
            # Az degerli sayim kolonlari (0,1,2,3...): ayrik dagilim, nadir degerler en yakina birlestirilir
            vals = s.dropna().astype(float)
            vc = vals.value_counts()
            kept = np.sort(vc[vc >= min_cat_count].index.values)
            if len(kept) == 0:
                kept = np.array([vals.median()])
            mapped = kept[np.abs(vals.values[:, None] - kept[None, :]).argmin(1)]
            vc = pd.Series(mapped).value_counts(normalize=True).reindex(kept)
            info.update(type="discrete", values=kept.tolist(), probs=vc.round(5).tolist())
            z[c] = normal_scores(s.astype(float))
        elif pd.api.types.is_numeric_dtype(s):
            vals = s.dropna().astype(float)
            probs = np.linspace(0, 1, N_QUANTILES)
            probs_clipped = np.clip(probs, tail_clip, 1 - tail_clip)
            qs = round_sig(np.quantile(vals, probs_clipped), sig_digits)
            info.update(
                type="numeric",
                is_integer=bool(np.all(np.mod(vals, 1) == 0)),
                zero_rate=round(float((vals == 0).mean()), 4),
                negative_rate=round(float((vals < 0).mean()), 4),
                quantiles=qs.tolist(),
            )
            z[c] = normal_scores(s.astype(float))
        else:
            s = s.astype("string")
            vc = s.value_counts()
            if len(vc) > max_cat_levels:
                skipped.append(c)
                continue
            rare = vc[vc < min_cat_count].index
            s = s.where(~s.isin(rare), "__OTHER__")
            vc = s.value_counts(normalize=True)
            info.update(type="categorical", categories=vc.index.tolist(), probs=vc.round(4).tolist())
            code = s.map({k: i for i, k in enumerate(vc.index)}).astype(float)
            z[c] = normal_scores(code)
        columns[c] = info

    Z = pd.DataFrame(z)
    ids = df[id_col]

    # ---- Zaman yapisi (normal skor uzayinda) ----
    month = df[date_col].dt.month
    dow = df[date_col].dt.dayofweek
    obs_per_id = per_id["count"].mean()
    for c in Z.columns:
        zc = Z[c]
        tot_var = zc.var()
        g = zc.groupby(ids)
        within = g.var().mean()
        between = g.mean().var()
        # Kisa panellerdeki yanliligi duzeltilmis firma-ici korelasyon (ICC)
        icc = (between - within / max(obs_per_id, 1)) / tot_var if tot_var > 0 else 0.0
        icc = float(np.clip(np.nan_to_num(icc), 0, 0.995))
        lag = g.shift(1)
        r1 = zc.corr(lag)
        r1 = 0.0 if np.isnan(r1) else r1
        phi = float(np.clip((r1 - icc) / (1 - icc), 0, 0.995))
        info = columns[c]
        # Firma icinde hic degismeyen kolonlar (sektor, il, sirket turu...)
        info["static"] = bool(df[c].groupby(ids).nunique().le(1).mean() >= 0.99)
        info["icc"] = round(icc, 3)
        info["ar1"] = round(phi, 3)
        trend = np.polyfit(np.arange(len(grid)), zc.groupby(df[date_col]).mean()
                           .reindex(grid).interpolate().bfill().ffill().values, 1)[0] if len(grid) > 2 else 0.0
        info["trend_per_period"] = round(float(trend), 5)
        if freq not in ("YS", "Y", "YE", "A"):
            info["month_effect"] = zc.groupby(month).mean().reindex(range(1, 13)).fillna(0).round(3).tolist()
        if freq == "D":
            info["dow_effect"] = zc.groupby(dow).mean().reindex(range(7)).fillna(0).round(3).tolist()

    # ---- Kolonlar arasi korelasyon (Gaussian copula) ----
    corr = Z.corr(min_periods=30).fillna(0).to_numpy(copy=True)
    np.fill_diagonal(corr, 1.0)

    profile = {
        "version": 1,
        "panel": panel,
        "columns": columns,
        "corr_columns": Z.columns.tolist(),
        "corr": np.round(corr, 3).tolist(),
        "skipped_columns": skipped,
    }
    return profile


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="CSV / parquet / xlsx dosyasi")
    ap.add_argument("--date-col", required=True)
    ap.add_argument("--id-col", required=True)
    ap.add_argument("-o", "--out", default="profile.json")
    ap.add_argument("--sep", default=",")
    ap.add_argument("--min-cat-count", type=int, default=10,
                    help="Bundan az gozlemli kategoriler __OTHER__ altinda birlestirilir")
    ap.add_argument("--max-cat-levels", type=int, default=50,
                    help="Bundan fazla seviyeli metin kolonlar (isim, adres vb.) atlanir")
    ap.add_argument("--tail-clip", type=float, default=0.005,
                    help="Uc degerleri saklamak icin min/max yerine bu kantiller kullanilir")
    ap.add_argument("--sig-digits", type=int, default=4, help="Kantiller bu kadar anlamli basamaga yuvarlanir")
    ap.add_argument("--exclude", nargs="*", default=[], help="Profile dahil edilmeyecek kolonlar")
    args = ap.parse_args()

    if args.path.endswith(".parquet"):
        df = pd.read_parquet(args.path)
    elif args.path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(args.path)
    else:
        df = pd.read_csv(args.path, sep=args.sep)

    profile = build_profile(df, args.date_col, args.id_col, args.exclude, args.min_cat_count,
                            args.max_cat_levels, args.tail_clip, args.sig_digits)
    panel, columns, skipped = profile["panel"], profile["columns"], profile["skipped_columns"]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=1)

    print(f"Profil yazildi: {args.out}")
    print(f"  {panel['n_ids']} firma, {panel['n_rows']} satir, frekans={panel['freq']}, {len(columns)} kolon")
    if skipped:
        print(f"  Atlanan yuksek kardinaliteli metin kolonlar: {skipped}", file=sys.stderr)
    print("  Paylasmadan once JSON'u kontrol et: icinde satir veya taxid yoktur.")


if __name__ == "__main__":
    main()
