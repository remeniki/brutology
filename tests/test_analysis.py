import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from brutology.analysis import analyze
from brutology.sources import SimulatedCar


def simulate(fault: bool, seconds: int = 120, hz: int = 10) -> pd.DataFrame:
    car = SimulatedCar(fault=fault)
    rows = {i / hz: car.read(i / hz) for i in range(seconds * hz)}
    return pd.DataFrame.from_dict(rows, orient="index")


class AnalysisTests(unittest.TestCase):
    def test_healthy_car_has_no_findings(self):
        self.assertEqual(analyze(simulate(fault=False)), [])

    def test_shaking_car_is_detected_while_cold(self):
        findings = analyze(simulate(fault=True))
        titles = " ".join(f.title for f in findings)
        self.assertIn("valec 3", titles)
        self.assertIn("voľnobeh", titles)
        for f in findings:
            self.assertTrue(f.cold, f"{f.title} by mal byť pri studenom motore")
            self.assertLess(f.t_start, 60)

    def test_most_severe_first(self):
        findings = analyze(simulate(fault=True))
        self.assertEqual(findings[0].severity, "vysoká")
        self.assertEqual(findings[-1].severity, "stredná")

    def test_missing_signals_are_skipped(self):
        df = simulate(fault=True)[["rpm"]]  # napr. zdroj, ktorý dá len otáčky
        findings = analyze(df)
        self.assertEqual([f.signal for f in findings], ["rpm"])
        self.assertIsNone(findings[0].coolant_c)

    def test_empty_session(self):
        self.assertEqual(analyze(pd.DataFrame()), [])


if __name__ == "__main__":
    unittest.main()
