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

## Nahrávanie z auta (ELM327 USB kábel, OBD-II)

```
python scripts\list_ports.py                        # zisti COM port kábla
python scripts\record_obd.py --port COM3 --check    # len over spojenie
python scripts\record_obd.py --port COM3 --note "studeny start"   # nahrávaj, Ctrl+C = stop
python scripts\record_obd.py --fake --seconds 20    # skúška bez auta
```

Pred spustením zavri ScanMaster (port môže používať len jedna appka).
Appka s autom len číta, nič nemaže ani nemení.

## Simulácia a grafy (bez auta)

```
python scripts\simulate.py            # nahrá simulovaný štart s trasením
python scripts\simulate.py --healthy  # nahrá zdravé auto na porovnanie
streamlit run app\dashboard.py        # otvorí grafy v prehliadači
```
