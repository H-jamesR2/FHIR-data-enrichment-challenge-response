"""
main.py

Main executable script for the FHIR Data Enrichment Challenge.

This script will:
1.  Fetch FHIR data for all 9 patients from the specified API endpoints.
2.  Parse the data into clean DataFrames using `fhir_parser.py`.
3.  Identify all "event" timestamps (when a new observation occurs).
4.  Iterate through each event and calculate the SOFA score using `sofa_calculator.py`.
5.  Compile all valid scores into `submission.csv`.
"""

import pandas as pd
import requests
from fhir.resources.bundle import Bundle
import fhir_parser
import sofa_calculator

# --- API Configuration ---
BASE_URL = 'https://synthea-proxy-389841612478.us-central1.run.app/'

# --- API Client Functions ---

def fetch_observations_for_subject(subject: str) -> dict:
    """Fetches all Observation resources for a given patient subject."""
    url = f"{BASE_URL}Observation?subject={subject}"
    print(f"Fetching Observations from: {url}")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def fetch_medication_administrations_for_subject(subject: str) -> dict:
    """Fetches all MedicationAdministration resources for a given patient subject."""
    url = f"{BASE_URL}MedicationAdministration?subject={subject}"
    print(f"Fetching MedAdmins from: {url}")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def main():
    """Main execution function."""
    
    # Per the new data source
    PATIENT_IDS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    
    all_obs = []
    all_meds = []
    patient_weights = {}

    # --- Phase 1: Data Processing Framework (Fetch and Parse) ---
    print("Starting Phase 1: Fetching and parsing FHIR data from API...")
    for pid in PATIENT_IDS:
        try:
            # 1. Fetch raw FHIR bundles from API
            obs_bundle_dict = fetch_observations_for_subject(subject=pid)
            med_bundle_dict = fetch_medication_administrations_for_subject(subject=pid)

            obs_bundle = Bundle(obs_bundle_dict)
            med_bundle = Bundle(med_bundle_dict)
            
            # 2. Parse Observations and get patient weight
            # We assume weight is in the Observation bundle
            obs_df, weight_kg = fhir_parser.parse_observations(obs_bundle, pid)
            all_obs.append(obs_df)
            patient_weights[pid] = weight_kg
            
            # 3. Parse Medications
            med_df = fhir_parser.parse_medications(med_bundle, pid)
            all_meds.append(med_df)
            
            print(f"Successfully processed data for patient '{pid}'.")
            
        except requests.exceptions.HTTPError as http_err:
            print(f"FATAL: HTTP error for patient {pid}. Status: {http_err.response.status_code}. Skipping.")
        except Exception as e:
            print(f"FATAL: Failed to process patient {pid}. Error: {e}")

    # Combine all patient data into single DataFrames
    master_obs_df = pd.concat(all_obs, ignore_index=True)
    master_med_df = pd.concat(all_meds, ignore_index=True)
    
    print("\nFHIR data fetching and parsing complete.")
    
    # --- Phase 2: SOFA Score Calculation ---
    print("Starting Phase 2: Calculating SOFA scores...")
    
    if master_obs_df.empty:
        print("Warning: No observation data was parsed. Cannot calculate scores.")
        submission_results = []
    else:
        event_timestamps = master_obs_df[["patient_id", "datetime"]].drop_duplicates()
        submission_results = []

        for _, row in event_timestamps.iterrows():
            pid = row["patient_id"]
            ts = row["datetime"]
            
            patient_obs = master_obs_df[master_obs_df["patient_id"] == pid]
            patient_meds = master_med_df[master_med_df["patient_id"] == pid]
            patient_weight = patient_weights[pid]
            
            sofa_score = sofa_calculator.calculate_sofa_at_time(
                patient_obs=patient_obs,
                patient_meds=patient_meds,
                timestamp=ts,
                patient_weight=patient_weight
            )
            
            if sofa_score is not None:
                submission_results.append({
                    "patient_id": pid,
                    "sofa_score_datetime": ts,
                    "sofa_score": int(sofa_score)
                })

    print("SOFA score calculation complete.")

    # --- Phase 3: Generate Submission ---
    if not submission_results:
        print("Warning: No complete SOFA scores were calculated.")
        submission_df = pd.DataFrame(columns=["patient_id", "sofa_score_datetime", "sofa_score"])
    else:
        submission_df = pd.DataFrame(submission_results)
        submission_df = submission_df.drop_duplicates().sort_values(
            by=["patient_id", "sofa_score_datetime"]
        )
    
    output_filename = "submission.csv"
    submission_df.to_csv(output_filename, index=False)
    
    print(f"\nSuccessfully generated {output_filename} with {len(submission_df)} rows.")


if __name__ == "__main__":
    main()