import json
import os
from config import OWNER_ID

DEFAULT_SETTINGS = {
    "prefix": "/",
    "allowed_users": [OWNER_ID],  # Default to owner ID
    "status_message": "Serving Shiraken12T",
    "embed_color": "0x3498db"
}

class Settings:
    def __init__(self):
        self.filename = "settings.json"
        self.settings = DEFAULT_SETTINGS.copy()  # Start with defaults
        self.save_settings()  # Create settings file if it doesn't exist
        self.load_settings()

    def load_settings(self):
        try:
            with open(self.filename, 'r') as f:
                loaded_settings = json.load(f)
                # Update defaults with loaded settings
                self.settings.update(loaded_settings)
        except (FileNotFoundError, json.JSONDecodeError):
            # If file doesn't exist or is invalid, use defaults
            self.settings = DEFAULT_SETTINGS.copy()
            self.save_settings()

    def save_settings(self):
        with open(self.filename, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings() 