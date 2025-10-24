"""
sofa_calculator.py

The SOFA Calculation Engine.
Contains one function for each of the 6 organ systems, plus a main
orchestrator function `calculate_sofa_at_time`.

All component functions return a score (0-4) or None if data is missing.
"""

import pandas as pd
from typing import Optional, Dict

# --- Helper Function: Get Most Recent Valid Measurement ---

def get_recent_value(df: pd.DataFrame, 
                     timestamp: pd.Timestamp, 
                     name: str,
                     lookback_hours: int = 6) -> Optional[float]:
    """
    Finds the most recent value for a given measurement within the
    6-hour validity window.
    """
    window_start = timestamp - pd.Timedelta(hours=lookback_hours)
    
    # Filter for the specific measurement and time window
    subset = df[
        (df["name"] == name) &
        (df["datetime"] >= window_start) &
        (df["datetime"] <= timestamp)
    ]
    
    if subset.empty:
        return None
    
    # Return the value of the most recent measurement
    return subset.iloc[-1]["value"]


# --- 1. Respiratory Score ---

def calculate_respiratory_score(obs_df: pd.DataFrame, 
                                timestamp: pd.Timestamp) -> Optional[int]:
    """
    Calculates the Respiratory SOFA score.
    Uses PaO2/FiO2 ratio, or substitutes SpO2/FiO2 ratio if PaO2 is unavailable.
    """
    pao2 = get_recent_value(obs_df, timestamp, "pao2")
    fio2 = get_recent_value(obs_df, timestamp, "fio2")
    spo2 = get_recent_value(obs_df, timestamp, "spo2")
    
    # Rule: Default FiO2 to 21% (room air) if not specified
    if fio2 is None:
        fio2 = 0.21
        
    # Rule: "Respiratory support" is defined as any FiO2 > 21%
    # (A more complex rule would also check for ventilation Observations)
    is_supported = (fio2 > 0.21)
    
    # --- Primary Logic: PaO2/FiO2 ---
    if pao2:
        ratio = pao2 / fio2
        if ratio < 100 and is_supported: return 4
        if ratio < 200 and is_supported: return 3
        if ratio < 300: return 2
        if ratio < 400: return 1
        return 0
        
    # --- Substitution Logic: SpO2/FiO2 ---
    if spo2:
        # Prevent division by zero if FiO2 is somehow 0
        if fio2 == 0: return None 
        
        # Ensure SpO2 is a percentage (e.g., 95, not 0.95)
        if spo2 <= 1.0: 
            spo2 = spo2 * 100.0
            
        ratio = spo2 / fio2
        
        # Using cutoffs *from the prompt*
        if ratio < 67 and is_supported: return 4
        if ratio < 142 and is_supported: return 3
        if ratio < 221: return 2
        if ratio <= 302: return 1 # Prompt: <302 is 1, >302 is 0
        return 0

    # If neither PaO2 nor SpO2 is available, score cannot be calculated
    return None

# --- 2. Coagulation Score ---

def calculate_coagulation_score(obs_df: pd.DataFrame, 
                                timestamp: pd.Timestamp) -> Optional[int]:
    """Calculates the Coagulation SOFA score based on Platelet count."""
    platelets = get_recent_value(obs_df, timestamp, "platelets")
    
    if platelets is None: return None
    
    if platelets < 20: return 4
    if platelets < 50: return 3
    if platelets < 100: return 2
    if platelets < 150: return 1
    return 0

# --- 3. Liver Score ---

def calculate_liver_score(obs_df: pd.DataFrame, 
                          timestamp: pd.Timestamp) -> Optional[int]:
    """Calculates the Liver SOFA score based on Bilirubin level."""
    bilirubin = get_recent_value(obs_df, timestamp, "bilirubin")
    
    if bilirubin is None: return None
    
    if bilirubin >= 12.0: return 4
    if bilirubin >= 6.0: return 3
    if bilirubin >= 2.0: return 2
    if bilirubin >= 1.2: return 1
    return 0

# --- 4. Cardiovascular Score ---

def calculate_cardiovascular_score(obs_df: pd.DataFrame, 
                                   med_df: pd.DataFrame, 
                                   timestamp: pd.Timestamp,
                                   patient_weight_kg: float) -> Optional[int]:
    """
    Calculates the Cardiovascular SOFA score based on MAP or
    active vasopressor infusions.
    """
    map_val = get_recent_value(obs_df, timestamp, "map")
    
    # Check for *active* vasopressor infusions at the given timestamp
    active_meds = med_df[
        (med_df["start_time"] <= timestamp) &
        (med_df["end_time"] >= timestamp)
    ]
    
    pressor_doses_mcg_kg_min = {"dopamine": 0, "dobutamine": 0, "epinephrine": 0, "norepinephrine": 0}
    
    if not active_meds.empty:
        for _, row in active_meds.iterrows():
            med_name = row["name"]
            
            # Convert rate from mg/hr to mcg/kg/min
            # (rate_mg_hr * 1000 mcg/mg) / (60 min/hr) / (weight_kg)
            rate_mcg_kg_min = (row["rate_mg_hr"] * 1000) / 60 / patient_weight_kg
            
            # Keep the *highest* dose if multiple are running (e.g., two Epi drips)
            pressor_doses_mcg_kg_min[med_name] = max(
                pressor_doses_mcg_kg_min[med_name],
                rate_mcg_kg_min
            )

    # Apply Sepsis-3 Cardiovascular Logic (worst score wins)
    dopa = pressor_doses_mcg_kg_min["dopamine"]
    dobu = pressor_doses_mcg_kg_min["dobutamine"]
    epi = pressor_doses_mcg_kg_min["epinephrine"]
    norepi = pressor_doses_mcg_kg_min["norepinephrine"]

    if dopa > 15 or epi > 0.1 or norepi > 0.1: return 4
    if dopa > 5 or epi <= 0.1 or norepi <= 0.1: return 3
    if dopa <= 5 or dobu > 0: return 2
    
    # If no pressors are running, score is based on MAP
    if map_val is None:
        # If no pressors AND no MAP, score is unknown
        return None
        
    if map_val < 70: return 1
    return 0

# --- 5. CNS Score ---

def calculate_cns_score(obs_df: pd.DataFrame, 
                        timestamp: pd.Timestamp) -> Optional[int]:
    """Calculates the CNS SOFA score based on Glasgow Coma Scale (GCS)."""
    gcs = get_recent_value(obs_df, timestamp, "gcs")
    
    if gcs is None: return None
    
    if gcs < 6: return 4
    if gcs <= 9: return 3
    if gcs <= 12: return 2
    if gcs <= 14: return 1
    return 0
    
# --- 6. Renal Score ---

def calculate_renal_score(obs_df: pd.DataFrame, 
                          timestamp: pd.Timestamp) -> Optional[int]:
    """
    Calculates the Renal SOFA score based on Creatinine OR Urine Output.
    The worst (highest) score of the two is used.
    """
    creatinine = get_recent_value(obs_df, timestamp, "creatinine")
    urine = get_recent_value(obs_df, timestamp, "urine_output")
    
    creatinine_score = -1 # Use -1 to distinguish from score 0
    if creatinine is not None:
        if creatinine >= 5.0: creatinine_score = 4
        elif creatinine >= 3.5: creatinine_score = 3
        elif creatinine >= 2.0: creatinine_score = 2
        elif creatinine >= 1.2: creatinine_score = 1
        else: creatinine_score = 0
        
    urine_score = -1
    if urine is not None:
        # Note: We assume the 'urine_output' LOINC code represents a 24-hr value
        if urine < 200: urine_score = 4
        elif urine < 500: urine_score = 3
        else:
            # If urine output is >= 500, it doesn't contribute a score of 3 or 4.
            # We set it to 0 so it doesn't wrongly override a creatinine score.
            urine_score = 0 
            
    # If both are missing, score is unknown
    if creatinine_score == -1 and urine_score == -1:
        return None
        
    # Return the worst (max) of the two scores
    return max(creatinine_score, urine_score)


# --- Main SOFA Score Orchestrator ---

def calculate_sofa_at_time(
    patient_obs: pd.DataFrame,
    patient_meds: pd.DataFrame,
    timestamp: pd.Timestamp,
    patient_weight: float
) -> Optional[int]:
    """
    Calculates the total SOFA score for a patient at a specific time.
    
    Returns the total score, or None if *any* component score is missing
    (per the "Data Completeness" rule).
    """
    
    scores = {
        "respiratory": calculate_respiratory_score(patient_obs, timestamp),
        "coagulation": calculate_coagulation_score(patient_obs, timestamp),
        "liver": calculate_liver_score(patient_obs, timestamp),
        "cardiovascular": calculate_cardiovascular_score(
            patient_obs, patient_meds, timestamp, patient_weight
        ),
        "cns": calculate_cns_score(patient_obs, timestamp),
        "renal": calculate_renal_score(patient_obs, timestamp)
    }
    
    # Rule: Data Completeness
    if any(score is None for score in scores.values()):
        return None
        
    return sum(scores.values())
