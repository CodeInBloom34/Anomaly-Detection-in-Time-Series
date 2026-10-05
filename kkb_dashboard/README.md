# KKB Kurumsal Sorgu Analitiği – Power BI başlangıç kiti

Son 12 ayda kurumsal müşteriler için yapılan KKB / Risk Merkezi sorgularını analiz eden Power BI dashboard'unun veri hazırlık katmanı. Rapor tasarımı (6 sayfa, her görselin ne gösterdiği, nasıl elde edildiği ve ne anlattığı) ayrı taslak belgededir. Bu klasör o tasarımın çalışan iskeletidir.

> Buradaki tüm veriler **sentetiktir**. VKN, unvan ve tutarlar rastgele üretilir. Gerçek müşteri verisi bu repoya konmamalıdır.

## İçerik

| Dosya | Ne yapar |
| --- | --- |
| `generate_sample_data.py` | Yıldız şemasındaki tüm tabloları CSV olarak üretir: `Dim_Tarih`, `Dim_Sube`, `Dim_Musteri`, `Dim_NotBandi`, `Fact_Sorgu`, `Fact_RiskDetay`, `Fact_KrediSonuc`. |
| `anomaly_score.py` | Her müşterinin ardışık sorgularından davranışsal anomali skoru (0–100) ve "neden" alanı üretir, `Fact_AnomaliSkor.csv` dosyasına yazar. |
| `powerbi/measures.dax` | Rapordaki tüm DAX ölçüleri ile cüzdan bölgesi ve aksiyon etiketi hesaplanmış sütunları. |
| `sql/fact_sorgu_view.sql` | Gerçek veride `Fact_Sorgu` tablosunu kuran view örneği (LAG ile önceki sorgu alanları ve 60 günlük sorgu sonucu). |
| `tests/test_pipeline.py` | Veri tutarlılığı ve skorun senaryoları ayırt ettiğini kontrol eden testler. |

## Hızlı başlangıç

```bash
cd kkb_dashboard
pip install -r requirements.txt
python generate_sample_data.py --out data --musteri 600
python anomaly_score.py --data data
python -m unittest discover tests
```

Ardından Power BI Desktop'ta:

1. *Veri al → Metin/CSV* ile `data/` klasöründeki 8 dosyayı yükleyin. VKN alanlarını **metin** tipine çevirin.
2. İlişkileri kurun. Hepsi tek yönlü ve 1→* olmalı:
   - `Dim_Musteri[VKN]` → `Fact_Sorgu`, `Fact_KrediSonuc`, `Fact_AnomaliSkor`
   - `Dim_Tarih[Tarih]` → `Fact_Sorgu[SorguTarihi]`, `Fact_KrediSonuc[Tarih]`
   - `Dim_Sube[SubeKod]` → `Fact_Sorgu[SubeKod]`
   - `Dim_NotBandi[Bant]` → `Fact_Sorgu[NotBandi]`
   - `Fact_Sorgu[SorguID]` → `Fact_RiskDetay[SorguID]`
3. `Dim_Tarih` tablosunu *tarih tablosu olarak işaretleyin*.
4. `powerbi/measures.dax` içindeki ölçüleri ekleyin. Yorum satırındaki iki hesaplanmış sütunu (`Cuzdan Bolgesi`, `Aksiyon Etiketi`) `Fact_Sorgu` tablosuna ekleyin.
5. `Dim_Musteri[_Senaryo]` sütununu gizleyin. Bu alan yalnızca sentetik verinin doğrulaması içindir, gerçek veride yoktur.

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

Örnek veride (600 müşteri) senaryo bazında medyan skorlar şöyle çıktı: stabil ≈ 27, bozulma ≈ 80, proje büyümesi ≈ 78. Gerçek veride eşikler (≥ 70 gibi) pilot dönemde geriye dönük testle kalibre edilmelidir.

## Gerçek veriye geçiş

1. `sql/fact_sorgu_view.sql` dosyasındaki kaynak tablo adlarını kendi ortamınıza uyarlayın. KKB sorgu yanıtının saklanması ön koşuldur.
2. `anomaly_score.py` scriptini `--data` ile view çıktılarının bulunduğu klasöre yönlendirin. Haftalık zamanlanmış bir iş olarak çalıştırın.
3. KKB verisinin kullanım amacını uyum ve hukuk birimine onaylatın. Ham yanıt rapora taşınmamalı, RLS ve export kısıtlarını açın.
