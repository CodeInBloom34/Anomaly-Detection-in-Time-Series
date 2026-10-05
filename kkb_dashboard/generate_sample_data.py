"""KKB kurumsal sorgu dashboard'u icin sentetik ornek veri ureticisi.

Gercek musteri verisi icermez. VKN'ler, unvanlar ve tum tutarlar rastgele
uretilir. Amac, Power BI modelini ve anomali skorlamasini gercek veri
baglanmadan once denemektir.

Kullanim:
    python generate_sample_data.py --out data --musteri 600 --seed 42
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DONEM_BAS = pd.Timestamp("2025-10-01")
DONEM_SON = pd.Timestamp("2026-09-30")

# Yer tutucu birim maliyet; gercek degeri KKB faturasindan alin.
SORGU_MALIYET_TL = {"Risk Merkezi": 40.0, "Ticari Kredi Notu": 65.0, "Cek Raporu": 30.0}

SEKTORLER = {
    "C": "Imalat",
    "F": "Insaat",
    "G": "Toptan ve perakende ticaret",
    "H": "Ulastirma ve depolama",
    "I": "Konaklama ve yiyecek",
    "J": "Bilgi ve iletisim",
    "M": "Mesleki ve teknik faaliyetler",
}
ILLER = {
    "Istanbul": "Marmara",
    "Kocaeli": "Marmara",
    "Bursa": "Marmara",
    "Ankara": "Ic Anadolu",
    "Konya": "Ic Anadolu",
    "Izmir": "Ege",
    "Denizli": "Ege",
    "Antalya": "Akdeniz",
    "Adana": "Akdeniz",
    "Gaziantep": "Guneydogu",
    "Kayseri": "Ic Anadolu",
    "Trabzon": "Karadeniz",
}
SEGMENTLER = ["Kurumsal", "Ticari", "KOBI"]
KREDI_TURLERI = ["Rotatif", "Spot", "Taksitli", "Teminat Mektubu", "Akreditif"]
NOT_BANTLARI = [
    ("A", 1600, 1900),
    ("B", 1400, 1599),
    ("C", 1100, 1399),
    ("D", 800, 1099),
    ("E", 1, 799),
]

# Musterinin 12 aylik hikayesi. Agirliklar portfoydeki yaklasik paylardir.
SENARYOLAR = {
    "stabil": 0.45,
    "birlikte_buyume": 0.15,
    "rakip_buyutuyor": 0.15,
    "proje_buyumesi": 0.07,
    "bozulma": 0.08,
    "sessiz_cikis": 0.05,
    "ana_banka": 0.05,
}


def not_bandi(skor):
    for bant, lo, hi in NOT_BANTLARI:
        if lo <= skor <= hi:
            return bant
    return "E"


def dim_tarih():
    gunler = pd.date_range(DONEM_BAS - pd.Timedelta(days=90), DONEM_SON + pd.Timedelta(days=90))
    # Basitlestirilmis resmi tatil listesi (2025-2026); gerekirse guncelleyin.
    tatiller = pd.to_datetime([
        "2025-10-29", "2026-01-01", "2026-03-19", "2026-03-20", "2026-03-21",
        "2026-03-22", "2026-04-23", "2026-05-01", "2026-05-19", "2026-05-26",
        "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30", "2026-07-15",
        "2026-08-30",
    ])
    bayram_bas = pd.to_datetime(["2026-03-20", "2026-05-27"])
    df = pd.DataFrame({"Tarih": gunler})
    df["Yil"] = df.Tarih.dt.year
    df["Ay"] = df.Tarih.dt.month
    df["AyAdi"] = df.Tarih.dt.strftime("%Y-%m")
    df["Ceyrek"] = "Q" + df.Tarih.dt.quarter.astype(str)
    df["HaftaninGunu"] = df.Tarih.dt.dayofweek + 1
    df["AyinHaftasi"] = ((df.Tarih.dt.day - 1) // 7 + 1).clip(upper=4)
    df["ResmiTatilMi"] = df.Tarih.isin(tatiller).astype(int)
    df["IsGunu"] = ((df.HaftaninGunu <= 5) & (df.ResmiTatilMi == 0)).astype(int)
    df["AySonuMu"] = (df.Tarih.dt.days_in_month - df.Tarih.dt.day < 5).astype(int)
    df["BayramOncesiMi"] = df.Tarih.apply(
        lambda d: int(any(0 < (b - d).days <= 5 for b in bayram_bas))
    )
    return df


def dim_sube(rng):
    rows = []
    for i, (il, bolge) in enumerate(ILLER.items()):
        for j, tip in enumerate(["Kurumsal", "Ticari", "KOBI"]):
            if il not in ("Istanbul", "Ankara", "Izmir") and tip == "Kurumsal":
                continue
            rows.append({
                "SubeKod": f"S{i:02d}{j}",
                "SubeAdi": f"{il} {tip} Subesi",
                "Il": il,
                "Bolge": bolge,
                "SubeTipi": tip,
            })
    return pd.DataFrame(rows)


def dim_musteri(rng, n, subeler):
    senaryo = rng.choice(list(SENARYOLAR), size=n, p=list(SENARYOLAR.values()))
    segment = rng.choice(SEGMENTLER, size=n, p=[0.2, 0.45, 0.35])
    rows = []
    for i in range(n):
        sube = subeler[subeler.SubeTipi == segment[i]].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
        rows.append({
            "VKN": f"9{rng.integers(10**8, 10**9):09d}",
            "Unvan": f"Musteri {i + 1:04d} A.S.",
            "Segment": segment[i],
            "NACE": rng.choice(list(SEKTORLER)),
            "Il": sube.Il,
            "Bolge": sube.Bolge,
            "SubeKod": sube.SubeKod,
            "GrupKod": f"G{rng.integers(1, 80):03d}" if rng.random() < 0.3 else "",
            "MusteriSinceTarihi": (DONEM_BAS - pd.Timedelta(days=int(rng.integers(90, 4000)))).date(),
            "PortfoyYoneticisi": f"PY{sube.SubeKod[1:3]}{rng.integers(1, 4)}",
            # Gizli senaryo etiketi: yalnizca test/dogrulama icindir, rapora tasinmaz.
            "_Senaryo": senaryo[i],
        })
    df = pd.DataFrame(rows).drop_duplicates("VKN").reset_index(drop=True)
    df["NACEAciklama"] = df.NACE.map(SEKTORLER)
    return df


def sorgu_tarihleri(rng, senaryo):
    """Bir musteri icin sorgu tarihleri; ay sonu yigilmasi ve mukerrer sorgu dahil."""
    if senaryo in ("bozulma", "rakip_buyutuyor", "proje_buyumesi"):
        adet = int(rng.integers(3, 7))
    else:
        adet = int(rng.integers(1, 5))
    gunler = []
    for _ in range(adet):
        ay = DONEM_BAS + pd.DateOffset(months=int(rng.integers(0, 12)))
        son_gun = ay.days_in_month
        # Ay sonuna yakin gunler daha olasi (hedef baskisi etkisi).
        gun = int(rng.choice([rng.integers(1, son_gun - 6), rng.integers(son_gun - 6, son_gun + 1)], p=[0.6, 0.4]))
        d = ay.replace(day=max(1, min(gun, son_gun)))
        while d.dayofweek >= 5:
            d -= pd.Timedelta(days=1)
        gunler.append(d)
    if rng.random() < 0.06:  # 7 gun icinde mukerrer sorgu
        gunler.append(gunler[0] + pd.Timedelta(days=int(rng.integers(1, 7))))
    return sorted(set(gunler))


def musteri_yolu(rng, m, tarihler):
    """Senaryoya gore her sorgu tarihindeki KKB gorunumunu uretir."""
    s = m["_Senaryo"]
    olcek = {"Kurumsal": 400e6, "Ticari": 60e6, "KOBI": 8e6}[m["Segment"]]
    risk0 = olcek * rng.lognormal(0, 0.6)
    doluluk0 = rng.uniform(0.45, 0.75)
    banka0 = int(rng.integers(2, 8))
    pay0 = rng.uniform(0.12, 0.45)
    not0 = rng.uniform(1250, 1800)
    gnakdi0 = rng.uniform(0.1, 0.35)
    akredi0 = rng.uniform(0.0, 0.1) if m["NACE"] in ("C", "G") else 0.0

    # Yillik egilimler (t: donem icindeki yil orani, 0-1)
    buyume = {"stabil": rng.normal(0.05, 0.05), "birlikte_buyume": 0.45, "rakip_buyutuyor": 0.55,
              "proje_buyumesi": 0.35, "bozulma": 0.4, "sessiz_cikis": -0.35, "ana_banka": -0.2}[s]
    pay_trend = {"stabil": 0.0, "birlikte_buyume": 0.12, "rakip_buyutuyor": -0.32, "proje_buyumesi": 0.0,
                 "bozulma": -0.05, "sessiz_cikis": -0.15, "ana_banka": 0.25}[s]

    rows = []
    for d in tarihler:
        t = (d - DONEM_BAS).days / 365
        g = 1 + buyume * t + rng.normal(0, 0.03)
        risk = max(risk0 * g, olcek * 0.05)
        doluluk = doluluk0 + rng.normal(0, 0.03)
        banka = banka0
        knot = not0 + rng.normal(0, 25)
        gnakdi = gnakdi0
        akredi = akredi0
        gecikme = takip = 0
        cek = 0
        if s == "bozulma":
            doluluk += 0.35 * t
            banka += int(round(3 * t))
            knot -= 500 * t
            gecikme = int(t > 0.55 and rng.random() < 0.8)
            takip = int(t > 0.85 and rng.random() < 0.4)
            cek = int(rng.poisson(2 * t)) if t > 0.4 else 0
        elif s == "rakip_buyutuyor":
            banka += int(round(2 * t))
            doluluk += 0.1 * t
        elif s == "proje_buyumesi":
            gnakdi += 0.5 * t
        elif s == "birlikte_buyume":
            knot += 120 * t
        elif s == "sessiz_cikis":
            banka -= int(round(1.5 * t))
            doluluk -= 0.15 * t
        if akredi and s == "birlikte_buyume":
            akredi += 0.1 * t
        doluluk = float(np.clip(doluluk, 0.15, 0.99))
        banka = max(1, banka)
        knot = float(np.clip(knot, 300, 1900))
        pay = float(np.clip(pay0 + pay_trend * t + rng.normal(0, 0.015), 0.0, 0.95))
        if banka == 1:
            pay = 1.0
        limit = risk / doluluk
        bizim_risk = risk * pay
        bizim_doluluk = float(np.clip(doluluk + rng.normal(-0.05, 0.08), 0.05, 0.99))
        if s == "rakip_buyutuyor":
            bizim_doluluk = float(np.clip(doluluk - 0.25, 0.05, 0.99))
        bizim_limit = min(bizim_risk / bizim_doluluk if bizim_risk else limit * 0.1, limit * 0.95)
        rows.append({
            "SorguTarihi": d,
            "SektorToplamLimit": round(limit, 0),
            "SektorToplamRisk": round(risk, 0),
            "GayrinakdiRisk": round(risk * min(gnakdi + akredi, 0.9), 0),
            "BankaSayisi": banka,
            "GecikmeVar": gecikme,
            "TakipVar": takip,
            "KKBNot": int(round(knot)),
            "CekKarsiliksizAdet": cek,
            "BizimLimit": round(bizim_limit, 0),
            "BizimRisk": round(bizim_risk, 0),
            "TmpGnakdi": gnakdi,
            "TmpAkredi": akredi,
        })
    return rows


def risk_detay(rng, sorgu):
    rows = []
    for r in sorgu.itertuples():
        gn, ak = r.TmpGnakdi, r.TmpAkredi
        nakdi = max(1 - gn - ak, 0.05)
        rot = rng.uniform(0.3, 0.6) + (0.25 if r.SektorToplamRisk / r.SektorToplamLimit > 0.85 else 0)
        rot = min(rot, 0.9)
        paylar = {
            "Rotatif": nakdi * rot,
            "Spot": nakdi * (1 - rot) * 0.4,
            "Taksitli": nakdi * (1 - rot) * 0.6,
            "Teminat Mektubu": gn,
            "Akreditif": ak,
        }
        toplam = sum(paylar.values())
        for tur, p in paylar.items():
            if p <= 0:
                continue
            risk = r.SektorToplamRisk * p / toplam
            rows.append({
                "SorguID": r.SorguID,
                "KrediTuru": tur,
                "Limit": round(r.SektorToplamLimit * p / toplam, 0),
                "Risk": round(risk, 0),
                "GecikmeGun": int(rng.integers(31, 120)) if (r.GecikmeVar and tur == "Rotatif") else 0,
            })
    return pd.DataFrame(rows)


def sorgu_sonucu(rng, senaryo, neden, d):
    """Basvuru amacli sorgularin 60 gunluk sonucunu uretir."""
    if neden not in ("Yeni Basvuru", "Limit Yenileme"):
        return "Izleme", None, None, None, ""
    ay_sonu = d.days_in_month - d.day < 5
    p_kul = {"stabil": 0.5, "birlikte_buyume": 0.75, "rakip_buyutuyor": 0.25, "proje_buyumesi": 0.55,
             "bozulma": 0.2, "sessiz_cikis": 0.15, "ana_banka": 0.7}[senaryo]
    if ay_sonu:
        p_kul *= 0.6
    u = rng.random()
    teklif = d + pd.Timedelta(days=int(rng.integers(2, 15)))
    if u < p_kul:
        onay = teklif + pd.Timedelta(days=int(rng.integers(1, 10)))
        kul = onay + pd.Timedelta(days=int(rng.integers(1, 30)))
        return "Kullandirim", teklif, onay, kul, ""
    if u < p_kul + 0.15:
        return "Ret", teklif, None, None, rng.choice(["Risk", "Teminat yetersiz", "Not dusuk"])
    if u < p_kul + 0.30:
        return "Teklif", teklif, None, None, "Musteri vazgecti"
    return "Aksiyon Yok", None, None, None, ""


def uret(n_musteri, seed):
    rng = np.random.default_rng(seed)
    tarih = dim_tarih()
    sube = dim_sube(rng)
    musteri = dim_musteri(rng, n_musteri, sube)

    # %8 musteri hic sorgulanmaz: kor nokta.
    kor = rng.random(len(musteri)) < 0.08
    sorgu_rows, sonuc_rows = [], []
    sid = 1
    for i, m in musteri.iterrows():
        if kor[i]:
            continue
        tarihler = sorgu_tarihleri(rng, m["_Senaryo"])
        for k, r in enumerate(musteri_yolu(rng, m, tarihler)):
            neden = "Yeni Basvuru" if k == 0 and rng.random() < 0.5 else rng.choice(
                ["Limit Yenileme", "Periyodik Izleme", "Tahsis Revizyonu"], p=[0.45, 0.4, 0.15])
            rapor = rng.choice(list(SORGU_MALIYET_TL), p=[0.6, 0.3, 0.1])
            sonuc, teklif, onay, kul, ret = sorgu_sonucu(rng, m["_Senaryo"], neden, r["SorguTarihi"])
            r.update({
                "SorguID": sid,
                "VKN": m["VKN"],
                "SubeKod": m["SubeKod"],
                "KullaniciID": f"U{m['SubeKod'][1:]}{rng.integers(1, 4)}",
                "RaporTipi": rapor,
                "SorguNedeni": neden,
                "SorguSonucu": sonuc,
                "SorguMaliyetTL": SORGU_MALIYET_TL[rapor],
            })
            r["NakdiRisk"] = r["SektorToplamRisk"] - r["GayrinakdiRisk"]
            sorgu_rows.append(r)
            if teklif is not None:
                sonuc_rows.append({
                    "VKN": m["VKN"], "Tarih": r["SorguTarihi"], "SorguID": sid,
                    "TeklifTarihi": teklif, "OnayTarihi": onay, "KullandirimTarihi": kul,
                    "RetNedeni": ret,
                })
            sid += 1
    sorgu = pd.DataFrame(sorgu_rows).sort_values(["VKN", "SorguTarihi"]).reset_index(drop=True)

    # Onceki sorgu alanlari: SQL'deki LAG() OVER (PARTITION BY VKN ORDER BY SorguTarihi) karsiligi.
    g = sorgu.groupby("VKN")
    for col in ["SorguID", "SorguTarihi", "BizimRisk", "SektorToplamRisk", "GecikmeVar",
                "TakipVar", "KKBNot", "BankaSayisi", "GayrinakdiRisk"]:
        sorgu["Onceki" + col] = g[col].shift(1)
    sorgu["SorgularArasiGun"] = (sorgu.SorguTarihi - sorgu.OncekiSorguTarihi).dt.days
    # Sonraki sorgu alanlari (LEAD): ret sonrasi kader ve skorun geriye donuk testi icin.
    sorgu["SonrakiSektorToplamRisk"] = g.SektorToplamRisk.shift(-1)
    sorgu["SonrakiGecikmeVar"] = g.GecikmeVar.shift(-1)
    sorgu["SonSorguMu"] = (g.SorguTarihi.transform("max") == sorgu.SorguTarihi).astype(int)
    sorgu["BizimPay"] = (sorgu.BizimRisk / sorgu.SektorToplamRisk).round(4)
    sorgu["OncekiBizimPay"] = (sorgu.OncekiBizimRisk / sorgu.OncekiSektorToplamRisk).round(4)
    sorgu["BizimDoluluk"] = (sorgu.BizimRisk / sorgu.BizimLimit).round(4)
    diger_limit = (sorgu.SektorToplamLimit - sorgu.BizimLimit).where(lambda s: s > 0)
    sorgu["DigerBankaDoluluk"] = ((sorgu.SektorToplamRisk - sorgu.BizimRisk) / diger_limit).round(4)
    sorgu["NotBandi"] = sorgu.KKBNot.apply(not_bandi)
    sorgu["OncekiNotBandi"] = sorgu.OncekiKKBNot.apply(lambda x: not_bandi(x) if pd.notna(x) else None)

    detay = risk_detay(rng, sorgu)
    sorgu = sorgu.drop(columns=["TmpGnakdi", "TmpAkredi"])

    # Fact_KrediSonuc: musteri x ay sonu snapshot + o ay gerceklesen olaylar.
    ay_sonlari = pd.date_range(DONEM_BAS, DONEM_SON, freq="ME")
    olay = pd.DataFrame(sonuc_rows)
    olay["AySonu"] = olay.Tarih + pd.offsets.MonthEnd(0)
    snap = []
    for i, m in musteri.iterrows():
        ms = sorgu[sorgu.VKN == m.VKN]
        if ms.empty:  # kor nokta: bizde riski var ama hic sorgulanmadi
            base = {"Kurumsal": 80e6, "Ticari": 12e6, "KOBI": 2e6}[m.Segment] * rng.lognormal(0, 0.5)
            seri = [(d, base * rng.uniform(0.95, 1.05), base * 1.4) for d in ay_sonlari]
        else:
            seri = []
            for d in ay_sonlari:
                once = ms[ms.SorguTarihi <= d]
                ref = once.iloc[-1] if not once.empty else ms.iloc[0]
                seri.append((d, ref.BizimRisk, ref.BizimLimit))
        # Ic rating (1 = en iyi, 8 = en kotu) ilk KKB notuyla iliskili, ama gecikmeli guncellenir:
        # not dustugu halde rating'i degismeyen musteriler "uyumsuzluk" olarak gorunur.
        ilk_not = ms.KKBNot.iloc[0] if not ms.empty else rng.uniform(1250, 1800)
        ic = int(np.clip(round((1900 - ilk_not) / 120 + rng.normal(0, 1)), 1, 8))
        for d, risk, limit in seri:
            snap.append({"VKN": m.VKN, "Tarih": d.date(), "BizimRisk": round(risk, 0),
                         "BizimLimit": round(limit, 0), "IcRating": ic})
    snap = pd.DataFrame(snap)
    olay_ozet = olay.groupby(["VKN", "AySonu"]).last().reset_index()
    olay_ozet["Tarih"] = olay_ozet.AySonu.dt.date
    kredi = snap.merge(
        olay_ozet[["VKN", "Tarih", "SorguID", "TeklifTarihi", "OnayTarihi", "KullandirimTarihi", "RetNedeni"]],
        on=["VKN", "Tarih"], how="left")

    not_df = pd.DataFrame(NOT_BANTLARI, columns=["Bant", "MinNot", "MaxNot"])
    not_df["Renk"] = ["#2E7D32", "#7CB342", "#FBC02D", "#F57C00", "#C62828"]
    return {
        "Dim_Tarih": tarih,
        "Dim_Sube": sube,
        "Dim_Musteri": musteri,
        "Dim_NotBandi": not_df,
        "Fact_Sorgu": sorgu,
        "Fact_RiskDetay": detay,
        "Fact_KrediSonuc": kredi,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data")
    ap.add_argument("--musteri", type=int, default=600)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for ad, df in uret(args.musteri, args.seed).items():
        df.to_csv(out / f"{ad}.csv", index=False, encoding="utf-8")
        print(f"{ad:16s} {len(df):7d} satir")


if __name__ == "__main__":
    main()
