-- Fact_Sorgu view'i: KKB sorgu logu + yanit ozeti + sorgu gunundeki bizim limit/risk.
-- Kaynak tablo adlari ornektir (kkb_sorgu_log, kkb_sorgu_yanit, kredi_snapshot_gunluk,
-- kkb_birim_maliyet); kendi ortaminizdaki adlarla degistirin. Sozdizimi ANSI'ye yakindir
-- (SQL Server / Oracle / PostgreSQL'de kucuk uyarlamalarla calisir).

CREATE VIEW vw_fact_sorgu AS
WITH sorgu AS (
    SELECT
        l.sorgu_id                                  AS SorguID,
        l.vkn                                       AS VKN,
        CAST(l.sorgu_zamani AS DATE)                AS SorguTarihi,
        l.sube_kod                                  AS SubeKod,
        l.kullanici_id                              AS KullaniciID,
        l.rapor_tipi                                AS RaporTipi,
        l.sorgu_nedeni                              AS SorguNedeni,
        y.sektor_toplam_limit                       AS SektorToplamLimit,
        y.sektor_toplam_risk                        AS SektorToplamRisk,
        y.nakdi_risk                                AS NakdiRisk,
        y.gayrinakdi_risk                           AS GayrinakdiRisk,
        y.banka_sayisi                              AS BankaSayisi,
        CASE WHEN y.gecikme_tutari > 0 THEN 1 ELSE 0 END AS GecikmeVar,
        CASE WHEN y.takip_tutari > 0 THEN 1 ELSE 0 END   AS TakipVar,
        y.kkb_not                                   AS KKBNot,
        y.cek_karsiliksiz_adet                      AS CekKarsiliksizAdet,
        m.birim_maliyet_tl                          AS SorguMaliyetTL,
        COALESCE(k.limit_tutari, 0)                 AS BizimLimit,
        COALESCE(k.risk_tutari, 0)                  AS BizimRisk
    FROM kkb_sorgu_log l
    JOIN kkb_sorgu_yanit y          ON y.sorgu_id = l.sorgu_id
    LEFT JOIN kkb_birim_maliyet m   ON m.rapor_tipi = l.rapor_tipi
                                   AND CAST(l.sorgu_zamani AS DATE) BETWEEN m.gecerlilik_bas AND m.gecerlilik_son
    LEFT JOIN kredi_snapshot_gunluk k
                                    ON k.vkn = l.vkn
                                   AND k.tarih = CAST(l.sorgu_zamani AS DATE)
    WHERE l.musteri_tipi = 'TUZEL'       -- yalnizca tuzel kisiler (KVKK notuna bakin)
      AND l.durum = 'BASARILI'
),
sonuc AS (
    -- Basvuru amacli sorgunun 60 gun icindeki sonucu.
    SELECT
        s.SorguID,
        CASE
            WHEN s.SorguNedeni NOT IN ('Yeni Basvuru', 'Limit Yenileme') THEN 'Izleme'
            WHEN MIN(t.kullandirim_tarihi) IS NOT NULL THEN 'Kullandirim'
            WHEN MAX(CASE WHEN t.karar = 'RET' THEN 1 ELSE 0 END) = 1 THEN 'Ret'
            WHEN MIN(t.teklif_tarihi) IS NOT NULL THEN 'Teklif'
            ELSE 'Aksiyon Yok'
        END AS SorguSonucu
    FROM sorgu s
    LEFT JOIN kredi_tahsis_basvuru t
           ON t.vkn = s.VKN
          AND t.basvuru_tarihi BETWEEN s.SorguTarihi AND s.SorguTarihi + 60   -- SQL Server: DATEADD(DAY, 60, s.SorguTarihi)
    GROUP BY s.SorguID, s.SorguNedeni
)
SELECT
    s.*,
    o.SorguSonucu,
    LAG(s.SorguID)          OVER w AS OncekiSorguID,
    LAG(s.SorguTarihi)      OVER w AS OncekiSorguTarihi,
    LAG(s.BizimRisk)        OVER w AS OncekiBizimRisk,
    LAG(s.SektorToplamRisk) OVER w AS OncekiSektorToplamRisk,
    LAG(s.GecikmeVar)       OVER w AS OncekiGecikmeVar,
    LAG(s.TakipVar)         OVER w AS OncekiTakipVar,
    LAG(s.KKBNot)           OVER w AS OncekiKKBNot,
    LAG(s.BankaSayisi)      OVER w AS OncekiBankaSayisi,
    LAG(s.GayrinakdiRisk)   OVER w AS OncekiGayrinakdiRisk,
    s.SorguTarihi - LAG(s.SorguTarihi) OVER w AS SorgularArasiGun,      -- SQL Server: DATEDIFF(DAY, ...)
    s.BizimRisk * 1.0 / NULLIF(s.SektorToplamRisk, 0)                   AS BizimPay,
    LAG(s.BizimRisk * 1.0 / NULLIF(s.SektorToplamRisk, 0)) OVER w       AS OncekiBizimPay,
    s.BizimRisk * 1.0 / NULLIF(s.BizimLimit, 0)                         AS BizimDoluluk,
    (s.SektorToplamRisk - s.BizimRisk) * 1.0
        / NULLIF(s.SektorToplamLimit - s.BizimLimit, 0)                 AS DigerBankaDoluluk
FROM sorgu s
JOIN sonuc o ON o.SorguID = s.SorguID
WINDOW w AS (PARTITION BY s.VKN ORDER BY s.SorguTarihi, s.SorguID);
-- SQL Server ve Oracle WINDOW yan cumlesini desteklemez: her LAG icin
-- OVER (PARTITION BY s.VKN ORDER BY s.SorguTarihi, s.SorguID) yazin.
