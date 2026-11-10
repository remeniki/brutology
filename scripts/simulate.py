"""Nahrá simulovaný studený štart do databázy a vypíše nálezy.

Spustenie:  python scripts/simulate.py [--fault vacuum_leak] [--seconds 300]
            python scripts/simulate.py --healthy      (zdravé auto)
            python scripts/simulate.py --list         (zoznam porúch)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.analysis import analyze, print_findings
from brutology.recorder import record
from brutology.sources import FAULTS, SimulatedCar
from brutology.storage import Storage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fault", choices=list(FAULTS), default="misfire",
                    help="aká porucha sa má simulovať (predvolene misfire)")
    ap.add_argument("--healthy", action="store_true", help="auto bez poruchy")
    ap.add_argument("--list", action="store_true", help="vypíš možné poruchy")
    ap.add_argument("--seconds", type=float, default=120)
    args = ap.parse_args()

    if args.list:
        for key, text in FAULTS.items():
            print(f"  {key:15s} {text}")
        return

    fault = None if args.healthy else args.fault
    storage = Storage()
    note = f"simulacia - {fault or 'zdravy'}"
    sid = record(SimulatedCar(fault=fault), storage, args.seconds, note=note)

    print(f"Nahraná relácia #{sid} ({note})")
    if fault:
        print(f"Simulovaná porucha: {FAULTS[fault]}")
    print_findings(analyze(storage.dataframe(sid)))
    storage.close()


if __name__ == "__main__":
    main()
