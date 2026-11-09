"""PBIP raporunun sayfa gorunumlerini ornek veriyle cizer ve PDF taslak dokumani uretir.

Power BI Desktop olmadan raporun nasil gorunecegini gostermek icindir:
yerlesim, gorsel tipleri, alanlar ve basliklar dogrudan PBIP dosyalarindan okunur;
degerler ornek CSV'lerden, build_pbip.py'deki DAX olculeriyle ayni mantikla hesaplanir.
Gorunum Power BI'in birebir ekran goruntusu degildir; renk, yazi ve eksen detaylari
Power BI'da biraz farkli olur.

Kullanim (kkb_dashboard klasorunden):
    python powerbi/render_mockup.py --data data --out docs
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import build_pbip  # noqa: E402

RAPOR = KOK / f"{build_pbip.PROJE}.Report" / "definition"

# Renkler: build_pbip.TEMA ile ayni kategorik palet + notr murekkep tonlari.
SERI = build_pbip.TEMA["dataColors"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SAYFA_ZEMIN, KART_ZEMIN = "#f3f2ef", "#ffffff"
SIRALI = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": AXIS,
                     "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED})

BICIM = {ad: fmt for _, ad, _, fmt, _ in build_pbip.OLCULER}


# --------------------------------------------------------------------------------------
# Veri ve hesaplanmis sutunlar (DAX ile ayni mantik)
# --------------------------------------------------------------------------------------

def yukle(data):
    d = Path(data)
    oku = lambda ad, **kw: pd.read_csv(d / f"{ad}.csv", dtype={"VKN": str}, **kw)  # noqa: E731
    tarih = oku("Dim_Tarih", parse_dates=["Tarih"])
    tarih["Ay Donemi"] = np.where(tarih.AySonuMu == 1, "Ay sonu (son 5 gün)", "Ay içi")
    tarih["Gun Adi"] = tarih.HaftaninGunu.map({1: "1 Pzt", 2: "2 Sal", 3: "3 Çar", 4: "4 Per", 5: "5 Cum",
                                               6: "6 Cmt", 7: "7 Paz"})
    tarih["Yil Ceyrek"] = tarih.Yil.astype(str) + "-" + tarih.Ceyrek
    musteri = oku("Dim_Musteri")
    sube = oku("Dim_Sube")
    s = oku("Fact_Sorgu", parse_dates=["SorguTarihi", "OncekiSorguTarihi"])
    a = oku("Fact_AnomaliSkor", parse_dates=["SorguTarihi"])
    k = oku("Fact_KrediSonuc", parse_dates=["Tarih", "KullandirimTarihi"])
    r = oku("Fact_RiskDetay")

    ilk = s.OncekiSorguID.isna()
    g = s.SorgularArasiGun
    s["Tekrar Araligi"] = np.select(
        [ilk, g <= 7, g <= 30, g <= 90, g <= 180],
        ["0) İlk sorgu", "1) 0-7 gün", "2) 8-30 gün", "3) 31-90 gün", "4) 91-180 gün"], "5) 180+ gün")
    db = s.BankaSayisi - s.OncekiBankaSayisi
    s["Banka Degisimi"] = np.select([ilk, db > 0, db < 0], ["İlk sorgu", "Arttı", "Azaldı"], "Aynı")
    dn = s.KKBNot - s.OncekiKKBNot
    s["Not Degisimi"] = np.select([ilk, dn >= 50, dn <= -50], ["İlk sorgu", "Yükseldi", "Düştü"], "Aynı")
    dpay = s.BizimPay - s.OncekiBizimPay
    drisk = s.SektorToplamRisk - s.OncekiSektorToplamRisk
    s["Cuzdan Bolgesi"] = np.select(
        [ilk, (drisk >= 0) & (dpay < 0), drisk >= 0, dpay < 0],
        ["Tek sorgu", "Rakip büyütüyor", "Birlikte büyüyoruz", "Sessiz çıkış"], "Ana bankaya dönüşüyoruz")
    skor = s.SorguID.map(a.set_index("SorguID").Skor)
    dgn = s.GayrinakdiRisk / s.SektorToplamRisk - s.OncekiGayrinakdiRisk / s.OncekiSektorToplamRisk
    dol = s.SektorToplamRisk / s.SektorToplamLimit
    s["Aksiyon Etiketi"] = np.select(
        [s.GecikmeVar == 1, s.TakipVar == 1, ~ilk & (skor >= 70) & (dn < 0), ~ilk & (db >= 2) & (dn < 0),
         ~ilk & (drisk > 0) & (dpay <= -0.05) & (dn >= 0),
         (dol > 0.85) & (s.BizimDoluluk.fillna(0) < 0.6) & s.NotBandi.isin(["A", "B"]),
         ~ilk & (dgn >= 0.10) & (s.GecikmeVar == 0), ~ilk & (g <= 7)],
        ["Erken uyarı", "Erken uyarı", "Erken uyarı", "Kredi açlığı", "Pay geri kazan", "Limit sıkışıklığı",
         "Proje büyümesi", "Gereksiz sorgu"], "İzle")
    et = s["Aksiyon Etiketi"]
    s["Potansiyel TL"] = np.select(
        [et == "Pay geri kazan", et == "Limit sıkışıklığı", et == "Proje büyümesi"],
        [(s.OncekiBizimPay - s.BizimPay).clip(lower=0) * s.SektorToplamRisk,
         (s.BizimLimit - s.BizimRisk).clip(lower=0),
         (s.GayrinakdiRisk - s.OncekiGayrinakdiRisk).clip(lower=0) * s.OncekiBizimPay], 0)
    s["Potansiyel TL"] = s["Potansiyel TL"].fillna(0)

    # Iliskiler: boyut sutunlarini olgu tablolarina tasiyarak filtre baglamini taklit et.
    mcols = ["VKN", "Unvan", "Segment", "NACEAciklama", "Bolge", "PortfoyYoneticisi"]
    tcols = ["Tarih", "AyAdi", "AyinHaftasi", "Gun Adi", "Ay Donemi", "Yil Ceyrek"]
    s = s.merge(musteri[mcols], on="VKN", how="left").merge(
        tarih[tcols], left_on="SorguTarihi", right_on="Tarih", how="left").drop(columns="Tarih").merge(
        sube[["SubeKod", "SubeAdi"]], on="SubeKod", how="left")
    a = a.merge(musteri[mcols], on="VKN", how="left").merge(
        tarih[tcols], left_on="SorguTarihi", right_on="Tarih", how="left").drop(columns="Tarih")
    k = k.merge(musteri[mcols], on="VKN", how="left").merge(tarih[tcols], on="Tarih", how="left")
    k = k.merge(s[["SorguID", "SorguTarihi"]], on="SorguID", how="left")
    r = r.merge(s.drop(columns=["Risk"], errors="ignore"), on="SorguID", how="left")
    return {"Fact_Sorgu": s, "Fact_AnomaliSkor": a, "Fact_KrediSonuc": k, "Fact_RiskDetay": r}


# Hangi tablonun sutunu hangi olgu tablolarini filtreler
FILTRELER = {
    "Dim_Musteri": ["Fact_Sorgu", "Fact_AnomaliSkor", "Fact_KrediSonuc", "Fact_RiskDetay"],
    "Dim_Tarih": ["Fact_Sorgu", "Fact_AnomaliSkor", "Fact_KrediSonuc", "Fact_RiskDetay"],
    "Dim_Sube": ["Fact_Sorgu", "Fact_RiskDetay"],
    "Fact_Sorgu": ["Fact_Sorgu", "Fact_RiskDetay"],
    "Fact_RiskDetay": ["Fact_RiskDetay"],
}


def filtrele(ctx, tablo, sutun, deger, haric=False):
    yeni = dict(ctx)
    if tablo in ("Huni Asama", "Risk Kopru"):
        yeni[tablo] = deger
        return yeni
    for f in FILTRELER[tablo]:
        df = ctx[f]
        if sutun in df.columns:
            m = df[sutun].isin(deger) if haric else (df[sutun] == deger)
            yeni[f] = df[~m] if haric else df[m]
    return yeni


# --------------------------------------------------------------------------------------
# Olculer (build_pbip.OLCULER ile ayni tanimlar)
# --------------------------------------------------------------------------------------

def _bos(x):
    return x is None or (isinstance(x, float) and np.isnan(x))


def bol(a, b):
    return np.nan if _bos(a) or _bos(b) or b == 0 else a / b


def olcu(ad, c):
    S, A, K, R = c["Fact_Sorgu"], c["Fact_AnomaliSkor"], c["Fact_KrediSonuc"], c["Fact_RiskDetay"]
    bas = S[S.SorguNedeni.isin(["Yeni Basvuru", "Limit Yenileme"])]
    onc = S[S.OncekiSorguID.notna()]
    son = S[S.SonSorguMu == 1]
    nz = lambda x: np.nan if x == 0 else x  # noqa: E731
    f = {
        "Sorgu Adedi": lambda: nz(len(S)),
        "Tekil Musteri": lambda: nz(S.VKN.nunique()),
        "Musteri Basina Sorgu": lambda: bol(len(S), S.VKN.nunique()),
        "Basvuru Sorgusu": lambda: nz(len(bas)),
        "Sorgu Donusum %": lambda: bol((bas.SorguSonucu == "Kullandirim").sum(), len(bas)),
        "Olu Sorgu Orani %": lambda: bol((bas.SorguSonucu == "Aksiyon Yok").sum(), len(bas)),
        "Toplam Sorgu Maliyeti TL": lambda: nz(S.SorguMaliyetTL.sum()) if len(S) else np.nan,
        "Olu Sorgu Maliyeti TL": lambda: S.loc[S.SorguSonucu == "Aksiyon Yok", "SorguMaliyetTL"].sum() or np.nan,
        "Cuzdan Payi": lambda: bol(S.BizimRisk.sum(), S.SektorToplamRisk.sum()),
        "Payi Eriyen Musteri": lambda: nz(onc[onc.BizimPay - onc.OncekiBizimPay < -0.05].VKN.nunique()) or np.nan,
        "Yeni Gecikme Sinyali": lambda: onc[(onc.GecikmeVar == 1) & (onc.OncekiGecikmeVar == 0)].VKN.nunique()
        or np.nan,
        "Yeni Takip Gecisi": lambda: onc[(onc.TakipVar == 1) & (onc.OncekiTakipVar == 0)].VKN.nunique() or np.nan,
        "Mukerrer Sorgu (7 gun)": lambda: (S.SorgularArasiGun <= 7).sum() or np.nan,
        "Ortalama Sorgudan Kullandirima Gun": lambda: (
            (K.KullandirimTarihi - K.SorguTarihi).dt.days.dropna().mean()),
        "Kor Nokta Musteri": lambda: len(set(K[K.BizimRisk > 0].VKN) - set(S.VKN)),
        "Kor Nokta Risk TL": lambda: K[(K.Tarih == K.Tarih.max()) & ~K.VKN.isin(S.VKN)].BizimRisk.sum(),
        "Sektor Risk TL": lambda: S.SektorToplamRisk.sum() if len(S) else np.nan,
        "Bizim Risk Artisi": lambda: (onc.BizimRisk - onc.OncekiBizimRisk).sum(),
        "Sektor Risk Artisi": lambda: (onc.SektorToplamRisk - onc.OncekiSektorToplamRisk).sum(),
        "Rakip Risk Artisi": lambda: olcu("Sektor Risk Artisi", c) - olcu("Bizim Risk Artisi", c),
        "Kopru Deger": lambda: {1: olcu("Bizim Risk Artisi", c), 2: olcu("Rakip Risk Artisi", c)}.get(
            c.get("Risk Kopru"), np.nan),
        "Sektor Risk Buyumesi %": lambda: bol(olcu("Sektor Risk Artisi", c), onc.OncekiSektorToplamRisk.sum()),
        "Not Degisimi Ort": lambda: (onc.KKBNot - onc.OncekiKKBNot).mean(),
        "Ortalama Limit Doluluk": lambda: bol(S.SektorToplamRisk.sum(), S.SektorToplamLimit.sum()),
        "Risk Detay TL": lambda: R.Risk.sum() if len(R) else np.nan,
        "Pay Degisimi": lambda: (onc.BizimPay - onc.OncekiBizimPay).mean(),
        "Yedek Banka Endeksi": lambda: (S.DigerBankaDoluluk - S.BizimDoluluk).mean(),
        "Rakip Ortalama Limit": lambda: ((S.SektorToplamLimit - S.BizimLimit) / (S.BankaSayisi - 1))[
            S.BankaSayisi > 1].mean(),
        "Bizim Limit / Rakip Limit": lambda: bol(S.BizimLimit.mean(), olcu("Rakip Ortalama Limit", c)),
        "Ana Banka Orani %": lambda: bol(S[S.BizimPay >= 1.5 / S.BankaSayisi].VKN.nunique(), S.VKN.nunique()),
        "Ret Sonrasi Buyuyen %": lambda: _ret(S, "buyume"),
        "Ret Sonrasi Gecikme %": lambda: _ret(S, "gecikme"),
        "Anomali Skoru (son sorgu)": lambda: A[A.SonSorguMu == 1].Skor.max(),
        "Anomali Nedeni (son)": lambda: _neden(A),
        "Ortalama Anomali Skoru": lambda: A.Skor.mean(),
        "Yuksek Anomali Musteri": lambda: A[(A.SonSorguMu == 1) & (A.Skor >= 70)].VKN.nunique(),
        "Skor70 Sonraki Gecikme %": lambda: A[(A.Skor >= 70) & (A.GecikmeVar == 0)].SonrakiGecikmeVar.mean(),
        "Diger Sonraki Gecikme %": lambda: A[(A.Skor < 70) & (A.GecikmeVar == 0)].SonrakiGecikmeVar.mean(),
        "Ortalama KKB Not": lambda: S.KKBNot.mean(),
        "Ortalama Ic Rating": lambda: K.IcRating.mean(),
        "Aksiyon Musteri": lambda: son.VKN.nunique() or np.nan,
        "Potansiyel TL (son)": lambda: son["Potansiyel TL"].sum() if len(son) else np.nan,
        "Bizim Risk (son)": lambda: son.BizimRisk.sum() if len(son) else np.nan,
        "Son Sorgu Tarihi": lambda: son.SorguTarihi.max() if len(son) else np.nan,
        "Anomali Skoru (aksiyon)": lambda: olcu("Anomali Skoru (son sorgu)", c) if len(son) else np.nan,
        "Ozet Cumle": lambda: _ozet(c),
        "Huni Deger": lambda: _huni(c),
    }
    return f[ad]()


def _ret(S, tur):
    t = S[S.SorguSonucu.isin(["Ret", "Teklif"])]
    if tur == "buyume":
        t = t[t.SonrakiSektorToplamRisk.notna()]
        return bol((t.SonrakiSektorToplamRisk > t.SektorToplamRisk * 1.1).sum(), len(t))
    t = t[t.SonrakiGecikmeVar.notna() & (t.GecikmeVar == 0)]
    return bol((t.SonrakiGecikmeVar == 1).sum(), len(t))


def _neden(A):
    a = A[A.SonSorguMu == 1]
    if a.empty:
        return np.nan
    return a[a.Skor == a.Skor.max()].Neden.max()


def _huni(c):
    S = c["Fact_Sorgu"]
    bas = S[S.SorguNedeni.isin(["Yeni Basvuru", "Limit Yenileme"])]
    return {1: len(bas), 2: bas.SorguSonucu.isin(["Teklif", "Ret", "Kullandirim"]).sum(),
            3: (bas.SorguSonucu == "Kullandirim").sum()}.get(c.get("Huni Asama"), np.nan)


def _ozet(c):
    v = lambda ad: tr_sayi(olcu(ad, c), "#,0")  # noqa: E731
    return (f"Bu dönemde {v('Tekil Musteri')} müşteriye {v('Sorgu Adedi')} sorgu attık. "
            f"{v('Payi Eriyen Musteri')} müşteride payımız eridi, {v('Yeni Gecikme Sinyali')} müşteride yeni "
            f"gecikme sinyali var. Aksiyonsuz sorguların maliyeti {v('Olu Sorgu Maliyeti TL')} TL; "
            f"{v('Kor Nokta Musteri')} riskli müşteriye hiç bakmadık.")


# --------------------------------------------------------------------------------------
# Bicimlendirme
# --------------------------------------------------------------------------------------

def tr_sayi(v, fmt, kisa=False):
    if _bos(v):
        return "(Boş)"
    if isinstance(v, str):
        return v
    if isinstance(v, pd.Timestamp):
        return v.strftime("%d.%m.%Y")
    if fmt and "%" in fmt:
        return "%" + f"{v * 100:.1f}".replace(".", ",")
    if kisa and abs(v) >= 1e6 or kisa == "hep" and abs(v) >= 1e3:
        for esik, ek in ((1e9, " Mr"), (1e6, " Mn"), (1e3, " B")):
            if abs(v) >= esik:
                return f"{v / esik:.1f}".replace(".", ",") + ek
    if fmt in ("0.00",):
        return f"{v:.2f}".replace(".", ",")
    if fmt in ("0.0",):
        return f"{v:.1f}".replace(".", ",")
    return f"{v:,.0f}".replace(",", ".")


def eksen_bicimi(fmt):
    return matplotlib.ticker.FuncFormatter(lambda v, _: tr_sayi(v, fmt, kisa=True))


GORUNEN = {  # model adlari ASCII; gorunumde Turkce karakterle yaz
    "İlk sorgu": "İlk sorgu", "Arttı": "Arttı", "Azaldı": "Azaldı", "Aynı": "Aynı", "Yükseldi": "Yükseldi",
    "Düştü": "Düştü", "Rakip büyütüyor": "Rakip büyütüyor", "Birlikte büyüyoruz": "Birlikte büyüyoruz",
    "Sessiz çıkış": "Sessiz çıkış", "Ana bankaya dönüşüyoruz": "Ana bankaya dönüşüyoruz",
    "Erken uyarı": "Erken uyarı", "Kredi açlığı": "Kredi açlığı", "Limit sıkışıklığı": "Limit sıkışıklığı",
    "Proje büyümesi": "Proje büyümesi", "Gereksiz sorgu": "Gereksiz sorgu", "Pay geri kazan": "Pay geri kazan",
    "Ay sonu (son 5 gun)": "Ay sonu (son 5 gün)", "Ay ici": "Ay içi", "Yeni Basvuru": "Yeni başvuru",
    "Limit Yenileme": "Limit yenileme", "Periyodik Izleme": "Periyodik izleme",
    "Tahsis Revizyonu": "Tahsis revizyonu", "Kullandirim": "Kullandırım", "Izleme": "İzleme",
    "Aksiyon Yok": "Aksiyon yok", "1. Başvuru sorgusu": "1. Başvuru sorgusu",
    "3. Kullandırım": "3. Kullandırım", "Bizim finanse ettiğimiz": "Bizim finanse ettiğimiz",
    "Rakiplerin finanse ettiği": "Rakiplerin finanse ettiği", "Imalat": "İmalat", "Insaat": "İnşaat",
    "Ulastirma ve depolama": "Ulaştırma ve depolama", "Mesleki ve teknik faaliyetler": "Mesleki ve teknik",
    "Toptan ve perakende ticaret": "Toptan ve perakende", "Bilgi ve iletisim": "Bilgi ve iletişim",
    "Ic Anadolu": "İç Anadolu", "Guneydogu": "Güneydoğu", "KOBI": "KOBİ",
    "Teminat Mektubu": "Teminat mektubu",
}
GORUNEN_OLCU = {
    "Sorgu Adedi": "Sorgu adedi", "Tekil Musteri": "Tekil müşteri", "Sorgu Donusum %": "Dönüşüm %",
    "Olu Sorgu Orani %": "Ölü sorgu %", "Olu Sorgu Maliyeti TL": "Ölü sorgu TL",
    "Sektor Risk Buyumesi %": "Risk büyümesi", "Not Degisimi Ort": "Not değ.",
    "Anomali Skoru (son sorgu)": "Skor", "Anomali Nedeni (son)": "Neden", "Bizim Risk (son)": "Bizim risk",
    "Potansiyel TL (son)": "Potansiyel TL", "Anomali Skoru (aksiyon)": "Skor", "Son Sorgu Tarihi": "Son sorgu",
    "Ret Sonrasi Buyuyen %": "Sonra büyüyen %", "Ret Sonrasi Gecikme %": "Sonra gecikmeye düşen %",
    "Unvan": "Müşteri", "Pay Degisimi": "Pay değişimi", "Ortalama KKB Not": "Ortalama KKB notu",
    "Ortalama Ic Rating": "Ortalama iç rating", "Segment": "Segment", "PortfoyYoneticisi": "Portföy yön.", "Aksiyon Etiketi": "Etiket",
    "SubeAdi": "Şube", "Ozet Cumle": "Özet",
}


def gor(x):
    return GORUNEN.get(x, x) if isinstance(x, str) else x


# --------------------------------------------------------------------------------------
# Gorsel cizimi
# --------------------------------------------------------------------------------------

def alanlar(v, rol):
    st = v["visual"].get("query", {}).get("queryState", {}).get(rol)
    if not st:
        return []
    out = []
    for p in st["projections"]:
        tur = "Measure" if "Measure" in p["field"] else "Column"
        e = p["field"][tur]
        out.append((tur, e["Expression"]["SourceRef"]["Entity"], e["Property"]))
    return out


def baslik(v):
    try:
        return v["visual"]["visualContainerObjects"]["title"][0]["properties"]["text"]["expr"]["Literal"][
            "Value"].strip("'")
    except KeyError:
        return None


def haric(v, ctx):
    for f in v.get("filterConfig", {}).get("filters", []):
        col = f["field"]["Column"]
        tablo, sutun = col["Expression"]["SourceRef"]["Entity"], col["Property"]
        cond = f["filter"]["Where"][0]["Condition"]["Not"]["Expression"]["In"]
        degerler = [x[0]["Literal"]["Value"].strip("'") for x in cond["Values"]]
        ctx = filtrele(ctx, tablo, sutun, degerler, haric=True)
    return ctx


def kategoriler(ctx, tablo, sutun):
    if tablo == "Huni Asama":
        return [1, 2, 3], ["1. Başvuru sorgusu", "2. Teklif / karar", "3. Kullandırım"]
    if tablo == "Risk Kopru":
        return [1, 2], ["Bizim finanse ettiğimiz", "Rakiplerin finanse ettiği"]
    vals = set()
    for f in FILTRELER.get(tablo, []):
        if sutun in ctx[f].columns:
            vals |= set(ctx[f][sutun].dropna().unique())
    vals = sorted(vals)
    return vals, vals


def tablo_verisi(ctx, kolonlar, olculer):
    """Kolon kombinasyonlari x olculer; tum olculeri bos olan satirlar Power BI'daki gibi gizlenir."""
    if not kolonlar:
        return pd.DataFrame([{m[2]: olcu(m[2], ctx) for m in olculer}])
    anahtar_df = None
    for _, tablo, sutun in kolonlar:
        kaynak = ctx["Fact_Sorgu"] if sutun in ctx["Fact_Sorgu"].columns else ctx["Fact_AnomaliSkor"]
        anahtar_df = kaynak[[c[2] for c in kolonlar]].drop_duplicates() if anahtar_df is None else anahtar_df
    satirlar = []
    for anahtar in anahtar_df.itertuples(index=False):
        c = ctx
        for (_, tablo, sutun), deger in zip(kolonlar, anahtar):
            c = filtrele(c, tablo, sutun, deger)
        sat = dict(zip([k[2] for k in kolonlar], anahtar))
        sat.update({m[2]: olcu(m[2], c) for m in olculer})
        if not all(_bos(sat[m[2]]) for m in olculer):
            satirlar.append(sat)
    return pd.DataFrame(satirlar)


def kart_ciz(ax_kart, v, ctx, sekil, rect):
    m = alanlar(v, "Values")[0]
    deger = olcu(m[2], ctx)
    x, y, w, h = rect
    sekil.text(x + w / 2, y + h * 0.42, tr_sayi(deger, BICIM.get(m[2]), kisa=True), ha="center", va="center",
               fontsize=19, color=INK, transform=sekil.transFigure)


def eksen_hazirla(ax, yatay=False):
    ax.set_facecolor(KART_ZEMIN)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left" if yatay else "bottom"].set_color(AXIS)
    ax.spines["bottom" if yatay else "left"].set_visible(False)
    ax.grid(axis="x" if yatay else "y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, labelsize=7)


def sar(s, n=14):
    import textwrap
    return "\n".join(textwrap.wrap(str(gor(s)), n)[:2])


def etiket_kisalt(s, n=18):
    s = str(gor(s))
    return s if len(s) <= n else s[: n - 1] + "…"


def gorsel_ciz(fig, v, ctx, secim):
    pos = v["position"]
    tip = v["visual"]["visualType"]
    X, Y, W, H = pos["x"], pos["y"], pos["width"], pos["height"]
    fx, fy, fw, fh = X / 1280, 1 - (Y + H) / 720, W / 1280, H / 720
    if tip == "textbox":
        par = v["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
        fig.text(fx + 14 / 1280, 1 - (Y + 30) / 720, par[0]["textRuns"][0]["value"], fontsize=17, fontweight="bold",
                 color=INK, va="baseline")
        if len(par) > 1:
            fig.text(fx + 14 / 1280, 1 - (Y + 52) / 720, par[1]["textRuns"][0]["value"], fontsize=9.5, color=INK2,
                     va="baseline")
        return
    fig.patches.append(FancyBboxPatch((fx + 2 / 1280, fy + 2 / 720), fw - 4 / 1280, fh - 4 / 720,
                                      boxstyle="round,pad=0,rounding_size=0.004", transform=fig.transFigure,
                                      facecolor=KART_ZEMIN, edgecolor="#dcdad3", linewidth=0.6,
                                      zorder=-10))
    b = baslik(v)
    ust = 22 if b else 6
    if b:
        fig.text(fx + 10 / 1280, 1 - (Y + 18) / 720, b, fontsize=8.5, fontweight="bold", color=INK, va="baseline")
    ctx = haric(v, ctx)
    if v["name"] in secim:  # sayfaya ozel dilimleyici secimi (orn. 5. sayfada musteri)
        tablo, sutun, deger = secim[v["name"]]
        ctx = filtrele(ctx, tablo, sutun, deger)

    if tip == "card":
        kart_ciz(None, v, ctx, fig, (fx, fy, fw, fh - ust / 720))
        return
    if tip == "slicer":
        sel = next((d for k, (t, s_, d) in secim.items() if k.startswith("_slicer_") and k[8:] == v["name"]), None)
        metin = gor(sel) if sel else "Tümü"
        fig.patches.append(Rectangle((fx + 10 / 1280, fy + 8 / 720), fw - 20 / 1280, 22 / 720,
                                     transform=fig.transFigure, facecolor="#fafaf8", edgecolor=AXIS, linewidth=0.6,
                                     zorder=-5))
        fig.text(fx + 16 / 1280, fy + 15 / 720, metin, fontsize=8, color=INK, va="baseline")
        fig.text(fx + fw - 22 / 1280, fy + 15 / 720, "▾", fontsize=9, color=INK2, va="baseline")
        return

    lejant = bool(alanlar(v, "Series")) or len(alanlar(v, "Y")) > 1
    sol, alt, sag, ust_bos = 12, 10, 12, ust + 6 + (18 if lejant else 0)
    if tip in ("tableEx", "pivotTable"):
        ax = fig.add_axes([fx + 8 / 1280, fy + 6 / 720, fw - 16 / 1280, fh - (ust + 10) / 720])
        ax.axis("off")
        tablo_ciz(ax, v, ctx, tip)
        return
    yatay = tip in ("clusteredBarChart", "stackedBarChart", "funnel")
    sol_pay = 118 if yatay else 46
    ax = fig.add_axes([fx + sol_pay / 1280, fy + (alt + (18 if not yatay else 6)) / 720,
                       fw - (sol_pay + sag) / 1280, fh - (ust_bos + alt + (18 if not yatay else 6) + 4) / 720])
    eksen_hazirla(ax, yatay)
    grafik_ciz(ax, v, ctx, tip)


def grafik_ciz(ax, v, ctx, tip):
    kat = alanlar(v, "Category")
    ys = alanlar(v, "Y")
    seri = alanlar(v, "Series")
    if tip == "scatterChart":
        return dagilim_ciz(ax, v, ctx)
    _, kt, ks = kat[0]
    anahtarlar, etiketler = kategoriler(ctx, kt, ks)
    if seri:
        _, st, ss = seri[0]
        s_anahtar, _ = kategoriler(ctx, st, ss)
        mat = np.array([[olcu(ys[0][2], filtrele(filtrele(ctx, kt, ks, a), st, ss, b)) for b in s_anahtar]
                        for a in anahtarlar], dtype=float)
        mat = np.nan_to_num(mat)
        if tip == "hundredPercentStackedColumnChart":
            mat = mat / np.where(mat.sum(1, keepdims=True) == 0, 1, mat.sum(1, keepdims=True))
        tut = mat.sum(1) > 0
        mat, etiketler = mat[tut], [e for e, t in zip(etiketler, tut) if t]
        x = np.arange(len(etiketler))
        alt = np.zeros(len(etiketler))
        for j, b in enumerate(s_anahtar):
            renk = SERI[j % len(SERI)]
            if tip == "stackedBarChart":
                ax.barh(x, mat[:, j], left=alt, color=renk, height=0.62, edgecolor=KART_ZEMIN, linewidth=1,
                        label=gor(b))
            else:
                ax.bar(x, mat[:, j], bottom=alt, color=renk, width=0.7, edgecolor=KART_ZEMIN, linewidth=1,
                       label=gor(b))
            alt += mat[:, j]
        if tip == "stackedBarChart":
            ax.set_yticks(x, [etiket_kisalt(e) for e in etiketler])
            ax.invert_yaxis()
            ax.xaxis.set_major_formatter(eksen_bicimi(BICIM.get(ys[0][2])))
        else:
            ax.set_xticks(x, [etiket_kisalt(e, 7) for e in etiketler], rotation=0)
            ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0)
                                         if tip.startswith("hundred") else eksen_bicimi(BICIM.get(ys[0][2])))
        ax.legend(fontsize=6.5, frameon=False, ncol=min(len(s_anahtar), 5), loc="lower left",
                  bbox_to_anchor=(-0.02, 1.02), handlelength=1, columnspacing=0.8, borderaxespad=0)
        return

    degerler = np.array([[olcu(m[2], filtrele(ctx, kt, ks, a)) for m in ys] for a in anahtarlar], dtype=float)
    tut = ~np.all(np.isnan(degerler), axis=1)
    degerler, etiketler = degerler[tut], [e for e, t in zip(etiketler, tut) if t]
    x = np.arange(len(etiketler))
    fmt = BICIM.get(ys[0][2])
    if tip == "lineChart":
        ax.plot(x, degerler[:, 0], color=SERI[0], linewidth=2, marker="o", markersize=3.5)
        adim = 2 if ax.bbox.width / max(len(x), 1) < 60 else 1
        ax.set_xticks(x[::adim], [str(e)[2:] if str(e)[:2] == "20" else etiket_kisalt(e, 8)
                                  for e in etiketler][::adim])
        ax.yaxis.set_major_formatter(eksen_bicimi(fmt))
        ax.margins(x=0.03)
        if len(x):
            ax.annotate(tr_sayi(degerler[-1, 0], fmt, kisa=True), (x[-1], degerler[-1, 0]), xytext=(0, 6),
                        textcoords="offset points", ha="center", fontsize=7, color=INK2)
    elif tip == "clusteredColumnChart":
        n = degerler.shape[1]
        gen = 0.7 / n
        for j in range(n):
            ax.bar(x + (j - (n - 1) / 2) * gen, np.nan_to_num(degerler[:, j]), width=gen * 0.92, color=SERI[j],
                   label=GORUNEN_OLCU.get(ys[j][2], ys[j][2]))
            if len(x) <= 8:
                for xi, d in zip(x, degerler[:, j]):
                    if not np.isnan(d):
                        ax.text(xi + (j - (n - 1) / 2) * gen, d, tr_sayi(d, BICIM.get(ys[j][2]), kisa=True),
                                ha="center", va="bottom", fontsize=6.5, color=INK2)
        n_kar = max(6, int(ax.bbox.width / max(len(x), 1) / 12))
        ax.set_xticks(x, [str(e)[2:] if str(e)[:2] == "20" and len(x) > 8 else sar(e, n_kar)
                          for e in etiketler], fontsize=6.5 if len(x) > 8 else 7)
        ax.yaxis.set_major_formatter(eksen_bicimi(fmt))
        if n > 1:
            ax.legend(fontsize=6.5, frameon=False, ncol=n, loc="lower left", bbox_to_anchor=(-0.02, 1.02),
                      handlelength=1, borderaxespad=0)
    elif tip == "clusteredBarChart":
        sira = np.argsort(-np.nan_to_num(degerler[:, 0]))
        degerler, etiketler = degerler[sira], [etiketler[i] for i in sira]
        ax.barh(x, np.nan_to_num(degerler[:, 0]), color=SERI[0], height=0.62)
        ax.set_yticks(x, [etiket_kisalt(e, 20) for e in etiketler])
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(eksen_bicimi(fmt))
        for xi, d in zip(x, degerler[:, 0]):
            ax.text(d, xi, " " + tr_sayi(d, fmt, kisa=True), va="center", fontsize=6.5, color=INK2)
        ax.margins(x=0.15)
    elif tip == "funnel":
        d = np.nan_to_num(degerler[:, 0])
        ax.barh(x, d, left=(d.max() - d) / 2, color=SERI[0], height=0.66)
        for xi, di in zip(x, d):
            ax.text(d.max() / 2, xi, f"{tr_sayi(di, '#,0')}  ({tr_sayi(di / d[0], '0.0%')})", ha="center",
                    va="center", fontsize=8, color="white", fontweight="bold")
        ax.set_yticks(x, [gor(e) for e in etiketler])
        ax.invert_yaxis()
        ax.set_xticks([])
        ax.grid(False)
        ax.spines["left"].set_visible(False)
    elif tip == "waterfallChart":
        d = np.nan_to_num(degerler[:, 0])
        bas = np.concatenate([[0], np.cumsum(d)[:-1]])
        renk = [SERI[0] if di >= 0 else SERI[7] for di in d]
        ax.bar(x, d, bottom=bas, color=renk, width=0.6)
        ax.bar(len(d), d.sum(), color="#898781", width=0.6)
        for xi, (b0, di) in enumerate(zip(bas, d)):
            ax.text(xi, b0 + di, tr_sayi(di, fmt, kisa=True), ha="center", va="bottom", fontsize=7, color=INK2)
        ax.text(len(d), d.sum(), tr_sayi(d.sum(), fmt, kisa=True), ha="center", va="bottom", fontsize=7,
                color=INK2)
        ax.set_xticks(list(x) + [len(d)], ["Bizim", "Rakipler", "Toplam artış"])
        ax.yaxis.set_major_formatter(eksen_bicimi(fmt))


def dagilim_ciz(ax, v, ctx):
    _, kt, ks = alanlar(v, "Category")[0]
    mx, my = alanlar(v, "X")[0][2], alanlar(v, "Y")[0][2]
    boy = alanlar(v, "Size")
    df = tablo_verisi(ctx, [("Column", kt, ks)], [("Measure", "", mx), ("Measure", "", my)] +
                      ([("Measure", "", boy[0][2])] if boy else [])).dropna(subset=[mx, my])
    if boy:
        sz = df[boy[0][2]].astype(float)
        s = 12 + 220 * (sz / sz.max()) ** 0.5
    else:
        s = 14
    ax.scatter(df[mx], df[my], s=s, color=SERI[0], alpha=0.55, edgecolor=KART_ZEMIN, linewidth=0.6)
    ax.xaxis.set_major_formatter(eksen_bicimi(BICIM.get(mx)))
    ax.yaxis.set_major_formatter(eksen_bicimi(BICIM.get(my)))
    ax.grid(axis="both", color=GRID, linewidth=0.6)
    ax.set_xlabel(GORUNEN_OLCU.get(mx, mx), fontsize=7, color=MUTED)
    ax.set_ylabel(GORUNEN_OLCU.get(my, my), fontsize=7, color=MUTED)
    if mx == "Pay Degisimi":  # cuzdan matrisi: sifir cizgileri ve bolge adlari
        ax.axvline(0, color=AXIS, linewidth=1)
        ax.axhline(0, color=AXIS, linewidth=1)
        xl, yl = ax.get_xlim(), ax.get_ylim()
        for tx, ty, t in ((xl[0], yl[1], "Rakip büyütüyor"), (xl[1], yl[1], "Birlikte büyüyoruz"),
                          (xl[0], yl[0], "Sessiz çıkış"), (xl[1], yl[0], "Ana bankaya dönüşüyoruz")):
            ax.text(tx, ty, t, ha="left" if tx == xl[0] else "right", va="top" if ty == yl[1] else "bottom",
                    fontsize=7.5, color=INK2, fontweight="bold")


def tablo_ciz(ax, v, ctx, tip):
    if tip == "pivotTable":
        r, c, val = alanlar(v, "Rows")[0], alanlar(v, "Columns")[0], alanlar(v, "Values")[0]
        satir, _ = kategoriler(ctx, r[1], r[2])
        sutun, _ = kategoriler(ctx, c[1], c[2])
        mat = np.array([[olcu(val[2], filtrele(filtrele(ctx, r[1], r[2], a), c[1], c[2], b)) for b in sutun]
                        for a in satir], dtype=float)
        tut = ~np.all(np.isnan(mat), axis=1)
        mat, satir = mat[tut], [s for s, t in zip(satir, tut) if t]
        etik = [f"{a}. hafta" if r[2] == "AyinHaftasi" else str(gor(a)) for a in satir]
        ilk = max(1.6, min(3.2, max(len(e) for e in etik) * 0.12)) if etik else 1.6
        nr, nc = len(satir) + 1, len(sutun) + 1
        ax.set_xlim(0, len(sutun) + ilk)
        ax.set_ylim(nr, 0)
        vmin, vmax = np.nanmin(mat), np.nanmax(mat)
        fmt = BICIM.get(val[2])
        for j, b in enumerate(sutun):
            ax.text(j + ilk + 0.5, 0.5, str(gor(b)).replace("-", "\n") if c[2] == "Yil Ceyrek" else etiket_kisalt(b, 9), ha="center", va="center", fontsize=6.5,
                    fontweight="bold", color=INK2)
        for i, a in enumerate(satir):
            ax.text(0.05, i + 1.5, etiket_kisalt(etik[i], int(ilk * 8)), ha="left", va="center", fontsize=6.5,
                    color=INK)
            for j in range(len(sutun)):
                d = mat[i, j]
                if not np.isnan(d):
                    t = 0 if vmax == vmin else (d - vmin) / (vmax - vmin)
                    renk = SIRALI[min(int(t * (len(SIRALI) - 1) + 0.5), len(SIRALI) - 1)]
                    ax.add_patch(Rectangle((j + ilk + 0.04, i + 1.04), 0.92, 0.92, facecolor=renk, edgecolor="none"))
                    ax.text(j + ilk + 0.5, i + 1.5, tr_sayi(d, fmt, kisa=True), ha="center", va="center",
                            fontsize=6.5, color="white" if t > 0.55 else INK)
        return

    vals = alanlar(v, "Values")
    kolonlar = [f for f in vals if f[0] == "Column"]
    olculer = [f for f in vals if f[0] == "Measure"]
    df = tablo_verisi(ctx, kolonlar, olculer)
    srt = v["visual"]["query"].get("sortDefinition", {}).get("sort")
    if srt and not df.empty:
        alan = srt[0]["field"]
        ad = (alan.get("Measure") or alan.get("Column"))["Property"]
        df = df.sort_values(ad, ascending=srt[0]["direction"] == "Ascending", na_position="last")
    basliklar = [GORUNEN_OLCU.get(f[2], f[2]) for f in vals]
    satir_h = 15
    maks = max(int(ax.bbox.height / (satir_h * ax.figure.dpi / 100)) - 2, 1)
    if len(df) > maks:
        maks -= 1  # son satir "ilk N / toplam" notuna ayrilir
    if olculer and olculer[0][2] == "Ozet Cumle":
        import textwrap
        ax.text(0.01, 0.95, textwrap.fill(df.iloc[0, 0], 62), ha="left", va="top", fontsize=8, color=INK,
                transform=ax.transAxes, linespacing=1.5)
        return
    genislik = [3.2 if f[2] in ("Unvan", "Anomali Nedeni (son)", "SubeAdi") else
                2.0 if f[2] in ("Aksiyon Etiketi", "PortfoyYoneticisi") else 1.6 for f in vals]
    toplam = sum(genislik)
    xs = np.cumsum([0] + genislik[:-1]) / toplam
    ax.set_xlim(0, 1)
    ax.set_ylim(maks + (2.2 if len(df) > maks else 1.2), 0)
    for xx, bb, f in zip(xs, basliklar, vals):
        ax.text(xx + 0.005, 0.5, bb, fontsize=6.8, fontweight="bold", color=INK2, va="center",
                ha="left" if f[0] == "Column" or f[2] == "Anomali Nedeni (son)" else "left")
    ax.axhline(1, color=AXIS, linewidth=0.8)
    for i, (_, sat) in enumerate(df.head(maks).iterrows()):
        if i % 2:
            ax.add_patch(Rectangle((0, i + 1), 1, 1, facecolor="#f7f6f3", edgecolor="none"))
        for xx, f, g in zip(xs, vals, genislik):
            d = sat[f[2]]
            metin = gor(d) if f[0] == "Column" else tr_sayi(d, BICIM.get(f[2]), kisa="TL" in f[2]
                                                              or "Risk" in f[2])
            n = int(g * 9.5)
            ax.text(xx + 0.005, i + 1.55, etiket_kisalt(metin, n), fontsize=6.6, color=INK, va="center")
    if len(df) > maks:
        ax.text(0.995, maks + 1.6, f"İlk {maks} satır gösteriliyor (toplam {len(df)})", fontsize=6.2,
                color=MUTED, ha="right", va="center")


def sayfa_listesi():
    sira = json.loads((RAPOR / "pages" / "pages.json").read_text("utf-8"))["pageOrder"]
    out = []
    for ad in sira:
        p = json.loads((RAPOR / "pages" / ad / "page.json").read_text("utf-8"))
        gorseller = [json.loads(f.read_text("utf-8")) for f in (RAPOR / "pages" / ad / "visuals").glob("*/visual.json")]
        gorseller.sort(key=lambda g: g["position"]["z"])
        out.append((p, gorseller))
    return out


def sayfa_ciz(p, gorseller, veri, yol, secim):
    fig = plt.figure(figsize=(12.8, 7.2), dpi=200)
    fig.patch.set_facecolor(SAYFA_ZEMIN)
    for g in gorseller:
        gorsel_ciz(fig, g, veri, secim)
    fig.savefig(yol, facecolor=SAYFA_ZEMIN)
    plt.close(fig)


def sayfa_secimleri(veri):
    """5. sayfada ornek olarak en yuksek skorlu musteriyi sec (dilimleyici yalnizca seri grafiklerini filtreler)."""
    a = veri["Fact_AnomaliSkor"]
    en = a[a.SonSorguMu == 1].sort_values("Skor", ascending=False).Unvan.iloc[0]
    return {"p5_uyari": {"seri": ("Dim_Musteri", "Unvan", en), "seridol": ("Dim_Musteri", "Unvan", en),
                         "_slicer_musteri": ("Dim_Musteri", "Unvan", en)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="docs")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    veri = yukle(args.data)
    secimler = sayfa_secimleri(veri)
    for i, (p, gorseller) in enumerate(sayfa_listesi(), 1):
        yol = out / f"sayfa_{i}_{p['name']}.png"
        sayfa_ciz(p, gorseller, veri, yol, secimler.get(p["name"], {}))
        print("yazildi:", yol)


if __name__ == "__main__":
    main()
