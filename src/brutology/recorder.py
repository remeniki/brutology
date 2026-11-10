"""Nahrá relaciu zo zdroja dát do databázy."""
import time

from .sources import DataSource
from .storage import Storage

COMMIT_EVERY = 50   # priebežne ukladaj, aby sa pri páde nestratilo všetko


def record(source: DataSource, storage: Storage, duration: float, hz: float = 10,
           note: str = "", realtime: bool = False, on_sample=None) -> int:
    """Nahráva `duration` sekúnd, najviac `hz` vzoriek za sekundu.

    realtime=False beží rýchlo s vymysleným časom (pre simuláciu).
    realtime=True meria skutočný čas - pre auto, kde jedno čítanie trvá
    rôzne dlho. Nahrávanie sa dá kedykoľvek zastaviť klávesmi Ctrl+C,
    doterajšie dáta zostanú uložené.
    """
    session_id = storage.start_session(note)
    try:
        if realtime:
            t0 = time.monotonic()
            i = 0
            while (t := time.monotonic() - t0) < duration:
                _sample(source, storage, session_id, t, on_sample)
                i += 1
                if i % COMMIT_EVERY == 0:
                    storage.commit()
                time.sleep(max(0.0, t0 + t + 1 / hz - time.monotonic()))
        else:
            for i in range(int(duration * hz)):
                _sample(source, storage, session_id, i / hz, on_sample)
    except KeyboardInterrupt:
        pass
    finally:
        storage.commit()
    return session_id


def _sample(source, storage, session_id, t, on_sample):
    values = source.read(t)
    storage.add_sample(session_id, t, values)
    if on_sample:
        on_sample(t, values)
