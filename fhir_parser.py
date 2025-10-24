"""
fhir_parser.py

This module is the Data Processing Framework. It defines functions to
transform raw FHIR JSON bundles into clean, flat pandas DataFrames 
suitable for analysis. It handles:
- Parsing Observation resources (with unit normalization)
- Parsing MedicationAdministration resources (handling infusion rates)
- Extracting patient weight (a critical value for dosing)
"""

import pandas as pd
from typing import List, Dict, Any, Tuple
from fhir.resources.bundle import Bundle
from fhir.resources.observation import Observation
from fhir.resources.medicationadministration import MedicationAdministration
from constants import LOINC_MAP, RXNORM_MAP

# Helper to reverse the LOINC_MAP for quick lookup
LOINC_LOOKUP: Dict[str, str] = {
    code: name for name, codes in LOINC_MAP.items() for code in codes
}

# Helper to reverse the RXNORM_MAP for quick lookup
RXNORM_LOOKUP: Dict[str, str] = {
    code: name for name, code in RXNORM_MAP.items()
}


def parse_observations(bundle: Bundle, patient_id: str) -> Tuple[pd.DataFrame, float]:
    """
    Parses all Observation resources from a FHIR bundle.

    Returns a tuple containing:
    1. A DataFrame of all relevant observations.
    2. The patient's weight in 'kg'.
    """
    observations = []
    patient_weight_kg = None

    for entry in bundle.entry or []:
        if entry.resource and entry.resource.resource_type == "Observation":
            obs = Observation(entry.resource.dict())
            
            # Check if this observation is one we care about
            code = obs.code.coding[0].code if obs.code and obs.code.coding else None
            if not code or code not in LOINC_LOOKUP:
                continue

            obs_name = LOINC_LOOKUP[code]
            value, unit = None, None

            # Get timestamp
            timestamp = obs.effectiveDateTime or obs.effectiveInstant
            if not timestamp:
                continue  # Skip observations without a time

            # Extract value (can be in valueQuantity or component)
            if obs.valueQuantity:
                value = obs.valueQuantity.value
                unit = obs.valueQuantity.unit
            elif obs.component:
                # Handle component observations (like GCS)
                # For this challenge, we assume GCS total is in valueQuantity
                # or a single component. A more complex parser would sum GCS components.
                pass 
            elif obs.valueCodeableConcept:
                # Can be used for GCS score (e.g., 'GCS 15')
                pass 
            
            if obs_name == 'gcs' and obs.valueQuantity:
                 value = obs.valueQuantity.value

            if value is None:
                continue
                
            # --- Unit Normalization ---
            # This is critical for accurate calculations
            try:
                if obs_name == "fio2" and unit == "%":
                    value = value / 100.0  # Convert 21% to 0.21
                elif obs_name == "weight" and unit == "lb":
                    value = value * 0.453592  # Convert lbs to kg
                
                # Store the normalized value
                if obs_name == "weight":
                    # Use the most recent weight
                    patient_weight_kg = value
                else:
                    observations.append({
                        "patient_id": patient_id,
                        "datetime": pd.to_datetime(timestamp),
                        "name": obs_name,
                        "value": float(value)
                    })
            except Exception as e:
                print(f"Warning: Could not parse value for {obs_name}: {e}")

    # Default weight if not found (a reasonable fallback for this challenge)
    if patient_weight_kg is None:
        patient_weight_kg = 70.0  # Assume 70kg adult
        print(f"Warning: No weight found for patient {patient_id}. Defaulting to 70kg.")

    obs_df = pd.DataFrame(observations)
    if not obs_df.empty:
        obs_df = obs_df.sort_values(by="datetime").reset_index(drop=True)
        
    return obs_df, patient_weight_kg


def parse_medications(bundle: Bundle, patient_id: str) -> pd.DataFrame:
    """
    Parses all MedicationAdministration resources from a FHIR bundle.
    Focuses on continuous infusions of vasopressors.
    """
    medications = []
    
    for entry in bundle.entry or []:
        if entry.resource and entry.resource.resource_type == "MedicationAdministration":
            med_admin = MedicationAdministration(entry.resource.dict())
            
            # Check for RxNorm code
            code = None
            if med_admin.medicationCodeableConcept and med_admin.medicationCodeableConcept.coding:
                for c in med_admin.medicationCodeableConcept.coding:
                    if c.system and "rxnorm" in c.system and c.code in RXNORM_LOOKUP:
                        code = c.code
                        break
            
            if not code:
                continue
                
            med_name = RXNORM_LOOKUP[code]
            
            # We only care about infusions with a rate
            if not med_admin.dosage or not med_admin.dosage.rateRatio:
                continue

            # Get infusion start/end times
            start_time = None
            end_time = None
            if med_admin.effectivePeriod:
                start_time = med_admin.effectivePeriod.start
                end_time = med_admin.effectivePeriod.end

            # Skip if no valid period
            if not start_time or not end_time:
                continue

            # Parse infusion rate (e.g., 5 mg / 1 hr)
            try:
                numerator = med_admin.dosage.rateRatio.numerator
                denominator = med_admin.dosage.rateRatio.denominator
                
                dose = float(numerator.value)
                dose_unit = numerator.unit
                
                duration = float(denominator.value)
                duration_unit = denominator.unit

                # --- Rate Normalization (to mg/hr) ---
                rate_mg_hr = None
                
                # 1. Convert dose to mg
                if dose_unit == "mcg":
                    dose_in_mg = dose / 1000.0
                elif dose_unit == "mg":
                    dose_in_mg = dose
                else:
                    continue # Skip units we don't handle
                
                # 2. Convert duration to hours
                if duration_unit == "min":
                    duration_in_hr = duration / 60.0
                elif duration_unit == "h":
                    duration_in_hr = duration
                else:
                    continue # Skip units we don't handle

                rate_mg_hr = dose_in_mg / duration_in_hr
                
                medications.append({
                    "patient_id": patient_id,
                    "start_time": pd.to_datetime(start_time),
                    "end_time": pd.to_datetime(end_time),
                    "name": med_name,
                    "rate_mg_hr": rate_mg_hr
                })

            except Exception as e:
                print(f"Warning: Could not parse rate for {med_name}: {e}")

    med_df = pd.DataFrame(medications)
    if not med_df.empty:
        med_df = med_df.sort_values(by="start_time").reset_index(drop=True)
        
    return med_df
