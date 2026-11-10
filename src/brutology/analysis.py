"""Hľadanie anomálií v nahranej relácii ("detektív").

Vstup je tabuľka (pandas DataFrame): index = čas v sekundách, stĺpce = veličiny
(názvy pozri v sources.py). Analýza pozná len názvy veličín, takže funguje
rovnako pre simulátor, OBD-II aj DS2. Ak niektorá veličina chýba (napr. ICV cez
ELM327), jej kontrola sa jednoducho preskočí.

Každý nález má zoznam možných PRÍČIN (kľúče do CAUSES). Funkcia rank_causes()
z nich spraví rebríček "na čo sa pozrieť najprv".

Prahy (limity) sú zatiaľ odhady. Keď budeme mať reálne dáta z Brutusa, doladíme ich.
"""
import re
from dataclasses import dataclass

import pandas as pd

# --- časové okná ---
WINDOW_S = 2.0        # dĺžka okna na meranie kolísania [s]
MIN_DURATION_S = 1.0  # kratšie úseky ignorujeme (náhodný šum)
MERGE_GAP_S = 10.0    # úseky bližšie k sebe spojíme do jedného

# --- prahy ---
RPM_STD_LIMIT = 25.0      # kolísanie otáčok na voľnobehu [ot/min]
IDLE_LOW_RPM = 600        # pod týmto hrozí zhasnutie
IDLE_HIGH_WARM_RPM = 950  # teplý motor by mal mať voľnobeh ~700-800
MAP_STD_LIMIT = 1.5       # kolísanie tlaku v sání [kPa]
STFT_LIMIT = 5.0          # krátkodobý fuel trim [%] (+ = ECU pridáva palivo)
LTFT_LIMIT = 8.0          # dlhodobý fuel trim [%]
BANK_DIFF_LIMIT = 6.0     # rozdiel trimov medzi bankami [%]
ROUGH_ABS = 1.2           # nerovnomernosť chodu valca (jednotky ECU, odhad!)
ROUGH_RATIO = 2.0         # valec je X-krát horší ako medián ostatných
MAF_IDLE_MIN = 2.5        # vzduch na voľnobehu [g/s]
TIMING_STD_LIMIT = 4.0    # kolísanie predstihu [°]
TPS_STD_LIMIT = 1.0       # "šum" polohy škrtiacej klapky pri voľnobehu [%]
ICV_LOW, ICV_HIGH = 22.0, 60.0   # otvorenie ICV [%]
ICV_STD_LIMIT = 5.0       # kolísanie ICV [%]
VANOS_DEV_LIMIT = 5.0     # odchýlka skutočnej polohy VANOS od požadovanej [°]
O2_SWING_MIN = 0.3        # lambda sonda by mala "spínať" aspoň o toľko [V]
O2_WINDOW_S = 10.0
CLOSED_LOOP_MAX_S = 180   # do kedy má ECU začať regulovať zmes podľa sondy
BATTERY_MIN_V = 13.0      # pri bežiacom motore by alternátor mal nabíjať nad 13 V
COLD_C = 40.0             # pod touto teplotou chladiva berieme motor ako studený
WARM_C = 70.0
SENSOR_DIFF_START_C = 20  # pri štarte po noci majú byť chladivo a vzduch podobné
TEMP_JUMP_C_PER_S = 5.0   # teplota sa nemôže meniť skokom
THERMOSTAT_MIN_S = 600    # po 10 min. jazdy/voľnobehu má byť motor teplý

SEVERITY_ORDER = {"vysoká": 0, "stredná": 1, "nízka": 2}
SEVERITY_WEIGHT = {"vysoká": 3.0, "stredná": 2.0, "nízka": 1.0}
POSITION_WEIGHT = (1.0, 0.7, 0.5, 0.35, 0.25, 0.2)   # prvá príčina v zozname je najpravdepodobnejšia

# Možné príčiny: kľúč -> (názov, čo skontrolovať)
CAUSES = {
    "coil_plug": ("Zapaľovacia cievka alebo sviečka",
                  "Prehoď cievku podozrivého valca s iným valcom. Ak sa výpadok presunie, "
                  "je to cievka; ak nie, skontroluj sviečku."),
    "injector": ("Vstrekovač (upchatý alebo kvapkajúci)",
                 "Ak cievka a sviečka sú OK, prehoď vstrekovač s iným valcom."),
    "vacuum_leak": ("Falošný vzduch (netesnosť v sání)",
                    "Hadice za MAF, tesnenie sacieho potrubia, hadica k brzdovému posilňovaču, "
                    "trubica mierky oleja. Na hľadanie pomôže dymová skúška."),
    "ccv": ("CCV – odvetranie kľukovej skrine",
            "Na M54 veľmi časté, v zime horšie (membrána stuhne). Pri bežiacom motore "
            "pootvor uzáver oleja: silný podtlak alebo zadúšanie = zlé CCV."),
    "maf": ("Merač hmotnosti vzduchu (MAF/HFM)",
            "Skús ho vyčistiť sprejom na MAF; pri pochybnostiach porovnaj s iným kusom."),
    "fuel_pressure": ("Slabý tlak paliva",
                      "Palivové čerpadlo, palivový filter (s regulátorom tlaku na E46)."),
    "icv": ("Nastavovač voľnobehu (ICV)",
            "Vymontuj a vyčisti čističom karburátora; pri studenom motore sa rád zasekáva."),
    "throttle": ("Škrtiaca klapka (EDK) alebo jej snímač polohy",
                 "Vyčisti klapku; skontroluj konektor. Po čistení môže byť potrebná adaptácia."),
    "coolant_sensor": ("Snímač teploty chladiva",
                       "Po noci státia porovnaj teplotu chladiva a vzduchu – majú byť podobné. "
                       "Zlý snímač robí pri studenom štarte chudobnú zmes."),
    "intake_temp_sensor": ("Snímač teploty nasávaného vzduchu", "Skontroluj snímač a konektor."),
    "thermostat": ("Termostat zaseknutý v otvorenej polohe",
                   "Motor sa pomaly zahrieva, kúrenie je vlažné."),
    "o2_sensor": ("Lambda sonda (alebo jej ohrev)",
                  "Lenivá alebo mŕtva sonda; skontroluj aj poistku a konektor ohrevu."),
    "vanos": ("VANOS",
              "Tesnenia VANOS (na M54 častá oprava), solenoidy, výška a kvalita oleja."),
    "disa": ("DISA klapka v sacom potrubí",
             "Vymontuj ventil a skontroluj vôľu klapky – zlomená klapka/čap sa v dátach "
             "prejaviť nemusí, treba ju skontrolovať rukou."),
    "battery_alternator": ("Batéria alebo alternátor", "Zmeraj napätie batérie a nabíjanie."),
    "wiring": ("Konektor alebo kabeláž snímača", "Hľadaj zlomený drôt alebo zhrdzavený konektor."),
}


@dataclass
class Finding:
    severity: str          # "vysoká" / "stredná" / "nízka"
    title: str
    detail: str
    signal: str
    t_start: float
    t_end: float
    coolant_c: float | None = None   # teplota chladiva na začiatku úseku
    causes: tuple = ()               # kľúče do CAUSES, najpravdepodobnejšia prvá
    direct: bool = False             # True = meranie priamo ukazuje na súčiastku (váži 2x)

    @property
    def cold(self) -> bool:
        return self.coolant_c is not None and self.coolant_c < COLD_C

    def when(self) -> str:
        txt = f"{self.t_start:.0f}-{self.t_end:.0f} s"
        if self.coolant_c is not None:
            txt += f", chladivo {self.coolant_c:.0f} °C"
            if self.cold:
                txt += " (studený motor)"
        return txt


# ---------------------------------------------------------------- pomocníci

def _window(df: pd.DataFrame, seconds: float = WINDOW_S) -> int:
    """Počet vzoriek, ktoré pokryjú `seconds` sekúnd."""
    if len(df) < 2:
        return 1
    step = pd.Series(df.index).diff().median()
    return max(3, int(round(seconds / step))) if step > 0 else 3


def _ranges(mask: pd.Series) -> list[tuple[float, float]]:
    """Z True/False série spraví zoznam časových úsekov (začiatok, koniec)."""
    mask = mask.fillna(False).astype(bool)
    ranges: list[list[float]] = []
    start = prev = None
    for t, flag in mask.items():
        if flag and start is None:
            start = t
        if not flag and start is not None:
            ranges.append([start, prev])
            start = None
        prev = t
    if start is not None:
        ranges.append([start, prev])

    merged: list[list[float]] = []
    for r in ranges:
        if merged and r[0] - merged[-1][1] <= MERGE_GAP_S:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [(a, b) for a, b in merged if b - a >= MIN_DURATION_S]


def _coolant_at(df: pd.DataFrame, t: float) -> float | None:
    if "coolant_temp_c" not in df:
        return None
    col = df["coolant_temp_c"].dropna()
    if col.empty:
        return None
    return float(col.iloc[col.index.get_indexer([t], method="nearest")[0]])


def _mean(df, col, seconds=WINDOW_S):
    return df[col].rolling(_window(df, seconds), center=True, min_periods=1).mean()


def _std(df, col, seconds=WINDOW_S):
    return df[col].rolling(_window(df, seconds), center=True, min_periods=2).std()


def _idle(df) -> pd.Series:
    """True tam, kde motor beží na voľnobehu (nízke otáčky, klapka zavretá)."""
    mask = pd.Series(True, index=df.index)
    if "rpm" in df:
        rpm = df["rpm"].rolling(_window(df), center=True, min_periods=1).median()
        mask &= (rpm > 300) & (rpm < 1300)
    if "throttle_pct" in df:
        mask &= df["throttle_pct"] < 10
    return mask


def _bank(col: str) -> str:
    return "banka 2 (valce 4-6)" if "_b2" in col else "banka 1 (valce 1-3)"


class _Out(list):
    """Zoznam nálezov s pohodlným pridávaním pre každý úsek masky."""

    def __init__(self, df):
        super().__init__()
        self.df = df

    def add(self, severity, title, detail, signal, a, b, causes=(), direct=False):
        self.append(Finding(severity, title, detail, signal, float(a), float(b),
                            _coolant_at(self.df, a), tuple(causes), direct))

    def each(self, mask, severity, title, detail_fn, signal, causes=(), direct=False):
        for a, b in _ranges(mask):
            self.add(severity, title, detail_fn(a, b), signal, a, b, causes, direct)


# ---------------------------------------------------------------- kontroly

def _misfires(df, out):
    for col in sorted(c for c in df.columns if re.fullmatch(r"misfire_cyl\d+", c)):
        hits = df[col][df[col] > 0]
        if hits.empty:
            continue
        cyl = col.removeprefix("misfire_cyl")
        out.add("vysoká", f"Výpadky zapaľovania – valec {cyl}",
                f"{int(hits.sum())}× výpadok na valci {cyl}.",
                col, hits.index.min(), hits.index.max(), ("coil_plug", "injector"), direct=True)


def _roughness(df, out):
    cols = sorted(c for c in df.columns if re.fullmatch(r"roughness_cyl\d+", c))
    if len(cols) < 3:
        return
    r = df[cols].rolling(_window(df), center=True, min_periods=1).mean()
    med = r.median(axis=1)
    for col in cols:
        cyl = col.removeprefix("roughness_cyl")
        out.each((r[col] > ROUGH_ABS) & (r[col] > ROUGH_RATIO * med), "stredná",
                 f"Valec {cyl} beží nerovnomerne",
                 lambda a, b, c=col: f"Nerovnomernosť {r[c].loc[a:b].max():.1f} oproti "
                                     f"{med.loc[a:b].mean():.1f} pri ostatných valcoch – "
                                     f"tento valec horí horšie (aj keď ešte nevypadáva).",
                 col, ("coil_plug", "injector", "vacuum_leak"), direct=True)
    out.each(med > ROUGH_ABS, "stredná", "Všetky valce bežia nerovnomerne",
             lambda a, b: f"Medián nerovnomernosti {med.loc[a:b].max():.1f} (limit {ROUGH_ABS:g}). "
                          f"Keď trpia všetky valce naraz, príčina je spoločná – zmes alebo vzduch.",
             cols[0], ("vacuum_leak", "ccv", "coolant_sensor", "fuel_pressure", "maf"))


def _rpm(df, out):
    if "rpm" not in df:
        return
    std = _std(df, "rpm")
    out.each(_idle(df) & (std > RPM_STD_LIMIT), "vysoká", "Nestabilný voľnobeh (kolísanie otáčok)",
             lambda a, b: f"Kolíše o ±{std.loc[a:b].max():.0f} ot/min (limit {RPM_STD_LIMIT:g}). "
                          f"Toto je samotné trasenie – príčinu ukážu ostatné nálezy.",
             "rpm")
    mean = _mean(df, "rpm")
    idle = _idle(df)
    out.each(idle & (mean < IDLE_LOW_RPM), "stredná", "Príliš nízky voľnobeh",
             lambda a, b: f"Klesá na {mean.loc[a:b].min():.0f} ot/min (limit {IDLE_LOW_RPM}).",
             "rpm", ("icv", "throttle", "vacuum_leak"))
    if "coolant_temp_c" in df:
        warm = df["coolant_temp_c"] > WARM_C
        out.each(idle & warm & (mean > IDLE_HIGH_WARM_RPM), "stredná",
                 "Vysoký voľnobeh pri teplom motore",
                 lambda a, b: f"Až {mean.loc[a:b].max():.0f} ot/min, hoci snímač hlási teplý motor "
                              f"(očakávané ~700-800). Buď do motora ide vzduch navyše, alebo "
                              f"snímač teploty klame a motor je v skutočnosti studenší.",
                 "rpm", ("coolant_sensor", "vacuum_leak", "icv"))


def _map(df, out):
    if "map_kpa" not in df:
        return
    std = _std(df, "map_kpa")
    out.each(_idle(df) & (std > MAP_STD_LIMIT), "stredná", "Kolísanie tlaku v sání (MAP)",
             lambda a, b: f"Kolíše o ±{std.loc[a:b].max():.1f} kPa (limit {MAP_STD_LIMIT:g}). "
                          f"Nerovnomerné spaľovanie alebo falošný vzduch.",
             "map_kpa")


def _trims(df, out):
    for col in sorted(c for c in df.columns if re.fullmatch(r"(stft|ltft)(_b\d)?_pct", c)):
        short = col.startswith("stft")
        limit = STFT_LIMIT if short else LTFT_LIMIT
        trim = _mean(df, col)
        kind = "krátkodobý" if short else "dlhodobý"
        for a, b in _ranges(trim.abs() > limit):
            avg = trim.loc[a:b].mean()
            if avg > 0:
                why = "ECU pridáva palivo – zmes je chudobná (priveľa vzduchu alebo málo paliva)."
                causes = ("vacuum_leak", "ccv", "maf", "fuel_pressure")
            else:
                why = "ECU uberá palivo – zmes je bohatá."
                causes = ("injector", "coolant_sensor", "o2_sensor", "fuel_pressure")
            out.add("stredná", f"Vysoký {kind} fuel trim – {_bank(col)}",
                    f"Priemerne {avg:+.1f} % (limit ±{limit:g} %). {why}", col, a, b, causes)

    for kind in ("stft", "ltft"):
        c1, c2 = f"{kind}_pct", f"{kind}_b2_pct"
        if c1 in df and c2 in df:
            diff = _mean(df, c1) - _mean(df, c2)
            label = "krátkodobý" if kind == "stft" else "dlhodobý"
            out.each(diff.abs() > BANK_DIFF_LIMIT, "stredná",
                     f"Banky motora sa líšia ({label} trim)",
                     lambda a, b, d=diff: (
                         f"{'Banka 1 (valce 1-3)' if d.loc[a:b].mean() > 0 else 'Banka 2 (valce 4-6)'}"
                         f" je chudobnejšia o {abs(d.loc[a:b].mean()):.1f} %. Problém je len na "
                         f"jednej strane motora – hľadaj netesnosť alebo vstrekovač na tej strane."),
                     c1, ("vacuum_leak", "injector", "o2_sensor"))


def _temperature_sensors(df, out):
    for col, name, hi, causes in (
            ("coolant_temp_c", "chladiva", 130, ("coolant_sensor", "wiring")),
            ("intake_temp_c", "nasávaného vzduchu", 100, ("intake_temp_sensor", "wiring"))):
        if col not in df:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        bad = (s <= -39) | (s >= hi)
        out.each(bad, "vysoká", f"Snímač teploty {name} hlási nezmysel",
                 lambda a, b, s=s: f"Hodnota {s.loc[a:b].iloc[0]:.0f} °C – typické pre odpojený "
                                   f"snímač alebo skrat.", col, causes, direct=True)
        rate = (s.diff() / pd.Series(s.index, index=s.index).diff()).abs()
        jumps = s.index[(rate > TEMP_JUMP_C_PER_S) & (s.diff().abs() > 3)]
        if len(jumps):
            out.add("stredná", f"Teplota {name} skáče",
                    f"{len(jumps)}× skok o viac ako 3 °C naraz. Skutočná teplota sa takto "
                    f"meniť nemôže – zlý kontakt snímača.", col, jumps.min(), jumps.max(), causes,
                    direct=True)

    if "coolant_temp_c" in df and "intake_temp_c" in df:
        start = df.loc[: df.index.min() + 3]
        cool, air = start["coolant_temp_c"].mean(), start["intake_temp_c"].mean()
        if cool < 60 and cool - air > SENSOR_DIFF_START_C:
            out.add("vysoká", "Teplota chladiva pri štarte nesedí",
                    f"Chladivo {cool:.0f} °C, vzduch {air:.0f} °C. Po noci státia by mali byť "
                    f"podobné. Buď motor nebol úplne studený, alebo snímač chladiva ukazuje viac – "
                    f"vtedy ECU dáva pri studenom štarte málo paliva a motor sa trasie.",
                    "coolant_temp_c", df.index.min(), df.index.min() + 3,
                    ("coolant_sensor", "wiring"), direct=True)
        if air - cool > SENSOR_DIFF_START_C and cool < 40:
            out.add("nízka", "Teplota nasávaného vzduchu pri štarte nesedí",
                    f"Vzduch {air:.0f} °C, chladivo {cool:.0f} °C (motor stál na slnku?).",
                    "intake_temp_c", df.index.min(), df.index.min() + 3,
                    ("intake_temp_sensor", "wiring"))

    if "coolant_temp_c" in df:
        s = df["coolant_temp_c"].dropna()
        duration = s.index.max() - s.index.min() if len(s) else 0
        if duration >= THERMOSTAT_MIN_S and s.iloc[:10].mean() < 50 and s.max() < WARM_C:
            out.add("stredná", "Motor sa nezahrieva",
                    f"Ani po {duration / 60:.0f} minútach chladivo neprekročilo {s.max():.0f} °C. "
                    f"Studený motor beží s bohatšou zmesou a horšie.",
                    "coolant_temp_c", s.index.min(), s.index.max(),
                    ("thermostat", "coolant_sensor"))


def _throttle(df, out):
    if "throttle_pct" not in df:
        return
    std, mean = _std(df, "throttle_pct"), _mean(df, "throttle_pct")
    out.each((std > TPS_STD_LIMIT) & (mean < 10) & _idle(df), "stredná",
             "Poloha škrtiacej klapky na voľnobehu skáče",
             lambda a, b: f"Kolíše o ±{std.loc[a:b].max():.1f} % pri zavretej klapke "
                          f"(limit {TPS_STD_LIMIT:g}). Ak si nestláčal plyn, snímač polohy "
                          f"alebo jeho konektor robí šum.",
             "throttle_pct", ("throttle", "wiring"), direct=True)


def _maf(df, out):
    if "maf_gs" not in df:
        return
    mean = _mean(df, "maf_gs")
    out.each(_idle(df) & (mean < MAF_IDLE_MIN), "stredná", "Málo vzduchu cez MAF na voľnobehu",
             lambda a, b: f"Len {mean.loc[a:b].min():.1f} g/s (očakávané nad {MAF_IDLE_MIN:g}). "
                          f"Časť vzduchu ide mimo MAF (netesnosť), alebo MAF meria málo.",
             "maf_gs", ("vacuum_leak", "maf"))


def _o2(df, out):
    if "closed_loop" in df:
        active = df["closed_loop"] > 0.5
        start_cold = _coolant_at(df, df.index.min())
        if start_cold is not None and start_cold < COLD_C:
            first = active[active].index.min() if active.any() else None
            t_rel = (first - df.index.min()) if first is not None else None
            if (t_rel is not None and t_rel > CLOSED_LOOP_MAX_S) or \
                    (t_rel is None and df.index.max() - df.index.min() > CLOSED_LOOP_MAX_S):
                out.add("stredná", "ECU dlho nereguluje zmes podľa lambda sondy",
                        f"Regulácia začala {'až po ' + format(t_rel, '.0f') + ' s' if t_rel else 'vôbec nezačala'}"
                        f" (očakávané do {CLOSED_LOOP_MAX_S} s). Sonda alebo jej ohrev nefunguje.",
                        "closed_loop", df.index.min(), df.index.max(),
                        ("o2_sensor", "coolant_sensor"))
    elif "coolant_temp_c" in df:
        active = df["coolant_temp_c"] > WARM_C
    else:
        return
    for col in sorted(c for c in df.columns if re.fullmatch(r"o2_b\ds1_v", c)):
        w = _window(df, O2_WINDOW_S)
        roll = df[col].rolling(w, center=True, min_periods=w // 2)
        swing = roll.max() - roll.min()
        out.each(active & (swing < O2_SWING_MIN), "stredná",
                 f"Lambda sonda {'banky 2' if '_b2' in col else 'banky 1'} nespína",
                 lambda a, b, s=swing: f"Napätie sa mení len o {s.loc[a:b].max():.2f} V "
                                       f"(zdravá sonda skáče 0,1-0,9 V niekoľkokrát za sekundu).",
                 col, ("o2_sensor", "wiring"), direct=True)


def _timing(df, out):
    if "timing_adv_deg" not in df:
        return
    std = _std(df, "timing_adv_deg")
    out.each(_idle(df) & (std > TIMING_STD_LIMIT), "nízka", "Predstih na voľnobehu silno kolíše",
             lambda a, b: f"±{std.loc[a:b].max():.1f}° (limit {TIMING_STD_LIMIT:g}°). ECU sa "
                          f"predstihom snaží udržať otáčky – bojuje s nestabilným voľnobehom.",
             "timing_adv_deg", ("icv", "vacuum_leak"))


def _icv(df, out):
    if "icv_pct" not in df:
        return
    mean, std = _mean(df, "icv_pct"), _std(df, "icv_pct")
    idle = _idle(df)
    out.each(idle & (mean < ICV_LOW), "stredná", "ICV je takmer zatvorený",
             lambda a, b: f"Otvorenie len {mean.loc[a:b].min():.0f} % (limit {ICV_LOW:g} %). ECU "
                          f"privrela ICV, lebo do motora ide vzduch inou cestou.",
             "icv_pct", ("vacuum_leak", "ccv"))
    out.each(idle & (mean > ICV_HIGH), "stredná", "ICV je príliš otvorený",
             lambda a, b: f"Otvorenie až {mean.loc[a:b].max():.0f} % (limit {ICV_HIGH:g} %). "
                          f"Motor potrebuje viac vzduchu, než by mal – zanesený ICV alebo klapka.",
             "icv_pct", ("icv", "throttle"), direct=True)
    out.each(idle & (std > ICV_STD_LIMIT), "vysoká", "ICV kolíše (nastavovač voľnobehu)",
             lambda a, b: f"Otvorenie kolíše o ±{std.loc[a:b].max():.0f} % (limit "
                          f"{ICV_STD_LIMIT:g}). Ventil sa zasekáva alebo ECU nevie ustáliť otáčky.",
             "icv_pct", ("icv",), direct=True)


def _disa(df, out):
    if "disa_open" not in df:
        return
    state = (df["disa_open"] > 0.5).astype(int)
    low = df["rpm"] < 2000 if "rpm" in df else pd.Series(True, index=df.index)
    changes = state.diff().abs().fillna(0)
    flips = changes[low & (changes > 0)]
    if len(flips) >= 3:
        out.add("stredná", "DISA klapka sa prepína na voľnobehu",
                f"{len(flips)}× zmena polohy pri nízkych otáčkach. DISA by sa mala prepínať "
                f"len pri vyšších otáčkach.", "disa_open", flips.index.min(), flips.index.max(),
                ("disa",), direct=True)


def _vanos(df, out):
    for target in sorted(c for c in df.columns if re.fullmatch(r"vanos_\w+_target_deg", c)):
        actual = target.replace("_target_", "_actual_")
        if actual not in df:
            continue
        side = "sania" if "_in_" in target else "výfuku"
        dev = (df[target] - df[actual]).abs().rolling(_window(df), center=True,
                                                       min_periods=1).mean()
        out.each(dev > VANOS_DEV_LIMIT, "vysoká", f"VANOS {side} nedosahuje požadovanú polohu",
                 lambda a, b, d=dev: f"Odchýlka až {d.loc[a:b].max():.0f}° (limit "
                                     f"{VANOS_DEV_LIMIT:g}°). Vačkový hriadeľ nie je tam, kde ho "
                                     f"ECU chce mať – motor beží nerovnomerne.",
                 actual, ("vanos",), direct=True)


def _battery(df, out):
    if "battery_v" not in df:
        return
    volts = _mean(df, "battery_v")
    out.each(volts < BATTERY_MIN_V, "nízka", "Nízke napätie palubnej siete",
             lambda a, b: f"Najnižšie {volts.loc[a:b].min():.2f} V (očakávané nad "
                          f"{BATTERY_MIN_V:g} V pri bežiacom motore). Slabé napätie zhoršuje "
                          f"zapaľovanie.", "battery_v", ("battery_alternator",), direct=True)


CHECKS = (_misfires, _roughness, _rpm, _map, _trims, _temperature_sensors, _throttle,
          _maf, _o2, _timing, _icv, _disa, _vanos, _battery)


def analyze(df: pd.DataFrame) -> list[Finding]:
    """Prejde reláciu a vráti zoznam nálezov, najvážnejšie prvé."""
    if df.empty:
        return []
    df = df.sort_index()
    out = _Out(df)
    for check in CHECKS:
        check(df, out)
    out.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.t_start))
    return list(out)


@dataclass
class Suspect:
    key: str
    name: str
    tip: str
    score: float
    evidence: list[str]


def rank_causes(findings: list[Finding]) -> list[Suspect]:
    """Zoradí možné príčiny podľa toho, koľko a aké vážne nálezy na ne ukazujú."""
    suspects: dict[str, Suspect] = {}
    for f in findings:
        for pos, key in enumerate(f.causes):
            name, tip = CAUSES[key]
            s = suspects.setdefault(key, Suspect(key, name, tip, 0.0, []))
            weight = POSITION_WEIGHT[min(pos, len(POSITION_WEIGHT) - 1)]
            s.score += (SEVERITY_WEIGHT.get(f.severity, 1) * weight
                        * (1.3 if f.cold else 1) * (2 if f.direct else 1))
            if f.title not in s.evidence:
                s.evidence.append(f.title)
    return sorted(suspects.values(), key=lambda s: -s.score)


NO_FINDINGS_HINT = ("Ak sa auto trasie, ale dáta sú v poriadku, pozri sa aj na veci, ktoré "
                    "riadiaca jednotka nevidí: silentbloky (uloženie) motora a prevodovky, "
                    "zlomená DISA klapka, a ešte nemáme dáta cez DS2 (ICV, VANOS, valce).")


def print_findings(findings: list[Finding], top: int = 5) -> None:
    """Vypíše nálezy a rebríček podozrivých do konzoly."""
    print(f"\nNálezy ({len(findings)}):")
    for f in findings:
        print(f"  [{f.severity}] {f.title}  ({f.when()})")
        print(f"      {f.detail}")
    if not findings:
        print("  žiadne anomálie")
        print(f"  {NO_FINDINGS_HINT}")
        return
    suspects = rank_causes(findings)
    if suspects:
        print("\nNajpravdepodobnejšie príčiny (na čo sa pozrieť najprv):")
        for i, s in enumerate(suspects[:top], 1):
            print(f"  {i}. {s.name}  (skóre {s.score:.1f})")
            print(f"      prečo: {', '.join(s.evidence)}")
            print(f"      čo urobiť: {s.tip}")
