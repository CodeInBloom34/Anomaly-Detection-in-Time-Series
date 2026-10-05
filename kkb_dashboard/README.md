# KKB Kurumsal Sorgu Analitiği – Power BI başlangıç kiti

Son 12 ayda kurumsal müşteriler için yapılan KKB / Risk Merkezi sorgularını analiz eden Power BI dashboard'unun veri hazırlık katmanı. Rapor tasarımı (6 sayfa, her görselin ne gösterdiği, nasıl elde edildiği ve ne anlattığı) ayrı taslak belgededir. Bu klasör o tasarımın çalışan iskeletidir.

> Buradaki tüm veriler **sentetiktir**. VKN, unvan ve tutarlar rastgele üretilir. Gerçek müşteri verisi bu repoya konmamalıdır.

## İçerik

| Dosya | Ne yapar |
| --- | --- |
| `powerbi/KKB_Sorgu_Analitigi.pbip` | **Power BI projesi.** Power BI Desktop'ta bu dosyayı açın. 6 sayfa, 50 ölçü, 10 tablo içerir. |
| `data/` | Projenin okuduğu sentetik örnek CSV'ler (8 dosya). |
| `generate_sample_data.py` | Örnek CSV'leri yeniden üretir: `Dim_Tarih`, `Dim_Sube`, `Dim_Musteri`, `Dim_NotBandi`, `Fact_Sorgu`, `Fact_RiskDetay`, `Fact_KrediSonuc`. |
| `anomaly_score.py` | Her müşterinin ardışık sorgularından davranışsal anomali skoru (0–100) ve "neden" alanı üretir, `Fact_AnomaliSkor.csv` dosyasına yazar. |
| `powerbi/build_pbip.py` | Power BI projesini ve `measures.dax` dosyasını üretir. Ölçü veya görsel değişikliği burada yapılır. |
| `docs/KKB_Dashboard_Taslak.pdf` | Paylaşılabilir taslak: 6 sayfanın örnek veriyle çizilmiş görüntüsü ve görsel bazında yapım kılavuzu. |
| `powerbi/render_mockup.py`, `powerbi/mockup_pdf.py` | Sayfa görüntülerini PBIP yerleşiminden çizer ve PDF'i üretir (`python powerbi/mockup_pdf.py`). |
| `powerbi/measures.dax` | Tüm DAX ölçüleri, hesaplanmış sütunlar ve tablolar (okumak için; üretilmiş dosya). |
| `sql/fact_sorgu_view.sql` | Gerçek veride `Fact_Sorgu` tablosunu kuran view örneği. |
| `tests/` | Veri tutarlılığı, skor ve Power BI projesinin iç tutarlılığı testleri. |

## Power BI'da açma

Ön koşul: Power BI Desktop'ta *Dosya → Seçenekler ve ayarlar → Seçenekler → Önizleme özellikleri* altında **Power BI Project (.pbip) kaydetme seçeneği** ve **PBIR biçiminde rapor depolama** açık olmalı. Yeni sürümlerde bu seçenekler varsayılan olarak açıktır.

1. Repoyu indirin (GitHub'da *Code → Download ZIP*) ve bir klasöre çıkarın, örneğin `C:\KKB`.
2. `kkb_dashboard\powerbi\KKB_Sorgu_Analitigi.pbip` dosyasını Power BI Desktop ile açın.
3. *Giriş → Verileri dönüştür → Parametreleri düzenle* ile `VeriKlasoru` parametresini CSV'lerin bulunduğu klasöre ayarlayın, örneğin `C:\KKB\<indirilen klasör>\kkb_dashboard\data`. Sonda `\` olmasın.
4. *Değişiklikleri uygula* deyin ve verilerin yüklenmesini bekleyin.
5. İsterseniz *Dosya → Farklı kaydet* ile `.pbix` olarak kaydedin.

Doğru yüklendiğini kontrol etmek için 1. sayfada şu değerleri görmelisiniz (filtre yokken):

| Kart | Beklenen değer |
| --- | --- |
| Toplam sorgu | 1.760 |
| Tekil müşteri | 564 |
| Sorgu → kullandırım | %39,0 |
| Ölü sorgu maliyeti (TL) | 14.150 |
| Cüzdan payı | %24,2 |
| Kör nokta müşteri | 36 |

Projede elle tamamlanması gereken birkaç adım var:

- **Isı haritası renkleri:** 2. sayfadaki "Ayın haftası × gün" matrisine *Koşullu biçimlendirme → Arka plan rengi* ekleyin.
- **Sankey:** 3. sayfadaki not göçü matrisini isterseniz AppSource'taki Sankey görseliyle değiştirebilirsiniz.
- **Drill-through:** 5. sayfadaki müşteri zaman serisi şimdilik dilimleyiciyle çalışıyor. İsterseniz ayrı bir drill-through sayfasına taşıyın.
- **Satır düzeyi güvenlik (RLS):** *Modelleme → Rolleri yönet* ile portföy yöneticisi rolünü `Dim_Musteri[PortfoyYoneticisi]` üzerinden tanımlayın.

Proje açılırken hata verirse hata mesajının ekran görüntüsünü paylaşın. Dosyalar Microsoft'un yayımladığı PBIR şemalarına göre doğrulandı, ancak Power BI Desktop'ta açılarak test edilmedi.

## Hızlı başlangıç (veriyi yeniden üretmek için)

```bash
cd kkb_dashboard
pip install -r requirements.txt
python generate_sample_data.py --out data --musteri 600
python anomaly_score.py --data data
python powerbi/build_pbip.py
python powerbi/mockup_pdf.py --data data --out docs
python -m unittest discover tests
```

## Anomali skoru nasıl çalışır?

Her sorgu bir önceki sorguyla karşılaştırılır ve 7 özellikten oluşan bir değişim vektörü çıkarılır:

- 30 güne normalize sektör riski büyümesi
- Limit doluluğu değişimi
- Banka sayısı değişimi
- KKB notu değişimi
- Gayrinakdi pay kayması
- Rotatif pay kayması
- Bizim pay değişimi

| Parça | Yöntem | Ne yakalar |
| --- | --- | --- |
| Bireysel sapma | Müşterinin kendi geçmiş değişimlerine göre robust z (medyan / MAD). En az 2 geçmiş değişim gerekir. | "Bu müşteri için alışılmadık" bir hareket |
| Akran sapması | Sektör × segment içinde standartlaştırılmış vektör üzerinde Isolation Forest | "Benzerlerine göre alışılmadık" bir hareket |
| Kural katmanı | Yeni gecikme ≥ 80, takibe düşüş ≥ 90 | Kaçırılmaması gereken kesin sinyaller |

Skor = 0,5 × bireysel + 0,5 × akran. Bireysel geçmiş yoksa yalnızca akran sapması kullanılır. `Neden` alanı en büyük sapmayı veren özelliği ve yönünü yazar.

Örnek veride (600 müşteri) senaryo bazında medyan skorlar şöyle çıktı: stabil ≈ 27, bozulma ≈ 78, proje büyümesi ≈ 78. Gerçek veride eşikler (≥ 70 gibi) pilot dönemde geriye dönük testle kalibre edilmelidir.

## Gerçek veriye geçiş

1. `sql/fact_sorgu_view.sql` dosyasındaki kaynak tablo adlarını kendi ortamınıza uyarlayın. KKB sorgu yanıtının saklanması ön koşuldur.
2. `anomaly_score.py` scriptini `--data` ile view çıktılarının bulunduğu klasöre yönlendirin. Haftalık zamanlanmış bir iş olarak çalıştırın.
3. KKB verisinin kullanım amacını uyum ve hukuk birimine onaylatın. Ham yanıt rapora taşınmamalı, RLS ve export kısıtlarını açın.
