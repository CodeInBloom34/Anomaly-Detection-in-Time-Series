"""Ornek veri + anomali skoru icin hizli dogrulama testleri.

Calistirma (kkb_dashboard klasorunden):
    python -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_sample_data as gen  # noqa: E402
from anomaly_score import skorla  # noqa: E402


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = gen.uret(n_musteri=400, seed=7)
        cls.skor = skorla(cls.t["Fact_Sorgu"], cls.t["Fact_RiskDetay"], cls.t["Dim_Musteri"], seed=7)

    def test_onceki_alanlar_lag_ile_tutarli(self):
        s = self.t["Fact_Sorgu"]
        ilk = s.groupby("VKN").SorguTarihi.transform("min") == s.SorguTarihi
        self.assertTrue(s.loc[ilk, "OncekiSorguID"].isna().all())
        self.assertTrue(s.loc[~ilk, "OncekiSorguID"].notna().all())
        self.assertTrue((s.loc[~ilk, "SorgularArasiGun"] > 0).all())

    def test_kor_nokta_musterileri_var(self):
        sorgulanan = set(self.t["Fact_Sorgu"].VKN)
        riskli = set(self.t["Fact_KrediSonuc"].query("BizimRisk > 0").VKN)
        self.assertGreater(len(riskli - sorgulanan), 0)

    def test_risk_detay_toplami_sektor_riskine_esit(self):
        toplam = self.t["Fact_RiskDetay"].groupby("SorguID").Risk.sum()
        s = self.t["Fact_Sorgu"].set_index("SorguID").SektorToplamRisk
        fark = (toplam - s.loc[toplam.index]).abs() / s.loc[toplam.index]
        self.assertLess(fark.max(), 0.001)

    def test_skor_araligi_ve_neden(self):
        self.assertTrue(self.skor.Skor.between(0, 100).all())
        self.assertFalse(self.skor.Neden.isna().any())

    def test_bozulan_musteri_stabilden_yuksek_skor_alir(self):
        m = self.t["Dim_Musteri"][["VKN", "_Senaryo"]]
        x = self.skor.merge(m, on="VKN").groupby("_Senaryo").Skor.median()
        self.assertGreater(x["bozulma"], x["stabil"] + 20)

    def test_yeni_gecikme_yuksek_oncelik_alir(self):
        yeni = self.skor[self.skor.Neden == "Yeni gecikme sinyali"]
        self.assertGreater(len(yeni), 0)
        self.assertTrue((yeni.Skor >= 80).all())


if __name__ == "__main__":
    unittest.main()
