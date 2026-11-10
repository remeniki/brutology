"""Slovník veličín a pojmov: čo ktorá skratka znamená, jednotka a prečo je dôležitá.

Názvy veličín sú rovnaké pre všetky zdroje dát (simulátor, OBD-II, DS2).
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Signal:
    title: str      # krátky slovenský názov
    unit: str
    text: str       # vysvetlenie pre začiatočníka


SIGNALS: dict[str, Signal] = {
    "rpm": Signal("Otáčky motora", "ot/min",
                  "Koľkokrát sa kľukový hriadeľ otočí za minútu. Na voľnobehu by mali byť "
                  "stabilné – kolísanie je to, čo cítiš ako trasenie. Studený motor má "
                  "voľnobeh vyšší (~1000-1200), teplý ~700-800."),
    "coolant_temp_c": Signal("Teplota chladiva", "°C",
                             "Teplota motora. Podľa nej ECU rozhoduje, koľko paliva pridať pri "
                             "studenom štarte. Ak snímač klame, motor dostane zlú zmes."),
    "intake_temp_c": Signal("Teplota nasávaného vzduchu", "°C",
                            "Teplota vzduchu v sání. Po noci státia má byť podobná teplote chladiva."),
    "throttle_pct": Signal("Poloha škrtiacej klapky", "%",
                           "Ako veľmi je otvorená klapka, ktorá púšťa vzduch do motora "
                           "(0 % = zavretá). Na voľnobehu má byť takmer zavretá a pokojná."),
    "map_kpa": Signal("Tlak v sacom potrubí (MAP)", "kPa",
                      "Podtlak v sání. Na voľnobehu je nízky a stabilný; kolísanie znamená "
                      "nerovnomerné spaľovanie. MS43 tento snímač pravdepodobne nemá."),
    "maf_gs": Signal("Množstvo vzduchu (MAF)", "g/s",
                     "Koľko vzduchu prúdi do motora, meria to merač hmotnosti vzduchu. Vzduch, "
                     "ktorý ide dierou (falošný vzduch), MAF nevidí."),
    "load_pct": Signal("Zaťaženie motora", "%", "Ako veľmi je motor zaťažený (vypočíta ECU)."),
    "stft_pct": Signal("Krátkodobý fuel trim – banka 1", "%",
                       "Okamžitá korekcia paliva pre valce 1-3. Plus = ECU pridáva palivo "
                       "(zmes bola chudobná), mínus = uberá. Normálne okolo 0, kolíše ±5 %."),
    "stft_b2_pct": Signal("Krátkodobý fuel trim – banka 2", "%",
                          "To isté pre valce 4-6. Ak sa banky výrazne líšia, problém je len na "
                          "jednej strane motora."),
    "ltft_pct": Signal("Dlhodobý fuel trim – banka 1", "%",
                       "Korekcia paliva, ktorú si ECU „zapamätala“ (valce 1-3). Trvalo vysoké "
                       "kladné číslo = dlhodobo chudobná zmes, často falošný vzduch."),
    "ltft_b2_pct": Signal("Dlhodobý fuel trim – banka 2", "%", "To isté pre valce 4-6."),
    "lambda_b1": Signal("Lambda – banka 1", "",
                        "Pomer vzduchu a paliva. 1,00 = ideálna zmes, nad 1 chudobná, pod 1 bohatá."),
    "timing_adv_deg": Signal("Predstih zapaľovania", "°",
                             "O koľko stupňov pred hornou úvraťou preskočí iskra. ECU ním jemne "
                             "dolaďuje voľnobeh; veľké kolísanie = ECU bojuje s nestabilnými otáčkami."),
    "o2_b1s1_v": Signal("Lambda sonda pred katalyzátorom – banka 1", "V",
                        "Meria kyslík vo výfuku. Zdravá zahriata sonda skáče 0,1-0,9 V niekoľkokrát "
                        "za sekundu. Ak stojí na mieste, je lenivá alebo mŕtva."),
    "o2_b2s1_v": Signal("Lambda sonda pred katalyzátorom – banka 2", "V", "To isté pre valce 4-6."),
    "o2_b1s2_v": Signal("Lambda sonda za katalyzátorom – banka 1", "V",
                        "Kontroluje katalyzátor; má byť pokojnejšia ako sonda pred ním."),
    "o2_b2s2_v": Signal("Lambda sonda za katalyzátorom – banka 2", "V", "To isté pre banku 2."),
    "closed_loop": Signal("Regulácia podľa lambda sondy", "0/1",
                          "1 = ECU dolaďuje zmes podľa lambda sondy (uzavretá slučka). Po studenom "
                          "štarte je chvíľu 0, kým sa sonda nezahreje – typicky do 1-2 minút."),
    "run_time_s": Signal("Čas od naštartovania", "s", "Ako dlho motor beží (hlási ECU)."),
    "battery_v": Signal("Napätie palubnej siete", "V",
                        "Pri bežiacom motore má alternátor nabíjať ~13,5-14,5 V. Nízke napätie "
                        "oslabuje iskru."),
    "icv_pct": Signal("Otvorenie nastavovača voľnobehu (ICV)", "%",
                      "ICV je ventil, ktorý púšťa vzduch popri zavretej klapke a tak drží "
                      "voľnobeh. Veľmi privretý = vzduch ide inou cestou (netesnosť); veľmi "
                      "otvorený = zanesený; kolíše = zasekáva sa. Len cez DS2."),
    "disa_open": Signal("DISA klapka otvorená", "0/1",
                        "DISA mení dĺžku sacieho potrubia podľa otáčok (viac sily v nízkych aj "
                        "vysokých otáčkach). Zlomená klapka spôsobuje trasenie, ale v dátach "
                        "ju nevidno – treba ju skontrolovať rukou. Len cez DS2."),
    "vanos_in_target_deg": Signal("VANOS sania – požadovaná poloha", "°",
                                  "Kam chce ECU natočiť vačkový hriadeľ sania. Len cez DS2."),
    "vanos_in_actual_deg": Signal("VANOS sania – skutočná poloha", "°",
                                  "Kde vačkový hriadeľ naozaj je. Ak sa líši od požadovanej, "
                                  "VANOS nefunguje dobre. Len cez DS2."),
    "vanos_ex_target_deg": Signal("VANOS výfuku – požadovaná poloha", "°",
                                  "To isté pre vačkový hriadeľ výfuku. Len cez DS2."),
    "vanos_ex_actual_deg": Signal("VANOS výfuku – skutočná poloha", "°", "Len cez DS2."),
}

CYLINDER_SIGNALS = {
    "roughness_cyl": ("Nerovnomernosť chodu – valec {n}", "",
                      "ECU meria, ako rovnomerne sa kľukový hriadeľ otáča pri zážihu každého "
                      "valca. Vyššie číslo = valec horí horšie, ešte pred tým, ako úplne "
                      "vypadne. Len cez DS2."),
    "misfire_cyl": ("Výpadky zapaľovania – valec {n}", "počet",
                    "Koľkokrát v danom okamihu valec nezapálil. Ak vypadáva stále ten istý valec, "
                    "podozrivá je jeho cievka, sviečka alebo vstrekovač. Len cez DS2."),
}

# Všeobecné pojmy a skratky
GLOSSARY: dict[str, str] = {
    "ECU / DME": "Riadiaca jednotka motora („mozog“). Na Brutusovi Siemens MS43.",
    "OBD-II": "Štandardný „jazyk“ diagnostiky, ktorý musí vedieť každé auto. Dá len "
              "emisné dáta (otáčky, teploty, trimy, lambda).",
    "DS2": "Vlastný „jazyk“ BMW. Dá aj ICV, VANOS, DISA a údaje po valcoch. Treba naň "
           "kábel K+DCAN.",
    "ELM327": "Lacný kábel/čip, ktorý prekladá OBD-II. Vie len OBD-II, nie DS2.",
    "K+DCAN": "Kábel na BMW diagnostiku (aj DS2); na E46 v režime K-line.",
    "Banka 1 / banka 2": "Motor M54 má 6 valcov v rade, rozdelených na dve polovice: "
                         "banka 1 = valce 1-3 (vpredu), banka 2 = valce 4-6 (vzadu). Každá má "
                         "vlastnú lambda sondu.",
    "Fuel trim (STFT / LTFT)": "Korekcia paliva v %. STFT (short term) = okamžitá, LTFT (long "
                               "term) = zapamätaná. Plus = ECU pridáva palivo.",
    "Chudobná / bohatá zmes": "Chudobná = priveľa vzduchu na dané palivo, bohatá = priveľa paliva.",
    "Falošný vzduch": "Vzduch, ktorý sa do motora dostane netesnosťou za MAF, takže ho ECU "
                      "nezapočíta. Zmes je chudobná, motor sa trasie – v zime horšie.",
    "MAF / HFM": "Merač hmotnosti vzduchu (Mass Air Flow, po nemecky HFM).",
    "MAP": "Snímač tlaku v sacom potrubí (Manifold Absolute Pressure).",
    "ICV": "Nastavovač voľnobehu (Idle Control Valve).",
    "CCV": "Odvetranie kľukovej skrine (Crankcase Ventilation). Na M54 častá príčina "
           "falošného vzduchu, najmä v zime.",
    "DISA": "Klapka v sacom potrubí, ktorá mení jeho dĺžku podľa otáčok.",
    "VANOS": "Systém BMW na natáčanie vačkových hriadeľov (variabilné časovanie ventilov).",
    "EDK": "Elektronická škrtiaca klapka (ovláda ju ECU, nie lanko).",
    "Lambda sonda (O2)": "Snímač kyslíka vo výfuku, podľa neho ECU dolaďuje zmes.",
    "Closed loop / open loop": "Uzavretá slučka = ECU reguluje podľa lambda sondy; otvorená = "
                               "ide podľa tabuliek (po studenom štarte, pri plnom plyne).",
    "Výpadok zapaľovania (misfire)": "Valec pri zážihu nezapáli – motor „kopne“ a trasie sa.",
    "Chybový kód (DTC)": "Kód poruchy uložený v ECU, napr. P0171 = chudobná zmes banka 1.",
}


def describe(name: str) -> Signal:
    """Popis veličiny podľa názvu; neznámej vráti aspoň jej názov."""
    if name in SIGNALS:
        return SIGNALS[name]
    m = re.fullmatch(r"(roughness_cyl|misfire_cyl)(\d+)", name)
    if m:
        title, unit, text = CYLINDER_SIGNALS[m.group(1)]
        return Signal(title.format(n=m.group(2)), unit, text)
    return Signal(name, "", "")


def label(name: str) -> str:
    """Názov do grafu, napr. 'Otáčky motora [ot/min]'."""
    s = describe(name)
    return f"{s.title} [{s.unit}]" if s.unit else s.title
