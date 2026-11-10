# Brutology

Diagnostická appka pre BMW E46 330i ("Brutus"). Číta a ukladá živé dáta z riadiacej
jednotky cez diagnostický kábel, zobrazuje grafy a pomáha nájsť príčinu problému.

## Čo hľadáme
Auto sa pri **studenom štarte trasie** a príčina nie je známa. Appka má zaznamenať
štart od studeného motora, zobraziť priebeh a upozorniť na anomálie (kolísanie
otáčok, fuel trimy, výpadky zapaľovania po valcoch, VANOS, voľnobeh...).

## Auto a hardvér
- BMW E46 330i, motor M54B30, riadiaca jednotka Siemens MS43
- Kábel: K+DCAN (USB sériový prevodník, hádam FTDI), na E46 musí byť v režime **K-line**
- Generické OBD-II dá len emisné dáta; BMW-špecifické dáta (zapaľovanie po valcoch,
  VANOS, voľnobeh) idú cez protokol **DS2** a ten je takmer nezdokumentovaný
- Kábel 2: ELM327 USB (lacná kópia) - len generické OBD-II; s autom funguje cez
  ScanMaster-ELM (fuel trimy), s ISTA nie. Appka ho číta cez `obd.py`
- Appka sa k autu ešte nepripojila; zatiaľ sa vyvíja so simulátorom a falošným ELM327

## Používateľ
Ivan je úplný začiatočník v programovaní a vibe codingu, hovorí po slovensky.
- Komunikuj po slovensky, jednoducho, bez zbytočného žargónu; nový pojem krátko vysvetli
- Pred väčšími zmenami povedz, čo ideš robiť a prečo
- Po každom fungujúcom kroku urob commit s výstižnou správou (Git = "uložiť hru")
- Neinštaluj nič mimo projektu bez opýtania; mazanie súborov vždy oznám
- `git push` rob, len keď o to Ivan požiada

## Technológie
- Python 3.12, `pyserial` (sériový port), SQLite (logy), pandas + plotly + Streamlit (grafy)
- Prostredie: Windows, virtuálne prostredie `.venv` (`setup.bat` ho vytvorí)

## Štruktúra
- `src/brutology/` - jadro: `sources.py` (zdroje dát), `storage.py` (SQLite), `recorder.py`,
  `analysis.py` (anomálie), `obd.py` (ELM327/OBD-II, povolené len čítacie príkazy),
  `fake_elm.py` (falošný ELM327 na testy), `signals.py` (slovník: názov, jednotka a
  vysvetlenie každej veličiny + pojmy; nová veličina musí mať popis, stráži to test)
- `app/dashboard.py` - grafy (`streamlit run app/dashboard.py`, alebo `start.bat`)
- `scripts/` - `simulate.py` (simulovaný štart, `--fault`, `--list`), `list_ports.py` (COM port),
  `record_obd.py` (nahrávanie z auta cez ELM327, `--check`, `--fake`)
- `tests/` - spustenie: `python -m unittest discover -s tests`
- `docs/PLAN.md` - plán a stav fáz, **aktualizuj ho po dokončení fázy**
- `data/logs/` - namerané dáta, nie sú v Gite

## Architektúra
Každý zdroj dát dedí z `DataSource` a vracia `{názov_veličiny: hodnota}`; katalóg
názvov je v hlavičke `sources.py`. Analýza preskočí kontroly, ktorých veličiny chýbajú,
a každý nález odkazuje na možné príčiny (`CAUSES`), z ktorých `rank_causes` robí rebríček. Existuje
`SimulatedCar` a `ObdSource` (OBD-II cez ELM327); pribudne `Ds2Source` (BMW DS2). Ukladanie,
grafy ani analýza sa pri pridaní nového zdroja nesmú meniť.

## Zásady
- Auto je reálne: komunikácia s riadiacou jednotkou je **len na čítanie**. Nikdy
  nezapisuj, nekóduj ani nemeň nič v DME bez výslovného súhlasu Ivana
- Najprv testy a simulátor, až potom reálne auto
- Dáta z auta (logy) sú osobné, necommituj ich
