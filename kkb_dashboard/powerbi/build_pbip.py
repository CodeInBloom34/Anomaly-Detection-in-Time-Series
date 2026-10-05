"""KKB Kurumsal Sorgu Analitigi Power BI projesini (PBIP) uretir.

Cikti, Power BI Desktop'ta dogrudan acilabilen metin tabanli bir projedir:

    KKB_Sorgu_Analitigi.pbip                 <- Desktop'ta bu dosyayi acin
    KKB_Sorgu_Analitigi.SemanticModel/       <- veri modeli (model.bim)
    KKB_Sorgu_Analitigi.Report/              <- 6 rapor sayfasi (PBIR formati)

Tablo/sutun listesi, ornek veri ureticisinin ciktisindan cikarilir; boylece CSV'ler
ile model her zaman uyumlu kalir. Olculer bu dosyada tanimlidir ve measures.dax
dosyasi da buradan yeniden yazilir.

Kullanim (kkb_dashboard klasorunden):
    python powerbi/build_pbip.py
"""

import json
import shutil
import sys
import uuid
from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK.parent))

import generate_sample_data as gen  # noqa: E402
from anomaly_score import skorla  # noqa: E402

PROJE = "KKB_Sorgu_Analitigi"
VARSAYILAN_VERI_KLASORU = r"C:\KKB\data"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
NS = uuid.UUID("6f1c2a52-3c1e-4d55-9a57-2f0a9b0e7c11")

# --------------------------------------------------------------------------------------
# Veri modeli
# --------------------------------------------------------------------------------------

TABLO_SIRASI = [
    "Dim_Tarih", "Dim_Sube", "Dim_Musteri", "Dim_NotBandi",
    "Fact_Sorgu", "Fact_RiskDetay", "Fact_KrediSonuc", "Fact_AnomaliSkor",
]
GIZLI_SUTUNLAR = {("Dim_Musteri", "_Senaryo")}
YUZDE_SUTUNLAR = {"BizimPay", "OncekiBizimPay", "BizimDoluluk", "DigerBankaDoluluk"}

ILISKILER = [
    # (cok taraf tablo, sutun, tek taraf tablo, sutun)
    ("Fact_Sorgu", "VKN", "Dim_Musteri", "VKN"),
    ("Fact_Sorgu", "SorguTarihi", "Dim_Tarih", "Tarih"),
    ("Fact_Sorgu", "SubeKod", "Dim_Sube", "SubeKod"),
    ("Fact_Sorgu", "NotBandi", "Dim_NotBandi", "Bant"),
    ("Fact_RiskDetay", "SorguID", "Fact_Sorgu", "SorguID"),
    ("Fact_KrediSonuc", "VKN", "Dim_Musteri", "VKN"),
    ("Fact_KrediSonuc", "Tarih", "Dim_Tarih", "Tarih"),
    ("Fact_AnomaliSkor", "VKN", "Dim_Musteri", "VKN"),
    ("Fact_AnomaliSkor", "SorguTarihi", "Dim_Tarih", "Tarih"),
]

HESAPLANMIS_SUTUNLAR = {
    "Dim_Tarih": [
        ("Ay Donemi", "string",
         'IF ( Dim_Tarih[AySonuMu] = 1, "Ay sonu (son 5 gün)", "Ay içi" )'),
        ("Gun Adi", "string",
         'SWITCH ( Dim_Tarih[HaftaninGunu], 1, "1 Pzt", 2, "2 Sal", 3, "3 Çar", 4, "4 Per", '
         '5, "5 Cum", 6, "6 Cmt", "7 Paz" )'),
        ("Yil Ceyrek", "string", 'Dim_Tarih[Yil] & "-" & Dim_Tarih[Ceyrek]'),
    ],
    "Fact_Sorgu": [
        ("Tekrar Araligi", "string", """
SWITCH (
    TRUE (),
    ISBLANK ( Fact_Sorgu[SorgularArasiGun] ), "0) İlk sorgu",
    Fact_Sorgu[SorgularArasiGun] <= 7, "1) 0-7 gün",
    Fact_Sorgu[SorgularArasiGun] <= 30, "2) 8-30 gün",
    Fact_Sorgu[SorgularArasiGun] <= 90, "3) 31-90 gün",
    Fact_Sorgu[SorgularArasiGun] <= 180, "4) 91-180 gün",
    "5) 180+ gün"
)"""),
        ("Banka Degisimi", "string", """
VAR d = Fact_Sorgu[BankaSayisi] - Fact_Sorgu[OncekiBankaSayisi]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Fact_Sorgu[OncekiBankaSayisi] ), "İlk sorgu",
        d > 0, "Arttı",
        d < 0, "Azaldı",
        "Aynı"
    )"""),
        ("Not Degisimi", "string", """
VAR d = Fact_Sorgu[KKBNot] - Fact_Sorgu[OncekiKKBNot]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Fact_Sorgu[OncekiKKBNot] ), "İlk sorgu",
        d >= 50, "Yükseldi",
        d <= -50, "Düştü",
        "Aynı"
    )"""),
        ("Cuzdan Bolgesi", "string", """
VAR dPay = Fact_Sorgu[BizimPay] - Fact_Sorgu[OncekiBizimPay]
VAR dRisk = Fact_Sorgu[SektorToplamRisk] - Fact_Sorgu[OncekiSektorToplamRisk]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( Fact_Sorgu[OncekiBizimPay] ), "Tek sorgu",
        dRisk >= 0 && dPay < 0, "Rakip büyütüyor",
        dRisk >= 0, "Birlikte büyüyoruz",
        dPay < 0, "Sessiz çıkış",
        "Ana bankaya dönüşüyoruz"
    )"""),
        ("Aksiyon Etiketi", "string", """
VAR ilk = ISBLANK ( Fact_Sorgu[OncekiSorguID] )
VAR dPay = Fact_Sorgu[BizimPay] - Fact_Sorgu[OncekiBizimPay]
VAR dRisk = Fact_Sorgu[SektorToplamRisk] - Fact_Sorgu[OncekiSektorToplamRisk]
VAR dGn =
    DIVIDE ( Fact_Sorgu[GayrinakdiRisk], Fact_Sorgu[SektorToplamRisk] )
        - DIVIDE ( Fact_Sorgu[OncekiGayrinakdiRisk], Fact_Sorgu[OncekiSektorToplamRisk] )
VAR dNot = Fact_Sorgu[KKBNot] - Fact_Sorgu[OncekiKKBNot]
VAR dBanka = Fact_Sorgu[BankaSayisi] - Fact_Sorgu[OncekiBankaSayisi]
VAR skor =
    LOOKUPVALUE ( Fact_AnomaliSkor[Skor], Fact_AnomaliSkor[SorguID], Fact_Sorgu[SorguID] )
VAR doluluk = DIVIDE ( Fact_Sorgu[SektorToplamRisk], Fact_Sorgu[SektorToplamLimit] )
RETURN
    SWITCH (
        TRUE (),
        Fact_Sorgu[GecikmeVar] = 1, "Erken uyarı",
        Fact_Sorgu[TakipVar] = 1, "Erken uyarı",
        NOT ilk && skor >= 70 && dNot < 0, "Erken uyarı",
        NOT ilk && dBanka >= 2 && dNot < 0, "Kredi açlığı",
        NOT ilk && dRisk > 0 && dPay <= -0.05 && dNot >= 0, "Pay geri kazan",
        doluluk > 0.85 && Fact_Sorgu[BizimDoluluk] < 0.6
            && Fact_Sorgu[NotBandi] IN { "A", "B" }, "Limit sıkışıklığı",
        NOT ilk && dGn >= 0.10 && Fact_Sorgu[GecikmeVar] = 0, "Proje büyümesi",
        NOT ilk && Fact_Sorgu[SorgularArasiGun] <= 7, "Gereksiz sorgu",
        "İzle"
    )"""),
        # Kaba potansiyel tahmini: pilot sonrasi kalibre edilmelidir.
        ("Potansiyel TL", "double", """
SWITCH (
    Fact_Sorgu[Aksiyon Etiketi],
    "Pay geri kazan",
        MAX ( 0, ( Fact_Sorgu[OncekiBizimPay] - Fact_Sorgu[BizimPay] ) * Fact_Sorgu[SektorToplamRisk] ),
    "Limit sıkışıklığı",
        MAX ( 0, Fact_Sorgu[BizimLimit] - Fact_Sorgu[BizimRisk] ),
    "Proje büyümesi",
        MAX ( 0, ( Fact_Sorgu[GayrinakdiRisk] - Fact_Sorgu[OncekiGayrinakdiRisk] ) * Fact_Sorgu[OncekiBizimPay] ),
    0
)"""),
    ],
}

HESAPLANMIS_TABLOLAR = {
    "Huni Asama": (
        'DATATABLE ( "Sira", INTEGER, "Asama", STRING, '
        '{ { 1, "1. Başvuru sorgusu" }, { 2, "2. Teklif / karar" }, { 3, "3. Kullandırım" } } )',
        [("Sira", "int64"), ("Asama", "string")],
    ),
    "Risk Kopru": (
        'DATATABLE ( "Sira", INTEGER, "Kalem", STRING, '
        '{ { 1, "Bizim finanse ettiğimiz" }, { 2, "Rakiplerin finanse ettiği" } } )',
        [("Sira", "int64"), ("Kalem", "string")],
    ),
}

# (ev tablosu, ad, DAX, format, klasor)
OLCULER = [
    # Sayfa 1 - Yonetici ozeti
    ("Fact_Sorgu", "Sorgu Adedi", "COUNTROWS ( Fact_Sorgu )", "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Tekil Musteri", "DISTINCTCOUNT ( Fact_Sorgu[VKN] )", "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Musteri Basina Sorgu", "DIVIDE ( [Sorgu Adedi], [Tekil Musteri] )", "0.00", "1 Ozet"),
    ("Fact_Sorgu", "Basvuru Sorgusu",
     'CALCULATE ( [Sorgu Adedi], KEEPFILTERS ( Fact_Sorgu[SorguNedeni] IN { "Yeni Basvuru", "Limit Yenileme" } ) )',
     "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Sorgu Donusum %",
     'DIVIDE ( CALCULATE ( [Basvuru Sorgusu], KEEPFILTERS ( Fact_Sorgu[SorguSonucu] = "Kullandirim" ) ), [Basvuru Sorgusu] )',
     "0.0%", "1 Ozet"),
    ("Fact_Sorgu", "Olu Sorgu Orani %",
     'DIVIDE ( CALCULATE ( [Basvuru Sorgusu], KEEPFILTERS ( Fact_Sorgu[SorguSonucu] = "Aksiyon Yok" ) ), [Basvuru Sorgusu] )',
     "0.0%", "1 Ozet"),
    ("Fact_Sorgu", "Toplam Sorgu Maliyeti TL", "SUM ( Fact_Sorgu[SorguMaliyetTL] )", "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Olu Sorgu Maliyeti TL",
     'CALCULATE ( [Toplam Sorgu Maliyeti TL], KEEPFILTERS ( Fact_Sorgu[SorguSonucu] = "Aksiyon Yok" ) )',
     "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Cuzdan Payi",
     "DIVIDE ( SUM ( Fact_Sorgu[BizimRisk] ), SUM ( Fact_Sorgu[SektorToplamRisk] ) )", "0.0%", "1 Ozet"),
    ("Fact_Sorgu", "Payi Eriyen Musteri", """
CALCULATE (
    [Tekil Musteri],
    FILTER (
        Fact_Sorgu,
        NOT ISBLANK ( Fact_Sorgu[OncekiBizimPay] )
            && Fact_Sorgu[BizimPay] - Fact_Sorgu[OncekiBizimPay] < -0.05
    )
)""", "#,0", "1 Ozet"),
    # DAX'ta BLANK = 0 dogru doner; ilk sorgulari disarida tutmak icin ISBLANK kontrolu sart.
    ("Fact_Sorgu", "Yeni Gecikme Sinyali", """
CALCULATE (
    [Tekil Musteri],
    FILTER (
        Fact_Sorgu,
        Fact_Sorgu[GecikmeVar] = 1
            && NOT ISBLANK ( Fact_Sorgu[OncekiGecikmeVar] )
            && Fact_Sorgu[OncekiGecikmeVar] = 0
    )
)""", "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Yeni Takip Gecisi", """
CALCULATE (
    [Tekil Musteri],
    FILTER (
        Fact_Sorgu,
        Fact_Sorgu[TakipVar] = 1
            && NOT ISBLANK ( Fact_Sorgu[OncekiTakipVar] )
            && Fact_Sorgu[OncekiTakipVar] = 0
    )
)""", "#,0", "1 Ozet"),
    ("Fact_Sorgu", "Ozet Cumle", """
"Bu dönemde " & FORMAT ( [Tekil Musteri], "#,0" ) & " müşteriye " & FORMAT ( [Sorgu Adedi], "#,0" )
    & " sorgu attık. " & FORMAT ( [Payi Eriyen Musteri], "#,0" ) & " müşteride payımız eridi, "
    & FORMAT ( [Yeni Gecikme Sinyali], "#,0" ) & " müşteride yeni gecikme sinyali var. "
    & "Aksiyonsuz sorguların maliyeti " & FORMAT ( [Olu Sorgu Maliyeti TL], "#,0" ) & " TL; "
    & FORMAT ( [Kor Nokta Musteri], "#,0" ) & " riskli müşteriye hiç bakmadık."
""", None, "1 Ozet"),

    # Sayfa 2 - Sorgu davranisi
    ("Fact_Sorgu", "Huni Deger", """
SWITCH (
    SELECTEDVALUE ( 'Huni Asama'[Sira] ),
    1, [Basvuru Sorgusu],
    2, CALCULATE ( [Basvuru Sorgusu], KEEPFILTERS ( Fact_Sorgu[SorguSonucu] IN { "Teklif", "Ret", "Kullandirim" } ) ),
    3, CALCULATE ( [Basvuru Sorgusu], KEEPFILTERS ( Fact_Sorgu[SorguSonucu] = "Kullandirim" ) )
)""", "#,0", "2 Davranis"),
    ("Fact_Sorgu", "Mukerrer Sorgu (7 gun)",
     """
CALCULATE (
    [Sorgu Adedi],
    FILTER (
        Fact_Sorgu,
        NOT ISBLANK ( Fact_Sorgu[SorgularArasiGun] ) && Fact_Sorgu[SorgularArasiGun] <= 7
    )
)""", "#,0", "2 Davranis"),
    ("Fact_Sorgu", "Ortalama Sorgudan Kullandirima Gun", """
AVERAGEX (
    FILTER ( Fact_KrediSonuc, NOT ISBLANK ( Fact_KrediSonuc[KullandirimTarihi] ) ),
    DATEDIFF (
        LOOKUPVALUE ( Fact_Sorgu[SorguTarihi], Fact_Sorgu[SorguID], Fact_KrediSonuc[SorguID] ),
        Fact_KrediSonuc[KullandirimTarihi],
        DAY
    )
)""", "0.0", "2 Davranis"),
    ("Fact_Sorgu", "Kor Nokta Musteri", """
VAR riskli =
    CALCULATETABLE ( VALUES ( Fact_KrediSonuc[VKN] ), KEEPFILTERS ( Fact_KrediSonuc[BizimRisk] > 0 ) )
VAR sorgulanan = VALUES ( Fact_Sorgu[VKN] )
RETURN
    COUNTROWS ( EXCEPT ( riskli, sorgulanan ) ) + 0""", "#,0", "2 Davranis"),
    ("Fact_Sorgu", "Kor Nokta Risk TL", """
VAR sonAy = MAX ( Fact_KrediSonuc[Tarih] )
VAR sorgulanan = VALUES ( Fact_Sorgu[VKN] )
RETURN
    SUMX (
        FILTER (
            Fact_KrediSonuc,
            Fact_KrediSonuc[Tarih] = sonAy
                && NOT ( Fact_KrediSonuc[VKN] IN sorgulanan )
        ),
        Fact_KrediSonuc[BizimRisk]
    )""", "#,0", "2 Davranis"),

    # Sayfa 3 - Risk gocu
    ("Fact_Sorgu", "Sektor Risk TL", "SUM ( Fact_Sorgu[SektorToplamRisk] )", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Bizim Risk Artisi", """
SUMX (
    FILTER ( Fact_Sorgu, NOT ISBLANK ( Fact_Sorgu[OncekiBizimRisk] ) ),
    Fact_Sorgu[BizimRisk] - Fact_Sorgu[OncekiBizimRisk]
)""", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Sektor Risk Artisi", """
SUMX (
    FILTER ( Fact_Sorgu, NOT ISBLANK ( Fact_Sorgu[OncekiSektorToplamRisk] ) ),
    Fact_Sorgu[SektorToplamRisk] - Fact_Sorgu[OncekiSektorToplamRisk]
)""", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Rakip Risk Artisi", "[Sektor Risk Artisi] - [Bizim Risk Artisi]", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Kopru Deger", """
SWITCH (
    SELECTEDVALUE ( 'Risk Kopru'[Sira] ),
    1, [Bizim Risk Artisi],
    2, [Rakip Risk Artisi]
)""", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Sektor Risk Buyumesi %", """
DIVIDE (
    [Sektor Risk Artisi],
    SUMX (
        FILTER ( Fact_Sorgu, NOT ISBLANK ( Fact_Sorgu[OncekiSektorToplamRisk] ) ),
        Fact_Sorgu[OncekiSektorToplamRisk]
    )
)""", "0.0%", "3 Risk Gocu"),
    ("Fact_Sorgu", "Buyumede Bizim Pay", "DIVIDE ( [Bizim Risk Artisi], [Sektor Risk Artisi] )", "0.0%",
     "3 Risk Gocu"),
    ("Fact_Sorgu", "Not Degisimi Ort", """
AVERAGEX (
    FILTER ( Fact_Sorgu, NOT ISBLANK ( Fact_Sorgu[OncekiKKBNot] ) ),
    Fact_Sorgu[KKBNot] - Fact_Sorgu[OncekiKKBNot]
)""", "#,0", "3 Risk Gocu"),
    ("Fact_Sorgu", "Ortalama Limit Doluluk",
     "DIVIDE ( SUM ( Fact_Sorgu[SektorToplamRisk] ), SUM ( Fact_Sorgu[SektorToplamLimit] ) )", "0.0%",
     "3 Risk Gocu"),
    ("Fact_Sorgu", "Banka Sayisi Artan Musteri", """
CALCULATE (
    [Tekil Musteri],
    FILTER ( Fact_Sorgu, Fact_Sorgu[BankaSayisi] > Fact_Sorgu[OncekiBankaSayisi]
        && NOT ISBLANK ( Fact_Sorgu[OncekiBankaSayisi] ) )
)""", "#,0", "3 Risk Gocu"),
    ("Fact_RiskDetay", "Risk Detay TL", "SUM ( Fact_RiskDetay[Risk] )", "#,0", "3 Risk Gocu"),

    # Sayfa 4 - Rakip sinyalleri
    ("Fact_Sorgu", "Pay Degisimi", """
AVERAGEX (
    FILTER ( Fact_Sorgu, NOT ISBLANK ( Fact_Sorgu[OncekiBizimPay] ) ),
    Fact_Sorgu[BizimPay] - Fact_Sorgu[OncekiBizimPay]
)""", "0.0%", "4 Rakip"),
    ("Fact_Sorgu", "Yedek Banka Endeksi",
     "AVERAGEX ( Fact_Sorgu, Fact_Sorgu[DigerBankaDoluluk] - Fact_Sorgu[BizimDoluluk] )", "0.00", "4 Rakip"),
    ("Fact_Sorgu", "Rakip Ortalama Limit", """
AVERAGEX (
    FILTER ( Fact_Sorgu, Fact_Sorgu[BankaSayisi] > 1 ),
    DIVIDE ( Fact_Sorgu[SektorToplamLimit] - Fact_Sorgu[BizimLimit], Fact_Sorgu[BankaSayisi] - 1 )
)""", "#,0", "4 Rakip"),
    ("Fact_Sorgu", "Bizim Limit / Rakip Limit",
     "DIVIDE ( AVERAGE ( Fact_Sorgu[BizimLimit] ), [Rakip Ortalama Limit] )", "0.00", "4 Rakip"),
    ("Fact_Sorgu", "Ana Banka Orani %", """
DIVIDE (
    CALCULATE (
        [Tekil Musteri],
        FILTER ( Fact_Sorgu, Fact_Sorgu[BizimPay] >= 1.5 / Fact_Sorgu[BankaSayisi] )
    ),
    [Tekil Musteri]
)""", "0.0%", "4 Rakip"),
    ("Fact_Sorgu", "Ret Sonrasi Musteri", """
COUNTROWS (
    FILTER (
        Fact_Sorgu,
        Fact_Sorgu[SorguSonucu] IN { "Ret", "Teklif" }
            && NOT ISBLANK ( Fact_Sorgu[SonrakiSektorToplamRisk] )
    )
)""", "#,0", "4 Rakip"),
    ("Fact_Sorgu", "Ret Sonrasi Buyuyen %", """
VAR t =
    FILTER (
        Fact_Sorgu,
        Fact_Sorgu[SorguSonucu] IN { "Ret", "Teklif" }
            && NOT ISBLANK ( Fact_Sorgu[SonrakiSektorToplamRisk] )
    )
RETURN
    DIVIDE (
        COUNTROWS ( FILTER ( t, Fact_Sorgu[SonrakiSektorToplamRisk] > Fact_Sorgu[SektorToplamRisk] * 1.1 ) ),
        COUNTROWS ( t )
    )""", "0.0%", "4 Rakip"),
    ("Fact_Sorgu", "Ret Sonrasi Gecikme %", """
VAR t =
    FILTER (
        Fact_Sorgu,
        Fact_Sorgu[SorguSonucu] IN { "Ret", "Teklif" }
            && NOT ISBLANK ( Fact_Sorgu[SonrakiGecikmeVar] )
            && Fact_Sorgu[GecikmeVar] = 0
    )
RETURN
    DIVIDE ( COUNTROWS ( FILTER ( t, Fact_Sorgu[SonrakiGecikmeVar] = 1 ) ), COUNTROWS ( t ) )""",
     "0.0%", "4 Rakip"),

    # Sayfa 5 - Erken uyari
    ("Fact_AnomaliSkor", "Anomali Skoru (son sorgu)",
     "CALCULATE ( MAX ( Fact_AnomaliSkor[Skor] ), KEEPFILTERS ( Fact_AnomaliSkor[SonSorguMu] = 1 ) )",
     "0.0", "5 Erken Uyari"),
    ("Fact_AnomaliSkor", "Anomali Nedeni (son)", """
VAR s = [Anomali Skoru (son sorgu)]
RETURN
    CALCULATE (
        MAX ( Fact_AnomaliSkor[Neden] ),
        KEEPFILTERS ( Fact_AnomaliSkor[SonSorguMu] = 1 ),
        KEEPFILTERS ( Fact_AnomaliSkor[Skor] = s )
    )""", None, "5 Erken Uyari"),
    ("Fact_AnomaliSkor", "Ortalama Anomali Skoru", "AVERAGE ( Fact_AnomaliSkor[Skor] )", "0.0", "5 Erken Uyari"),
    ("Fact_AnomaliSkor", "Yuksek Anomali Musteri", """
CALCULATE (
    DISTINCTCOUNT ( Fact_AnomaliSkor[VKN] ),
    KEEPFILTERS ( Fact_AnomaliSkor[SonSorguMu] = 1 ),
    KEEPFILTERS ( Fact_AnomaliSkor[Skor] >= 70 )
) + 0""", "#,0", "5 Erken Uyari"),
    ("Fact_AnomaliSkor", "Skor70 Sonraki Gecikme %", """
CALCULATE (
    AVERAGE ( Fact_AnomaliSkor[SonrakiGecikmeVar] ),
    KEEPFILTERS ( Fact_AnomaliSkor[Skor] >= 70 ),
    KEEPFILTERS ( Fact_AnomaliSkor[GecikmeVar] = 0 )
)""", "0.0%", "5 Erken Uyari"),
    ("Fact_AnomaliSkor", "Diger Sonraki Gecikme %", """
CALCULATE (
    AVERAGE ( Fact_AnomaliSkor[SonrakiGecikmeVar] ),
    KEEPFILTERS ( Fact_AnomaliSkor[Skor] < 70 ),
    KEEPFILTERS ( Fact_AnomaliSkor[GecikmeVar] = 0 )
)""", "0.0%", "5 Erken Uyari"),
    ("Fact_Sorgu", "Ortalama KKB Not", "AVERAGE ( Fact_Sorgu[KKBNot] )", "#,0", "5 Erken Uyari"),
    ("Fact_KrediSonuc", "Ortalama Ic Rating", "AVERAGE ( Fact_KrediSonuc[IcRating] )", "0.0", "5 Erken Uyari"),

    # Sayfa 6 - Aksiyon
    ("Fact_Sorgu", "Aksiyon Musteri",
     "CALCULATE ( [Tekil Musteri], KEEPFILTERS ( Fact_Sorgu[SonSorguMu] = 1 ) )", "#,0", "6 Aksiyon"),
    ("Fact_Sorgu", "Potansiyel TL (son)",
     "CALCULATE ( SUM ( Fact_Sorgu[Potansiyel TL] ), KEEPFILTERS ( Fact_Sorgu[SonSorguMu] = 1 ) )",
     "#,0", "6 Aksiyon"),
    ("Fact_Sorgu", "Bizim Risk (son)",
     "CALCULATE ( SUM ( Fact_Sorgu[BizimRisk] ), KEEPFILTERS ( Fact_Sorgu[SonSorguMu] = 1 ) )",
     "#,0", "6 Aksiyon"),
    ("Fact_Sorgu", "Son Sorgu Tarihi",
     "CALCULATE ( MAX ( Fact_Sorgu[SorguTarihi] ), KEEPFILTERS ( Fact_Sorgu[SonSorguMu] = 1 ) )",
     "dd.mm.yyyy", "6 Aksiyon"),
    ("Fact_Sorgu", "Anomali Skoru (aksiyon)",
     "IF ( NOT ISBLANK ( [Son Sorgu Tarihi] ), [Anomali Skoru (son sorgu)] )", "0.0", "6 Aksiyon"),
]


def ornek_tablolar():
    """Sutun adlari ve tiplerini cikarmak icin kucuk bir ornek veri uretir."""
    t = gen.uret(n_musteri=80, seed=1)
    t["Fact_AnomaliSkor"] = skorla(t["Fact_Sorgu"], t["Fact_RiskDetay"], t["Dim_Musteri"], seed=1)
    # CSV'ye yazilip geri okunmus hali, Power Query'nin gorecegi tiplerle ayni olsun.
    import io
    out = {}
    for ad in TABLO_SIRASI:
        buf = io.StringIO()
        t[ad].to_csv(buf, index=False)
        buf.seek(0)
        out[ad] = pd.read_csv(buf, dtype={"VKN": str})
    return out


TAMSAYI_ALANLAR = {"SorguID", "GecikmeVar", "TakipVar", "KKBNot", "BankaSayisi", "SorgularArasiGun",
                   "BankaSayisiDelta", "NotDelta"}


def sutun_tipi(tablo, ad, seri):
    if "Tarih" in ad:
        return "dateTime"
    if ad == "VKN" or not pd.api.types.is_numeric_dtype(seri):
        return "string"
    if pd.api.types.is_integer_dtype(seri):
        return "int64"
    # NaN iceren tamsayi alanlar CSV'den float gelir (OncekiKKBNot, SonrakiGecikmeVar...).
    kok = ad.removeprefix("Onceki").removeprefix("Sonraki")
    dolu = seri.dropna()
    if kok in TAMSAYI_ALANLAR and (dolu == dolu.round()).all():
        return "int64"
    return "double"


M_TIPI = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date"}


def m_ifadesi(tablo, sutunlar):
    tipler = ", ".join(f'{{"{ad}", {M_TIPI[tip]}}}' for ad, tip in sutunlar)
    return [
        "let",
        f'    Kaynak = Csv.Document(File.Contents(VeriKlasoru & "\\{tablo}.csv"), '
        '[Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Basliklar = Table.PromoteHeaders(Kaynak, [PromoteAllScalars = true]),",
        '    Bosluklar = Table.TransformColumns(Basliklar, {}, each if _ = "" then null else _),',
        f'    Tipler = Table.TransformColumnTypes(Bosluklar, {{{tipler}}}, "en-US")',
        "in",
        "    Tipler",
    ]


def satirlar(dax):
    return dax.strip("\n").split("\n")


def model_olustur(ornek):
    tablolar = []
    for ad in TABLO_SIRASI:
        df = ornek[ad]
        sutunlar = [(c, sutun_tipi(ad, c, df[c])) for c in df.columns]
        cols = []
        for c, tip in sutunlar:
            col = {"name": c, "dataType": tip, "sourceColumn": c, "summarizeBy": "none"}
            if tip == "dateTime":
                col["formatString"] = "dd.mm.yyyy"
            elif tip == "double":
                col["formatString"] = "0.0%" if c in YUZDE_SUTUNLAR else "#,0.##"
            elif tip == "int64":
                col["formatString"] = "0"
            if (ad, c) in GIZLI_SUTUNLAR:
                col["isHidden"] = True
            if ad == "Dim_Tarih" and c == "Tarih":
                col["isKey"] = True
            cols.append(col)
        for c, tip, dax in HESAPLANMIS_SUTUNLAR.get(ad, []):
            col = {"type": "calculated", "name": c, "dataType": tip, "isDataTypeInferred": True,
                   "expression": satirlar(dax), "summarizeBy": "none"}
            if tip == "double":
                col["formatString"] = "#,0"
            cols.append(col)
        tablo = {
            "name": ad,
            "columns": cols,
            "partitions": [{"name": ad, "mode": "import",
                            "source": {"type": "m", "expression": m_ifadesi(ad, sutunlar)}}],
        }
        if ad == "Dim_Tarih":
            tablo["dataCategory"] = "Time"
        olculer = [o for o in OLCULER if o[0] == ad]
        if olculer:
            tablo["measures"] = []
            for _, oad, dax, fmt, klasor in olculer:
                m = {"name": oad, "expression": satirlar(dax), "displayFolder": klasor}
                if fmt:
                    m["formatString"] = fmt
                tablo["measures"].append(m)
        tablolar.append(tablo)

    for ad, (dax, cols) in HESAPLANMIS_TABLOLAR.items():
        tablolar.append({
            "name": ad,
            "columns": [{"type": "calculatedTableColumn", "name": c, "dataType": tip, "isNameInferred": True,
                         "isDataTypeInferred": True, "sourceColumn": f"[{c}]", "summarizeBy": "none"}
                        for c, tip in cols],
            "partitions": [{"name": ad, "mode": "import", "source": {"type": "calculated", "expression": dax}}],
        })

    iliskiler = [{
        "name": str(uuid.uuid5(NS, f"{a}.{b}->{c}.{d}")),
        "fromTable": a, "fromColumn": b, "toTable": c, "toColumn": d,
    } for a, b, c, d in ILISKILER]

    return {
        "name": PROJE,
        "compatibilityLevel": 1550,
        "model": {
            "culture": "tr-TR",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "tr-TR",
            "tables": tablolar,
            "relationships": iliskiler,
            "expressions": [{
                "name": "VeriKlasoru",
                "kind": "m",
                "expression": f'"{VARSAYILAN_VERI_KLASORU}" meta [IsParameterQuery = true, Type = "Text", '
                              "IsParameterQueryRequired = true]",
            }],
            "annotations": [
                {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                {"name": "PBI_QueryOrder", "value": json.dumps(["VeriKlasoru"] + TABLO_SIRASI)},
            ],
        },
    }


def dax_dosyasi_yaz(yol):
    parcalar = ["// KKB Kurumsal Sorgu Analitigi - DAX olculeri ve hesaplanmis sutunlar",
                "// Bu dosya powerbi/build_pbip.py tarafindan uretilir; elle duzenlemeyin.", ""]
    klasor = None
    for tablo, ad, dax, fmt, k in OLCULER:
        if k != klasor:
            parcalar += [f"// ---------- {k} ----------", ""]
            klasor = k
        parcalar += [f"// Tablo: {tablo}" + (f" | Bicim: {fmt}" if fmt else ""),
                     f"{ad} =", dax.strip("\n"), ""]
    parcalar += ["// ---------- Hesaplanmis sutunlar ----------", ""]
    for tablo, cols in HESAPLANMIS_SUTUNLAR.items():
        for ad, _, dax in cols:
            parcalar += [f"// Tablo: {tablo}", f"{ad} =", dax.strip("\n"), ""]
    parcalar += ["// ---------- Hesaplanmis tablolar ----------", ""]
    for ad, (dax, _) in HESAPLANMIS_TABLOLAR.items():
        parcalar += [f"{ad} =", dax, ""]
    yol.write_text("\n".join(parcalar), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Rapor (PBIR)
# --------------------------------------------------------------------------------------

def M(tablo, ad):
    return ("Measure", tablo, ad)


def C(tablo, ad):
    return ("Column", tablo, ad)


def alan(f):
    tur, tablo, ad = f
    return {tur: {"Expression": {"SourceRef": {"Entity": tablo}}, "Property": ad}}


def lit(deger):
    return {"expr": {"Literal": {"Value": deger}}}


def metin(s):
    return "'" + s.replace("'", "''") + "'"


class Sayfa:
    def __init__(self, ad, sekme, baslik, alt_baslik):
        self.ad = ad
        self.sekme = sekme
        self.gorseller = []
        self.etkilesimler = []  # (kaynak gorsel, hedef gorsel, tur)
        self.textbox("baslik", 0, 0, 900, 64, baslik, alt_baslik)

    def ekle(self, ad, tip, x, y, w, h, roller, baslik=None, siralama=None, haric=None, nesneler=None):
        query = {"queryState": {
            rol: {"projections": [{"field": alan(f), "queryRef": f"{f[1]}.{f[2]}", "nativeQueryRef": f[2]}
                                  for f in alanlar]}
            for rol, alanlar in roller.items()
        }}
        if siralama:
            f, yon = siralama
            query["sortDefinition"] = {"sort": [{"field": alan(f), "direction": yon}], "isDefaultSort": False}
        visual = {"visualType": tip, "query": query, "drillFilterOtherVisuals": True}
        if nesneler:
            visual["objects"] = nesneler
        if baslik:
            visual["visualContainerObjects"] = {"title": [{"properties": {
                "show": lit("true"), "text": lit(metin(baslik))}}]}
        g = {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.5.0/schema.json",
             "name": ad, "position": {"x": x, "y": y, "z": len(self.gorseller) * 100, "width": w, "height": h,
                                      "tabOrder": len(self.gorseller) * 100},
             "visual": visual}
        if haric:
            f, degerler = haric
            g["filterConfig"] = {"filters": [{
                "name": f"{ad}_filtre",
                "field": alan(f),
                "type": "Categorical",
                "filter": {
                    "Version": 2,
                    "From": [{"Name": "t", "Entity": f[1], "Type": 0}],
                    "Where": [{"Condition": {"Not": {"Expression": {"In": {
                        "Expressions": [{f[0]: {"Expression": {"SourceRef": {"Source": "t"}}, "Property": f[2]}}],
                        "Values": [[{"Literal": {"Value": metin(v)}}] for v in degerler],
                    }}}}}],
                },
            }]}
        self.gorseller.append(g)

    def kart(self, ad, x, y, w, h, olcu, baslik):
        self.ekle(ad, "card", x, y, w, h, {"Values": [olcu]}, baslik=baslik)

    def dilimleyici(self, ad, x, y, w, h, sutun, baslik):
        self.ekle(ad, "slicer", x, y, w, h, {"Values": [sutun]}, baslik=baslik,
                  nesneler={"data": [{"properties": {"mode": lit("'Dropdown'")}}]})

    def textbox(self, ad, x, y, w, h, baslik, alt):
        paragraflar = [{"textRuns": [{"value": baslik, "textStyle": {"fontWeight": "bold", "fontSize": "18pt"}}]}]
        if alt:
            paragraflar.append({"textRuns": [{"value": alt, "textStyle": {"fontSize": "11pt", "color": "#605E5C"}}]})
        self.gorseller.append({
            "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.5.0/schema.json",
            "name": ad,
            "position": {"x": x, "y": y, "z": len(self.gorseller) * 100, "width": w, "height": h,
                         "tabOrder": len(self.gorseller) * 100},
            "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraflar}}]},
                       "drillFilterOtherVisuals": True},
        })


def sayfalar():
    S, D, T, K, A, NB = "Fact_Sorgu", "Dim_Musteri", "Dim_Tarih", "Fact_KrediSonuc", "Fact_AnomaliSkor", "Dim_NotBandi"
    ay = C(T, "AyAdi")
    unvan = C(D, "Unvan")
    sp = []

    # 1 - Yonetici ozeti
    p = Sayfa("p1_ozet", "1 Yönetici Özeti", "Bir yılda ne gördük?",
              "KKB kurumsal sorgularından çıkan efor, risk ve cüzdan payı özeti")
    p.dilimleyici("seg", 920, 6, 170, 56, C(D, "Segment"), "Segment")
    p.dilimleyici("bolge", 1100, 6, 170, 56, C(D, "Bolge"), "Bölge")
    kartlar = [("Sorgu Adedi", "Toplam sorgu"), ("Tekil Musteri", "Tekil müşteri"),
               ("Sorgu Donusum %", "Sorgu → kullandırım"), ("Olu Sorgu Maliyeti TL", "Ölü sorgu maliyeti (TL)"),
               ("Cuzdan Payi", "Cüzdan payı"), ("Payi Eriyen Musteri", "Payı eriyen müşteri"),
               ("Yeni Gecikme Sinyali", "Yeni gecikme sinyali")]
    for i, (olcu, baslik) in enumerate(kartlar):
        p.kart(f"k{i}", 14 + i * 180, 76, 172, 110, M(S, olcu), baslik)
    # Iki farkli olcek iki ayri grafikte (cift eksenli grafik yaniltici okunur).
    p.ekle("trend", "clusteredColumnChart", 14, 198, 840, 250,
           {"Category": [ay], "Y": [M(S, "Sorgu Adedi")]},
           baslik="Aylık sorgu adedi", siralama=(ay, "Ascending"))
    p.ekle("paytrend", "lineChart", 14, 458, 840, 250,
           {"Category": [ay], "Y": [M(S, "Cuzdan Payi")]},
           baslik="Aylık cüzdan payı", siralama=(ay, "Ascending"))
    p.ekle("ozet", "tableEx", 864, 198, 402, 180, {"Values": [M(S, "Ozet Cumle")]},
           baslik="Bu dönemin özeti",
           nesneler={"values": [{"properties": {"wordWrap": lit("true")}}],
                     "columnHeaders": [{"properties": {"wordWrap": lit("true")}}]})
    p.kart("kor", 864, 388, 198, 100, M(S, "Kor Nokta Musteri"), "Kör nokta müşteri")
    p.kart("korrisk", 1068, 388, 198, 100, M(S, "Kor Nokta Risk TL"), "Kör nokta risk (TL)")
    p.kart("anomali", 864, 498, 198, 100, M(A, "Yuksek Anomali Musteri"), "Anomali skoru ≥ 70")
    p.kart("yedek", 1068, 498, 198, 100, M(S, "Yedek Banka Endeksi"), "Yedek banka endeksi")
    p.kart("mukerrer", 864, 608, 198, 100, M(S, "Mukerrer Sorgu (7 gun)"), "Mükerrer sorgu (7 gün)")
    p.kart("musbasina", 1068, 608, 198, 100, M(S, "Musteri Basina Sorgu"), "Müşteri başına sorgu")
    sp.append(p)

    # 2 - Sorgu davranisi
    p = Sayfa("p2_davranis", "2 Sorgu Davranışı", "Ne zaman, neden bakıyoruz?", "Sorgu eforunun ticari karşılığı")
    p.kart("gun", 920, 6, 170, 60, M(S, "Ortalama Sorgudan Kullandirima Gun"), "Kullandırıma gün")
    p.kart("maliyet", 1100, 6, 170, 60, M(S, "Toplam Sorgu Maliyeti TL"), "Sorgu maliyeti (TL)")
    p.ekle("huni", "funnel", 14, 76, 420, 300,
           {"Category": [C("Huni Asama", "Asama")], "Y": [M(S, "Huni Deger")]},
           baslik="Başvuru sorgusundan kullandırıma", siralama=(C("Huni Asama", "Asama"), "Ascending"))
    p.ekle("isi", "pivotTable", 444, 76, 420, 300,
           {"Rows": [C(T, "AyinHaftasi")], "Columns": [C(T, "Gun Adi")], "Values": [M(S, "Sorgu Adedi")]},
           baslik="Ayın haftası × gün (sorgu adedi)")
    p.ekle("aysonu", "clusteredColumnChart", 874, 76, 392, 300,
           {"Category": [C(T, "Ay Donemi")], "Y": [M(S, "Sorgu Donusum %"), M(S, "Olu Sorgu Orani %")]},
           baslik="Ay sonu baskısı: dönüşüm ve ölü sorgu")
    p.ekle("neden", "clusteredBarChart", 14, 386, 420, 322,
           {"Category": [C(S, "SorguNedeni")], "Y": [M(S, "Sorgu Adedi")]}, baslik="Sorgu nedeni")
    p.ekle("tekrar", "clusteredColumnChart", 444, 386, 300, 322,
           {"Category": [C(S, "Tekrar Araligi")], "Y": [M(S, "Sorgu Adedi")]},
           baslik="Aynı müşteriye tekrar bakma aralığı", siralama=(C(S, "Tekrar Araligi"), "Ascending"),
           haric=(C(S, "Tekrar Araligi"), ["0) İlk sorgu"]))
    p.ekle("sube", "tableEx", 754, 386, 512, 322,
           {"Values": [C("Dim_Sube", "SubeAdi"), M(S, "Sorgu Adedi"), M(S, "Sorgu Donusum %"),
                       M(S, "Olu Sorgu Orani %"), M(S, "Olu Sorgu Maliyeti TL")]},
           baslik="Şube bazında sorgu verimi", siralama=(M(S, "Olu Sorgu Maliyeti TL"), "Descending"))
    sp.append(p)

    # 3 - Risk gocu
    p = Sayfa("p3_risk", "3 Risk Göçü", "İki sorgu arasında ne değişti?", "Yalnızca en az iki kez sorgulanan müşteriler")
    p.ekle("notgocu", "pivotTable", 14, 76, 420, 300,
           {"Rows": [C(S, "OncekiNotBandi")], "Columns": [C(S, "NotBandi")], "Values": [M(S, "Tekil Musteri")]},
           baslik="KKB not bandı göçü (önceki → son)", haric=(C(S, "Not Degisimi"), ["İlk sorgu"]))
    p.ekle("bankanot", "pivotTable", 444, 76, 420, 300,
           {"Rows": [C(S, "Banka Degisimi")], "Columns": [C(S, "Not Degisimi")], "Values": [M(S, "Tekil Musteri")]},
           baslik="Banka sayısı × not değişimi", haric=(C(S, "Banka Degisimi"), ["İlk sorgu"]))
    p.ekle("kopru", "waterfallChart", 874, 76, 392, 300,
           {"Category": [C("Risk Kopru", "Kalem")], "Y": [M(S, "Kopru Deger")]},
           baslik="Sektör risk artışını kim finanse etti?", siralama=(C("Risk Kopru", "Kalem"), "Ascending"))
    p.ekle("karisim", "hundredPercentStackedColumnChart", 14, 386, 620, 322,
           {"Category": [ay], "Series": [C("Fact_RiskDetay", "KrediTuru")], "Y": [M("Fact_RiskDetay", "Risk Detay TL")]},
           baslik="Kredi türü karışımı (sektör geneli)", siralama=(ay, "Ascending"))
    p.ekle("doluluk", "lineChart", 644, 386, 300, 322,
           {"Category": [ay], "Y": [M(S, "Ortalama Limit Doluluk")]},
           baslik="Limit doluluk oranı", siralama=(ay, "Ascending"))
    p.ekle("gocler", "tableEx", 954, 386, 312, 322,
           {"Values": [unvan, M(S, "Sektor Risk Buyumesi %"), M(S, "Not Degisimi Ort")]},
           baslik="En büyük göçler", siralama=(M(S, "Sektor Risk Buyumesi %"), "Descending"))
    sp.append(p)

    # 4 - Rakip sinyalleri
    p = Sayfa("p4_rakip", "4 Rakip Sinyalleri", "Müşteri büyürken kim büyüyor?", "Sektör toplamı ile bizim veri arasındaki fark")
    p.ekle("cuzdan", "scatterChart", 14, 76, 620, 420,
           {"Category": [unvan], "X": [M(S, "Pay Degisimi")], "Y": [M(S, "Sektor Risk Buyumesi %")],
            "Size": [M(S, "Sektor Risk TL")]},
           baslik="Cüzdan matrisi: x = pay değişimi, y = sektör risk büyümesi")
    p.kart("yedek", 644, 76, 200, 100, M(S, "Yedek Banka Endeksi"), "Yedek banka endeksi")
    p.kart("anabanka", 854, 76, 200, 100, M(S, "Ana Banka Orani %"), "Ana banka olma oranı")
    p.kart("eriyen", 1064, 76, 202, 100, M(S, "Payi Eriyen Musteri"), "Payı eriyen müşteri")
    p.ekle("bolge", "clusteredColumnChart", 644, 186, 622, 310,
           {"Category": [C(S, "Cuzdan Bolgesi")], "Y": [M(S, "Tekil Musteri")]},
           baslik="Cüzdan bölgelerine göre müşteri", haric=(C(S, "Cuzdan Bolgesi"), ["Tek sorgu"]))
    p.ekle("limit", "clusteredBarChart", 14, 506, 420, 202,
           {"Category": [C(D, "NACEAciklama")], "Y": [M(S, "Bizim Limit / Rakip Limit")]},
           baslik="Bizim limit / rakip ortalama limit (sektör)")
    p.ekle("anatrend", "lineChart", 444, 506, 400, 202,
           {"Category": [ay], "Y": [M(S, "Ana Banka Orani %")]},
           baslik="Ana banka olma oranı", siralama=(ay, "Ascending"))
    p.ekle("ret", "clusteredColumnChart", 854, 506, 412, 202,
           {"Category": [C(S, "SorguSonucu")], "Y": [M(S, "Ret Sonrasi Buyuyen %"), M(S, "Ret Sonrasi Gecikme %")]},
           baslik="Ret / vazgeçme sonrası kader")
    sp.append(p)

    # 5 - Erken uyari
    p = Sayfa("p5_uyari", "5 Erken Uyarı", "Kim kendi geçmişinden kopuyor?", "Skor bir karar değil, bakış önceliğidir")
    kartlar = [(M(A, "Yuksek Anomali Musteri"), "Skor ≥ 70 müşteri"),
               (M(S, "Yeni Gecikme Sinyali"), "Yeni gecikme sinyali"),
               (M(S, "Yeni Takip Gecisi"), "Takibe düşüş"),
               (M(A, "Skor70 Sonraki Gecikme %"), "Skor ≥ 70 → sonra gecikme"),
               (M(A, "Diger Sonraki Gecikme %"), "Skor < 70 → sonra gecikme")]
    for i, (olcu, baslik) in enumerate(kartlar):
        p.kart(f"k{i}", 14 + i * 252, 76, 244, 96, olcu, baslik)
    p.ekle("liste", "tableEx", 14, 182, 620, 526,
           {"Values": [unvan, C(D, "Segment"), M(A, "Anomali Skoru (son sorgu)"), M(A, "Anomali Nedeni (son)"),
                       M(S, "Bizim Risk (son)")]},
           baslik="Bu hafta kime bakmalıyız?", siralama=(M(A, "Anomali Skoru (son sorgu)"), "Descending"))
    p.dilimleyici("musteri", 644, 182, 300, 56, unvan, "Müşteri seç")
    # Musteri secimi yalnizca zaman serisi grafiklerini filtreler; liste ve kartlar tum portfoyu gosterir.
    for hedef in ["k0", "k1", "k2", "k3", "k4", "liste", "sektor", "rating"]:
        p.etkilesimler.append(("musteri", hedef, "NoFilter"))
    p.ekle("seri", "lineChart", 644, 244, 306, 226,
           {"Category": [ay], "Y": [M(S, "Sektor Risk TL")]},
           baslik="Seçili müşteri: sektör riski (TL)", siralama=(ay, "Ascending"))
    p.ekle("seridol", "lineChart", 960, 244, 306, 226,
           {"Category": [ay], "Y": [M(S, "Ortalama Limit Doluluk")]},
           baslik="Seçili müşteri: limit doluluğu", siralama=(ay, "Ascending"))
    p.ekle("sektor", "pivotTable", 644, 480, 300, 228,
           {"Rows": [C(D, "NACEAciklama")], "Columns": [C(T, "Yil Ceyrek")], "Values": [M(A, "Ortalama Anomali Skoru")]},
           baslik="Sektör × çeyrek ortalama skor")
    p.ekle("rating", "scatterChart", 954, 480, 312, 228,
           {"Category": [unvan], "X": [M(S, "Ortalama KKB Not")], "Y": [M(K, "Ortalama Ic Rating")]},
           baslik="KKB notu × iç rating")
    sp.append(p)

    # 6 - Aksiyon
    p = Sayfa("p6_aksiyon", "6 Aksiyon", "Pazartesi kimi arıyoruz?", "Son sorguya göre aksiyon etiketi ve potansiyel")
    p.dilimleyici("py", 1100, 6, 170, 56, C(D, "PortfoyYoneticisi"), "Portföy yöneticisi")
    izle = (C(S, "Aksiyon Etiketi"), ["İzle"])
    p.ekle("liste", "tableEx", 14, 76, 760, 632,
           {"Values": [unvan, C(D, "PortfoyYoneticisi"), C(S, "Aksiyon Etiketi"), M(S, "Potansiyel TL (son)"),
                       M(S, "Bizim Risk (son)"), M(S, "Anomali Skoru (aksiyon)"), M(S, "Son Sorgu Tarihi")]},
           baslik="Aksiyon listesi", siralama=(M(S, "Potansiyel TL (son)"), "Descending"), haric=izle)
    p.ekle("etiket", "clusteredBarChart", 784, 76, 482, 300,
           {"Category": [C(S, "Aksiyon Etiketi")], "Y": [M(S, "Potansiyel TL (son)")]},
           baslik="Etiket başına potansiyel (TL)", haric=izle)
    p.ekle("bolge", "stackedBarChart", 784, 386, 482, 322,
           {"Category": [C(D, "Bolge")], "Series": [C(S, "Aksiyon Etiketi")], "Y": [M(S, "Aksiyon Musteri")]},
           baslik="Bölgelere göre aksiyon bekleyen müşteri", haric=izle)
    sp.append(p)
    return sp


TEMA = {
    "name": "KKB Tema",
    # Renk korlugu testinden gecen kategorik palet (sira onemli, degistirmeyin).
    "dataColors": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    "background": "#FFFFFF",
    "foreground": "#0b0b0b",
    "tableAccent": "#2a78d6",
    "good": "#0ca30c",
    "neutral": "#fab219",
    "bad": "#d03b3b",
}


def yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def platform(tur, ad):
    return {
        "$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": tur, "displayName": ad},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid5(NS, f"{tur}:{ad}"))},
    }


def proje_yaz(hedef):
    sm = hedef / f"{PROJE}.SemanticModel"
    rp = hedef / f"{PROJE}.Report"
    for d in (sm, rp):
        if d.exists():
            shutil.rmtree(d)

    yaz(hedef / f"{PROJE}.pbip", {
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{PROJE}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })

    yaz(sm / ".platform", platform("SemanticModel", PROJE))
    yaz(sm / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "settings": {},
    })
    yaz(sm / "model.bim", model_olustur(ornek_tablolar()))

    yaz(rp / ".platform", platform("Report", PROJE))
    yaz(rp / "definition.pbir", {
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{PROJE}.SemanticModel"}},
    })
    tanim = rp / "definition"
    yaz(tanim / "version.json", {
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    yaz(tanim / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/1.2.0/schema.json",
        "themeCollection": {"customTheme": {"name": "KKB_Tema.json", "reportVersionAtImport": "5.55",
                                            "type": "RegisteredResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": "KKB_Tema.json", "path": "KKB_Tema.json",
                                         "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True},
    })
    yaz(rp / "StaticResources" / "RegisteredResources" / "KKB_Tema.json", TEMA)

    sp = sayfalar()
    yaz(tanim / "pages" / "pages.json", {
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.ad for p in sp],
        "activePageName": sp[0].ad,
    })
    for p in sp:
        yaz(tanim / "pages" / p.ad / "page.json", {
            "$schema": f"{SCHEMA}/item/report/definition/page/1.3.0/schema.json",
            "name": p.ad,
            "displayName": p.sekme,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
            **({"visualInteractions": [{"source": a, "target": b, "type": c} for a, b, c in p.etkilesimler]}
               if p.etkilesimler else {}),
        })
        for g in p.gorseller:
            yaz(tanim / "pages" / p.ad / "visuals" / g["name"] / "visual.json", g)
    return hedef


def main():
    hedef = proje_yaz(KOK)
    dax_dosyasi_yaz(KOK / "measures.dax")
    print(f"PBIP projesi yazildi: {hedef / (PROJE + '.pbip')}")


if __name__ == "__main__":
    main()
