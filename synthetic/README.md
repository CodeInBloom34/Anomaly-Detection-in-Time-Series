# Gizlilik korumalı sentetik panel veri üretimi (taxid × tarih)

Gerçek veri kurum dışına çıkmaz. Akış:

```
[Senin ortamın]                         [Paylaşılabilir]          [Herhangi bir yer]
gerçek veri ──profile_data.py──▶ profile.json ──generate_synthetic.py──▶ sentetik.csv
                                 (sadece özet istatistik)          └─validate.py─▶ kalite raporu
```

## 1) Profil çıkar (gerçek verinin olduğu makinede)

```bash
pip install -r requirements.txt
python profile_data.py veri.csv --date-col tarih --id-col taxid -o profile.json
# isim/adres gibi kolonlar varsa: --exclude unvan adres
```

`profile.json` içinde **satır, taxid ve min/max yok**. Sadece:
- her kolonun tipi, eksik oranı, 101 noktalı kantil dağılımı (uçlar %0.5/%99.5'ten kırpılmış, 4 anlamlı basamağa yuvarlanmış)
- kategorilerin oranları (10'dan az gözlemli kategoriler `__OTHER__` olarak birleştirilir)
- kolonlar arası korelasyon matrisi (rank tabanlı)
- zaman yapısı: firma-içi benzerlik (ICC), AR(1), ay etkisi, trend; firma sabiti kolon bayrağı
- panel yapısı: firma sayısı, frekans, başlangıç/bitiş dağılımı, doluluk oranı

`examples/demo_profile.json` nasıl göründüğüne örnektir. Paylaşmadan önce gözle kontrol et.

## 2) Sentetik veri üret

```bash
python generate_synthetic.py profile.json -o sentetik.csv --n-ids 10000 --anomaly-rate 0.03
```

- taxid'ler `SYN0000001` biçiminde, gerçek VKN ile karışmaz
- `--start 2020-01-01` ile tarih ekseni kaydırılabilir
- `--anomaly-rate` > 0 ise şu tipler enjekte edilir ve etiketlenir (`is_anomaly`, `anomaly_type`, `anomaly_cols`):
  `spike` (tek dönem sıçrama), `level_shift` (kalıcı seviye kayması), `drift` (giderek artan sapma), `zero_out` (beyanın sıfırlanması)

## 3) Doğrula

```bash
python validate.py profile.json sentetik.csv
```

Kolon bazında eksik oranı, medyan, kantil hatası, ICC/AR(1) ve korelasyon farkını gösterir.

## Model

Gaussian copula + panel zaman serisi:

```
z[firma,t,j] = √icc_j · b[firma,j]  +  √(1−icc_j) · AR1_j(t)  +  ay_etkisi_j  +  trend_j·t
```

`b` ve AR inovasyonları korelasyon matrisinden (Cholesky) çekilir; her kolon sonra sıralama ile kendi
kantil dağılımına eşlenir. Böylece sıfır yığılması, çarpıklık, tam sayılık ve eksiklik korunur.

## Bilinen sınırlar

- Muhasebe kimlikleri (ör. `hesaplanan_kdv = matrah × oran`, `net_kar = satış − gider`) yalnızca korelasyonla
  yaklaşık korunur. Bu tür kuralları üretim sonrası türetilmiş kolon olarak yeniden hesaplamak en doğrusu.
- Çok yoğun sıfırlı / ikili kolonlar arasındaki korelasyon bir miktar zayıflar.
- Doğrusal olmayan ve koşullu ilişkiler (ör. sektöre göre farklı mevsimsellik) modellenmez.
- Bu yöntem formal diferansiyel gizlilik garantisi vermez; özet istatistik paylaşımıdır.
