import json
import os
from pathlib import Path
from typing import Dict, Any

# Simple local storage for AI training context
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_FILE = DATA_DIR / "ai_training_config.json"

def _ensure_data_dir():
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_training_config() -> Dict[str, Any]:
    """Retrieve the AI training configuration."""
    if not CONFIG_FILE.exists():
        return {
            "business_description": "A B2B SaaS platform for AI-powered lead generation and outreach.",
            "icp": "Sales teams at mid-sized B2B companies.",
            "tone": "professional"
        }
    
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_training_config(config: Dict[str, Any]) -> bool:
    """Save the AI training configuration."""
    _ensure_data_dir()
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Failed to save AI training config: {e}")
        return False
