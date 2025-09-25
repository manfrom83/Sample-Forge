"""
Global Application Settings Manager
Handles settings that affect multiple tabs/components
"""

import json
import os
from typing import Optional
from .path_manager import app_paths
from utils.logger import logger


class GlobalSettings:
    """Manager for global application settings"""
    
    def __init__(self):
        self.settings_file = app_paths.data / "global_settings.json"
        self.default_settings = {
            "endpoint_type": "chat_completions",  # "chat_completions" or "completions"
            "suppress_popups": True,  # Auto-approve confirmations; avoid modal popups in UI flows
            "theme": "Sunset 70s"
        }
        self.settings = self.default_settings.copy()
        self.load_settings()
    
    def load_settings(self) -> bool:
        """Load settings from file, return True if successful"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    # Merge with defaults in case new settings were added
                    self.settings.update(loaded_settings)
                return True
        except Exception as e:
            logger.warning(f"Could not load global settings: {e}")
            self.settings = self.default_settings.copy()
        return False
    
    def save_settings(self) -> bool:
        """Save current settings to file, return True if successful"""
        try:
            # Ensure directory exists
            os.makedirs(str(self.settings_file.parent), exist_ok=True)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning(f"Could not save global settings: {e}")
            return False
    
    def get_endpoint_type(self) -> str:
        """Get current endpoint type"""
        return self.settings.get("endpoint_type", "chat_completions")
    
    def set_endpoint_type(self, endpoint_type: str):
        """Set endpoint type and save"""
        if endpoint_type in ["chat_completions", "completions"]:
            self.settings["endpoint_type"] = endpoint_type
            self.save_settings()

    def get_theme(self) -> str:
        """Return currently selected UI theme"""
        return self.settings.get("theme", "Modern Light")

    def set_theme(self, theme_name: str):
        """Persist selected UI theme"""
        self.settings["theme"] = theme_name
        self.save_settings()

    def get_suppress_popups(self) -> bool:
        """Return whether UI should suppress modal popups and auto-approve confirmations"""
        return bool(self.settings.get("suppress_popups", True))

    def set_suppress_popups(self, value: bool):
        """Set popup suppression and save"""
        self.settings["suppress_popups"] = bool(value)
        self.save_settings()


# Global instance
global_settings = GlobalSettings()


