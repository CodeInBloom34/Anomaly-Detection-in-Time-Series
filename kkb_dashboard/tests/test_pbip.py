"""PBIP projesinin ic tutarliligi: gorsel alanlari ve DAX referanslari modelde var mi?

Calistirma (kkb_dashboard klasorunden):
    python -m unittest discover tests
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "powerbi"))

import build_pbip  # noqa: E402

DAX_KOLON = re.compile(r"(?:'([^']+)'|\b([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
DAX_OLCU = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")


def dax_temizle(dax):
    # String literal'leri cikar ki icindeki koseli parantezler referans sanilmasin.
    return re.sub(r'"(?:[^"]|"")*"', '""', dax)


class PbipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        hedef = build_pbip.proje_yaz(Path(cls.tmp.name))
        cls.model = json.loads((hedef / f"{build_pbip.PROJE}.SemanticModel" / "model.bim").read_text("utf-8"))
        cls.rapor = hedef / f"{build_pbip.PROJE}.Report" / "definition"
        cls.kolonlar, cls.olculer = set(), set()
        for t in cls.model["model"]["tables"]:
            for c in t["columns"]:
                cls.kolonlar.add((t["name"], c["name"]))
            for m in t.get("measures", []):
                cls.olculer.add(m["name"])
        cls.olcu_tablo = {(t["name"], m["name"]) for t in cls.model["model"]["tables"] for m in t.get("measures", [])}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def dax_ifadeleri(self):
        for t in self.model["model"]["tables"]:
            for c in t["columns"]:
                if c.get("type") == "calculated":
                    yield f"{t['name']}[{c['name']}]", "\n".join(c["expression"])
            for m in t.get("measures", []):
                yield m["name"], "\n".join(m["expression"])
            for p in t["partitions"]:
                if p["source"]["type"] == "calculated":
                    yield t["name"], p["source"]["expression"]

    def test_dax_referanslari_modelde_var(self):
        for ad, dax in self.dax_ifadeleri():
            temiz = dax_temizle(dax)
            for m in DAX_KOLON.finditer(temiz):
                tablo = m.group(1) or m.group(2)
                self.assertIn((tablo, m.group(3)), self.kolonlar, f"{ad}: {tablo}[{m.group(3)}] yok")
            for m in DAX_OLCU.finditer(temiz):
                self.assertIn(m.group(1), self.olculer, f"{ad}: [{m.group(1)}] olcusu yok")

    def test_dax_parantez_dengesi(self):
        for ad, dax in self.dax_ifadeleri():
            temiz = dax_temizle(dax)
            self.assertEqual(temiz.count("("), temiz.count(")"), ad)
            self.assertEqual(temiz.count("{"), temiz.count("}"), ad)
            self.assertEqual(dax.count('"') % 2, 0, ad)

    def test_gorsel_alanlari_modelde_var(self):
        for f in self.rapor.rglob("visual.json"):
            v = json.loads(f.read_text("utf-8"))
            metin = json.dumps(v)
            for tur, tablo, ad in re.findall(
                    r'"(Measure|Column)": \{"Expression": \{"SourceRef": \{"Entity": "([^"]+)"\}\}, "Property": "([^"]+)"',
                    metin):
                if tur == "Measure":
                    self.assertIn((tablo, ad), self.olcu_tablo, f"{f}: olcu {tablo}.{ad}")
                else:
                    self.assertIn((tablo, ad), self.kolonlar, f"{f}: sutun {tablo}.{ad}")

    def test_iliski_sutunlari_ve_tipleri(self):
        tipler = {(t["name"], c["name"]): c["dataType"] for t in self.model["model"]["tables"] for c in t["columns"]}
        for r in self.model["model"]["relationships"]:
            a, b = (r["fromTable"], r["fromColumn"]), (r["toTable"], r["toColumn"])
            self.assertIn(a, tipler)
            self.assertIn(b, tipler)
            self.assertEqual(tipler[a], tipler[b], r)

    def test_sutun_tipleri(self):
        tipler = {(t["name"], c["name"]): c["dataType"] for t in self.model["model"]["tables"] for c in t["columns"]}
        beklenen = {
            ("Fact_Sorgu", "VKN"): "string", ("Dim_Musteri", "Unvan"): "string", ("Dim_Tarih", "AyAdi"): "string",
            ("Dim_Sube", "SubeKod"): "string", ("Fact_Sorgu", "SorguNedeni"): "string",
            ("Fact_Sorgu", "SorguTarihi"): "dateTime", ("Fact_Sorgu", "SorguID"): "int64",
            ("Fact_KrediSonuc", "SorguID"): "int64", ("Fact_Sorgu", "OncekiGecikmeVar"): "int64",
            ("Fact_Sorgu", "BizimPay"): "double", ("Fact_AnomaliSkor", "Skor"): "double",
        }
        for k, v in beklenen.items():
            self.assertEqual(tipler[k], v, k)

    def test_gorseller_sayfaya_sigar(self):
        for f in self.rapor.rglob("visual.json"):
            p = json.loads(f.read_text("utf-8"))["position"]
            self.assertLessEqual(p["x"] + p["width"], 1280, f)
            self.assertLessEqual(p["y"] + p["height"], 720, f)


if __name__ == "__main__":
    unittest.main()
