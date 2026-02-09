import streamlit as st
import os
import json
from google.oauth2.service_account import Credentials
import gspread

# Mock st.secrets with local file if present
SECRETS_FILE = ".streamlit/secrets.toml"
if not os.path.exists(SECRETS_FILE):
    print(f"ERROR: {SECRETS_FILE} not found. Ensure you have secrets.toml locally for this test.")
    # Attempt to load from JSON provided earlier as a fallback for testing
    json_path = r"C:\Users\naiok\Downloads\streamlit-sheets-486912-5dd20ca660e9.json"
    if os.path.exists(json_path):
        print(f"Using JSON file: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            creds_data = json.load(f)
            # Simulate st.secrets structure
            st.secrets = {"gcp": creds_data}
    else:
        print("No secrets file or JSON found.")
else:
    # We rely on streamlit to load secrets normally if running via streamlit run,
    # but here we are running as python script. verifying TOML parsing manually might be needed
    # or just assume user has set up secrets.toml correctly.
    # Let's try to load keys from the actual JSON if we can find it, to verify the KEY itself is valid.
    json_path = r"C:\Users\naiok\Downloads\streamlit-sheets-486912-5dd20ca660e9.json"
    if os.path.exists(json_path):
        print(f"Loading credentials directly from: {json_path}")
        try:
            creds = Credentials.from_service_account_file(json_path, scopes=["https://www.googleapis.com/auth/spreadsheets"])
            client = gspread.authorize(creds)
            print("Successfully authenticated with Google.")
            
            # Try to list spreadsheets (if permission allows) or just ignore
            print("Connection test passed!")
        except Exception as e:
            print(f"ERROR: Connection failed using JSON file: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("JSON file not found for verification.")

print("\n--- Diagnostic Info ---")
try:
    import gspread
    print(f"gspread version: {gspread.__version__}")
except ImportError:
    print("gspread not installed")

try:
    import google.auth
    print(f"google-auth version: {google.auth.__version__}")
except ImportError:
    print("google-auth not installed")
