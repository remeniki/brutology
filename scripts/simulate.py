"""Nahrá simulovaný studený štart do databázy a vypíše súhrn.

Spustenie:  python scripts/simulate.py [--healthy] [--seconds 120]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.recorder import record
from brutology.sources import SimulatedCar
from brutology.storage import Storage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--healthy", action="store_true", help="auto bez poruchy")
    ap.add_argument("--seconds", type=float, default=120)
    args = ap.parse_args()

    storage = Storage()
    note = "simulacia - zdravy" if args.healthy else "simulacia - trasenie"
    sid = record(SimulatedCar(fault=not args.healthy), storage, args.seconds, note=note)

    print(f"Nahrana relacia #{sid} ({note})")
    for name in ("rpm", "coolant_temp_c", "stft_pct", "misfire_cyl3"):
        vals = [v for _, v in storage.series(sid, name)]
        print(f"  {name:16s} min={min(vals):8.1f}  max={max(vals):8.1f}  vzoriek={len(vals)}")
    storage.close()


if __name__ == "__main__":
    main()
