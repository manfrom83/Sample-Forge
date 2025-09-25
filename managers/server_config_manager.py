import json
import os
from typing import Dict, Any, List, Tuple, Optional
from .path_manager import app_paths
from utils.config_utils import (
    validate_filename, prepare_json_filepath, load_json_schema,
    save_json_config, load_json_config, get_config_files,
    save_last_used_config, load_last_used_config
)
from utils.logger import logger
from utils.config_utils import detect_config_kind


class ServerConfig:
    
    BOOLEAN_FLAGS = {
        "--flash-attn", "--no-webui", "--metrics", "--slots", "--props", "--embedding", 
        "--reranking", "--cont-batching", "--mlock", "--no-mmap", 
        "--no-kv-offload", "--no-mmproj", "--no-mmproj-offload", "--lora-init-without-apply",
        "--log-disable", "--verbose",
        "--log-colors", "--log-timestamps", "--log-prefix", "--verbose-prompt",
        "--no-context-shift", "--special", "--no-warmup", "--spm-infill",
        "--no-prefill-assistant", "--tts-use-guide-tokens", "--jinja",
        "--list-devices", "--check-tensors",
        # NOTE: --cpu-strict, --cpu-strict-batch, --poll-batch removed - they need explicit 0/1 values
        "--no-perf", "--escape", "--no-escape", "--no-cont-batching", "--no-slots"
    }

    def __init__(self, executable_path: str = None):
        self.schema_file = app_paths.llama_server_cli_flags
        self.executable_path = executable_path
        self.save_dir = app_paths.server_configs
        os.makedirs(self.save_dir, exist_ok=True)
        self.last_config_file = os.path.join(self.save_dir, ".last_config")
        self.schema = self.load_schema()
        self.values = {}
        self.enabled = {}
        self.initialize_blank_config()
    
    def load_schema(self) -> Dict[str, Dict[str, Any]]:
        return load_json_schema(self.schema_file, "server CLI schema")
    
    def auto_load_last_config(self) -> bool:
        try:
            if os.path.exists(self.last_config_file):
                with open(self.last_config_file, 'r') as f:
                    last_config_name = f.read().strip()
                
                if last_config_name and self.load_config(last_config_name):
                    logger.info(f"Auto-loaded server config: {last_config_name}")
                    return True
        except Exception as e:
            logger.warning(f"Could not auto-load server config: {e}")
            self.initialize_blank_config()
            return False
        
        return False
    
    def initialize_blank_config(self):
        self.values = {}
        self.enabled = {}
        
        for category, params in self.schema.items():
            for param_name, param_def in params.items():
                self.enabled[param_name] = False
                
    
    def get_parameter_info(self, param_name: str) -> Optional[Dict[str, Any]]:
        for category, params in self.schema.items():
            if param_name in params:
                param_def = params[param_name].copy()
                param_def['category'] = category  
                return param_def
        return None
    
    def get_enabled_parameters(self) -> Dict[str, Any]:
        return {param: value for param, value in self.values.items() 
                if self.enabled.get(param, False) and value is not None}
    
    def set_parameter(self, param_name: str, value: Any, enabled: bool = True):
        self.values[param_name] = value
        self.enabled[param_name] = enabled
    
    def generate_server_command(self) -> List[str]:
        if not self.executable_path:
            raise ValueError("Executable path not configured. Please set the path to the llama-server binary in the server configuration.")
            
        command = [self.executable_path]
        
        for param_name, enabled in self.enabled.items():
            if not enabled:
                continue
                
            if param_name in self.BOOLEAN_FLAGS:
                command.append(param_name)
            else:
                value = self.values.get(param_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                command.extend([param_name, str(value)])
                
        return command
    
    def get_server_url(self) -> str:
        host = self.values.get('--host')
        port = self.values.get('--port')
        if not host:
            raise ValueError(f"Server host not configured. Please set --host in server configuration.")
        if not port:
            raise ValueError(f"Server port not configured. Please set --port in server configuration.")
        
        try:
            port_num = int(port)
        except (ValueError, TypeError):
            raise ValueError(f"Server port must be numeric. Current value: '{port}'")
            
        logger.info(f"Using server configuration: {host}:{port}")
        return f"http://{host}:{port}"
    
    def get_connection_timeouts(self) -> dict:
        server_timeout = self.values.get('--timeout')
        if server_timeout is None:
            raise ValueError(f"Server timeout not configured. Please set --timeout in server configuration.")
            
        try:
            server_timeout = int(server_timeout)
        except (ValueError, TypeError):
            raise ValueError(f"Server timeout must be numeric. Current value: '{server_timeout}'")
        
        connection_timeout = int(server_timeout * 0.1)
        request_timeout = int(server_timeout * 0.8)

        # Sanity caps to avoid effectively infinite waits from extreme --timeout values
        # These caps keep the UI responsive while still generous for long generations.
        capped_connection = max(1, min(connection_timeout, 15))
        # Allow long generations; cap request timeout at 600s (10 minutes)
        capped_request = max(5, min(request_timeout, 600))
        if capped_connection != connection_timeout or capped_request != request_timeout:
            logger.warning(
                f"Clamping timeouts from (conn={connection_timeout}s, req={request_timeout}s) "
                f"to (conn={capped_connection}s, req={capped_request}s) for stability."
            )
            connection_timeout = capped_connection
            request_timeout = capped_request
        
        logger.info(f"Using server timeout configuration: {server_timeout}s (conn: {connection_timeout}s, req: {request_timeout}s)")
        return {
            'connection_timeout': connection_timeout,
            'request_timeout': request_timeout
        }
    
    def save_config(self, filename: str) -> bool:
        try:
            filename = validate_filename(filename, "server configuration")
            
            config_data = {
                "values": self.values,
                "enabled": self.enabled,
                "executable_path": self.executable_path,
                "command_line": self.generate_server_command() if self.executable_path else []
            }
            
            filepath = prepare_json_filepath(self.save_dir, filename)
            success = save_json_config(filepath, config_data, "server configuration")
            
            if success:
                save_last_used_config(self.last_config_file, filename)
            
            return success
        except Exception as e:
            logger.error(f"Error saving server config: {e}")
            return False
    
    def load_config(self, filename: str) -> bool:
        try:
            filename = validate_filename(filename, "server configuration")
            filepath = prepare_json_filepath(self.save_dir, filename)
            
            success, config_data = load_json_config(filepath, "server configuration")
            if not success:
                return False
            # Validate content kind
            kind = detect_config_kind(config_data)
            if kind != 'server':
                logger.error(f"Invalid configuration type for server config: {filename}")
                return False
            
            self.values = config_data.get("values", {})
            self.enabled = config_data.get("enabled", {})
            self.executable_path = config_data.get("executable_path", None)
            
            # Validate loaded configuration against current schema
            self._validate_loaded_config()
            
            # Save as last used config
            save_last_used_config(self.last_config_file, filename)
            
            return True
        except Exception as e:
            logger.error(f"Error loading server config: {e}")
            return False
    
    def _validate_loaded_config(self):
        # Remove parameters that no longer exist in schema
        valid_params = set()
        for category, params in self.schema.items():
            valid_params.update(params.keys())
        
        invalid_params = set(self.values.keys()) - valid_params
        for param in invalid_params:
            del self.values[param]
            if param in self.enabled:
                del self.enabled[param]
        
        for param in valid_params:
            if param not in self.values:
                self.values[param] = None
                self.enabled[param] = False
    
    def get_available_configs(self) -> List[str]:
        return get_config_files(self.save_dir)
    
    def reset_to_defaults(self):
        self.initialize_blank_config()
    
    def reset_parameter_to_default(self, param_name: str) -> bool:
        if param_name in self.values:
            del self.values[param_name]
        self.enabled[param_name] = False
        return True
    
    def get_enabled_count(self) -> int:
        return sum(1 for enabled in self.enabled.values() if enabled)
    
    def get_total_count(self) -> int:
        return len(self.enabled)
