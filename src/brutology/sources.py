"""Zdroje dat. Každý zdroj vráti slovník {názov_veličiny: hodnota}.

SimulatedCar napodobňuje studený štart E46 330i vrátane rôznych porúch.
ObdSource (obd.py) číta skutočné auto cez ELM327. Neskôr pribudne Ds2Source
(BMW DS2) so zhodným rozhraním, takže zvyšok appky sa nemusí meniť.

Katalóg názvov veličín (rovnaké pre všetky zdroje):
  OBD-II aj DS2:  rpm, coolant_temp_c, intake_temp_c, throttle_pct, map_kpa, maf_gs,
                  stft_pct, stft_b2_pct, ltft_pct, ltft_b2_pct, timing_adv_deg,
                  o2_b1s1_v, o2_b2s1_v, closed_loop (1 = ECU reguluje zmes podľa
                  lambda sondy), battery_v
  len DS2:        icv_pct (otvorenie nastavovača voľnobehu), disa_open (0/1),
                  vanos_in_target_deg / vanos_in_actual_deg (sanie),
                  vanos_ex_target_deg / vanos_ex_actual_deg (výfuk),
                  roughness_cyl1..6 (nerovnomernosť chodu valca),
                  misfire_cyl1..6 (výpadky zapaľovania)
"""
import math
import random

# Poruchy, ktoré vie simulátor napodobniť (na skúšanie analýzy)
FAULTS = {
    "misfire": "výpadky zapaľovania na valci 3 (zlá cievka/sviečka)",
    "vacuum_leak": "falošný vzduch na banke 2 (valce 4-6)",
    "coolant_sensor": "snímač teploty chladiva ukazuje o 30 °C viac",
    "icv": "zaseknutý nastavovač voľnobehu (ICV)",
    "vanos": "zaseknutý VANOS sania",
    "o2_sensor": "mŕtva lambda sonda banky 1",
    "thermostat": "termostat zaseknutý v otvorenej polohe",
}


class DataSource:
    """Spoločné rozhranie pre všetky zdroje dát."""

    def read(self, t: float) -> dict:
        """Vráti hodnoty v čase t (sekundy od začiatku nahrávania)."""
        raise NotImplementedError

    def close(self) -> None:
        pass


class SimulatedCar(DataSource):
    """Simulácia studeného štartu.

    fault=True  -> "misfire" (výpadky na valci 3, pôvodné správanie)
    fault=False / None -> zdravé auto
    fault="vacuum_leak" ... -> jedna z porúch v FAULTS
    """

    def __init__(self, fault=True, seed: int = 42):
        if fault is True:
            fault = "misfire"
        elif not fault:
            fault = None
        if fault is not None and fault not in FAULTS:
            raise ValueError(f"Neznáma porucha {fault!r}, možnosti: {', '.join(FAULTS)}")
        self.fault = fault
        self.rng = random.Random(seed)

    def read(self, t: float) -> dict:
        r, f = self.rng, self.fault
        g = r.gauss
        warm = 1 - math.exp(-t / 90)               # 0 = studený, 1 = zahriaty
        cold = 1 - warm
        early = t < 60                             # prvá minúta po štarte

        # --- teploty ---
        coolant = 10 + (55 if f == "thermostat" else 80) * warm
        if f == "coolant_sensor":
            coolant += 30                          # ECU si myslí, že motor je teplejší
        coolant += r.uniform(-0.3, 0.3)
        intake = 12 + 10 * warm + r.uniform(-0.2, 0.2)

        # --- otáčky a voľnobeh ---
        rpm_sd = 8.0
        if f == "misfire" and early:
            rpm_sd = 60
        elif f == "coolant_sensor" and early:
            rpm_sd = 45
        elif f == "vacuum_leak":
            rpm_sd = 8 + 30 * cold
        elif f == "vanos":
            rpm_sd = 30
        rpm = 1100 - 300 * warm + g(0, rpm_sd)
        icv = 38 + 10 * cold + g(0, 1.5)
        timing = 8 + g(0, 0.7)
        if f == "icv":                             # ICV sa zasekáva -> otáčky "plávajú"
            wave = math.sin(2 * math.pi * t / 4)
            rpm += 90 * wave
            icv += 15 * wave
            timing += 7 * wave
        if f == "vacuum_leak":                     # ECU privrie ICV, lebo vzduch ide inde
            icv = 18 + 4 * cold + g(0, 1.5)

        # --- valce ---
        misfires = [0] * 6
        if f == "misfire" and early and r.random() < 0.25:
            misfires[2] = 1
        rough = [0.5 + g(0, 0.15) for _ in range(6)]
        if f == "misfire":
            rough[2] = (3.0 if early else 0.7) + g(0, 0.3)
        if f == "coolant_sensor" and early:
            rough = [1.6 + g(0, 0.2) for _ in range(6)]

        # --- zmes ---
        stft1 = 1 * cold + g(0, 0.5)
        stft2 = 1 * cold + g(0, 0.5)
        if f == "misfire" and early:
            stft1 += 7 * cold
        if f == "coolant_sensor" and early:
            stft1 += 7 * cold
            stft2 += 7 * cold
        ltft1 = 1.5 + g(0, 0.1)
        ltft2 = 1.5 + g(0, 0.1)
        maf = 4.5 + 2 * cold + g(0, 0.1)
        if f == "vacuum_leak":
            stft2 += 4 + 6 * cold
            ltft2 += 9
            maf -= 2.6                             # MAF nevidí vzduch, ktorý ide dierou
        shaking = (f in ("misfire", "coolant_sensor")) and early
        map_kpa = 34 + g(0, 3 if shaking else 0.5)

        # --- lambda sondy ---
        closed_loop = 1 if t >= 45 else 0
        def o2(phase):
            if not closed_loop:
                return 0.45 + g(0, 0.01)
            return 0.45 + 0.4 * math.sin(2 * math.pi * t / 1.3 + phase) + g(0, 0.02)
        o2_b1, o2_b2 = o2(0), o2(1.0)
        if f == "o2_sensor":
            o2_b1 = 0.45 + g(0, 0.01)

        # --- VANOS ---
        in_target = 5 + 15 * warm
        in_actual = (5 if f == "vanos" else in_target) + g(0, 0.5)
        ex_target = 8 + 4 * warm
        ex_actual = ex_target + g(0, 0.5)

        values = {
            "rpm": round(rpm, 1),
            "coolant_temp_c": round(coolant, 1),
            "intake_temp_c": round(intake, 1),
            "throttle_pct": round(3.0 + r.uniform(-0.1, 0.1), 2),
            "map_kpa": round(map_kpa, 1),
            "maf_gs": round(maf, 2),
            "stft_pct": round(stft1, 2),
            "stft_b2_pct": round(stft2, 2),
            "ltft_pct": round(ltft1, 2),
            "ltft_b2_pct": round(ltft2, 2),
            "lambda_b1": round(1 + stft1 / 100 + g(0, 0.005), 4),
            "timing_adv_deg": round(timing, 1),
            "o2_b1s1_v": round(o2_b1, 3),
            "o2_b2s1_v": round(o2_b2, 3),
            "closed_loop": closed_loop,
            "icv_pct": round(icv, 1),
            "disa_open": 0,
            "vanos_in_target_deg": round(in_target, 1),
            "vanos_in_actual_deg": round(in_actual, 1),
            "vanos_ex_target_deg": round(ex_target, 1),
            "vanos_ex_actual_deg": round(ex_actual, 1),
            "battery_v": round(13.9 - 0.5 * cold + g(0, 0.02), 2),
        }
        for i in range(6):
            values[f"roughness_cyl{i + 1}"] = round(rough[i], 2)
            values[f"misfire_cyl{i + 1}"] = misfires[i]
        return values
