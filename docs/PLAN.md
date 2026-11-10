# Plán projektu Brutology

- [x] Fáza 0: Prostredie, Git, štruktúra projektu
- [ ] Fáza 1: Kábel pripojený, nájdený COM port (scripts/list_ports.py)
- [ ] Fáza 2: Prvé spojenie s autom, výpis živých dát do konzoly
      - pripravené pre ELM327 USB (OBD-II): src/brutology/obd.py, scripts/record_obd.py,
        otestované s falošným káblom (fake_elm.py); čaká na vyskúšanie na aute
      - ELM327 funguje so ScanMaster-ELM (fuel trimy prečítané), s ISTA nie
      - číta aj chybové kódy (mód 03/07, len čítanie)
- [x] Fáza 3 (simulácia): Ukladanie do SQLite, nahrávanie relácie, simulátor studeného štartu
- [x] Fáza 4 (základ): Grafy relácií (app/dashboard.py)
- [x] Fáza 5 (základ): Analýza anomálií pri studenom štarte (src/brutology/analysis.py)
      - hotové: výpadky a nerovnomernosť po valcoch, voľnobeh (kolísanie, nízky/vysoký),
        MAP, MAF, fuel trimy oboch bánk (krátko- aj dlhodobé, rozdiel bánk), snímače
        teploty (nezmysel, skoky, nesedí pri štarte, termostat), poloha klapky, lambda
        sondy a regulácia, predstih, ICV, DISA, VANOS, napätie
      - rebríček pravdepodobných príčin s radou, čo skontrolovať (rank_causes)
      - simulátor vie 7 porúch (simulate.py --list), každá je pokrytá testom
      - ICV, DISA, VANOS, valce: kontroly hotové, dáta prídu až s DS2 (Fáza 6)
      - zostáva: doladiť prahy na reálnych dátach, porovnanie relácií
- [ ] Fáza 6: BMW DS2 protokol (dáta špecifické pre MS43)
- [ ] Fáza 7: Telefón

## Poznámky
- Motor M54B30, DME Siemens MS43, komunikácia cez K-line (DS2).
- Kábel: K+DCAN, na E46 musí byť v režime K-line (na DS2).
- Kábel 2: ELM327 USB (lacná kópia) - len generické OBD-II, bez DS2.
- Názvy veličín (katalóg) sú v hlavičke src/brutology/sources.py; Ds2Source ich musí dodržať.
- Prahy v analysis.py sú odhady (najmä roughness_cyl a ICV - jednotky MS43 zatiaľ nepoznáme).
