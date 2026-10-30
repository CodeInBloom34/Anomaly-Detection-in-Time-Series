"""
Sentetik verinin profile ne kadar benzedigini olcer (gercek veri gerekmez).

Kullanim:
    python validate.py profile.json synthetic.csv
"""
import argparse
import json

import numpy as np
import pandas as pd

from profile_data import build_profile

LABEL_COLS = ["is_anomaly", "anomaly_type", "anomaly_cols"]


def compare(ref, syn):
    rows = []
    for c, r in ref["columns"].items():
        s = syn["columns"].get(c)
        if s is None:
            continue
        row = {"kolon": c, "tip": r["type"],
               "eksik_ref": r["missing_rate"], "eksik_syn": s["missing_rate"],
               "icc_ref": r["icc"], "icc_syn": s["icc"], "ar1_ref": r["ar1"], "ar1_syn": s["ar1"]}
        if r["type"] != s["type"]:
            row["not"] = f"tip farkli: {s['type']}"
        elif r["type"] in ("discrete", "categorical"):
            key = "values" if r["type"] == "discrete" else "categories"
            pr = dict(zip(map(str, r[key]), r["probs"]))
            ps = dict(zip(map(str, s[key]), s["probs"]))
            row["dagilim_tvd"] = round(0.5 * sum(abs(pr.get(k, 0) - ps.get(k, 0)) for k in pr.keys() | ps.keys()), 3)
        elif r["type"] == "numeric":
            qr, qs = np.asarray(r["quantiles"]), np.asarray(s["quantiles"])
            iqr = max(qr[75] - qr[25], qr[95] - qr[5], 1e-9)
            row["medyan_ref"], row["medyan_syn"] = qr[50], qs[50]
            row["kantil_hata_iqr"] = round(float(np.mean(np.abs(qr[5:96] - qs[5:96])) / iqr), 3)
        rows.append(row)
    table = pd.DataFrame(rows)

    names = [c for c in ref["corr_columns"] if c in syn["corr_columns"]]
    ir = [ref["corr_columns"].index(c) for c in names]
    is_ = [syn["corr_columns"].index(c) for c in names]
    cr = np.asarray(ref["corr"])[np.ix_(ir, ir)]
    cs = np.asarray(syn["corr"])[np.ix_(is_, is_)]
    mask = ~np.eye(len(names), dtype=bool)
    d = np.abs(cr - cs) * mask
    i, j = np.unravel_index(d.argmax(), d.shape)
    print(f"En buyuk korelasyon farki: {names[i]} ~ {names[j]}: ref={cr[i, j]:.2f} syn={cs[i, j]:.2f}")
    return table, float(np.mean(np.abs(cr - cs)[mask])), float(np.max(np.abs(cr - cs)[mask]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("synthetic")
    ap.add_argument("--date-col", default="tarih")
    ap.add_argument("--id-col", default="taxid")
    args = ap.parse_args()

    with open(args.profile, encoding="utf-8") as f:
        ref = json.load(f)
    df = pd.read_parquet(args.synthetic) if args.synthetic.endswith(".parquet") else pd.read_csv(args.synthetic)
    df = df.drop(columns=[c for c in LABEL_COLS if c in df])
    syn = build_profile(df, args.date_col, args.id_col)

    table, mae, mx = compare(ref, syn)
    pd.set_option("display.width", 200, "display.max_rows", 200)
    print(table.to_string(index=False))
    print(f"\nKorelasyon farki: ortalama |d| = {mae:.3f}, en buyuk |d| = {mx:.3f}")
    print(f"Firma: ref={ref['panel']['n_ids']} syn={syn['panel']['n_ids']}, "
          f"satir: ref={ref['panel']['n_rows']} syn={syn['panel']['n_rows']}")


if __name__ == "__main__":
    main()
