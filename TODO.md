# TODO List — Anomaly Detection in Time Series

## 1. Proje Kurulumu
- [x] `requirements.txt` / `pyproject.toml` oluştur (numpy, pandas, scikit-learn, matplotlib, vb.)
- [x] Proje klasör yapısını oluştur (`data/`, `notebooks/`, `src/`, `tests/`, `models/`)
- [x] `.gitignore` ekle (veri dosyaları, model çıktıları, `__pycache__`, vb.)
- [x] README.md dosyasını proje amacı, kurulum ve kullanım talimatlarıyla genişlet

## 2. Veri
- [ ] Kullanılacak zaman serisi veri setini belirle/indir (ör. NAB, Yahoo S5, KPI, ya da sentetik veri)
- [ ] Veri yükleme ve ön işleme (temizleme, eksik değer doldurma, zaman damgası düzeni) fonksiyonlarını yaz
- [ ] Veri normalizasyonu / ölçekleme uygula
- [ ] Train/validation/test bölünmesini zaman serisi mantığına uygun şekilde yap (data leakage olmadan)

## 3. Keşifsel Veri Analizi (EDA)
- [ ] Zaman serisini görselleştir (trend, mevsimsellik, gürültü)
- [ ] Temel istatistikleri çıkar (ortalama, varyans, ACF/PACF)
- [ ] Bilinen anomalileri/etiketleri (varsa) görselleştirerek incele

## 4. Anomali Tespit Yöntemleri
- [ ] İstatistiksel yöntemler: Z-score, moving average + std, IQR tabanlı eşikleme
- [ ] Klasik ML: Isolation Forest, One-Class SVM, Local Outlier Factor
- [ ] Zaman serisine özel modeller: ARIMA/SARIMA rezidü analizi, Prophet
- [ ] Derin öğrenme: LSTM/GRU Autoencoder, Transformer tabanlı yaklaşım
- [ ] Her yöntem için ayrı bir modül/dosya oluştur (`src/models/`)

## 5. Değerlendirme
- [ ] Değerlendirme metriklerini tanımla (Precision, Recall, F1, ROC-AUC, Point-Adjust metrikleri)
- [ ] Farklı modelleri aynı veri seti üzerinde karşılaştıran bir script yaz
- [ ] Sonuçları tablo/grafik olarak raporla

## 6. Test ve Kalite
- [ ] Veri işleme fonksiyonları için unit testler yaz (`tests/`)
- [ ] Model eğitim/çıkarım pipeline'ı için entegrasyon testi ekle
- [ ] CI (GitHub Actions) ile testleri otomatikleştir

## 7. Dokümantasyon ve Sunum
- [ ] Kullanılan yöntemleri ve sonuçları özetleyen bir rapor/notebook hazırla
- [ ] API/CLI kullanım örnekleri ekle
- [ ] Lisans dosyası ekle

## 8. İleri Seviye (Opsiyonel)
- [ ] Gerçek zamanlı (streaming) anomali tespiti desteği ekle
- [ ] Basit bir dashboard/görselleştirme arayüzü (Streamlit/Dash) oluştur
- [ ] Modeli bir API olarak sun (FastAPI/Flask)
