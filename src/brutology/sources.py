"""Zdroje dat. Každý zdroj vráti slovník {názov_veličiny: hodnota}.

SimulatedCar napodobňuje studený štart E46 330i. Neskôr pribudne
ObdSource (OBD-II) a Ds2Source (BMW DS2) so zhodným rozhraním,
takže zvyšok appky sa nemusí meniť.
"""
import math
import random


class DataSource:
    """Spoločné rozhranie pre všetky zdroje dát."""

    def read(self, t: float) -> dict:
        """Vráti hodnoty v čase t (sekundy od začiatku nahrávania)."""
        raise NotImplementedError


class SimulatedCar(DataSource):
    """Simulácia studeného štartu. fault=True pridá "trasenie" (výpadky
    zapaľovania na valci 3), aby sme mali na čom skúšať analýzu."""

    def __init__(self, fault: bool = True, seed: int = 42):
        self.fault = fault
        self.rng = random.Random(seed)

    def read(self, t: float) -> dict:
        r = self.rng
        warm = 1 - math.exp(-t / 90)               # 0 = studený, 1 = zahriaty
        coolant = 10 + 80 * warm + r.uniform(-0.3, 0.3)
        target_idle = 1100 - 300 * warm            # studený motor drží vyššie otáčky
        shaking = self.fault and t < 60
        rpm = target_idle + r.gauss(0, 60 if shaking else 8)
        misfires = 0
        if shaking and r.random() < 0.25:
            misfires = 1
        fuel_trim = (8 if shaking else 1) * (1 - warm) + r.gauss(0, 0.5)
        return {
            "rpm": round(rpm, 1),
            "coolant_temp_c": round(coolant, 1),
            "intake_temp_c": round(12 + 10 * warm + r.uniform(-0.2, 0.2), 1),
            "throttle_pct": round(3.0 + r.uniform(-0.1, 0.1), 2),
            "map_kpa": round(34 + r.gauss(0, 3 if shaking else 0.5), 1),
            "stft_pct": round(fuel_trim, 2),
            "lambda_b1": round(1 + fuel_trim / 100 + r.gauss(0, 0.005), 4),
            "misfire_cyl3": misfires,
            "battery_v": round(13.9 - 0.5 * (1 - warm) + r.gauss(0, 0.02), 2),
        }
