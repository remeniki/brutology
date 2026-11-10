"""Nahrá živé dáta z auta cez ELM327 kábel (generické OBD-II).

Postup pri studenom štarte:
  1. python scripts\\list_ports.py                    -> zisti COM port kábla
  2. python scripts\\record_obd.py --port COM3 --check -> len overí spojenie
  3. python scripts\\record_obd.py --port COM3 --note "studeny start 5 C"
     Spusti pri zapnutom zapaľovaní, potom naštartuj. Zastavíš Ctrl+C.

Bez auta (falošný kábel):  python scripts\\record_obd.py --fake --seconds 20
Appka s autom LEN ČÍTA - nič nemaže ani nemení.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brutology.analysis import analyze, print_findings
from brutology.fake_elm import FakeElm327
from brutology.obd import PIDS, Elm327, ObdError, ObdSource
from brutology.recorder import record
from brutology.storage import Storage

SHOW = ("rpm", "coolant_temp_c", "stft_pct", "stft_b2_pct", "battery_v")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="COM port kábla, napr. COM3")
    ap.add_argument("--fake", action="store_true", help="falošný kábel, bez auta")
    ap.add_argument("--check", action="store_true", help="len over spojenie, nenahrávaj")
    ap.add_argument("--seconds", type=float, default=600, help="max. dĺžka (predvolene 10 min)")
    ap.add_argument("--note", default="", help="poznámka k relácii")
    args = ap.parse_args()
    if not args.port and not args.fake:
        ap.error("zadaj --port COMx (alebo --fake na skúšku bez auta)")

    print("Pripájam sa ku káblu..." if not args.fake else "Falošný kábel (bez auta)...")
    try:
        source = (ObdSource(Elm327(FakeElm327())) if args.fake
                  else ObdSource.from_port(args.port))
    except (ObdError, OSError) as e:
        print(f"CHYBA: {e}")
        sys.exit(1)

    names = {p.pid: p.name for p in PIDS}
    print(f"Kábel:    {source.version}")
    print(f"Protokol: {source.protocol}")
    print(f"Auto pozná {len(source.supported)} hodnôt, nahrávať budeme: "
          f"{', '.join(names[p.pid] for p in source.pids)}")

    if args.check:
        print("\nSkúšobné čítanie:")
        for k, v in source.read(0).items():
            print(f"  {k:16s} {v}")
        source.close()
        return

    note = args.note or ("fake ELM327" if args.fake else "OBD")
    storage = Storage()
    print(f"\nNahrávam (max {args.seconds:.0f} s). Zastavíš klávesmi Ctrl+C.\n")

    def show(t, values):
        line = "  ".join(f"{k}={values[k]}" for k in SHOW if k in values)
        print(f"\r{t:6.1f} s  {line}    ", end="", flush=True)

    sid = record(source, storage, args.seconds, hz=10, note=note,
                 realtime=True, on_sample=show)
    source.close()
    df = storage.dataframe(sid)
    print(f"\n\nUložená relácia #{sid}: {len(df)} vzoriek za {df.index.max():.0f} s "
          f"({len(df) / max(df.index.max(), 1):.1f} za sekundu)")
    print_findings(analyze(df))
    print("\nGrafy: start.bat")
    storage.close()


if __name__ == "__main__":
    main()
