"""
User and machine configuration settings helper.
"""

import json
import uuid
from app_paths import CONFIG_PATH

def get_full_config():
    """
    Load the full configuration dictionary from the config file.
    """
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_full_config(config_dict):
    """
    Save the full configuration dictionary to the config file.
    """
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_dict, f)

def get_machine_id():
    """
    Get or generate a unique machine ID for global metrics syncing.
    """
    cfg = get_full_config()
    if "machine_id" not in cfg:
        cfg["machine_id"] = str(uuid.uuid4())
        save_full_config(cfg)
    return cfg["machine_id"]

def save_config(annotator_name):
    """
    Persist the annotator's name to a hidden JSON config file.
    
    This is called automatically whenever the annotator name field changes
    (on every keystroke and focus-out), so the name is remembered for
    the next session without needing to click Save.
    
    Args:
        annotator_name: The annotator's name string to save.
    """
    cfg = get_full_config()
    cfg["annotator"] = annotator_name
    save_full_config(cfg)

def load_config():
    """
    Load the previously saved annotator name from the config file.
    
    Called once at startup to pre-fill the annotator name field.
    
    Returns:
        str: The saved annotator name, or empty string if no config exists.
    """
    return get_full_config().get("annotator", "")

def sanitize_name(name):
    """
    Convert an annotator name into a filesystem-safe string.
    
    Replaces any non-alphanumeric character with an underscore.
    Used when building image filenames to avoid spaces or special chars.
    
    Args:
        name: Raw annotator name string.
    
    Returns:
        str: Sanitized name safe for use in filenames.
    """
    return "".join(c if c.isalnum() else "_" for c in name.strip())
