import json
import os
from typing import Dict, Any, List, Tuple, Optional
from .path_manager import app_paths
from utils.config_utils import (
    validate_filename, prepare_json_filepath, load_json_schema, 
    save_json_config, load_json_config, get_config_files,
    save_last_used_config, load_last_used_config
)
from utils.config_utils import detect_config_kind
from utils.logger import logger


class ParameterConfig:
    
    def __init__(self):
        self.schema_file = app_paths.openai_api_schema
        self.schema = self.load_schema()
        self.values = {}
        self.enabled = {}
        self.array_values = {}  # NEW: Store array values for ACO feature
        self.initialize_blank_config()
        
        self.save_dir = app_paths.saved_configs
    
    def load_schema(self) -> Dict[str, Dict[str, Any]]:
        try:
            schema = load_json_schema(self.schema_file, "API parameter schema")
            # Sanitize tooltip and text fields to remove stray Unicode artifacts
            def _clean_text(val):
                try:
                    if isinstance(val, str):
                        cleaned = val.replace("\uFFFD", "").replace("\ufffd", "")
                        cleaned = cleaned.replace("�?�", "-")
                        cleaned = cleaned.replace("�?\"", " - ")
                        return cleaned
                except Exception:
                    pass
                return val
            try:
                for _category, params in schema.items():
                    if isinstance(params, dict):
                        for _pname, pdef in params.items():
                            if isinstance(pdef, dict):
                                if 'tooltip' in pdef:
                                    pdef['tooltip'] = _clean_text(pdef.get('tooltip'))
                                if 'description' in pdef:
                                    pdef['description'] = _clean_text(pdef.get('description'))
            except Exception:
                pass  # Non-fatal; UI will also sanitize at render time
            return schema
        except Exception as e:
            error_msg = f"CRITICAL ERROR: Failed to load parameter schema from {self.schema_file}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def initialize_blank_config(self):
        self.values = {}
        self.enabled = {}
        self.array_values = {}  # Reset array values too
        
        for category, params in self.schema.items():
            for param_name, param_def in params.items():
                self.enabled[param_name] = False
    
    def get_parameter_info(self, param_name: str) -> Dict[str, Any]:
        for category, params in self.schema.items():
            if param_name in params:
                info = params[param_name].copy()
                info['category'] = category
                return info
        return {}
    
    def get_all_parameters(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        result = []
        for category, params in self.schema.items():
            for param_name, param_def in params.items():
                result.append((category, param_name, param_def))
        return result
    
    def set_parameter(self, param_name: str, value: Any, enabled: Optional[bool] = None):
        self.values[param_name] = value
        if enabled is not None:
            self.enabled[param_name] = enabled
    
    def get_api_payload(self, include_messages: bool = True) -> Dict[str, Any]:
        payload = {}
        
        if include_messages:
            payload["messages"] = [{"role": "user", "content": ""}]
        
        # Handle samplers sequence specially - check both enabled state and value
        # Fixed: Now respects enabled/disabled toggle like other parameters
        if self.enabled.get('samplers', False):
            samplers_value = self.values.get('samplers', '')
            if samplers_value and samplers_value.strip():
                # Convert comma-separated string to array
                samplers_array = [s.strip() for s in samplers_value.split(',') if s.strip()]
                if samplers_array:
                    payload['samplers'] = samplers_array
        
        for param_name in self.enabled:
            if self.enabled.get(param_name, False):
                # Skip samplers as we handled it above
                if param_name == 'samplers':
                    continue
                    
                param_info = self.get_parameter_info(param_name)
                param_type = param_info.get("type", "string")
                
                if param_type == "bool":
                    payload[param_name] = self.values.get(param_name, True)
                elif param_type == "object":
                    # Handle JSON object parameters (like chat_template_kwargs)
                    value = self.values.get(param_name)
                    if value is not None and value.strip():
                        try:
                            # Parse JSON string to object
                            import json
                            parsed_object = json.loads(value)
                            payload[param_name] = parsed_object
                        except json.JSONDecodeError as e:
                            # Keep as string if JSON parsing fails (transparency principle)
                            logger.warning(f"Failed to parse JSON for {param_name}: {e}")
                            payload[param_name] = value
                else:
                    value = self.values.get(param_name)
                    if value is not None:
                        payload[param_name] = value
                
        return payload
    
    def save_config(self, filename: str, system_prompt: str = "", user_input: str = "") -> bool:
        try:
            filename = validate_filename(filename, "API configuration")
            
            config_data = {
                "values": self.values,
                "enabled": self.enabled,
                "array_values": self.array_values,
                "system_prompt": system_prompt,
                "user_input": user_input,
                "api_payload": self.get_api_payload()
            }
            
            filepath = prepare_json_filepath(self.save_dir, filename)
            return save_json_config(filepath, config_data, "API configuration")
            
        except Exception as e:
            logger.error(f"Error saving API configuration: {e}")
            return False
    
    def load_config(self, filename: str) -> Tuple[bool, str, str]:
        try:
            filename = validate_filename(filename, "API configuration")
            filepath = prepare_json_filepath(self.save_dir, filename)
            
            success, config_data = load_json_config(filepath, "API configuration")
            if not success:
                return False, "", ""
            # Validate content kind
            kind = detect_config_kind(config_data)
            if kind != 'api':
                try:
                    from tkinter import messagebox
                    messagebox.showerror("Invalid File", f"Selected file is not an API Parameters configuration: {filename}")
                except Exception:
                    pass
                return False, "", ""
            
            # Load values and enabled states
            if 'values' in config_data:
                self.values.update(config_data['values'])
            if 'enabled' in config_data:
                self.enabled.update(config_data['enabled'])
            if 'array_values' in config_data:
                self.array_values.update(config_data['array_values'])
                
            system_prompt = config_data.get('system_prompt', '')
            user_input = config_data.get('user_input', '')
            return True, system_prompt, user_input
            
        except Exception as e:
            logger.error(f"Error loading API configuration: {e}")
            return False, "", ""
    
    def load_last_config(self) -> Optional[str]:
        last_config_file = os.path.join(self.save_dir, ".last_config")
        config_name = load_last_used_config(last_config_file)
        return config_name if config_name else None
    
    def save_last_config(self, config_name: str):
        last_config_file = os.path.join(self.save_dir, ".last_config")
        save_last_used_config(last_config_file, config_name)

    def get_save_files(self) -> List[str]:
        return get_config_files(self.save_dir)
    
    def get_enabled_count(self) -> int:
        return sum(1 for enabled in self.enabled.values() if enabled)
    
    def reset_to_defaults(self):
        self.initialize_blank_config()
    
    def reset_parameter_to_default(self, param_name: str) -> bool:
        if param_name in self.values:
            del self.values[param_name]
        self.enabled[param_name] = False
        return True
    
