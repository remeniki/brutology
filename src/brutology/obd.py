"""Čítanie generických OBD-II dát cez ELM327 kábel (USB = COM port).

Ako to funguje: kábel ELM327 je "tlmočník". Pošleme mu textový príkaz,
napr. "010C" (= mód 01, PID 0C = otáčky). On sa spýta auta a vráti odpoveď
v šestnástkovej sústave, napr. "410C1AF8" -> 0x1AF8 / 4 = 1726 ot/min.

BEZPEČNOSŤ: komunikácia je LEN NA ČÍTANIE. Metóda `_send` pustí do kábla iba
príkazy zo zoznamu povolených (nastavenie kábla + mód 01 = živé dáta).
Napr. mód 04 (mazanie chýb) sa poslať nedá.
"""
import re
import time
from dataclasses import dataclass
from typing import Callable

from .sources import DataSource

BAUDRATES = (38400, 9600, 115200, 57600)   # najčastejšie rýchlosti USB ELM327

# Povolené nastavovacie príkazy kábla (týkajú sa len kábla, nie auta)
ALLOWED_AT = {
    "ATZ",    # reset kábla
    "ATI",    # verzia kábla
    "ATE0",   # vypni ozvenu (kábel neopakuje náš príkaz)
    "ATL0",   # bez prázdnych riadkov
    "ATS0",   # bez medzier v odpovedi
    "ATH0",   # bez hlavičiek
    "ATSP0",  # protokol automaticky
    "ATAT2",  # rýchlejšie čakanie na odpoveď
    "ATDP",   # názov zisteného protokolu
    "ATRV",   # napätie na OBD zásuvke (meria kábel sám, auto sa nepýta)
}
READ_ONLY = re.compile(r"^01[0-9A-F]{2}$")   # mód 01 = aktuálne dáta


class ObdError(Exception):
    pass


@dataclass
class Pid:
    pid: int
    name: str
    decode: Callable[[bytes], float]
    slow: bool = False   # pomaly sa meniace veličiny čítame zriedkavejšie


def _trim(d: bytes) -> float:
    return round((d[0] - 128) * 100 / 128, 2)


# Názvy veličín sú rovnaké ako v SimulatedCar -> grafy aj analýza fungujú bez zmeny.
PIDS = [
    Pid(0x0C, "rpm", lambda d: round((d[0] * 256 + d[1]) / 4, 1)),
    Pid(0x06, "stft_pct", _trim),                 # krátkodobý trim, banka 1 (valce 1-3)
    Pid(0x08, "stft_b2_pct", _trim),              # krátkodobý trim, banka 2 (valce 4-6)
    Pid(0x0B, "map_kpa", lambda d: float(d[0])),
    Pid(0x10, "maf_gs", lambda d: round((d[0] * 256 + d[1]) / 100, 2)),
    Pid(0x04, "load_pct", lambda d: round(d[0] * 100 / 255, 1)),
    Pid(0x0E, "timing_adv_deg", lambda d: d[0] / 2 - 64),
    Pid(0x14, "o2_b1s1_v", lambda d: d[0] / 200),
    Pid(0x18, "o2_b2s1_v", lambda d: d[0] / 200),
    Pid(0x11, "throttle_pct", lambda d: round(d[0] * 100 / 255, 1)),
    Pid(0x05, "coolant_temp_c", lambda d: float(d[0] - 40), slow=True),
    Pid(0x0F, "intake_temp_c", lambda d: float(d[0] - 40), slow=True),
    Pid(0x07, "ltft_pct", _trim, slow=True),      # dlhodobý trim, banka 1
    Pid(0x09, "ltft_b2_pct", _trim, slow=True),   # dlhodobý trim, banka 2
]

ERRORS = ("NO DATA", "UNABLE TO CONNECT", "ERROR", "STOPPED", "?", "CAN ERROR")


class Elm327:
    """Rozhovor s ELM327 káblom. `port` je otvorený pyserial port (alebo FakeElm327)."""

    def __init__(self, port):
        self.port = port

    def _send(self, cmd: str, timeout: float = 2.0) -> str:
        cmd = cmd.upper().replace(" ", "")
        if cmd not in ALLOWED_AT and not READ_ONLY.match(cmd):
            raise PermissionError(f"Príkaz {cmd!r} nie je povolený (appka smie len čítať).")
        self.port.reset_input_buffer()
        self.port.write((cmd + "\r").encode("ascii"))
        self.port.timeout = timeout
        raw = self.port.read_until(b">").decode("ascii", errors="replace")
        if not raw.endswith(">"):
            raise ObdError(f"Kábel neodpovedal na {cmd} (timeout).")
        lines = [ln.strip() for ln in raw[:-1].replace("\n", "\r").split("\r")]
        lines = [ln for ln in lines if ln and ln != cmd and not ln.startswith("SEARCHING")]
        return "\r".join(lines)

    def setup(self) -> str:
        """Pripraví kábel. Vráti jeho verziu, napr. 'ELM327 v1.5'."""
        version = self._send("ATZ", timeout=3).split("\r")[-1]
        for cmd in ("ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
            self._send(cmd)
        try:
            self._send("ATAT2")   # niektoré kópie nepoznajú, nevadí
        except ObdError:
            pass
        return version

    def query(self, pid: int, timeout: float = 2.0) -> bytes | None:
        """Mód 01 dotaz. Vráti dátové bajty, alebo None ak auto túto hodnotu nepozná."""
        cmd = f"01{pid:02X}"
        resp = self._send(cmd, timeout)
        if any(resp.upper().startswith(e) for e in ERRORS):
            return None
        want = f"41{pid:02X}"
        for line in resp.split("\r"):
            hexline = line.replace(" ", "").upper()
            if hexline.startswith(want):
                try:
                    return bytes.fromhex(hexline[len(want):])
                except ValueError:
                    return None
        return None

    def supported_pids(self) -> set[int]:
        """Opýta sa auta, ktoré hodnoty (PIDy) pozná."""
        supported: set[int] = set()
        base = 0x00
        while True:
            data = self.query(base, timeout=10)   # prvý dotaz pripája auto, trvá dlhšie
            if data is None or len(data) < 4:
                if base == 0x00:
                    raise ObdError("Auto neodpovedá. Je zapnuté zapaľovanie (alebo motor)?")
                break
            bits = int.from_bytes(data[:4], "big")
            for i in range(32):
                if bits & (1 << (31 - i)):
                    supported.add(base + i + 1)
            if (base + 0x20) not in supported:
                break
            base += 0x20
        return supported

    def voltage(self) -> float | None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*V", self._send("ATRV"))
        return float(m.group(1)) if m else None

    def protocol(self) -> str:
        return self._send("ATDP")


def open_port(device: str):
    """Otvorí COM port a vyskúša bežné rýchlosti, kým kábel neodpovie."""
    import serial

    for baud in BAUDRATES:
        try:
            port = serial.Serial(device, baud, timeout=1)
        except serial.SerialException as e:
            raise ObdError(
                f"Port {device} sa nedá otvoriť. Je kábel zapojený v USB a je to správny "
                f"port (scripts\\list_ports.py)? Nemáš otvorený ScanMaster alebo inú "
                f"appku, ktorá kábel používa?\n  (technicky: {e})") from e
        try:
            port.write(b"\r")              # zahodí prípadný rozpísaný príkaz
            time.sleep(0.3)
            port.reset_input_buffer()
            port.write(b"ATI\r")
            if b"ELM" in port.read_until(b">").upper():
                return port
        except serial.SerialException:
            pass
        port.close()
    raise ObdError(f"Na {device} neodpovedá ELM327 kábel (skúšané rýchlosti {BAUDRATES}).")


class ObdSource(DataSource):
    """Zdroj dát z auta cez ELM327 (generické OBD-II).

    Rýchle veličiny (otáčky, trimy...) čítame v každom kole, pomalé
    (teploty, dlhodobé trimy) len každé `slow_every`-té kolo a medzitým
    vraciame poslednú hodnotu - tak dostaneme viac vzoriek otáčok za sekundu.
    """

    def __init__(self, elm: Elm327, slow_every: int = 10, read_voltage: bool = True):
        self.elm = elm
        self.slow_every = slow_every
        self.read_voltage = read_voltage
        self.version = elm.setup()
        self.supported = elm.supported_pids()
        self.pids = [p for p in PIDS if p.pid in self.supported]
        self.protocol = elm.protocol()
        self._last: dict = {}
        self._round = 0

    @classmethod
    def from_port(cls, device: str, **kw) -> "ObdSource":
        return cls(Elm327(open_port(device)), **kw)

    def read(self, t: float) -> dict:
        slow_round = self._round % self.slow_every == 0
        self._round += 1
        for p in self.pids:
            if p.slow and not slow_round:
                continue
            data = self.elm.query(p.pid)
            if data:
                self._last[p.name] = p.decode(data)
        if self.read_voltage and slow_round:
            v = self.elm.voltage()
            if v is not None:
                self._last["battery_v"] = v
        return dict(self._last)

    def close(self) -> None:
        self.elm.port.close()
