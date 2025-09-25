"""
UI Configuration Constants
Centralized configuration for all UI dimensions, timeouts, and styling
"""

import platform
from typing import Dict, Any, List


class UIConfig:
    """Centralized UI configuration to eliminate hardcoded magic numbers"""

    # Window Configuration
    WINDOW_GEOMETRY = "1400x900"
    WINDOW_START_MAXIMIZED = True

    # Component Heights (in text lines)
    SYSTEM_PROMPT_HEIGHT = 4   # System prompt text area height
    LLM_INPUT_HEIGHT = 3       # LLM input text area height
    JSON_PREVIEW_HEIGHT = 12   # JSON preview text area height
    LLM_OUTPUT_HEIGHT = 8      # LLM output text area height
    SLOTS_DISPLAY_HEIGHT = 11  # Slots display text area height
    AUTO_LOG_HEIGHT = 20       # Auto Mode activity log height

    # Tooltip Configuration
    TOOLTIP_AUTO_HIDE_MS = 5000
    TOOLTIP_DELAY_MS = 500

    # Theme palettes -----------------------------------------------------
    DEFAULT_COLORS: Dict[str, str] = {
        'tooltip_bg': "#FFFFE0",
        'window_bg': "#EEF2F8",
        'surface_bg': "#FFFFFF",
        'surface_alt_bg': "#F3F4F6",
        'surface_hover': "#E6EBF2",
        'surface_active': "#D9E2F5",
        'border': "#D0D5DD",
        'accent': "#2563EB",
        'accent_hover': "#1D4ED8",
        'accent_active': "#1E40AF",
        'text_primary': "#101828",
        'text_secondary': "#475467",
        'muted_text': "#667085",
        'priority_critical': "#F97066",
        'priority_important': "#FACC15",
        'priority_optional': "#FFFFFF",
        'toggle_on': "#16A34A",
        'toggle_off': "#DC2626",
        'boolean_true': "#1D4ED8",
        'boolean_false': "#6B7280",
        'critical_on': "#DC2626",
        'critical_off': "#16A34A",
        'caution_on': "#FACC15",
        'caution_off': "#6B7280",
        'safe_on': "#16A34A",
        'safe_off': "#6B7280",
        'default_value': "#16A34A",
        'modified_value': "#FACC15",
        'gray_text': "#667085",
        'blue_text': "#2563EB",
        'green_text': "#16A34A",
        'red_text': "#DC2626"
    }

    THEME_PRESETS: Dict[str, Dict[str, str]] = {
        "Modern Light": DEFAULT_COLORS.copy(),
        "Midnight Dusk": {
            **DEFAULT_COLORS,
            'window_bg': "#0B1120",
            'surface_bg': "#111827",
            'surface_alt_bg': "#1E293B",
            'surface_hover': "#27334F",
            'surface_active': "#334155",
            'border': "#1F2A3D",
            'accent': "#6366F1",
            'accent_hover': "#4F46E5",
            'accent_active': "#4338CA",
            'text_primary': "#E2E8F0",
            'text_secondary': "#94A3B8",
            'muted_text': "#94A3B8",
            'boolean_true': "#38BDF8",
            'boolean_false': "#64748B",
            'gray_text': "#94A3B8",
            'blue_text': "#60A5FA",
            'green_text': "#34D399",
            'red_text': "#F87171"
        },
        "Sunset 70s": {
            **DEFAULT_COLORS,
            'window_bg': "#FFF1E0",
            'surface_bg': "#FBE7D0",
            'surface_alt_bg': "#F6D0AA",
            'surface_hover': "#F0BF8A",
            'surface_active': "#E89F63",
            'border': "#D28B5D",
            'accent': "#C2410C",
            'accent_hover': "#9A3412",
            'accent_active': "#7C2D12",
            'text_primary': "#4B1D10",
            'text_secondary': "#7C3E1D",
            'muted_text': "#A35F2B",
            'toggle_on': "#EA580C",
            'boolean_true': "#C26A1B",
            'boolean_false': "#8C5A3C",
            'gray_text': "#7C4A2D",
            'blue_text': "#B45309",
            'green_text': "#2F855A",
            'red_text': "#C53030"
        },
        "Forest Dawn": {
            **DEFAULT_COLORS,
            'window_bg': "#F1F8F3",
            'surface_bg': "#FFFFFF",
            'surface_alt_bg': "#E6F2E6",
            'surface_hover': "#D9EAD9",
            'surface_active': "#C4DAC4",
            'border': "#A3C9A8",
            'accent': "#2F855A",
            'accent_hover': "#276749",
            'accent_active': "#22543D",
            'text_primary': "#1F3C2D",
            'text_secondary': "#3F604D",
            'muted_text': "#61826C",
            'toggle_on': "#2F855A",
            'boolean_true': "#2F855A",
            'boolean_false': "#5F6F64",
            'gray_text': "#5F6F64",
            'blue_text': "#2C7A7B",
            'green_text': "#2F855A",
            'red_text': "#C53030"
        },
        "Ocean Breeze": {
            **DEFAULT_COLORS,
            'window_bg': "#E0F2F7",
            'surface_bg': "#FFFFFF",
            'surface_alt_bg': "#D9EDF3",
            'surface_hover': "#C4E3EC",
            'surface_active': "#ACD7E3",
            'border': "#8FC3D4",
            'accent': "#0EA5E9",
            'accent_hover': "#0284C7",
            'accent_active': "#0369A1",
            'text_primary': "#0F172A",
            'text_secondary': "#1E3A5F",
            'muted_text': "#3F5C7A",
            'boolean_true': "#0284C7",
            'boolean_false': "#64748B",
            'gray_text': "#486581",
            'blue_text': "#0284C7",
            'green_text': "#0D9488",
            'red_text': "#E11D48"
        },
        "Mono Noir": {
            **DEFAULT_COLORS,
            'window_bg': "#1A1A1A",
            'surface_bg': "#202020",
            'surface_alt_bg': "#2A2A2A",
            'surface_hover': "#2F2F2F",
            'surface_active': "#383838",
            'border': "#3F3F3F",
            'accent': "#F97316",
            'accent_hover': "#EA580C",
            'accent_active': "#C2410C",
            'text_primary': "#F5F5F5",
            'text_secondary': "#D4D4D4",
            'muted_text': "#A3A3A3",
            'toggle_on': "#22C55E",
            'boolean_true': "#F97316",
            'boolean_false': "#737373",
            'gray_text': "#B3B3B3",
            'blue_text': "#60A5FA",
            'green_text': "#4ADE80",
            'red_text': "#F87171"
        },
    }

    COLORS: Dict[str, str] = THEME_PRESETS["Sunset 70s"].copy()
    CURRENT_THEME: str = "Sunset 70s"

    @classmethod
    def get_available_themes(cls) -> List[str]:
        return list(cls.THEME_PRESETS.keys())

    @classmethod
    def set_theme(cls, theme_name: str) -> bool:
        palette = cls.THEME_PRESETS.get(theme_name)
        if not palette:
            return False
        cls.COLORS = palette.copy()
        cls.CURRENT_THEME = theme_name
        return True

    @classmethod
    def get_current_theme(cls) -> str:
        return cls.CURRENT_THEME

    # Mouse Wheel Configuration (platform-specific)
    @staticmethod
    def get_mouse_wheel_config() -> Dict[str, int]:
        """Get platform-specific mouse wheel configuration"""
        system = platform.system().lower()

        if system == "windows":
            return {
                "delta": 120,
                "scroll_units": 3
            }
        elif system == "darwin":  # macOS
            return {
                "delta": 1,
                "scroll_units": 5
            }
        else:  # Linux
            return {
                "delta": 120,
                "scroll_units": 3
            }

    # Font Configuration
    FONTS = {
        'label_bold': ("Segoe UI", 10, "bold"),
        'label_normal': ("Segoe UI", 10),
        'label_small': ("Segoe UI", 9),
        'code_normal': ("Consolas", 10),
        'code_small': ("Consolas", 9),
        'json_preview': ("Consolas", 9)
    }

    # Layout Dimensions
    DIMENSIONS = {
        'text_width': 72,
        'json_width': 46,
        'right_frame_width': 440,
        'toggle_button_width': 4,
        'toggle_button_height': 1,
        'boolean_button_width': 5,
        'boolean_button_height': 1,
        'browse_button_width': 4,
        'combo_width': 32,
        'combo_sub_width': 22,
        'entry_width': 14,
        'tooltip_wrap': 500,
        'tooltip_border': 1,
        'content_pad_x': 18,
        'content_pad_y': 16,
        'section_pad_y': 14,
        'section_internal_pad': 14,
        'notebook_tab_pad': (18, 10),
        'control_pad_y': 8,
        'min_column_width': {
            'checkbox': 30,
            'param_name': 160,
            'value_input': 110,
            'description': 240
        }
    }

    # Validation Limits
    VALIDATION = {
        'max_path_length': 260,             # Windows MAX_PATH
        'max_param_value_length': 1024,     # Reasonable max parameter value
        'max_numeric_string_length': 20,    # Max length for numeric strings
        'max_flag_name_length': 50,         # Max parameter flag length
        'max_tooltip_width': 400,           # Tooltip max width in pixels
        'tooltip_wrap_length': 50           # Characters per line in tooltips
    }

    # Grid Layout Configuration
    GRID_CONFIG = {
        'column_weights': {
            'checkbox': 0,      # Fixed width
            'param_name': 0,    # Fixed width
            'value_input': 0,   # Fixed width
            'description': 1    # Expandable
        },
        'padding': {
            'internal': 5,      # Internal widget padding
            'external': 10,     # External frame padding
            'button_spacing': 2  # Space between buttons
        }
    }

    # Performance Configuration
    PERFORMANCE = {
        'ui_update_delay_ms': 100,          # Delay between UI updates
        'search_debounce_ms': 300,          # Debounce delay for search
        'auto_save_interval_s': 30,         # Auto-save interval in seconds
        'max_tooltip_instances': 10         # Max simultaneous tooltips
    }

    # File Dialog Configuration
    FILE_DIALOGS = {
        'config_files': {
            'title': "Configuration Files",
            'filetypes': [("JSON files", "*.json"), ("All files", "*.*")]
        },
        'model_files': {
            'title': "Model Files",
            'filetypes': [("GGUF files", "*.gguf"), ("All files", "*.*")]
        },
        'log_files': {
            'title': "Log Files",
            'filetypes': [("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        },
        'cert_files': {
            'title': "Certificate Files",
            'filetypes': [("Certificate files", "*.pem"), ("All files", "*.*")]
        }
    }


# Global configuration instance
ui_config = UIConfig()

# Convenience functions --------------------------------------------------
def get_font(font_name: str) -> tuple:
    """Get font configuration by name"""
    return ui_config.FONTS.get(font_name, ui_config.FONTS['label_normal'])


def get_color(color_name: str) -> str:
    """Get color by name"""
    return ui_config.COLORS.get(color_name, "#000000")


def get_dimension(dim_name: str) -> int:
    """Get dimension by name"""
    return ui_config.DIMENSIONS.get(dim_name, 100)


def get_validation_limit(limit_name: str) -> int:
    """Get validation limit by name"""
    return ui_config.VALIDATION.get(limit_name, 100)


def get_available_themes() -> List[str]:
    """Return available theme names"""
    return UIConfig.get_available_themes()


def set_theme(theme_name: str) -> bool:
    """Helper to apply a theme globally"""
    return UIConfig.set_theme(theme_name)


def get_current_theme() -> str:
    """Return the currently active theme name"""
    return UIConfig.get_current_theme()
