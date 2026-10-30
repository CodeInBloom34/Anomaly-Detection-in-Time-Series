"""
Demo amacli 'gizli veri yerine gecen' 40 degiskenli vergi paneli uretir.
Gercek verin olmadan tum hatti (profil -> uretim -> dogrulama) denemek icindir.

Kullanim:
    python demo_raw_data.py -o demo_raw.csv
"""
import argparse

import numpy as np
import pandas as pd


def make(n_ids=2000, start="2021-01-01", periods=60, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=periods, freq="MS")
    sektor = rng.choice(["imalat", "ticaret", "insaat", "hizmet", "tarim", "turizm", "bilisim"],
                        n_ids, p=[.22, .3, .12, .2, .05, .06, .05])
    il = rng.choice(["Istanbul", "Ankara", "Izmir", "Bursa", "Antalya", "Kocaeli", "Diger"],
                    n_ids, p=[.35, .12, .1, .06, .05, .05, .27])
    tur = rng.choice(["Ltd", "AS", "Sahis"], n_ids, p=[.55, .15, .3])
    size = rng.lognormal(13, 1.4, n_ids)
    start_ix = np.minimum(rng.geometric(0.05, n_ids) - 1, periods - 6) * (rng.uniform(size=n_ids) < 0.4)

    recs = []
    for i in range(n_ids):
        T = periods - start_ix[i]
        ar = np.zeros(T)
        for t in range(1, T):
            ar[t] = 0.7 * ar[t - 1] + rng.normal(0, 0.15)
        m = dates[start_ix[i]:].month.values
        season = 1 + 0.15 * np.sin((m - 3) / 12 * 2 * np.pi) + (0.3 if sektor[i] == "turizm" else 0) * (m >= 6) * (m <= 9)
        growth = np.exp(0.006 * np.arange(T))
        satis = size[i] * season * growth * np.exp(ar)
        k = lambda s: np.exp(rng.normal(0, s, T))
        calisan = np.maximum(1, np.round(size[i] / 4e4 * k(0.05)))
        alis = satis * rng.uniform(.5, .8) * k(.1)
        ihracat = satis * (rng.uniform(.1, .6) if rng.uniform() < .25 else 0) * k(.3)
        ithalat = alis * (rng.uniform(.1, .5) if rng.uniform() < .3 else 0) * k(.3)
        matrah = satis - ihracat
        hes_kdv = matrah * 0.20
        ind_kdv = alis * 0.20 * k(.08)
        devreden = np.maximum(ind_kdv - hes_kdv, 0)
        odenecek = np.maximum(hes_kdv - ind_kdv, 0)
        maas = calisan * 25000 * k(.03)
        sgk = maas * 0.225
        kira = size[i] * 0.02 * np.ones(T) * k(.01)
        amort = size[i] * 0.015 * k(.02)
        finans = size[i] * rng.uniform(0, .03) * k(.2)
        gider = alis + maas + sgk + kira + amort + finans
        brut = satis - alis
        net = satis - gider
        recs.append(pd.DataFrame({
            "taxid": f"{rng.integers(1e9, 1e10)}", "tarih": dates[start_ix[i]:],
            "sektor": sektor[i], "il": il[i], "sirket_turu": tur[i],
            "e_fatura": int(size[i] > 3e5 or rng.uniform() < .3), "e_defter": int(size[i] > 6e5),
            "calisan_sayisi": calisan, "satis_hasilati": satis, "kdv_matrahi": matrah,
            "hesaplanan_kdv": hes_kdv, "indirilecek_kdv": ind_kdv, "odenecek_kdv": odenecek,
            "devreden_kdv": devreden, "ihracat_tutari": ihracat, "ithalat_tutari": ithalat,
            "alis_tutari": alis, "gider_toplam": gider, "brut_kar": brut, "net_kar": net,
            "kv_matrahi": np.maximum(net, 0), "stopaj_tutari": maas * 0.15 + kira * 0.2,
            "sgk_prim": sgk, "maas_toplam": maas, "kira_gideri": kira, "amortisman": amort,
            "finansman_gideri": finans, "nakit": size[i] * 0.05 * k(.4), "banka_bakiyesi": size[i] * 0.2 * k(.3),
            "alacaklar": satis * 1.5 * k(.2), "borclar": alis * 1.8 * k(.2), "stok": alis * 1.2 * k(.25),
            "duran_varlik": size[i] * 1.0 * growth, "ozkaynak": size[i] * 0.6 * growth * k(.05),
            "ba_form_tutari": alis * (alis > 5000) * k(.05), "bs_form_tutari": satis * (satis > 5000) * k(.05),
            "fatura_adedi": np.round(satis / rng.uniform(2e3, 2e4) * k(.1)),
            "iade_talebi": (devreden > 0) & (rng.uniform(size=T) < .3),
            "gecikme_gun": np.where(rng.uniform(size=T) < .1, rng.integers(1, 90, T), 0),
            "ceza_tutari": np.where(rng.uniform(size=T) < .04, rng.lognormal(8, 1, T), 0.0),
            "duzeltme_sayisi": rng.poisson(0.08, T),
            "risk_skoru": np.clip(50 + 20 * ar + rng.normal(0, 10, T), 0, 100).round(1),
        }))
    df = pd.concat(recs, ignore_index=True)
    for c in ["nakit", "ithalat_tutari", "finansman_gideri", "stok"]:
        df.loc[rng.uniform(size=len(df)) < 0.05, c] = np.nan
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="demo_raw.csv")
    args = ap.parse_args()
    df = make()
    df.to_csv(args.out, index=False)
    print(f"{df.shape[0]} satir, {df.shape[1] - 2} degisken -> {args.out}")
