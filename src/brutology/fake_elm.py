"""Falošný ELM327 kábel na skúšanie bez auta.

Správa sa ako sériový port s pripojeným ELM327: prijíma textové príkazy
a odpovedá rovnako ako skutočný kábel. Hodnoty berie zo SimulatedCar,
takže ObdSource sa dá otestovať celý - od bajtov až po analýzu.
"""
import time

from .sources import SimulatedCar

# PIDy, ktoré "pozná" simulované auto (MS43 nemá MAP snímač, ale pre test ho dáme)
SUPPORTED = {0x04, 0x05, 0x06, 0x07, 0x0B, 0x0C, 0x0F, 0x11}


def _encode(pid: int, v: dict) -> bytes | None:
    """Hodnoty zo simulátora -> bajty presne ako ich posiela auto."""
    trim = lambda pct: bytes([max(0, min(255, round(pct * 128 / 100 + 128)))])
    if pid == 0x0C:
        raw = round(v["rpm"] * 4)
        return bytes([raw // 256, raw % 256])
    if pid == 0x05:
        return bytes([round(v["coolant_temp_c"]) + 40])
    if pid == 0x0F:
        return bytes([round(v["intake_temp_c"]) + 40])
    if pid == 0x11:
        return bytes([round(v["throttle_pct"] * 255 / 100)])
    if pid == 0x0B:
        return bytes([round(v["map_kpa"])])
    if pid == 0x06:
        return trim(v["stft_pct"])
    if pid == 0x07:
        return trim(0.0)
    if pid == 0x04:
        return bytes([60])
    return None


class FakeElm327:
    def __init__(self, car: SimulatedCar | None = None, clock=None):
        self.car = car or SimulatedCar()
        start = time.monotonic()
        self.clock = clock or (lambda: time.monotonic() - start)
        self.timeout = 1.0
        self.echo = True
        self.connected = False
        self.sent: list[str] = []      # všetky prijaté príkazy (na kontrolu v testoch)
        self._out = b""

    # --- rozhranie ako pyserial ---
    def reset_input_buffer(self):
        self._out = b""

    def write(self, data: bytes):
        for cmd in data.decode("ascii").split("\r"):
            if cmd.strip():
                self._handle(cmd.strip().upper())

    def read_until(self, expected=b">"):
        out, self._out = self._out, b""
        return out

    def close(self):
        pass

    # --- logika kábla ---
    def _reply(self, cmd: str, text: str):
        echo = cmd + "\r" if self.echo else ""
        self._out += (echo + text + "\r\r>").encode("ascii")

    def _handle(self, cmd: str):
        self.sent.append(cmd)
        if cmd == "ATZ":
            self.echo = True
            self._reply(cmd, "\rELM327 v1.5")
        elif cmd == "ATI":
            self._reply(cmd, "ELM327 v1.5")
        elif cmd == "ATE0":
            self.echo = False
            self._reply(cmd, "OK")
        elif cmd in ("ATL0", "ATS0", "ATH0", "ATSP0", "ATAT2"):
            self._reply(cmd, "OK")
        elif cmd == "ATDP":
            self._reply(cmd, "AUTO, ISO 9141-2")
        elif cmd == "ATRV":
            self._reply(cmd, f"{self.car.read(self.clock())['battery_v']:.1f}V")
        elif cmd.startswith("01") and len(cmd) == 4:
            pid = int(cmd[2:], 16)
            prefix = "" if self.connected else "SEARCHING...\r"
            self.connected = True
            if pid == 0x00:
                bits = sum(1 << (32 - p) for p in SUPPORTED)
                self._reply(cmd, prefix + f"4100{bits:08X}")
                return
            data = _encode(pid, self.car.read(self.clock())) if pid in SUPPORTED else None
            self._reply(cmd, prefix + (f"41{pid:02X}{data.hex().upper()}" if data else "NO DATA"))
        else:
            self._reply(cmd, "?")
