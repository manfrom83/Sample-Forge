"""
Main UI Module
Handles core window management, tabs, and application lifecycle
"""

import tkinter as tk
from tkinter import ttk
import os
from typing import Optional
from managers.server_config_manager import ServerConfig
from managers.global_settings import global_settings
from .ui_config import UIConfig
from .base_components import BaseUIComponent, ScrollableFrameManager
from .api_parameters_tab import ParameterTabUI
from .server_config_tab import ServerUI  
from .benchmark_tab import BenchmarkUI
from .benchmark_runner_tab import BenchmarkRunnerUI
from .scoring_tab import ScoringUI
from .aco_data_viewer_tab import ACODataViewerTab


class MainUI(BaseUIComponent):
    """Main application UI - handles window, tabs, and core functionality"""
    
    def __init__(self, config_manager, api_client, cache_manager=None, scroll_sensitivity=None):
        UIConfig.set_theme(global_settings.get_theme())
        super().__init__(None, config_manager, api_client)
        self.cache_manager = cache_manager
        
        self.root = None
        self.theme_var = None
        self.theme_dropdown = None
        self.global_settings_frame = None
        
        # Load UI configuration
        mouse_config = UIConfig.get_mouse_wheel_config()
        self.scroll_sensitivity = scroll_sensitivity or mouse_config["scroll_units"]
        
        # Initialize server config manager
        self.server_config = ServerConfig()
        self.server_executable_path = None
        
        # UI managers for each tab
        self.parameter_ui = None
        self.server_ui = None
        self.benchmark_ui = None
        self.benchmark_runner_ui = None
        self.scoring_ui = None
        self.auto_mode_ui = None
        self.aco_data_viewer_ui = None
        
        # Scrollable frame manager
        self.scroll_manager = ScrollableFrameManager(self)
    
    def create_main_window(self) -> tk.Tk:
        """Create and configure the main application window"""
        self.root = tk.Tk()
        self.ensure_styles()
        self.root.title("Sample Forge")
        self.root.geometry(self.ui_config.WINDOW_GEOMETRY)
        self.root.configure(bg=self.COLORS.get('window_bg'))

        if self.ui_config.WINDOW_START_MAXIMIZED:
            self.root.state('zoomed')  # Windows maximized

        try:
            self.root.option_add('*Font', self.FONTS['label_normal'])
            self.root.option_add('*TCombobox*Listbox.font', self.FONTS['label_normal'])
        except tk.TclError:
            pass

        # Configure window closing
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Global settings bar (above tabs)
        self._create_global_settings_bar()

        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=(0, self.content_pad_y))
        # Track which tabs have been initialized
        self.tab_initialized = {
            "Server Config": False,
            "API Parameters": False,
            "Dataset Conversion": False,
            "Run Benchmark": False,
            "Auto Mode": False,
            "ACO Data Viewer": False,
            "Scoring & Analysis": False
        }
        
        # Create Server Config tab immediately (most commonly used on startup)
        self.server_ui = ServerUI(self, self.server_config, self.api_client)
        self.server_ui.create_server_config_tab(self.notebook)
        self.tab_initialized["Server Config"] = True
        
        # Add placeholder frames for other tabs (lazy loaded on first access)
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="API Parameters")
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="Dataset Conversion")
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="Run Benchmark")
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="Scoring & Analysis")
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="Auto Mode")
        self.notebook.add(ttk.Frame(self.notebook, style='Content.TFrame'), text="ACO Data Viewer")
        
        # Bind tab change event for lazy loading
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        
        self.apply_theme(UIConfig.get_current_theme())
        return self.root
    
    def _create_global_settings_bar(self):
        """Create the global settings bar above tabs"""
        global_frame = ttk.Frame(self.root, style='App.TFrame')
        global_frame.pack(fill=tk.X, padx=self.content_pad_x, pady=(self.content_pad_y, 0))
        
        # Endpoint selection
        ttk.Label(global_frame, text="Completions Endpoint:").pack(side=tk.LEFT, padx=(5,5))

        self.endpoint_var = tk.StringVar(value=global_settings.get_endpoint_type())

        endpoint_dropdown = ttk.Combobox(global_frame, textvariable=self.endpoint_var,
                                       values=["chat_completions", "completions"],
                                       state="readonly", width=15)
        endpoint_dropdown.pack(side=tk.LEFT, padx=(0,5))

        # Set display values
        display_values = ["Chat Completions", "Text Completions (Raw)"]
        endpoint_dropdown.configure(values=display_values)

        # Set current display value
        current_type = global_settings.get_endpoint_type()
        if current_type == "chat_completions":
            endpoint_dropdown.set("Chat Completions")
        else:
            endpoint_dropdown.set("Text Completions (Raw)")

        # Bind change event
        endpoint_dropdown.bind("<<ComboboxSelected>>", self._on_endpoint_changed)

        # Theme selection
        ttk.Label(global_frame, text="Theme:").pack(side=tk.LEFT, padx=(18,5))
        available_themes = UIConfig.get_available_themes()
        self.theme_var = tk.StringVar(value=UIConfig.get_current_theme())
        self.theme_dropdown = ttk.Combobox(global_frame, textvariable=self.theme_var,
                                          values=available_themes, state="readonly", width=18)
        self.theme_dropdown.pack(side=tk.LEFT, padx=(0,5))
        self.theme_dropdown.bind("<<ComboboxSelected>>", self._on_theme_selected)

        self.global_settings_frame = global_frame
    
    def _on_endpoint_changed(self, event=None):
        """Handle endpoint type change"""
        display_value = self.endpoint_var.get()
        
        # Convert display value to internal value
        if display_value == "Chat Completions":
            endpoint_type = "chat_completions"
        else:  # "Text Completions (Raw)"
            endpoint_type = "completions"
        
        # Save setting
        global_settings.set_endpoint_type(endpoint_type)
        
        # Notify all tabs about the change
        self._notify_tabs_endpoint_change(endpoint_type)

    def _on_theme_selected(self, event=None):
        """Handle theme selection changes"""
        if not self.theme_var:
            return
        selected = self.theme_var.get()
        if selected:
            self.apply_theme(selected, persist=True)

    def _notify_tabs_endpoint_change(self, endpoint_type: str):
        """Notify all initialized tabs about endpoint change"""
        if self.parameter_ui:
            self.parameter_ui.on_endpoint_changed(endpoint_type)
        if self.benchmark_runner_ui:
            self.benchmark_runner_ui.on_endpoint_changed(endpoint_type)

    def apply_theme(self, theme_name: str, persist: bool = False):
        """Apply a named theme across the UI"""
        if not UIConfig.set_theme(theme_name):
            self.log_warning(f"Unknown theme selected: {theme_name}")
            return
        if persist:
            global_settings.set_theme(theme_name)

        BaseUIComponent._style_configured = False
        super().apply_theme()
        self.ensure_styles()

        if self.theme_var:
            self.theme_var.set(UIConfig.get_current_theme())
        if self.theme_dropdown:
            self.theme_dropdown.configure(values=UIConfig.get_available_themes())

        components = [
            self.server_ui,
            self.parameter_ui,
            self.benchmark_ui,
            self.benchmark_runner_ui,
            self.scoring_ui,
            self.auto_mode_ui,
            self.aco_data_viewer_ui
        ]
        for component in components:
            if component:
                component.apply_theme()

        if self.notebook:
            try:
                self.notebook.configure(style='TNotebook')
            except tk.TclError:
                pass

    def on_theme_changed(self):
        """Update main window surfaces when theme updates"""
        window_bg = self.COLORS.get('window_bg', '#ffffff')
        if self.root:
            self.root.configure(bg=window_bg)
        if self.global_settings_frame:
            self.global_settings_frame.configure(style='App.TFrame')

    
    def get_current_endpoint_type(self) -> str:
        """Get current endpoint type"""
        return global_settings.get_endpoint_type()
    
    def _on_tab_changed(self, event):
        """Handle tab change events and lazy load tabs as needed"""
        # Get current tab name
        current_tab_index = self.notebook.index("current")
        tab_text = self.notebook.tab(current_tab_index, "text")
        
        # Check if tab needs initialization
        if not self.tab_initialized.get(tab_text, False):
            self._initialize_tab(tab_text, current_tab_index)
    
    def _initialize_tab(self, tab_name: str, tab_index: int):
        """Lazy initialize a tab on first access"""
        # Store the current notebook state
        all_tabs = self.notebook.tabs()
        
        if tab_name == "API Parameters" and not self.parameter_ui:
            # Create API Parameters tab UI manager
            self.parameter_ui = ParameterTabUI(self, self.config, self.api_client)
            # Remove placeholder
            self.notebook.forget(tab_index)
            # Create the actual tab (this adds it to the end)
            self.parameter_ui.create_parameter_tab(self.notebook)
            # Move the newly created tab back to its original position
            new_tab = self.notebook.tabs()[-1]
            if tab_index < len(self.notebook.tabs()) - 1:
                # Move tab to correct position by reinserting
                self.notebook.forget(new_tab)
                self.notebook.insert(tab_index, new_tab, text="API Parameters")
            # Select the tab to show it
            self.notebook.select(tab_index)
            
        elif tab_name == "Dataset Conversion" and not self.benchmark_ui:
            # Create Dataset Conversion tab
            self.benchmark_ui = BenchmarkUI(self, self.config, self.api_client, self.cache_manager)
            self.notebook.forget(tab_index)
            self.benchmark_ui.create_benchmark_conversion_tab(self.notebook)
            # Move to correct position and select
            new_tab = self.notebook.tabs()[-1]
            if tab_index < len(self.notebook.tabs()) - 1:
                self.notebook.forget(new_tab)
                self.notebook.insert(tab_index, new_tab, text="Dataset Conversion")
            self.notebook.select(tab_index)
            
        elif tab_name == "Run Benchmark" and not self.benchmark_runner_ui:
            # Create Run Benchmark tab
            self.benchmark_runner_ui = BenchmarkRunnerUI(self, self.config, self.api_client)
            self.notebook.forget(tab_index)
            self.benchmark_runner_ui.create_benchmark_runner_tab(self.notebook)
            # Move to correct position and select
            new_tab = self.notebook.tabs()[-1]
            if tab_index < len(self.notebook.tabs()) - 1:
                self.notebook.forget(new_tab)
                self.notebook.insert(tab_index, new_tab, text="Run Benchmark")
            self.notebook.select(tab_index)
            
        elif tab_name == "Auto Mode" and not self.auto_mode_ui:
            from .auto_mode_tab import AutoModeUI
            self.auto_mode_ui = AutoModeUI(self, self.config, self.api_client)
            placeholder_frame = self.notebook.nametowidget(self.notebook.tabs()[tab_index])
            for widget in placeholder_frame.winfo_children():
                widget.destroy()
            self.auto_mode_ui.create_auto_mode_tab(self.notebook)
            # Remove the placeholder tab (we just added a real tab at the end)
            self.notebook.forget(tab_index)
            # Move the newly created tab to the same index
            new_tab = self.notebook.tabs()[-1]
            self.notebook.insert(tab_index, new_tab, text="Auto Mode")
            self.notebook.select(tab_index)

        elif tab_name == "ACO Data Viewer" and not self.aco_data_viewer_ui:
            # Create ACO Data Viewer tab - replace placeholder content directly
            self.aco_data_viewer_ui = ACODataViewerTab(self, self.api_client)
            placeholder_frame = self.notebook.nametowidget(self.notebook.tabs()[tab_index])
            # Clear placeholder content and initialize data viewer in place
            for widget in placeholder_frame.winfo_children():
                widget.destroy()
            self.aco_data_viewer_ui.parent = placeholder_frame
            self.aco_data_viewer_ui.setup_ui()
            
        elif tab_name == "Scoring & Analysis" and not self.scoring_ui:
            # Create Scoring tab
            self.scoring_ui = ScoringUI(self, self.config, self.api_client)
            self.notebook.forget(tab_index)
            self.scoring_ui.create_scoring_tab(self.notebook)
            # Move to correct position and select
            new_tab = self.notebook.tabs()[-1]
            if tab_index < len(self.notebook.tabs()) - 1:
                self.notebook.forget(new_tab)
                self.notebook.insert(tab_index, new_tab, text="Scoring & Analysis")
            self.notebook.select(tab_index)
        
        # Mark tab as initialized
        self.tab_initialized[tab_name] = True
    
    def set_scroll_sensitivity(self, sensitivity: int):
        """Update scroll sensitivity for all components"""
        self.scroll_sensitivity = sensitivity
        # Update all tab managers
        if self.parameter_ui:
            self.parameter_ui.set_scroll_sensitivity(sensitivity)
        if self.server_ui:
            self.server_ui.set_scroll_sensitivity(sensitivity)
        if self.benchmark_ui:
            self.benchmark_ui.set_scroll_sensitivity(sensitivity)
        # Note: benchmark_runner_ui and scoring_ui don't use scrollable frames
    
    def get_scroll_sensitivity(self) -> int:
        """Get current scroll sensitivity"""
        return self.scroll_sensitivity
    
    def on_benchmark_completed(self):
        """Called when a benchmark run completes - notify scoring tab to refresh"""
        if self.scoring_ui:
            self.scoring_ui.refresh_runs_if_needed()
    
    # Removed UI-local last config tracking; use ParameterConfig's persistence instead
    
    # Removed hardcoded executable path search - users now configure via UI
    
    def _on_window_close(self):
        """Handle window closing event"""
        try:
            # Cleanup ACO Data Viewer database connections
            if self.aco_data_viewer_ui:
                self.aco_data_viewer_ui.cleanup()
            
            # Cleanup our managed server process (multi-instance safe)
            from utils.server_manager import app_server_manager
            app_server_manager.cleanup()
            
            # Start cleanup in background thread to avoid blocking UI
            import threading
            cleanup_thread = threading.Thread(target=self._cleanup_orphaned_servers, daemon=True)
            cleanup_thread.start()
            
            # Give cleanup a brief moment to start (but don't wait for completion)
            import time
            time.sleep(0.1)  # 100ms is enough to initiate cleanup
            
        except Exception as e:
            self.log_warning(f"Warning during cleanup: {e}")
        finally:
            self.root.destroy()
    
    def _cleanup_orphaned_servers(self):
        """Clean up any orphaned llama-server processes"""
        try:
            from utils.server_manager import cleanup_all_servers
            cleanup_all_servers()
        except Exception as e:
            self.log_warning(f"Warning: Could not clean up servers: {e}")
    
    def run(self):
        """Start the main application loop"""
        if self.root:
            self.root.mainloop()
        else:
            raise RuntimeError("Main window not created. Call create_main_window() first.")


# For backward compatibility - main class that applications import
class ParameterUI(MainUI):
    """Backward compatibility alias for MainUI"""
    pass
