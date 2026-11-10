# Plán projektu Brutology

- [x] Fáza 0: Prostredie, Git, štruktúra projektu
- [ ] Fáza 1: Kábel pripojený, nájdený COM port (scripts/list_ports.py)
- [ ] Fáza 2: Prvé spojenie s autom, výpis živých dát do konzoly
      - pripravené pre ELM327 USB (OBD-II): src/brutology/obd.py, scripts/record_obd.py,
        otestované s falošným káblom (fake_elm.py); čaká na vyskúšanie na aute
      - ELM327 funguje so ScanMaster-ELM (fuel trimy prečítané), s ISTA nie
- [x] Fáza 3 (simulácia): Ukladanie do SQLite, nahrávanie relácie, simulátor studeného štartu
- [x] Fáza 4 (základ): Grafy relácií (app/dashboard.py)
- [x] Fáza 5 (základ): Analýza anomálií pri studenom štarte (src/brutology/analysis.py)
      - hotové: výpadky po valcoch, kolísanie otáčok a MAP, fuel trim, napätie
      - zostáva: doladiť prahy na reálnych dátach, VANOS a voľnobeh (po DS2), porovnanie relácií
- [ ] Fáza 6: BMW DS2 protokol (dáta špecifické pre MS43)
- [ ] Fáza 7: Telefón

## Poznámky
- Motor M54B30, DME Siemens MS43, komunikácia cez K-line (DS2).
- Kábel: K+DCAN, na E46 musí byť v režime K-line (na DS2).
- Kábel 2: ELM327 USB (lacná kópia) - len generické OBD-II, bez DS2.
- Analýza fuel trimu zatiaľ kontroluje len banku 1 (stft_pct); OBD dáva aj banku 2 (stft_b2_pct).
