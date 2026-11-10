import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.recorder import record
from brutology.sources import SimulatedCar
from brutology.storage import Storage


class BasicTests(unittest.TestCase):
    def test_record_and_read_back(self):
        st = Storage(":memory:")
        sid = record(SimulatedCar(), st, duration=5, hz=10)
        rpm = st.series(sid, "rpm")
        self.assertEqual(len(rpm), 50)
        self.assertTrue(all(500 < v < 1500 for _, v in rpm))

    def test_cold_engine_warms_up(self):
        car = SimulatedCar()
        self.assertLess(car.read(0)["coolant_temp_c"], 20)
        self.assertGreater(car.read(300)["coolant_temp_c"], 70)

    def test_fault_causes_misfires_healthy_does_not(self):
        faulty = sum(SimulatedCar(fault=True).read(t / 10)["misfire_cyl3"] for t in range(600))
        healthy = sum(SimulatedCar(fault=False).read(t / 10)["misfire_cyl3"] for t in range(600))
        self.assertGreater(faulty, 0)
        self.assertEqual(healthy, 0)


if __name__ == "__main__":
    unittest.main()
