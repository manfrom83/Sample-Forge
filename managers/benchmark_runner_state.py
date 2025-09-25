"""
Benchmark Runner UI State Manager
Handles persistence of user interface state between app sessions
"""

import copy
import json
import os
from typing import Dict, Any, Optional
from .path_manager import app_paths


class BenchmarkRunnerState:
    """Manager for benchmark runner UI state persistence"""
    
    DEFAULT_STATE = {
        "system_prompt_override": {
            "enabled": False,
            "text": ""
        },
        "prompt_formatting": {
            "system_prefix": "",
            "system_suffix": "",
            "user_prefix": "",
            "user_suffix": ""
        },
        "last_directories": {
            "dataset": "",
            "server_config": "",
            "api_config": ""
        },
        "last_selections": {
            "dataset_path": "",
            "server_config_path": "",
            "api_config_path": "",
            "questions": ""
        }
    }
    
    def __init__(self):
        self.state_file = app_paths.benchmark_runner_state / "ui_state.json"
        
        # Use deep copy to avoid reference issues with nested dictionaries
        self.state = copy.deepcopy(self.DEFAULT_STATE)
        
        # Ensure the directory exists
        os.makedirs(str(app_paths.benchmark_runner_state), exist_ok=True)
        
        # Load existing state if available
        self.load_state()
    
    def load_state(self) -> bool:
        """Load UI state from file, return True if successful"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    loaded_state = json.load(f)
                    
                # Merge loaded state with defaults (in case new fields were added)
                self._merge_state(loaded_state)
                return True
        except Exception as e:
            logger.warning(f"Could not load benchmark runner UI state: {e}")
            self.state = self.DEFAULT_STATE.copy()
        
        return False
    
    def save_state(self) -> bool:
        """Save current UI state to file, return True if successful"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning(f"Could not save benchmark runner UI state: {e}")
            return False
    
    def _merge_state(self, loaded_state: Dict[str, Any]):
        """Merge loaded state with defaults to handle schema evolution"""
        # Deep merge: preserve loaded values but add missing defaults
        for key, default_value in self.DEFAULT_STATE.items():
            if key in loaded_state:
                if isinstance(default_value, dict):
                    # Merge nested dictionaries
                    merged_dict = default_value.copy()
                    merged_dict.update(loaded_state[key])
                    self.state[key] = merged_dict
                else:
                    self.state[key] = loaded_state[key]
            else:
                self.state[key] = default_value
    
    # System Prompt Override
    def get_system_prompt_override_enabled(self) -> bool:
        return self.state["system_prompt_override"]["enabled"]
    
    def set_system_prompt_override_enabled(self, enabled: bool):
        self.state["system_prompt_override"]["enabled"] = enabled
        self.save_state()
    
    def get_system_prompt_override_text(self) -> str:
        return self.state["system_prompt_override"]["text"]
    
    def set_system_prompt_override_text(self, text: str):
        self.state["system_prompt_override"]["text"] = text
        self.save_state()
    
    # Prompt Formatting
    def get_system_prefix(self) -> str:
        return self.state["prompt_formatting"]["system_prefix"]
    
    def set_system_prefix(self, prefix: str):
        self.state["prompt_formatting"]["system_prefix"] = prefix
        self.save_state()
    
    def get_system_suffix(self) -> str:
        return self.state["prompt_formatting"]["system_suffix"]
    
    def set_system_suffix(self, suffix: str):
        self.state["prompt_formatting"]["system_suffix"] = suffix
        self.save_state()
    
    def get_user_prefix(self) -> str:
        return self.state["prompt_formatting"]["user_prefix"]
    
    def set_user_prefix(self, prefix: str):
        self.state["prompt_formatting"]["user_prefix"] = prefix
        self.save_state()
    
    def get_user_suffix(self) -> str:
        return self.state["prompt_formatting"]["user_suffix"]
    
    def set_user_suffix(self, suffix: str):
        self.state["prompt_formatting"]["user_suffix"] = suffix
        self.save_state()
    
    # Last Directories
    def get_last_dataset_dir(self) -> str:
        return self.state["last_directories"]["dataset"]
    
    def set_last_dataset_dir(self, directory: str):
        self.state["last_directories"]["dataset"] = directory
        self.save_state()
    
    def get_last_server_config_dir(self) -> str:
        return self.state["last_directories"]["server_config"]
    
    def set_last_server_config_dir(self, directory: str):
        self.state["last_directories"]["server_config"] = directory
        self.save_state()
    
    def get_last_api_config_dir(self) -> str:
        return self.state["last_directories"]["api_config"]
    
    def set_last_api_config_dir(self, directory: str):
        self.state["last_directories"]["api_config"] = directory
        self.save_state()
    
    # Last Selections
    def get_last_dataset_path(self) -> str:
        return self.state["last_selections"]["dataset_path"]
    
    def set_last_dataset_path(self, path: str):
        self.state["last_selections"]["dataset_path"] = path
        self.save_state()
    
    def get_last_server_config_path(self) -> str:
        return self.state["last_selections"]["server_config_path"]
    
    def set_last_server_config_path(self, path: str):
        self.state["last_selections"]["server_config_path"] = path
        self.save_state()
    
    def get_last_api_config_path(self) -> str:
        return self.state["last_selections"]["api_config_path"]
    
    def set_last_api_config_path(self, path: str):
        self.state["last_selections"]["api_config_path"] = path
        self.save_state()
    
    def get_last_questions(self) -> str:
        return self.state["last_selections"]["questions"]
    
    def set_last_questions(self, questions: str):
        self.state["last_selections"]["questions"] = questions
        self.save_state()
    
    # Utility methods
    def reset_to_defaults(self):
        """Reset all state to defaults"""
        self.state = copy.deepcopy(self.DEFAULT_STATE)
        self.save_state()
    
    def get_all_state(self) -> Dict[str, Any]:
        """Get complete state dictionary (for debugging)"""
        return self.state.copy()