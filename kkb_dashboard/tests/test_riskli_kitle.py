"""Riskli kitle tespiti: yon kisiti, ayirma gucu ve senaryo tutarliligi.

Calistirma (kkb_dashboard klasorunden):
    python -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_sample_data as gen  # noqa: E402
from anomaly_score import skorla  # noqa: E402
from riskli_kitle import riskli_kitle  # noqa: E402


class RiskliKitleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = gen.uret(n_musteri=600, seed=11)
        skorla(t["Fact_Sorgu"], t["Fact_RiskDetay"], t["Dim_Musteri"], seed=11)
        cls.musteri = t["Dim_Musteri"]
        cls.liste, cls.bozuk, cls.test, cls.agirlik, cls.taban = riskli_kitle(
            t["Fact_Sorgu"], t["Fact_RiskDetay"], t["Dim_Musteri"])

    def test_olumsuz_sapmalar_riski_azaltmaz(self):
        sapma = self.agirlik[self.agirlik.index.str.startswith("sapma_")]
        self.assertTrue((sapma >= 0).all(), sapma)

    def test_zaman_bazli_testte_ayirma_gucu(self):
        self.assertGreater(self.test["kaldirac"], 2)

    def test_yuksek_kademe_bozulma_senaryosundan(self):
        x = self.liste.merge(self.musteri[["VKN", "_Senaryo"]], on="VKN")
        yuksek = x[x.Kademe == "Yüksek"]
        self.assertGreater(len(yuksek), 0)
        self.assertGreaterEqual((yuksek._Senaryo == "bozulma").mean(), 0.6)

    def test_gecikmedeki_musteri_listede_yok(self):
        self.assertTrue(set(self.liste.VKN).isdisjoint(self.bozuk.VKN))

    def test_her_satirda_en_az_bir_neden(self):
        self.assertTrue((self.liste.Neden1.str.len() > 0).all())


if __name__ == "__main__":
    unittest.main()
