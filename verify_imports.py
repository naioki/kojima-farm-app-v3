import sys
import os

print("Verifying imports...")
try:
    from email_config_manager import load_email_config, save_email_config, detect_imap_server, load_sender_rules, save_sender_rules
    print("SUCCESS: email_config_manager imports are working.")
except ImportError as e:
    print(f"ERROR: Failed to import from email_config_manager: {e}")
except Exception as e:
    print(f"ERROR: Unexpected error during import: {e}")

try:
    import app
    print("SUCCESS: app.py imports are likely working (though app execution is not tested).")
except ImportError as e:
    # app.py runs streamlit code at top level which might fail without streamlit context, 
    # but we are checking for ImportErrors specifically.
    print(f"WARNING: Error importing app.py (might be normal if streamlit is missing in this env): {e}")
except Exception as e:
    print(f"WARNING: Error importing app.py: {e}")

print("Done.")
