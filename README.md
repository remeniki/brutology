# Brutology

Diagnostika a logovanie živých dát z BMW E46 330i ("Brutus") cez K+DCAN kábel.

Cieľ: vyčítať a uložiť čo najviac živých dát z riadiacej jednotky (Siemens MS43),
zobraziť ich v grafoch a pomôcť nájsť príčinu trasenia motora pri studenom štarte.

## Rýchly štart (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\list_ports.py
```

Plán a postup: pozri `docs/PLAN.md`.
