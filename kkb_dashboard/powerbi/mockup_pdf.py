"""Dashboard taslak PDF'i: kapak, her sayfanin gorunumu ve gorsel bazinda yapim kilavuzu.

Kullanim (kkb_dashboard klasorunden):
    python powerbi/mockup_pdf.py --data data --out docs
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import render_mockup  # noqa: E402

FONT_DIZIN = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIZIN / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIZIN / "DejaVuSans-Bold.ttf")))

INK, INK2, MUTED, CIZGI, VURGU = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#2a78d6"
STIL = {
    "baslik": ParagraphStyle("baslik", fontName="DejaVu-Bold", fontSize=24, leading=30, textColor=INK),
    "alt": ParagraphStyle("alt", fontName="DejaVu", fontSize=12, leading=17, textColor=INK2),
    "h1": ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=15, leading=19, textColor=INK),
    "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=11, leading=15, textColor=INK, spaceBefore=6),
    "metin": ParagraphStyle("metin", fontName="DejaVu", fontSize=9.5, leading=14, textColor=INK, alignment=TA_LEFT),
    "kucuk": ParagraphStyle("kucuk", fontName="DejaVu", fontSize=8, leading=11, textColor=INK2),
    "hucre": ParagraphStyle("hucre", fontName="DejaVu", fontSize=7.8, leading=10.2, textColor=INK),
    "hucre_b": ParagraphStyle("hucre_b", fontName="DejaVu-Bold", fontSize=7.8, leading=10.2, textColor=INK),
    "bas": ParagraphStyle("bas", fontName="DejaVu-Bold", fontSize=8, leading=10, textColor=colors.white),
}

SAYFALAR = [
    ("Bir yılda ne gördük?",
     "Üst yönetime 30 saniyede efor, risk ve cüzdan payını anlatan özet. Her kart diğer sayfalara giriş kapısıdır."),
    ("Ne zaman, neden bakıyoruz?",
     "Rapor müşteriyi değil bankanın kendi sorgu davranışını aynaya tutar: sorgu bütçesi nereye gidiyor, "
     "krediye dönüşüyor mu?"),
    ("İki sorgu arasında ne değişti?",
     "Aynı müşterinin ardışık iki sorgusu karşılaştırılır. Tek rapor bir fotoğraf, iki rapor bir filmdir."),
    ("Müşteri büyürken kim büyüyor?",
     "KKB rakip banka adı vermez; ama sektör toplamı ile bizim veri arasındaki fark rakiplerin toplam hareketini "
     "verir."),
    ("Kim kendi geçmişinden kopuyor?",
     "Her müşteri sabit eşiklere göre değil kendi normaline ve benzerlerine göre değerlendirilir."),
    ("Pazartesi kimi arıyoruz?",
     "Önceki sayfaların sinyalleri her müşteri için tek bir aksiyon etiketine ve potansiyel tutara dönüşür."),
]

# (görsel, nasıl hesaplanır, ne anlatır)
KILAVUZ = [
    [
        ("Dilimleyiciler: Segment, Bölge", "Dim_Musteri[Segment], Dim_Musteri[Bolge]; açılır liste",
         "Tüm sayfayı segment/bölgeye daraltır."),
        ("Kart: Toplam sorgu", "COUNTROWS(Fact_Sorgu)", "12 aydaki sorgu eforu."),
        ("Kart: Tekil müşteri", "DISTINCTCOUNT(VKN)", "Kaç farklı firmaya baktık."),
        ("Kart: Sorgu → kullandırım", "60 gün içinde kullandırıma dönen başvuru sorgusu / başvuru sorgusu",
         "Sorgu eforunun ticari verimi."),
        ("Kart: Ölü sorgu maliyeti (TL)", "Sonucu 'Aksiyon yok' olan sorguların KKB ücreti toplamı",
         "Boşa giden sorgu bütçesi; bankalarda neredeyse hiç raporlanmaz."),
        ("Kart: Cüzdan payı", "Σ bizim risk / Σ sektör toplam risk", "Sorgulanan müşterilerin toplam borcundaki yerimiz."),
        ("Kart: Payı eriyen müşteri", "Son iki sorgu arasında payı 5 puandan fazla düşen müşteri",
         "Rakibe kaymakta olan müşteriler."),
        ("Kart: Yeni gecikme sinyali", "Önceki sorguda temiz, son sorguda gecikmesi olan müşteri",
         "Başka bankada başlayan bozulmayı bizden önce gösterir."),
        ("Sütun: Aylık sorgu adedi", "Dim_Tarih[AyAdi] × Sorgu Adedi", "Efor trendi, ay ay."),
        ("Çizgi: Aylık cüzdan payı", "Dim_Tarih[AyAdi] × Cüzdan Payı",
         "Efor artarken pay artıyor mu? Üstteki grafikle birlikte okunur (bilerek iki ayrı grafik)."),
        ("Tablo: Bu dönemin özeti", "DAX ile birleştirilmiş metin ölçüsü",
         "Hikâyenin tek paragraflık özeti; filtrelerle değişir."),
        ("Kartlar: Kör nokta müşteri / risk", "Bizde riski olup dönem içinde hiç sorgulanmamış müşteri ve son ay riski",
         "Riskini taşıdığımız ama dışarıdan hiç bakmadığımız portföy."),
        ("Kartlar: Anomali ≥ 70, Yedek banka endeksi, Mükerrer sorgu, Müşteri başına sorgu",
         "İlgili ölçüler (5. ve 4. sayfalarda detaylı)", "Diğer sayfalara geçiş noktaları."),
    ],
    [
        ("Kartlar: Kullandırıma gün, Sorgu maliyeti", "Ortalama (kullandırım tarihi − sorgu tarihi); Σ sorgu ücreti",
         "Hız ve toplam bütçe."),
        ("Huni: Başvuru → teklif → kullandırım", "Ayrık 'Huni Aşama' tablosu + SWITCH ölçüsü",
         "Kayıp nerede: fiyatta mı, tahsiste mi, müşteride mi?"),
        ("Matris: Ayın haftası × gün", "Dim_Tarih[AyinHaftasi] × Dim_Tarih[Gun Adi], değer: sorgu adedi; "
                                     "arka plan rengi koşullu biçimlendirme", "Ay sonu yığılmasını gösterir."),
        ("Sütun: Ay sonu baskısı", "Dim_Tarih[Ay Donemi] × Dönüşüm % ve Ölü sorgu %",
         "Hedef baskısıyla ay sonunda atılan sorguların daha az krediye döndüğünü gösterir."),
        ("Çubuk: Sorgu nedeni", "Fact_Sorgu[SorguNedeni] × Sorgu Adedi", "Proaktif izleme ile reaktif sorgu dengesi."),
        ("Sütun: Tekrar bakma aralığı", "Ardışık iki sorgu arası gün, 5 gruba ayrılmış",
         "0–7 gün mükerrer maliyet; 180+ gün izleme açığı."),
        ("Tablo: Şube bazında sorgu verimi", "Dim_Sube[SubeAdi] × sorgu, dönüşüm, ölü sorgu %, ölü sorgu TL",
         "Çok sorgulayıp az kazandıran birimler; koçluk fırsatı, ceza aracı değil."),
    ],
    [
        ("Matris: Not bandı göçü", "Önceki sorgunun not bandı × son sorgunun not bandı; değer: tekil müşteri",
         "Portföy kalitesinin hangi yöne aktığı (Sankey ile de çizilebilir)."),
        ("Matris: Banka sayısı × not değişimi", "Banka sayısı arttı/aynı/azaldı × not yükseldi/aynı/düştü",
         "'Banka arttı + not düştü' kredi açlığı; 'banka arttı + not yükseldi' büyüyen müşteri."),
        ("Şelale: Sektör risk artışını kim finanse etti?", "Σ(bizim risk − önceki) ve Σ(sektör − önceki) − bizim",
         "Müşterilerin borç büyümesinin ne kadarını bizim, ne kadarını rakiplerin finanse ettiği."),
        ("%100 yığın sütun: Kredi türü karışımı", "Fact_RiskDetay[KrediTuru] payları, ay bazında",
         "Rotatif artışı işletme sermayesi sıkışması; TM artışı proje; akreditif ithalat büyümesi."),
        ("Çizgi: Limit doluluk oranı", "Σ sektör risk / Σ sektör limit, ay bazında",
         "%85 üstü limit sıkışıklığı: fırsat ya da risk."),
        ("Tablo: En büyük göçler", "Müşteri × sektör risk büyümesi ve not değişimi, büyümeye göre sıralı",
         "Portföy yöneticisinin bakması gereken somut isimler."),
    ],
    [
        ("Dağılım: Cüzdan matrisi", "x = pay değişimi, y = sektör risk büyümesi, balon = sektör riski; "
                                   "sıfır çizgileri dört bölge oluşturur",
         "Sol üst 'Rakip büyütüyor' en değerli bölge: müşteri büyüyor, biz pay alamıyoruz."),
        ("Kart: Yedek banka endeksi", "Rakiplerdeki limit doluluğu − bizdeki limit doluluğu",
         "Pozitif ve büyükse müşteri önce rakip limitlerini kullanıyor, bizi yedekte tutuyor."),
        ("Kart: Ana banka olma oranı", "Payımızın eşit paydan 1,5 kat fazla olduğu müşterilerin oranı",
         "Ana banka ilişkisinin gücü."),
        ("Sütun: Cüzdan bölgelerine göre müşteri", "Hesaplanmış 'Cüzdan Bölgesi' sütunu × tekil müşteri",
         "Dört bölgenin büyüklüğü; her bölge farklı aksiyon."),
        ("Çubuk: Bizim limit / rakip limit", "Ortalama bizim limit / rakiplerin müşteri başı ortalama limiti, sektörde",
         "1'in altı: o sektörde limit cimrisiyiz; tahsis politikası tartışmasına girer."),
        ("Çizgi: Ana banka olma oranı", "Aylık", "İlişkinin zaman içindeki yönü."),
        ("Sütun: Ret / vazgeçme sonrası kader", "Ret ve vazgeçen müşterilerin bir sonraki sorgusunda risk ≥ %10 "
                                               "büyüyen ve gecikmeye düşen oranı",
         "Ret kararlarının geriye dönük testi: büyüdüyse fırsat kaçtı, gecikmeye düştüyse ret doğruydu."),
    ],
    [
        ("Kartlar: Skor ≥ 70, yeni gecikme, takibe düşüş", "Fact_AnomaliSkor ve Fact_Sorgu geçişleri",
         "Bu haftanın erken uyarı hacmi."),
        ("Kartlar: Skor ≥ 70 / < 70 → sonra gecikme", "O an temiz olup bir sonraki sorguda gecikmeye düşenlerin oranı",
         "Modelin geriye dönük isabeti; bu kart olmadan yönetim skora güvenmez."),
        ("Tablo: Bu hafta kime bakmalıyız?", "Müşteri, segment, son sorgu skoru, neden, bizim risk; skora göre sıralı",
         "Neden alanı sayesinde liste kara kutu değildir."),
        ("Dilimleyici + 2 çizgi: Seçili müşteri", "Müşteri seçimi yalnızca bu iki grafiği filtreler "
                                                  "(etkileşim ayarı)", "Müşterinin hikâyesi; kredi komitesinde kullanılır."),
        ("Matris: Sektör × çeyrek ortalama skor", "NACE × çeyrek, değer: ortalama anomali skoru",
         "Bir sektörün birlikte bozulduğu dönem: sektörel erken uyarı."),
        ("Dağılım: KKB notu × iç rating", "x = ortalama KKB notu, y = ortalama iç rating (1 en iyi)",
         "Köşegen dışındakiler: modelimiz bir şeyi kaçırıyor ya da fazla temkinliyiz."),
    ],
    [
        ("Dilimleyici: Portföy yöneticisi", "Dim_Musteri[PortfoyYoneticisi]; RLS ile kişiye özel",
         "Her yönetici kendi listesini görür."),
        ("Tablo: Aksiyon listesi", "Son sorguya göre aksiyon etiketi, potansiyel TL, bizim risk, skor, son sorgu; "
                                   "'İzle' etiketi filtrelenir", "Günlük iş listesi: rapor analizden operasyona döner."),
        ("Çubuk: Etiket başına potansiyel", "Σ potansiyel TL, etikete göre",
         "Masada kaç TL var? (Potansiyel kaba bir tahmindir; pilotta kalibre edilir.)"),
        ("Yığın çubuk: Bölgelere göre aksiyon", "Bölge × aksiyon bekleyen müşteri, etikete göre renkli",
         "Bölge müdürlerinin sahadaki önceliği."),
    ],
]

ETIKETLER = [
    ("Erken uyarı", "Yeni gecikme, takip veya skor ≥ 70 ve not düşüşü", "İzleme listesi, teminat gözden geçirme"),
    ("Kredi açlığı", "Banka sayısı ≥ 2 arttı ve not düştü", "Limit artışını dondur, analist incelemesi"),
    ("Pay geri kazan", "Sektör riski arttı, payımız ≥ 5 puan düştü, not stabil", "Limit ve fiyat teklifiyle ziyaret"),
    ("Limit sıkışıklığı", "Sektör doluluğu > %85, bizde boş limit var, not A–B", "Bizdeki limitin kullanımını teşvik"),
    ("Proje büyümesi", "Gayrinakdi pay ≥ 10 puan arttı, gecikme yok", "Teminat mektubu / ihale finansmanı"),
    ("Gereksiz sorgu", "7 gün içinde mükerrer sorgu", "Süreç iyileştirme"),
]

VERI = [
    ("Fact_Sorgu", "Bir sorgu", "VKN, sorgu tarihi, şube, sorgu nedeni, sektör limit/risk, nakdi/gayrinakdi, "
                               "banka sayısı, gecikme/takip, KKB notu, sorgu ücreti, sorgu günündeki bizim limit/risk",
     "KKB entegrasyon logu + saklanan yanıt + core banking günlük snapshot"),
    ("Fact_RiskDetay", "Sorgu × kredi türü", "Rotatif, spot, taksitli, TM, akreditif limit/risk", "KKB yanıtı"),
    ("Fact_KrediSonuc", "Müşteri × ay", "Bizim limit/risk, teklif/onay/kullandırım tarihi, ret nedeni, iç rating",
     "Tahsis iş akışı + core banking"),
    ("Fact_AnomaliSkor", "Bir sorgu", "Skor 0–100, neden, bireysel ve akran sapması",
     "Python skorlama (haftalık)"),
    ("Dim_Musteri / Dim_Tarih / Dim_Sube", "Müşteri / gün / şube", "Segment, NACE, il, bölge, portföy yöneticisi; "
                                                                   "ay sonu ve tatil bayrakları", "Müşteri ana verisi"),
]


def tablo(satirlar, genislikler, baslik_satiri):
    veri = [[Paragraph(h, STIL["bas"]) for h in baslik_satiri]]
    for s in satirlar:
        veri.append([Paragraph(s[0], STIL["hucre_b"])] + [Paragraph(x, STIL["hucre"]) for x in s[1:]])
    t = Table(veri, colWidths=genislikler, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(VURGU)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f6f3")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(CIZGI)),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def alt_bilgi(canvas, doc):
    canvas.saveState()
    canvas.setFont("DejaVu", 7)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(12 * mm, 7 * mm, "KKB Kurumsal Sorgu Analitiği · Power BI dashboard taslağı · sentetik örnek veri")
    canvas.drawRightString(doc.pagesize[0] - 12 * mm, 7 * mm, str(doc.page))
    canvas.restoreState()


def pdf_yaz(gorseller, cikti):
    sayfa = landscape(A4)
    doc = SimpleDocTemplate(str(cikti), pagesize=sayfa, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm,
                            bottomMargin=12 * mm, title="KKB Kurumsal Sorgu Analitiği - Dashboard Taslağı",
                            author="KKB Dashboard Taslağı")
    gen = sayfa[0] - 24 * mm
    hikaye = []

    hikaye += [Spacer(1, 18 * mm),
               Paragraph("KKB Kurumsal Sorgu Analitiği", STIL["baslik"]),
               Paragraph("Power BI dashboard taslağı · 6 sayfa · " + date.today().strftime("%d.%m.%Y"), STIL["alt"]),
               Spacer(1, 8 * mm),
               Paragraph("<b>Raporun sorusu:</b> Biz bu müşterilerin ilk bankası mıyız, yoksa yedek bankası mı? "
                         "Son 12 ayda kurumsal müşteriler için yaptığımız KKB / Risk Merkezi sorguları tek tek onay "
                         "belgesi olarak değil, aynı müşteriye yapılan ardışık sorgular bir <b>zaman serisi</b> olarak "
                         "okunur. Böylece rakip bankaların hareketi, müşterinin kredi iştahı ve bozulma sinyalleri "
                         "kredi kararından aylar önce görünür hale gelir.", STIL["metin"]),
               Spacer(1, 6 * mm)]
    hikaye.append(tablo([(f"{i}. {s[0]}", s[1]) for i, s in enumerate(SAYFALAR, 1)], [70 * mm, gen - 70 * mm],
                        ["Sayfa", "Ne anlatır"]))
    hikaye += [Spacer(1, 6 * mm), Paragraph(
        "<b>Bu dokümandaki görüntüler hakkında:</b> Sayfa görüntüleri, Power BI proje dosyasındaki (PBIP) yerleşim, "
        "görsel tipleri ve alanlardan, <b>tamamen sentetik</b> örnek veriyle çizilmiş taslaklardır. Gerçek müşteri "
        "verisi içermez; rakamlar yalnızca görünümü göstermek içindir. Power BI'da yazı tipi, renk tonları ve eksen "
        "ayrıntıları biraz farklı görünebilir.", STIL["kucuk"])]

    sekmeler = [p["displayName"] for p, _ in render_mockup.sayfa_listesi()]
    for i, ((ad, alt), yol, kilavuz, sekme) in enumerate(zip(SAYFALAR, gorseller, KILAVUZ, sekmeler), 1):
        hikaye.append(PageBreak())
        hikaye.append(Paragraph(f"Sayfa {sekme}", STIL["h1"]))
        hikaye.append(Paragraph(alt, STIL["kucuk"]))
        hikaye.append(Spacer(1, 3 * mm))
        yuk = sayfa[1] - 10 * mm - 12 * mm - 18 * mm
        w = min(gen, yuk * 16 / 9)
        hikaye.append(Image(str(yol), width=w, height=w * 9 / 16))
        hikaye.append(PageBreak())
        hikaye.append(Paragraph(f"Sayfa {sekme} · Yapım kılavuzu", STIL["h1"]))
        hikaye.append(Spacer(1, 3 * mm))
        hikaye.append(tablo(kilavuz, [62 * mm, 105 * mm, gen - 167 * mm], ["Görsel", "Nasıl hesaplanır", "Ne anlatır"]))
        if i == 6:
            hikaye.append(Spacer(1, 4 * mm))
            hikaye.append(KeepTogether([
                Paragraph("Aksiyon etiketleri (yukarıdan aşağı ilk tutan kural geçerli)", STIL["h2"]),
                tablo(ETIKETLER, [40 * mm, 127 * mm, gen - 167 * mm], ["Etiket", "Koşul", "Önerilen aksiyon"])]))

    hikaye += [PageBreak(), Paragraph("Veri gereksinimi ve uyum", STIL["h1"]), Spacer(1, 3 * mm),
               tablo(VERI, [45 * mm, 32 * mm, 120 * mm, gen - 197 * mm], ["Tablo", "Bir satır =", "Temel alanlar", "Kaynak"]),
               Spacer(1, 5 * mm), Paragraph("Ön koşul ve uyum notları", STIL["h2"])]
    for madde in [
        "KKB sorgu yanıtının (rapor içeriği) saklanması ön koşuldur; saklanmıyorsa 3., 4. ve 5. sayfalar çalışmaz.",
        "Her sorgu, aynı VKN'nin bir önceki sorgusuyla (LAG) eşleştirilir; ilk sorgular göç ve değişim hesaplarına girmez.",
        "KKB verisinin kullanım amacı (özellikle aksiyon/pazarlama sayfası) uyum ve hukuk birimine onaylatılmalıdır.",
        "Yalnızca tüzel kişiler; ham yanıt rapora taşınmaz; portföy yöneticisi bazlı satır düzeyi güvenlik (RLS) ve "
        "dışa aktarma kısıtı açılır.",
        "Potansiyel TL ve etiket eşikleri ilk tahmindir; tek bölgede 4 haftalık pilotla kalibre edilmelidir.",
    ]:
        hikaye.append(Paragraph("• " + madde, STIL["metin"]))
    doc.build(hikaye, onFirstPage=alt_bilgi, onLaterPages=alt_bilgi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="docs")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    veri = render_mockup.yukle(args.data)
    secimler = render_mockup.sayfa_secimleri(veri)
    gorseller = []
    for i, (p, g) in enumerate(render_mockup.sayfa_listesi(), 1):
        yol = out / f"sayfa_{i}.png"
        render_mockup.sayfa_ciz(p, g, veri, yol, secimler.get(p["name"], {}))
        gorseller.append(yol)
    cikti = out / "KKB_Dashboard_Taslak.pdf"
    pdf_yaz(gorseller, cikti)
    print("PDF yazildi:", cikti)


if __name__ == "__main__":
    main()
