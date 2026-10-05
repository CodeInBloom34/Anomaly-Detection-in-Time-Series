"""KKB sorgu serilerinden musteri bazli davranissal anomali skoru.

Her sorgu, ayni musterinin bir onceki sorgusuyla karsilastirilarak bir
degisim vektorune donusturulur. Skor iki parcadan olusur:

* Bireysel sapma: son degisim, musterinin kendi gecmis degisimlerinden
  ne kadar uzak? (robust z: medyan ve MAD)
* Akran sapmasi: degisim vektoru ayni sektor ve segmentteki diger
  musterilere gore ne kadar siradisi? (Isolation Forest)

Iki sapma 0-100 araligina olceklenip agirlikli ortalamasi alinir. En cok
katkiyi yapan ozellik "Neden" alanina yazilir. Cikti Power BI'a
Fact_AnomaliSkor tablosu olarak alinir.

Kullanim:
    python anomaly_score.py --data data --out data/Fact_AnomaliSkor.csv
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

OZELLIKLER = {
    "RiskBuyume30g": "Sektör riski hızlı değişti",
    "DolulukDelta": "Limit doluluğu değişti",
    "BankaSayisiDelta": "Banka sayısı değişti",
    "NotDelta": "KKB notu değişti",
    "GayrinakdiPayDelta": "Gayrinakdi pay kaydı",
    "RotatifPayDelta": "Rotatif pay kaydı",
    "BizimPayDelta": "Bizim pay değişti",
}
YENI_SINYAL_NEDENI = {
    "YeniGecikme": "Yeni gecikme sinyali",
    "YeniTakip": "Takibe düşüş",
}
BIREYSEL_AGIRLIK = 0.5
MIN_GECMIS = 2  # bireysel sapma icin gereken en az onceki degisim sayisi


def ozellik_cikar(sorgu, detay):
    s = sorgu.sort_values(["VKN", "SorguTarihi"]).copy()
    rot = (detay[detay.KrediTuru == "Rotatif"].groupby("SorguID").Risk.sum()
           / detay.groupby("SorguID").Risk.sum()).rename("RotatifPay")
    s = s.join(rot, on="SorguID")
    s["RotatifPay"] = s.RotatifPay.fillna(0)
    s["Doluluk"] = s.SektorToplamRisk / s.SektorToplamLimit
    s["GayrinakdiPay"] = s.GayrinakdiRisk / s.SektorToplamRisk

    g = s.groupby("VKN")
    gun = s.SorgularArasiGun.clip(lower=7)
    s["RiskBuyume30g"] = np.log(s.SektorToplamRisk / g.SektorToplamRisk.shift(1)) * 30 / gun
    s["DolulukDelta"] = s.Doluluk - g.Doluluk.shift(1)
    s["BankaSayisiDelta"] = s.BankaSayisi - s.OncekiBankaSayisi
    s["NotDelta"] = s.KKBNot - s.OncekiKKBNot
    s["GayrinakdiPayDelta"] = s.GayrinakdiPay - g.GayrinakdiPay.shift(1)
    s["RotatifPayDelta"] = s.RotatifPay - g.RotatifPay.shift(1)
    s["BizimPayDelta"] = s.BizimPay - s.OncekiBizimPay
    s["YeniGecikme"] = ((s.GecikmeVar == 1) & (s.OncekiGecikmeVar == 0)).astype(int)
    s["YeniTakip"] = ((s.TakipVar == 1) & (s.OncekiTakipVar == 0)).astype(int)
    # Ilk sorgunun degisim vektoru yoktur.
    return s[s.OncekiSorguID.notna()].copy()


def olcek(ref):
    """Robust olcek: MAD; MAD sifirsa (banka sayisi gibi kesikli alanlar) std'nin dortte biri."""
    ref = ref[~np.isnan(ref)]
    if len(ref) == 0:
        return 1.0
    mad = np.median(np.abs(ref - np.median(ref))) * 1.4826
    return max(mad, 0.25 * np.std(ref), 1e-6)


def robust_z(x, ref):
    return (x - np.nanmedian(ref)) / olcek(ref)


def bireysel_sapma(s):
    """Her degisimi, ayni musterinin ondan onceki degisimlerine gore olcer."""
    cols = list(OZELLIKLER)
    sonuc = pd.DataFrame(np.nan, index=s.index, columns=cols)
    # Ozellik olcekleri farkli oldugundan MAD alt siniri portfoy genelinden alinir.
    taban = np.array([olcek(s[c].to_numpy(dtype=float)) for c in cols])
    for _, grp in s.groupby("VKN"):
        vals = grp[cols].to_numpy()
        for i in range(MIN_GECMIS, len(grp)):
            ref = vals[:i]
            med = np.nanmedian(ref, axis=0)
            mad = np.maximum(np.nanmedian(np.abs(ref - med), axis=0) * 1.4826, taban)
            sonuc.iloc[sonuc.index.get_loc(grp.index[i])] = (vals[i] - med) / mad
    return sonuc


def akran_sapmasi(s, seed):
    """Sektor x segment icinde standartlastirilmis vektor uzerinde Isolation Forest."""
    cols = list(OZELLIKLER)
    std = pd.DataFrame(index=s.index, columns=cols, dtype=float)
    for _, grp in s.groupby(["NACE", "Segment"]):
        # Kucuk akran gruplarinda portfoy geneli referans alinir.
        ref = grp if len(grp) >= 20 else s
        for c in cols:
            std.loc[grp.index, c] = robust_z(grp[c].to_numpy(), ref[c].to_numpy())
    std = std.clip(-10, 10)
    iso = IsolationForest(n_estimators=300, contamination="auto", random_state=seed)
    iso.fit(std)
    ham = -iso.score_samples(std)  # buyuk = daha siradisi
    return pd.Series(ham, index=s.index), std


def yuzdelik(x):
    return pd.Series(x).rank(pct=True).to_numpy() * 100


def skorla(sorgu, detay, musteri, seed=42):
    s = ozellik_cikar(sorgu, detay)
    s = s.merge(musteri[["VKN", "NACE", "Segment"]], on="VKN", how="left").set_index(s.index)

    bz = bireysel_sapma(s)
    bz_buyukluk = bz.abs().max(axis=1)
    akran_ham, akran_z = akran_sapmasi(s, seed)

    akran_puan = yuzdelik(akran_ham)
    birey_puan = np.full(len(s), np.nan)
    mask = bz_buyukluk.notna().to_numpy()
    # Bireysel puan: |z| 0 -> 0, |z| 6 ve uzeri -> 100
    birey_puan[mask] = np.clip(bz_buyukluk[mask] / 6, 0, 1) * 100

    skor = np.where(mask, BIREYSEL_AGIRLIK * birey_puan + (1 - BIREYSEL_AGIRLIK) * akran_puan, akran_puan)
    # Yeni gecikme ve takip gecisleri dogrudan yuksek oncelik alir.
    skor = np.maximum(skor, s.YeniGecikme.to_numpy() * 80)
    skor = np.maximum(skor, s.YeniTakip.to_numpy() * 90)

    # Neden: en buyuk mutlak sapmayi veren ozellik (bireysel varsa o, yoksa akran).
    katki = bz.abs().where(bz.notna(), akran_z.abs())
    neden_kol = katki.astype(float).idxmax(axis=1)
    neden = neden_kol.map(OZELLIKLER)
    yon = np.sign([s.at[i, c] for i, c in neden_kol.items()])
    neden = neden + np.where(yon > 0, " (artış)", " (azalış)")
    neden = np.where(s.YeniGecikme == 1, YENI_SINYAL_NEDENI["YeniGecikme"], neden)
    neden = np.where(s.YeniTakip == 1, YENI_SINYAL_NEDENI["YeniTakip"], neden)

    out = pd.DataFrame({
        "SorguID": s.SorguID.astype(int),
        "VKN": s.VKN,
        "SorguTarihi": s.SorguTarihi,
        "Skor": np.round(skor, 1),
        "Neden": neden,
        "BireyselSapma": np.round(birey_puan, 1),
        "AkranSapmasi": np.round(akran_puan, 1),
        "SonSorguMu": (s.groupby("VKN").SorguTarihi.transform("max") == s.SorguTarihi).astype(int),
        # Geriye donuk test: skor aninda gecikme var miydi, bir sonraki sorguda var mi?
        "GecikmeVar": s.GecikmeVar.astype(int),
        "SonrakiGecikmeVar": s.SonrakiGecikmeVar if "SonrakiGecikmeVar" in s else np.nan,
    })
    for c in OZELLIKLER:
        out[c] = s[c].round(4)
    return out.sort_values("Skor", ascending=False).reset_index(drop=True)


def oku(data):
    data = Path(data)
    sorgu = pd.read_csv(data / "Fact_Sorgu.csv", dtype={"VKN": str}, parse_dates=["SorguTarihi"])
    detay = pd.read_csv(data / "Fact_RiskDetay.csv")
    musteri = pd.read_csv(data / "Dim_Musteri.csv", dtype={"VKN": str})
    return sorgu, detay, musteri


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    sorgu, detay, musteri = oku(args.data)
    skor = skorla(sorgu, detay, musteri, args.seed)
    out = Path(args.out) if args.out else Path(args.data) / "Fact_AnomaliSkor.csv"
    skor.to_csv(out, index=False, encoding="utf-8")
    print(f"{len(skor)} sorgu skorlandi, skor >= 70: {(skor.Skor >= 70).sum()} -> {out}")


if __name__ == "__main__":
    main()
