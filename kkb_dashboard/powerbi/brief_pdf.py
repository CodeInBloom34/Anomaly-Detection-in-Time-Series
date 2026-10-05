"""Ekibe gonderilecek yonetici brifi: numarali taslak gorseller + her gorselin amaci.

Hesaplama detayina girmez; her gorselde neye ulasmak istedigimizi anlatir.
Taslak sayfa gorsellerini (render_mockup) uretir, her gorselin kosesine numara koyar.

Kullanim (kkb_dashboard klasorunden):
    python powerbi/brief_pdf.py --data data --out docs
"""

import argparse
import sys
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

import render_mockup  # noqa: E402
from mockup_pdf import INK2, MUTED, STIL, VURGU, ParagraphStyle  # noqa: E402  (fontlari da kaydeder)

ROZET_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

GIRIS = """Merhaba ekip,

Son bir yılda kurumsal müşterilerimiz için yaptığımız KKB sorgularını bir maliyet kalemi olmaktan çıkarıp
bankanın en ucuz pazar istihbaratına dönüştürmek istiyorum. Her sorgu, müşterinin diğer bankalarla ilişkisine
açılan bir pencere. Biz bu pencereye bugüne kadar sadece kredi onaylarken baktık.

Kurmanızı istediğim dashboard'un tek bir sorusu var: <b>Biz bu müşterilerin ilk bankası mıyız, yoksa yedek
bankası mı?</b> Ekteki taslaklar bu soruyu altı adımda cevaplıyor. Görsellerdeki rakamlar sentetik, gerçek
müşteri verisi değil; sadece nasıl görünmesini istediğimi anlatıyor.

Her sayfada görsellerin üzerine numara koydum. Numaraların karşısında o görselden ne öğrenmek istediğimi ve
o bilgiyle hangi kararı vereceğimizi yazdım. Hesaplama detayları ayrıca paylaştığım teknik dokümanda var;
burada önemli olan neye ulaşmaya çalıştığımızı ortak anlamamız."""

# Her sayfa: (giris cumlesi, [(numara verilecek gorseller, baslik, amac), ...])
SAYFALAR = {
    "p1_ozet": ("Bu sayfayı üst yönetime açacağız. 30 saniyede efor, risk ve payımızı anlatabilmeli.", [
        (["seg", "bolge"], "Segment ve bölge filtreleri",
         "Her şeyi segment ve bölge bazında kırabilmek istiyorum. Kurumsal ile KOBİ'nin hikâyesi aynı değil."),
        (["k0", "k1"], "Toplam sorgu ve tekil müşteri",
         "Bir yılda ne kadar efor harcadığımızı ve kaç firmaya baktığımızı tek bakışta görmek istiyorum."),
        (["k2"], "Sorgudan kullandırıma",
         "Baktığımız dosyaların ne kadarı krediye dönüyor? Eforumuzun ticari karşılığını bilmek istiyorum."),
        (["k3"], "Ölü sorgu maliyeti",
         "Hiçbir aksiyona dönüşmeyen sorgulara ödediğimiz parayı görünür kılın. Bu rakam bugün kimsenin önünde değil."),
        (["k4"], "Cüzdan payı",
         "Müşterilerimizin toplam borcunda ne kadar yer tuttuğumuzu bilmek istiyorum. Asıl hedefimiz bu rakam."),
        (["k5", "k6"], "Payı eriyen müşteri, yeni gecikme",
         "İki alarm: rakibe kayan müşteri ve başka bankada bozulmaya başlayan müşteri. İkisini de kendi "
         "kitabımıza yansımadan görmeliyiz."),
        (["trend", "paytrend"], "Aylık sorgu ve aylık cüzdan payı",
         "Daha çok bakıyor muyuz, baktıkça payımız artıyor mu? İkisini alt alta görüp yorumlamak istiyorum."),
        (["ozet"], "Dönem özeti",
         "Yönetime gidecek üç cümle. Filtre değiştikçe kendiliğinden güncellensin, kimse elle yazmasın."),
        (["kor", "korrisk"], "Kör nokta",
         "Riskini taşıdığımız ama bir yıldır dışarıdan hiç bakmadığımız müşteriler. Bu sayının sıfıra yakın "
         "olmasını istiyorum."),
        (["anomali", "yedek", "mukerrer", "musbasina"], "Diğer sayfalara kapılar",
         "Bu kartlar diğer sayfaların özeti. Tıklayınca ilgili sayfaya gidilebilsin."),
    ]),
    "p2_davranis": ("Bu sayfa müşteriyi değil bizi aynaya tutuyor: sorgu bütçemiz nereye gidiyor?", [
        (["gun", "maliyet"], "Hız ve toplam maliyet",
         "Sorgudan krediye ne kadar sürede geçiyoruz ve sorgulara toplam ne ödüyoruz? Yavaş kaldığımız dosyada "
         "müşteri başka bankaya gidebilir."),
        (["huni"], "Başvurudan kullandırıma huni",
         "Müşteriyi nerede kaybettiğimizi görmek istiyorum: teklif aşamasında mı, kararda mı, kullandırımda mı?"),
        (["isi"], "Ayın haftası × gün",
         "Sorguların ayın hangi günlerinde yığıldığını görelim. Ay sonu telaşı varsa kanıtıyla görmek istiyorum."),
        (["aysonu"], "Ay sonu baskısı",
         "Ay sonunda yaptığımız sorgular gerçekten daha az mı krediye dönüyor? Cevap evetse hedef sistemimizi "
         "konuşacağız."),
        (["neden"], "Sorgu nedeni",
         "Ne kadarı müşteri gelince bakılan, ne kadarı bizim proaktif izlememiz? Dengenin izleme tarafına "
         "kaymasını istiyorum."),
        (["tekrar"], "Tekrar bakma aralığı",
         "Aynı müşteriye bir hafta içinde ikinci kez bakıyorsak boşa para ödüyoruz. Altı aydır bakmıyorsak izleme "
         "açığımız var. İki ucu da görmek istiyorum."),
        (["sube"], "Şube bazında verim",
         "Hangi birim çok sorgulayıp az kazanıyor? Amaç kimseyi suçlamak değil, nerede desteğe ihtiyaç olduğunu "
         "bulmak."),
    ]),
    "p3_risk": ("Aynı müşteriye iki kez baktıysak arada ne değişti? Tek rapor fotoğraf, iki rapor film.", [
        (["notgocu"], "Not bandı göçü",
         "Portföyün kalitesi bir yılda ne yöne aktı? İyi notlu müşterilerimiz kötüleşiyor mu, kötüler toparlıyor mu?"),
        (["bankanot"], "Banka sayısı × not değişimi",
         "Yeni banka ekleyen müşteri ya büyüyordur ya da sıkışıyordur. Bu tablo ikisini birbirinden ayırsın."),
        (["kopru"], "Risk artışını kim finanse etti?",
         "Bu sayfanın en önemli sorusu: müşterilerimizin borcu büyüdü, bu büyümenin ne kadarını biz, ne kadarını "
         "rakipler finanse etti?"),
        (["karisim"], "Kredi türü karışımı",
         "Müşteriler ne tür kredi kullanıyor ve bu değişiyor mu? Rotatif artıyorsa nakit sıkışması, teminat "
         "mektubu artıyorsa yeni projeler var demektir."),
        (["doluluk"], "Limit doluluğu",
         "Müşteriler limitlerini ne kadar dolduruyor? Sıkışma başladığında ilk biz görmek istiyorum."),
        (["gocler"], "En büyük göçler",
         "Bütün bunların somut isimleri. Portföy yöneticisi bu listeye bakıp telefonu açabilmeli."),
    ]),
    "p4_rakip": ("KKB rakip adı vermiyor ama rakiplerin toplam hareketini veriyor. Bu sayfa onu okuyor.", [
        (["cuzdan"], "Cüzdan matrisi",
         "Raporun kalbi. Her müşteri dört bölgeden birine düşsün. Sol üst köşe benim için en önemlisi: müşteri "
         "büyüyor ama biz pay alamıyoruz."),
        (["yedek"], "Yedek banka endeksi",
         "Müşteri bizi ana banka mı yoksa yedek mi görüyor? Bizde boş limit dururken rakibin limitini kullanıyorsa "
         "fiyatta ya da üründe bir şeyi yanlış yapıyoruz."),
        (["anabanka", "anatrend"], "Ana banka olma oranı",
         "Ana bankası olduğumuz müşterilerin oranı ve gidişatı. Bu oran düşüyorsa benim için alarm."),
        (["eriyen"], "Payı eriyen müşteri",
         "Rakibe kayan müşteri sayısı. Bu sayfada da gözümün önünde olsun."),
        (["bolge"], "Cüzdan bölgeleri",
         "Dört bölgede kaç müşterimiz var? Her bölge ayrı bir eylem planı demek."),
        (["limit"], "Bizim limit / rakip limit",
         "Hangi sektörde rakiplere göre limit cimrisiyiz? Bu bilgiyle kredi politikasını konuşmak istiyorum."),
        (["ret"], "Ret ve vazgeçme sonrası",
         "Reddettiğimiz ya da bizden vazgeçen müşteriye sonra ne oldu? Başka yerde büyüdüyse fırsat kaçırmışız, "
         "gecikmeye düştüyse doğru karar vermişiz. Kararlarımızın karnesi."),
    ]),
    "p5_uyari": ("Sabit eşiklere değil, her müşterinin kendi normaline bakıyoruz. Skor karar değil, bakış önceliği.", [
        (["k0", "k1", "k2"], "Bu haftanın alarmları",
         "Bu hafta kaç müşteri olağan dışı davranıyor, kaçında yeni gecikme ya da takip var?"),
        (["k3", "k4"], "Modelin karnesi",
         "Yüksek skor verdiğimiz müşteriler gerçekten daha sık bozuluyor mu? Bu fark görünmüyorsa skora "
         "güvenmeyeceğiz. Bu iki kart olmadan sayfayı yayına almayın."),
        (["liste"], "Bu hafta kime bakmalıyız?",
         "Her hafta öncelikli müşteri listesi, nedeniyle birlikte. Neden yazmayan bir liste istemiyorum."),
        (["musteri", "seri", "seridol"], "Seçili müşterinin hikâyesi",
         "Bir müşteriyi seçince geçmişini görelim. Kredi komitesine bu grafiklerle gidilebilsin."),
        (["sektor"], "Sektör × çeyrek",
         "Tek bir müşteri değil, bütün bir sektör birlikte bozuluyorsa bunu çeyrek bazında erken görmek istiyorum."),
        (["rating"], "KKB notu × iç rating",
         "KKB'nin gördüğü ile bizim iç notumuz nerede ayrışıyor? Ayrışanlar ya modelimizin kaçırdığı risk ya da "
         "fazla temkinli davrandığımız fırsat."),
    ]),
    "p6_aksiyon": ("Bütün analiz burada iş listesine dönüşüyor. Rapor bu sayfa kullanıldığında başarılı olacak.", [
        (["py"], "Portföy yöneticisi filtresi",
         "Her portföy yöneticisi sadece kendi müşterilerini görsün."),
        (["liste"], "Aksiyon listesi",
         "Pazartesi sabahı iş listesi: kimi arıyoruz, neden arıyoruz ve masada ne kadar iş var."),
        (["etiket"], "Etiket başına potansiyel",
         "Hangi tür fırsatta ne kadar potansiyel olduğunu görüp önceliği buna göre vereceğiz."),
        (["bolge"], "Bölgelere göre aksiyon",
         "Hangi bölgede ne kadar iş birikmiş, saha ekiplerini buna göre yönlendireceğiz."),
    ]),
}

BEKLENTILER = [
    "<b>Öncelik sırası:</b> İlk sürümde 1. ve 4. sayfayı, ardından 6. sayfayı görmek istiyorum. Diğer sayfalar "
    "ikinci adımda gelebilir.",
    "<b>Önce veri:</b> Kuruluma başlamadan KKB sorgu yanıtlarının sistemde saklanıp saklanmadığını kontrol edin. "
    "Saklanmıyorsa 3., 4. ve 5. sayfalar çalışmaz; bunu en başta bilmemiz lazım.",
    "<b>Uyum:</b> KKB verisini bu amaçla kullanmamız için uyum ve hukuk biriminin onayını alalım. Rapor sadece "
    "tüzel kişileri kapsasın, her portföy yöneticisi sadece kendi müşterilerini görsün.",
    "<b>Esneklik:</b> Görseller taslak. Daha iyi bir gösterim yolu bulursanız önerin; ama her görselin cevapladığı "
    "soru değişmesin.",
    "<b>Pilot:</b> Önce tek bir bölgede birkaç hafta deneyelim, etiketlerin ve skorun isabetini ölçüp sonra "
    "yaygınlaştıralım.",
]


def numarala(kaynak, hedef, gorseller, maddeler):
    """Gorsellerin sag ust kosesine madde numarasini rozet olarak ekler."""
    im = PILImage.open(kaynak).convert("RGB")
    olcek = im.width / 1280
    ciz = ImageDraw.Draw(im)
    font = ImageFont.truetype(ROZET_FONT, int(15 * olcek))
    konum = {g["name"]: g["position"] for g in gorseller}
    r = 13 * olcek
    for no, (adlar, _, _) in enumerate(maddeler, 1):
        for ad in adlar:
            p = konum[ad]
            cx = (p["x"] + p["width"] - 18) * olcek
            cy = (p["y"] + 17) * olcek
            ciz.ellipse([cx - r, cy - r, cx + r, cy + r], fill=VURGU, outline="white", width=int(2 * olcek))
            ciz.text((cx, cy), str(no), fill="white", font=font, anchor="mm")
    im.save(hedef)


def pdf_yaz(sayfalar, cikti):
    boyut = landscape(A4)
    doc = SimpleDocTemplate(str(cikti), pagesize=boyut, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm,
                            bottomMargin=12 * mm, title="KKB Sorgu Dashboard'u - Ekip Brifi")
    gen = boyut[0] - 24 * mm
    madde_no = ParagraphStyle("no", parent=STIL["hucre_b"], textColor=colors.HexColor(VURGU), fontSize=11,
                              leading=12)
    madde_bas = ParagraphStyle("mb", parent=STIL["hucre_b"], fontSize=8.6, leading=11)
    madde_metin = ParagraphStyle("mm", parent=STIL["hucre"], fontSize=8.4, leading=11.2)
    giris = ParagraphStyle("giris", parent=STIL["metin"], fontSize=10.5, leading=16)

    def alt_bilgi(canvas, d):
        canvas.saveState()
        canvas.setFont("DejaVu", 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(12 * mm, 7 * mm, "KKB sorgu dashboard'u · ekip brifi · görseller sentetik örnek veriyle "
                                           "hazırlanmış taslaklardır")
        canvas.drawRightString(boyut[0] - 12 * mm, 7 * mm, str(d.page))
        canvas.restoreState()

    h = [Spacer(1, 10 * mm), Paragraph("KKB Sorgu Dashboard'u: Neye Ulaşmak İstiyoruz?", STIL["baslik"]),
         Paragraph("Ekip brifi", STIL["alt"]), Spacer(1, 8 * mm)]
    for par in GIRIS.split("\n\n"):
        h += [Paragraph(par.replace("\n", " "), giris), Spacer(1, 3 * mm)]
    h += [Spacer(1, 3 * mm), Paragraph("Altı sayfa, altı soru", STIL["h2"]), Spacer(1, 1 * mm)]
    sorular = [(sekme, soru) for sekme, soru, *_ in sayfalar]
    t = Table([[Paragraph(s, madde_bas), Paragraph(q, madde_metin)] for s, q in sorular], colWidths=[55 * mm, 120 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e1e0d9")),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    h.append(t)

    for sekme, soru, giris_cumle, resim, maddeler in sayfalar:
        h.append(PageBreak())
        h.append(Paragraph(f"{sekme}: {soru}", STIL["h1"]))
        h.append(Paragraph(giris_cumle, ParagraphStyle("gc", parent=STIL["kucuk"], fontSize=9, textColor=INK2)))
        h.append(Spacer(1, 3 * mm))
        resim_gen = 178 * mm
        satirlar = []
        for no, (_, baslik, amac) in enumerate(maddeler, 1):
            satirlar.append([Paragraph(str(no), madde_no),
                             [Paragraph(baslik, madde_bas), Paragraph(amac, madde_metin)]])
        liste = Table(satirlar, colWidths=[10 * mm, gen - resim_gen - 14 * mm])
        stil = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        stil.append(("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e1e0d9")))
        liste.setStyle(TableStyle(stil))
        duzen = Table([[Image(str(resim), width=resim_gen, height=resim_gen * 9 / 16), liste]],
                      colWidths=[resim_gen + 4 * mm, gen - resim_gen - 4 * mm])
        duzen.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        h.append(duzen)

    h += [PageBreak(), Paragraph("Ekipten beklentilerim", STIL["h1"]), Spacer(1, 4 * mm)]
    for b in BEKLENTILER:
        h += [Paragraph("• " + b, giris), Spacer(1, 2.5 * mm)]
    h += [Spacer(1, 6 * mm), Paragraph(
        "Soruları bu doküman üzerinden toplayalım. Her görselin neden orada olduğu konusunda aynı noktada olursak "
        "gerisi teknik detay. Teşekkürler.", giris), Spacer(1, 8 * mm), Paragraph("[Adınız]", giris)]
    doc.build(h, onFirstPage=alt_bilgi, onLaterPages=alt_bilgi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="docs")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    veri = render_mockup.yukle(args.data)
    secimler = render_mockup.sayfa_secimleri(veri)
    sayfalar = []
    from mockup_pdf import SAYFALAR as SORULAR
    for i, ((p, gorseller), (soru, _)) in enumerate(zip(render_mockup.sayfa_listesi(), SORULAR), 1):
        ham = out / f"sayfa_{i}.png"
        render_mockup.sayfa_ciz(p, gorseller, veri, ham, secimler.get(p["name"], {}))
        numarali = out / f"brif_sayfa_{i}.png"
        giris_cumle, maddeler = SAYFALAR[p["name"]]
        numarala(ham, numarali, gorseller, maddeler)
        sayfalar.append((p["displayName"], soru, giris_cumle, numarali, maddeler))
    cikti = out / "KKB_Dashboard_Ekip_Brifi.pdf"
    pdf_yaz(sayfalar, cikti)
    print("PDF yazildi:", cikti)


if __name__ == "__main__":
    main()
