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

def fetch_observations_for_subject(subject, start_date=None, end_date=None) -> list:
    """Fetches all Observation resources for a given patient subject."""
    url = f"{BASE_URL}Observation?subject={subject}"
    if start_date: url += f"&date=ge{start_date}"
    if end_date: url += f"&date=le{end_date}"
    print(f"Fetching Observations from: {url}")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def fetch_medication_administrations_for_subject(subject, start_date=None, end_date=None) -> list:
    """Fetches all MedicationAdministration resources for a given patient subject."""
    url = f"{BASE_URL}MedicationAdministration?subject={subject}"
    if start_date: url += f"&effective-time=ge{start_date}"
    if end_date: url += f"&effective-time=le{end_date}"
    print(f"Fetching MedAdmins from: {url}")
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

# JSON File Saving Function ---

def save_json_output(data: dict | list, filename: str):
    """Saves the provided data as a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Successfully saved raw data to {filename}")
    except Exception as e:
        print(f"Error saving data to {filename}: {e}")



def main():
    """Main execution function."""
    
    PATIENT_IDS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i']
    
    all_obs = []
    all_meds = []
    patient_weights = {}

    # --- Phase 1: Data Processing Framework (Fetch and Parse) ---
    print("Starting Phase 1: Fetching and parsing FHIR data from API...")
    for pid in PATIENT_IDS:
        try:
            # 1. Fetch raw FHIR resource lists from API
            obs_list = fetch_observations_for_subject(subject=pid)
            med_list = fetch_medication_administrations_for_subject(subject=pid)
            
            # FIX: The API returns a list of resources (JSON array) instead of 
            # a Bundle object (JSON dictionary). We manually create the Bundle 
            # structure needed for Pydantic validation.
            obs_bundle_dict = {
                "resourceType": "Bundle",
                "entry": [{"resource": res} for res in obs_list]
            }
            med_bundle_dict = {
                "resourceType": "Bundle",
                "entry": [{"resource": res} for res in med_list]
            }

            # 2. Validate and parse the new Bundle dictionary structures
            obs_bundle = Bundle.model_validate(obs_bundle_dict)
            med_bundle = Bundle.model_validate(med_bundle_dict)
            
            # 3. Parse Observations and get patient weight
            obs_df, weight_kg = fhir_parser.parse_observations(obs_bundle, pid)
            all_obs.append(obs_df)
            patient_weights[pid] = weight_kg
            
            # 4. Parse Medications
            med_df = fhir_parser.parse_medications(med_bundle, pid)
            all_meds.append(med_df)
            
            print(f"Successfully processed data for patient '{pid}'.")
            
        except requests.exceptions.HTTPError as http_err:
            print(f"FATAL: HTTP error for patient {pid}. Status: {http_err.response.status_code}. Skipping.")
        except Exception as e:
            print(f"FATAL: Failed to process patient {pid}. Error: {e}")

    # Combine all patient data into single DataFrames
    if not all_obs:
        print("Error: No observation data was successfully parsed. Exiting.")
        master_obs_df = pd.DataFrame(columns=["patient_id", "datetime", "name", "value"])
    else:
        master_obs_df = pd.concat(all_obs, ignore_index=True)
    
    if not all_meds:
         master_med_df = pd.DataFrame(columns=["patient_id", "start_time", "end_time", "name", "rate_mg_hr"])
    else:
        master_med_df = pd.concat(all_meds, ignore_index=True)
    
    print("\nFHIR data fetching and parsing complete.")
    
    # --- Phase 2: SOFA Score Calculation ---
    print("Starting Phase 2: Calculating SOFA scores...")
    
    if master_obs_df.empty:
        print("Warning: No observation data was parsed. Cannot calculate scores.")
        submission_results = []
    else:
        # Find all unique times an observation occurred across all patients
        event_timestamps = master_obs_df[["patient_id", "datetime"]].drop_duplicates()
        submission_results = []

        for _, row in event_timestamps.iterrows():
            pid = row["patient_id"]
            ts = row["datetime"]
            
            patient_obs = master_obs_df[master_obs_df["patient_id"] == pid]
            patient_meds = master_med_df[master_med_df["patient_id"] == pid]
            # Use patient_weights[pid] for the weight in the calculation (defaulting to 70kg if missing)
            patient_weight = patient_weights.get(pid, 70.0) 
            
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
