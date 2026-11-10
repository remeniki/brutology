import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.analysis import analyze
from brutology.fake_elm import FakeElm327
from brutology.obd import Elm327, ObdSource, READ_ONLY, ALLOWED_AT
from brutology.recorder import record
from brutology.sources import DataSource, SimulatedCar
from brutology.storage import Storage


class Clocked(DataSource):
    """Posúva čas falošného kábla podľa nahrávania (aby test bežal rýchlo)."""

    def __init__(self, fault=True):
        self.now = 0.0
        self.fake = FakeElm327(SimulatedCar(fault=fault), clock=lambda: self.now)
        self.obd = ObdSource(Elm327(self.fake))

    def read(self, t):
        self.now = t
        return self.obd.read(t)


class ObdTests(unittest.TestCase):
    def test_setup_and_supported_pids(self):
        src = ObdSource(Elm327(FakeElm327()))
        self.assertEqual(src.version, "ELM327 v1.5")
        self.assertIn("ISO 9141-2", src.protocol)
        names = {p.name for p in src.pids}
        self.assertIn("rpm", names)
        self.assertNotIn("maf_gs", names)   # simulované auto ho nepozná

    def test_decoding(self):
        elm = Elm327(FakeElm327())
        elm.port._handle = lambda cmd: elm.port._reply(cmd, "410C1AF8")
        self.assertEqual(elm.query(0x0C), bytes([0x1A, 0xF8]))
        from brutology.obd import PIDS
        rpm = next(p for p in PIDS if p.name == "rpm")
        self.assertEqual(rpm.decode(bytes([0x1A, 0xF8])), 1726.0)
        trim = next(p for p in PIDS if p.name == "stft_pct")
        self.assertEqual(trim.decode(bytes([128])), 0)
        self.assertEqual(trim.decode(bytes([138])), 7.81)

    def test_no_data_returns_none(self):
        elm = Elm327(FakeElm327())
        elm.setup()
        self.assertIsNone(elm.query(0x10))   # MAF simulované auto nemá

    def test_values_are_realistic(self):
        values = ObdSource(Elm327(FakeElm327())).read(0)
        self.assertTrue(500 < values["rpm"] < 1500)
        self.assertTrue(0 < values["coolant_temp_c"] < 30)
        self.assertIn("battery_v", values)

    def test_read_only_guard(self):
        elm = Elm327(FakeElm327())
        for forbidden in ("04", "03", "0902", "ATSH7E0", "1001", "2E0101", "ATMA"):
            with self.assertRaises(PermissionError, msg=forbidden):
                elm._send(forbidden)

    def test_only_allowed_commands_reach_cable(self):
        src = Clocked()
        record(src, Storage(":memory:"), duration=5, hz=10)
        for cmd in src.fake.sent:
            self.assertTrue(cmd in ALLOWED_AT or READ_ONLY.match(cmd), cmd)

    def test_shaking_detected_through_obd(self):
        st = Storage(":memory:")
        sid = record(Clocked(fault=True), st, duration=120, hz=10)
        titles = " ".join(f.title for f in analyze(st.dataframe(sid)))
        self.assertIn("voľnobeh", titles)
        self.assertIn("fuel trim", titles)

    def test_healthy_through_obd(self):
        st = Storage(":memory:")
        sid = record(Clocked(fault=False), st, duration=120, hz=10)
        self.assertEqual(analyze(st.dataframe(sid)), [])

    def test_realtime_recording_uses_real_time(self):
        st = Storage(":memory:")
        sid = record(SimulatedCar(), st, duration=0.5, hz=10, realtime=True)
        times = [t for t, _ in st.series(sid, "rpm")]
        self.assertTrue(3 <= len(times) <= 6, times)
        self.assertEqual(times, sorted(times))
        self.assertLess(times[-1], 0.5)


if __name__ == "__main__":
    unittest.main()
