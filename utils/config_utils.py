"""
Shared configuration utilities to eliminate duplicate validation logic
"""
import json
import os
from typing import Dict, Any, Tuple, List, Optional
from .logger import logger


def validate_filename(filename: str, context: str = "configuration") -> str:
    """Validate and clean filename input
    
    Args:
        filename: Raw filename input
        context: Description for error messages
        
    Returns:
        Cleaned filename
        
    Raises:
        ValueError: If filename is empty or invalid
    """
    if not filename or not filename.strip():
        raise ValueError(f"Filename cannot be empty for {context}")
    
    return filename.strip()


def prepare_json_filepath(save_dir: str, filename: str, auto_add_extension: bool = True) -> str:
    """Prepare filepath for JSON config files
    
    Args:
        save_dir: Directory to save in
        filename: Base filename (validated)
        auto_add_extension: Whether to add .json if missing
        
    Returns:
        Full filepath
    """
    filepath = os.path.join(save_dir, filename)
    
    if auto_add_extension and not filename.endswith('.json'):
        filepath += '.json'
        
    return filepath


def load_json_schema(schema_file: str, schema_name: str = "schema") -> Dict[str, Any]:
    """Load and validate JSON schema file with proper error handling
    
    Args:
        schema_file: Path to schema file
        schema_name: Name for error messages
        
    Returns:
        Loaded schema data
        
    Raises:
        FileNotFoundError: If schema file doesn't exist
        ValueError: If schema is empty or invalid JSON
        RuntimeError: For other errors
    """
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema = json.load(f)
            
        if not schema:
            raise ValueError(f"Schema file {schema_file} is empty")
            
        return schema
        
    except FileNotFoundError:
        raise FileNotFoundError(f"Schema file not found: {schema_file}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {schema_name} file {schema_file}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load {schema_name} from {schema_file}: {e}")


def save_json_config(filepath: str, config_data: Dict[str, Any], context: str = "configuration") -> bool:
    """Save configuration data as JSON with proper error handling
    
    Args:
        filepath: Full path where to save
        config_data: Data to save
        context: Description for error messages
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Configuration saved to: {filepath}")
        return True
        
    except Exception as e:
        logger.warn(f"Error saving {context}: {e}")
        return False


def load_json_config(filepath: str, context: str = "configuration") -> Tuple[bool, Dict[str, Any]]:
    """Load JSON configuration with proper error handling
    
    Args:
        filepath: Path to config file
        context: Description for error messages
        
    Returns:
        Tuple of (success, config_data)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        logger.info(f"Configuration loaded from: {filepath}")
        return True, config_data
        
    except Exception as e:
        logger.warn(f"Error loading {context}: {e}")
        return False, {}


def detect_config_kind(config_data: Dict[str, Any]) -> str:
    """Heuristically detect whether a JSON config is an API parameter config or a server config.

    Returns:
        'api' | 'server' | 'unknown'

    Heuristics:
    - Server config typically contains 'executable_path' and CLI flags under 'values' starting with '--'.
    - API config typically contains 'array_values' and/or 'api_payload' and may include fields like
      'system_prompt' / 'user_input'.
    - If ambiguous, count occurrence of server-like keys ('--host','--port','--timeout') vs API-like keys
      ('temperature','top_k','top_p','min_p','repeat_penalty','seed').
    """
    if not isinstance(config_data, dict):
        return 'unknown'

    # Strong signals
    if 'executable_path' in config_data:
        return 'server'
    if 'api_payload' in config_data or 'array_values' in config_data:
        return 'api'

    values = config_data.get('values')
    if not isinstance(values, dict):
        return 'unknown'

    # Check for server-style flags vs api-style params
    server_hits = 0
    api_hits = 0

    # Server indicators
    for k in ('--host', '--port', '--timeout', '--threads', '--model'):
        if k in values:
            server_hits += 1
    # Any leading '--' key is server-ish
    server_hits += sum(1 for k in values.keys() if isinstance(k, str) and k.startswith('--'))

    # API indicators
    for k in ('temperature', 'top_k', 'top_p', 'min_p', 'repeat_penalty', 'seed', 'stream', 'typical_p'):
        if k in values:
            api_hits += 1

    if server_hits > api_hits and server_hits >= 1:
        return 'server'
    if api_hits > server_hits and api_hits >= 1:
        return 'api'

    # Weak signals: presence of system/user prompt fields
    if 'system_prompt' in config_data or 'user_input' in config_data:
        return 'api'

    return 'unknown'


def get_config_files(save_dir: str, extension: str = '.json') -> List[str]:
    """Get list of configuration files in directory
    
    Args:
        save_dir: Directory to scan
        extension: File extension to look for
        
    Returns:
        List of filenames (without extension for .json files)
    """
    try:
        if extension == '.json':
            # Remove .json extension for backwards compatibility
            files = [f[:-5] for f in os.listdir(save_dir) 
                    if f.endswith('.json') and not f.startswith('.')]
        else:
            files = [f for f in os.listdir(save_dir) if f.endswith(extension)]
        
        return sorted(files)
        
    except Exception as e:
        logger.warn(f"Could not list config files in {save_dir}: {e}")
        return []


def save_last_used_config(last_config_file: str, config_name: str) -> None:
    """Save the name of the last used configuration
    
    Args:
        last_config_file: Path to last config tracking file
        config_name: Name of config to remember
    """
    try:
        with open(last_config_file, 'w') as f:
            f.write(config_name)
    except Exception as e:
        logger.warn(f"Could not save last config name: {e}")


def load_last_used_config(last_config_file: str) -> str:
    """Load the name of the last used configuration
    
    Args:
        last_config_file: Path to last config tracking file
        
    Returns:
        Config name or empty string if not found
    """
    try:
        if os.path.exists(last_config_file):
            with open(last_config_file, 'r') as f:
                config_name = f.read().strip()
                if config_name:
                    return config_name
    except Exception as e:
        logger.warn(f"Could not load last config name: {e}")
    
    return ""


def load_parameter_config_from_file(filepath: str) -> Tuple[bool, Optional[object], str, str]:
    """Load ParameterConfig object from file with full validation
    
    Args:
        filepath: Path to config file (with or without .json extension)
        
    Returns:
        Tuple of (success, config_object, system_prompt, user_input)
        
    Raises:
        ImportError: If ParameterConfig cannot be imported
    """
    try:
        # Import ParameterConfig dynamically to avoid circular imports
        from managers.api_config_manager import ParameterConfig
        
        # Validate filename and prepare
        filename = validate_filename(filepath, "API configuration")
        
        # If filepath is absolute or contains subdirectories, load directly from file
        if os.path.isabs(filepath) or os.path.dirname(filepath):
            # Load directly from the provided path
            success, config_data = load_json_config(filepath, "API configuration")
            if not success:
                return False, None, "", ""

            # Create ParameterConfig and manually populate it
            temp_config = ParameterConfig()

            # Validate content kind
            kind = detect_config_kind(config_data)
            if kind != 'api':
                logger.error(f"Invalid configuration type for API parameters: {filepath}")
                return False, None, "", ""

            # Load values and enabled states
            if 'values' in config_data:
                temp_config.values = config_data['values']
            if 'enabled' in config_data:
                temp_config.enabled = config_data['enabled']
            if 'array_values' in config_data:
                temp_config.array_values = config_data['array_values']

            # Extract prompts
            # Prefer top-level fields saved by ParameterConfig.save_config for consistency
            # Fallback to nested values if older files did not include top-level keys
            system_prompt = (
                config_data.get('system_prompt')
                if isinstance(config_data, dict) and config_data.get('system_prompt') is not None
                else ""
            )
            user_input = (
                config_data.get('user_input')
                if isinstance(config_data, dict) and config_data.get('user_input') is not None
                else ""
            )
            # Backward-compatible fallback to nested location inside values
            if not system_prompt:
                try:
                    system_prompt = temp_config.values.get('system_prompt', '')
                except Exception:
                    system_prompt = ""
            if not user_input:
                try:
                    user_input = temp_config.values.get('user_input', '')
                except Exception:
                    user_input = ""

            return True, temp_config, system_prompt, user_input
        else:
            # Use the standard load_config method for simple filenames
            config_name = os.path.splitext(os.path.basename(filename))[0]
            temp_config = ParameterConfig()
            success, system_prompt, user_input = temp_config.load_config(config_name)
            
            if success:
                return True, temp_config, system_prompt, user_input
            else:
                return False, None, "", ""
            
    except Exception as e:
        logger.warn(f"Error loading ParameterConfig from {filepath}: {e}")
        return False, None, "", ""
