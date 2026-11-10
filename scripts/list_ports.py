"""Vypíše všetky sériové (COM) porty. Slúži na nájdenie K+DCAN kábla."""
from serial.tools import list_ports


def main() -> None:
    ports = list(list_ports.comports())
    if not ports:
        print("Žiadny COM port nenájdený. Je kábel pripojený a nainštalovaný ovládač?")
        return
    for p in ports:
        print(f"{p.device}: {p.description} (VID:PID={p.vid}:{p.pid})")


if __name__ == "__main__":
    main()
