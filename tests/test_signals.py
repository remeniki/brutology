import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.obd import PIDS
from brutology.signals import describe, label
from brutology.sources import SimulatedCar


class SignalsTests(unittest.TestCase):
    def test_every_signal_has_description(self):
        """Každá veličina, ktorú appka nahráva, musí mať v slovníku popis."""
        names = set(SimulatedCar(None).read(0)) | {p.name for p in PIDS} | {"battery_v"}
        for name in sorted(names):
            with self.subTest(name=name):
                self.assertTrue(describe(name).text, f"{name} nemá popis v signals.py")

    def test_cylinder_signals(self):
        self.assertEqual(describe("misfire_cyl5").title, "Výpadky zapaľovania – valec 5")

    def test_label_has_unit(self):
        self.assertEqual(label("rpm"), "Otáčky motora [ot/min]")

    def test_unknown_signal(self):
        self.assertEqual(label("nieco_nove"), "nieco_nove")


if __name__ == "__main__":
    unittest.main()
