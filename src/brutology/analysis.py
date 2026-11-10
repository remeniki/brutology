"""Hľadanie anomálií v nahranej relácii ("detektív").

Vstup je tabuľka (pandas DataFrame): index = čas v sekundách, stĺpce = veličiny
(rpm, stft_pct, misfire_cyl3, ...). Analýza pozná len názvy veličín, takže funguje
rovnako pre simulátor, OBD-II aj DS2. Ak niektorá veličina chýba, jej kontrola sa
jednoducho preskočí.

Prahy (limity) sú zatiaľ odhady. Keď budeme mať reálne dáta z Brutusa, doladíme ich.
"""
import re
from dataclasses import dataclass

import pandas as pd

WINDOW_S = 2.0        # dĺžka okna na meranie kolísania [s]
MIN_DURATION_S = 1.0  # kratšie úseky ignorujeme (náhodný šum)
MERGE_GAP_S = 1.5     # úseky bližšie k sebe spojíme do jedného

RPM_STD_LIMIT = 25.0     # kolísanie otáčok na voľnobehu [ot/min]
MAP_STD_LIMIT = 1.5      # kolísanie tlaku v sání [kPa]
STFT_LIMIT = 5.0         # krátkodobý fuel trim [%] (+ = ECU pridáva palivo)
BATTERY_MIN_V = 13.0     # pri bežiacom motore by alternátor mal nabíjať nad 13 V
COLD_C = 40.0            # pod touto teplotou chladiva berieme motor ako studený

SEVERITY_ORDER = {"vysoká": 0, "stredná": 1, "nízka": 2}


@dataclass
class Finding:
    severity: str          # "vysoká" / "stredná" / "nízka"
    title: str
    detail: str
    signal: str
    t_start: float
    t_end: float
    coolant_c: float | None = None   # teplota chladiva na začiatku úseku

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


def _window(df: pd.DataFrame) -> int:
    """Počet vzoriek, ktoré pokryjú WINDOW_S sekúnd."""
    if len(df) < 2:
        return 1
    step = pd.Series(df.index).diff().median()
    return max(3, int(round(WINDOW_S / step))) if step > 0 else 3


def _ranges(mask: pd.Series) -> list[tuple[float, float]]:
    """Z True/False série spraví zoznam časových úsekov (začiatok, koniec)."""
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


def _check_unsteady(df, findings, signal, limit, unit, title, why, severity):
    """Spoločná kontrola kolísania: smerodajná odchýlka v kĺzavom okne."""
    if signal not in df:
        return
    std = df[signal].rolling(_window(df), center=True, min_periods=2).std()
    for a, b in _ranges(std > limit):
        peak = std.loc[a:b].max()
        findings.append(Finding(
            severity, title,
            f"Kolíše o ±{peak:.1f} {unit} (limit {limit:g}). {why}",
            signal, a, b, _coolant_at(df, a)))


def print_findings(findings: list[Finding]) -> None:
    """Vypíše nálezy do konzoly."""
    print(f"\nNálezy ({len(findings)}):")
    for f in findings:
        print(f"  [{f.severity}] {f.title}  ({f.when()})")
        print(f"      {f.detail}")
    if not findings:
        print("  žiadne anomálie")


def analyze(df: pd.DataFrame) -> list[Finding]:
    """Prejde reláciu a vráti zoznam nálezov, najvážnejšie prvé."""
    findings: list[Finding] = []
    if df.empty:
        return findings
    df = df.sort_index()

    # 1) Výpadky zapaľovania po valcoch (misfire_cyl1 ... misfire_cyl6)
    for col in sorted(c for c in df.columns if re.fullmatch(r"misfire_cyl\d+", c)):
        hits = df[col][df[col] > 0]
        if hits.empty:
            continue
        cyl = col.removeprefix("misfire_cyl")
        a, b = float(hits.index.min()), float(hits.index.max())
        findings.append(Finding(
            "vysoká", f"Výpadky zapaľovania – valec {cyl}",
            f"{int(hits.sum())}× výpadok. Typicky zapaľovacia cievka, sviečka alebo "
            f"vstrekovač na tomto valci (skús prehodiť cievku s iným valcom).",
            col, a, b, _coolant_at(df, a)))

    # 2) Kolísanie otáčok = to, čo cítiš ako trasenie
    _check_unsteady(df, findings, "rpm", RPM_STD_LIMIT, "ot/min",
                    "Nestabilný voľnobeh (kolísanie otáčok)",
                    "Motor nedrží rovnomerné otáčky – to je trasenie.", "vysoká")

    # 3) Kolísanie tlaku v sání
    _check_unsteady(df, findings, "map_kpa", MAP_STD_LIMIT, "kPa",
                    "Kolísanie tlaku v sání (MAP)",
                    "Nerovnomerné nasávanie – nerovnomerné spaľovanie alebo falošný vzduch.",
                    "stredná")

    # 4) Fuel trim: ECU musí výrazne dolaďovať zmes
    if "stft_pct" in df:
        trim = df["stft_pct"].rolling(_window(df), center=True, min_periods=1).mean()
        for a, b in _ranges(trim.abs() > STFT_LIMIT):
            avg = trim.loc[a:b].mean()
            why = ("ECU pridáva palivo – zmes je chudobná. Častá príčina na M54: "
                   "falošný vzduch (prasknuté hadice, CCV/odvetranie kľukovej skrine, "
                   "tesnenie sania) alebo slabý tlak paliva."
                   if avg > 0 else
                   "ECU uberá palivo – zmes je bohatá (vstrekovač, tlak paliva, snímač).")
            findings.append(Finding(
                "stredná", "Vysoký krátkodobý fuel trim",
                f"Priemerne {avg:+.1f} % (limit ±{STFT_LIMIT:g} %). {why}",
                "stft_pct", a, b, _coolant_at(df, a)))

    # 5) Napätie batérie (slabé napätie zhoršuje zapaľovanie)
    if "battery_v" in df:
        volts = df["battery_v"].rolling(_window(df), center=True, min_periods=1).mean()
        for a, b in _ranges(volts < BATTERY_MIN_V):
            findings.append(Finding(
                "nízka", "Nízke napätie palubnej siete",
                f"Najnižšie {volts.loc[a:b].min():.2f} V (očakávané nad {BATTERY_MIN_V:g} V "
                f"pri bežiacom motore). Skontroluj batériu a alternátor.",
                "battery_v", a, b, _coolant_at(df, a)))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.t_start))
    return findings
