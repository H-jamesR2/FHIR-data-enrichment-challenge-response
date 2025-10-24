"""
constants.py

Central repository for all medical codes (LOINC, RxNorm) and SOFA scoring
criteria. This isolates the clinical "knowledge" from the execution logic,
making the framework highly maintainable.
"""

from typing import Dict, List, Set

# --- LOINC Code Mappings ---
# We map human-readable names to a *set* of common LOINC codes.
LOINC_MAP: Dict[str, Set[str]] = {
    # Respiratory
    "pao2": {"2703-7", "11556-8"},  # Arterial pO2
    "fio2": {"3150-0", "19993-5"},  # Fraction of inspired O2
    "spo2": {"59408-5", "2708-6"},  # O2 saturation by Pulse oximetry

    # Coagulation
    "platelets": {"26515-7", "777-3"},  # Platelet count

    # Liver
    "bilirubin": {"1975-2", "59828-4"},  # Bilirubin.total

    # Cardiovascular
    "map": {"8478-0", "8479-8"},  # Mean arterial pressure

    # CNS
    "gcs": {"9269-2", "35088-4"},  # Glasgow Coma Scale total score

    # Renal
    "creatinine": {"2160-0", "38483-4"},  # Creatinine
    "urine_output": {"3167-4", "9192-6"},  # 24-hour Urine output

    # Other
    "weight": {"29463-7", "3141-9"}  # Patient body weight
}

# --- RxNorm Code Mappings ---
# We map vasopressor names to their RxNorm Ingredient Code (IN)
RXNORM_MAP: Dict[str, str] = {
    "dopamine": "3628",
    "dobutamine": "3616",
    "epinephrine": "3992",
    "norepinephrine": "7512",
}

# --- SOFA Scoring Criteria (Sepsis-3 / Table T1) ---

# Note: These are implemented as functions in sofa_calculator.py
# This is a reference for the logic:

# Respiratory (PaO2/FiO2 ratio)
# 0: >= 400
# 1: < 400
# 2: < 300
# 3: < 200 (with respiratory support)
# 4: < 100 (with respiratory support)

# SpO2/FiO2 Substitution (From Prompt)
# 0: > 302
# 1: <= 302
# 2: < 221
# 3: < 142 (with respiratory support)
# 4: < 67 (with respiratory support)

# Coagulation (Platelets x10^3/uL)
# 0: >= 150
# 1: < 150
# 2: < 100
# 3: < 50
# 4: < 20

# Liver (Bilirubin mg/dL)
# 0: < 1.2
# 1: 1.2 - 1.9
# 2: 2.0 - 5.9
# 3: 6.0 - 11.9
# 4: >= 12.0

# Cardiovascular (MAP or Vasopressors in mcg/kg/min)
# 0: MAP >= 70
# 1: MAP < 70
# 2: Dopamine <= 5 OR Dobutamine (any dose)
# 3: Dopamine 5.1-15 OR Epi/Norepi <= 0.1
# 4: Dopamine > 15 OR Epi/Norepi > 0.1

# CNS (Glasgow Coma Scale)
# 0: 15
# 1: 13-14
# 2: 10-12
# 3: 6-9
# 4: < 6

# Renal (Creatinine mg/dL or Urine Output mL/day)
# 0: < 1.2
# 1: 1.2 - 1.9
# 2: 2.0 - 3.4
# 3: 3.5 - 4.9 OR Urine < 500 mL/day
# 4: >= 5.0 OR Urine < 200 mL/day