import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from brutology.analysis import CAUSES, analyze, rank_causes
from brutology.sources import FAULTS, SimulatedCar


def simulate(fault, seconds: int = 120, hz: int = 10) -> pd.DataFrame:
    car = SimulatedCar(fault=fault)
    rows = {i / hz: car.read(i / hz) for i in range(seconds * hz)}
    return pd.DataFrame.from_dict(rows, orient="index")


def titles(findings) -> str:
    return " | ".join(f.title for f in findings)


# porucha simulátora -> príčina, ktorá musí vyjsť ako najpravdepodobnejšia
EXPECTED_TOP_CAUSE = {
    "misfire": "coil_plug",
    "vacuum_leak": "vacuum_leak",
    "coolant_sensor": "coolant_sensor",
    "icv": "icv",
    "vanos": "vanos",
    "o2_sensor": "o2_sensor",
    "thermostat": "thermostat",
}


class AnalysisTests(unittest.TestCase):
    def test_healthy_car_has_no_findings(self):
        self.assertEqual(analyze(simulate(fault=None, seconds=300)), [])

    def test_healthy_long_session_has_no_findings(self):
        self.assertEqual(analyze(simulate(fault=None, seconds=900, hz=2)), [])

    def test_every_fault_points_to_right_cause(self):
        self.assertEqual(set(EXPECTED_TOP_CAUSE), set(FAULTS))
        for fault, cause in EXPECTED_TOP_CAUSE.items():
            with self.subTest(fault=fault):
                seconds = 900 if fault == "thermostat" else 300
                hz = 2 if fault == "thermostat" else 10
                suspects = rank_causes(analyze(simulate(fault, seconds, hz)))
                self.assertTrue(suspects, "žiadny podozrivý")
                self.assertEqual(suspects[0].key, cause, [s.key for s in suspects[:3]])

    def test_shaking_car_is_detected_while_cold(self):
        findings = analyze(simulate(fault="misfire"))
        self.assertIn("valec 3", titles(findings))
        self.assertIn("voľnobeh", titles(findings))
        for f in findings:
            self.assertTrue(f.cold, f"{f.title} by mal byť pri studenom motore")
            self.assertLess(f.t_start, 60)

    def test_vacuum_leak_shows_bank_2(self):
        t = titles(analyze(simulate("vacuum_leak", seconds=300)))
        self.assertIn("banka 2", t)
        self.assertIn("ICV je takmer zatvorený", t)
        self.assertIn("MAF", t)

    def test_most_severe_first(self):
        findings = analyze(simulate(fault="misfire"))
        order = {"vysoká": 0, "stredná": 1, "nízka": 2}
        self.assertEqual([order[f.severity] for f in findings],
                         sorted(order[f.severity] for f in findings))

    def test_missing_signals_are_skipped(self):
        df = simulate(fault="misfire")[["rpm"]]  # napr. zdroj, ktorý dá len otáčky
        findings = analyze(df)
        self.assertEqual([f.signal for f in findings], ["rpm"])
        self.assertIsNone(findings[0].coolant_c)

    def test_empty_session(self):
        self.assertEqual(analyze(pd.DataFrame()), [])
        self.assertEqual(rank_causes([]), [])

    def test_all_causes_are_known(self):
        for fault in FAULTS:
            for f in analyze(simulate(fault)):
                for c in f.causes:
                    self.assertIn(c, CAUSES)


class SyntheticTests(unittest.TestCase):
    """Poruchy, ktoré simulátor nevie, otestujeme na ručne vyrobených dátach."""

    def base(self, seconds=60, hz=10):
        return simulate(fault=None, seconds=seconds, hz=hz)

    def test_disa_flapping_at_idle(self):
        df = self.base()
        df["disa_open"] = [(i // 20) % 2 for i in range(len(df))]   # prepína každé 2 s
        self.assertIn("DISA", titles(analyze(df)))
        self.assertEqual(rank_causes(analyze(df))[0].key, "disa")

    def test_coolant_sensor_jumps(self):
        df = self.base()
        df.loc[df.index[300:310], "coolant_temp_c"] += 25
        findings = analyze(df)
        self.assertIn("Teplota chladiva skáče", titles(findings))

    def test_disconnected_sensor(self):
        df = self.base()
        df["intake_temp_c"] = -40.0
        self.assertIn("nasávaného vzduchu hlási nezmysel", titles(analyze(df)))

    def test_throttle_noise(self):
        df = self.base()
        df["throttle_pct"] = [3 + (4 if i % 3 == 0 else 0) for i in range(len(df))]
        self.assertIn("škrtiacej klapky", titles(analyze(df)))

    def test_low_idle(self):
        df = self.base()
        df["rpm"] = 520.0
        self.assertIn("Príliš nízky voľnobeh", titles(analyze(df)))

    def test_rich_mixture(self):
        df = self.base()
        df["ltft_pct"] = -12.0
        findings = [f for f in analyze(df) if "dlhodobý" in f.title]
        self.assertTrue(findings)
        self.assertIn("bohatá", findings[0].detail)

    def test_battery_low(self):
        df = self.base()
        df["battery_v"] = 12.2
        self.assertIn("napätie", titles(analyze(df)))

    def test_revving_is_not_unstable_idle(self):
        df = self.base()
        df.loc[df.index[200:400], "rpm"] = [1500 + 30 * (i % 50) for i in range(200)]
        df.loc[df.index[200:400], "throttle_pct"] = 25.0
        self.assertNotIn("Nestabilný voľnobeh", titles(analyze(df)))

    def test_warm_engine_start_is_not_flagged_as_sensor_fault(self):
        df = self.base()
        df["coolant_temp_c"] = 85.0     # motor naštartovaný teplý
        self.assertNotIn("pri štarte nesedí", titles(analyze(df)))


if __name__ == "__main__":
    unittest.main()
