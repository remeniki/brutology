"""Nahrá relaciu zo zdroja dát do databázy."""
import time

from .sources import DataSource
from .storage import Storage


def record(source: DataSource, storage: Storage, duration: float, hz: float = 10,
           note: str = "", realtime: bool = False, on_sample=None) -> int:
    """Nahráva `duration` sekúnd pri `hz` vzorkách za sekundu.
    realtime=False beží rýchlo (pre simuláciu), True čaká reálny čas."""
    session_id = storage.start_session(note)
    n = int(duration * hz)
    t0 = time.time()
    for i in range(n):
        t = i / hz
        values = source.read(t)
        storage.add_sample(session_id, t, values)
        if on_sample:
            on_sample(t, values)
        if realtime:
            time.sleep(max(0.0, t0 + (i + 1) / hz - time.time()))
    storage.commit()
    return session_id
