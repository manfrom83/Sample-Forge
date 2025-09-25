import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import os
import json
from typing import Optional
from .base_components import BaseUIComponent, ScrollableFrameManager, ThemedScrolledText
from .ui_config import get_dimension
from managers.path_manager import app_paths


class ServerUI(BaseUIComponent):
    
    def __init__(self, parent, server_config, api_client):
        super().__init__(parent, None, api_client)
        self.server_config = server_config
        self.parent = parent
        
        # UI components
        self.server_scrollable_frame = None
        self.server_command_text = None
        self.server_status_text = None
        self.server_param_count_label = None
        self.server_widgets = {}
        self.server_process = None
        
        # Track last used directories for file browsing with persistence
        self.server_ui_state_file = app_paths.data / "server_ui_state.json"
        self.last_model_dir = self._load_last_model_dir()
        self.last_file_dir = self._load_last_file_dir()
        self.last_executable_dir = self._load_last_executable_dir()
        
        # Scrollable frame manager
        self.scroll_manager = ScrollableFrameManager(self)
    
    def _load_server_ui_state(self) -> dict:
        """Load server UI state from file, return default state if none exists"""
        default_state = {
            "last_model_dir": os.path.expanduser("~"),
            "last_file_dir": os.path.expanduser("~"),
            "last_executable_dir": os.path.expanduser("~")
        }
        
        try:
            if self.server_ui_state_file.exists():
                with open(self.server_ui_state_file, 'r', encoding='utf-8') as f:
                    loaded_state = json.load(f)
                    # Merge with defaults in case new fields were added
                    default_state.update(loaded_state)
        except Exception as e:
            self.log_warning(f"Could not load server UI state: {e}")
        
        return default_state
    
    def _save_server_ui_state(self):
        """Save current server UI state to file"""
        try:
            state = {
                "last_model_dir": self.last_model_dir,
                "last_file_dir": self.last_file_dir,
                "last_executable_dir": self.last_executable_dir
            }
            
            # Ensure directory exists
            self.server_ui_state_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.server_ui_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log_warning(f"Could not save server UI state: {e}")
    
    def _load_last_model_dir(self) -> str:
        """Load last model directory from persistent state"""
        state = self._load_server_ui_state()
        return state["last_model_dir"]
    
    def _load_last_file_dir(self) -> str:
        """Load last file directory from persistent state"""
        state = self._load_server_ui_state()
        return state["last_file_dir"]
    
    def _load_last_executable_dir(self) -> str:
        """Load last executable directory from persistent state"""
        state = self._load_server_ui_state()
        return state["last_executable_dir"]
        
        
    def create_server_config_tab(self, notebook):
        """Create the server configuration tab"""
        server_tab = ttk.Frame(notebook)
        notebook.add(server_tab, text="Server Config")
        
        # Create main container (grid-based for consistent alignment)
        content_frame = ttk.Frame(server_tab, style='Content.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=self.content_pad_y)
        content_frame.columnconfigure(0, weight=3)
        content_frame.columnconfigure(1, weight=2)
        content_frame.rowconfigure(0, weight=1)
        
        # Left column - server parameters
        left_frame = ttk.Frame(content_frame, style='Content.TFrame')
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, self.content_pad_x))
        
        # Create inference engine configuration section
        self.create_inference_engine_section(left_frame)
        
        # Create scrollable area for server parameters
        self.create_server_scrollable_parameters(left_frame)
        
        # Right column - command preview and controls
        right_frame = ttk.Frame(content_frame, width=get_dimension('right_frame_width'), style='Content.TFrame')
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(0, self.content_pad_x))

        # Command preview (top half)
        ttk.Label(right_frame, text="Server Command Preview", font=self.FONTS['label_bold']).pack(anchor='w')
        self.server_command_text = ThemedScrolledText(
            right_frame,
            height=self.ui_config.JSON_PREVIEW_HEIGHT,
            width=get_dimension('json_width'),
            font=self.FONTS['json_preview']
        )
        self.server_command_text.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        self.style_text_widget(self.server_command_text.text)
        
        # Status area (bottom half)
        ttk.Label(right_frame, text="Server Status", font=self.FONTS['label_bold']).pack(anchor='w')
        self.server_status_text = ThemedScrolledText(
            right_frame,
            height=self.ui_config.LLM_OUTPUT_HEIGHT,
            width=get_dimension('json_width'),
            font=self.FONTS['code_normal']
        )
        self.server_status_text.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        self.style_text_widget(self.server_status_text.text)
        
        # Control buttons at the bottom
        self.create_server_control_buttons(server_tab)
        
        
        # Initial update
        self.update_server_command_preview()
        self.update_server_parameter_count()
    
    def create_inference_engine_section(self, parent):
        """Create the inference engine configuration section"""
        # Inference Engine section
        engine_frame = self.create_section(parent, "Inference Engine Configuration")
        engine_frame.pack(fill=tk.X)
        self.apply_card_padding(engine_frame)
        
        # Executable path row
        path_row = ttk.Frame(engine_frame)
        path_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(path_row, text="Executable Path:", 
                  font=self.FONTS['label_bold']).pack(side=tk.LEFT)
        
        # Entry for executable path
        self.executable_path_var = tk.StringVar()
        self.executable_path_var.set(self.server_config.executable_path or "")
        self.executable_path_var.trace('w', self.on_executable_path_changed)
        
        self.executable_path_entry = ttk.Entry(path_row, textvariable=self.executable_path_var,
                                               font=self.FONTS['code_normal'], width=50)
        self.executable_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5))
        
        # Browse button
        ttk.Button(path_row, text="Browse...", 
                   command=self.browse_executable_path).pack(side=tk.RIGHT)
        
        # Status/info row
        info_row = ttk.Frame(engine_frame)
        info_row.pack(fill=tk.X)
        
        self.executable_status_label = ttk.Label(info_row, text="", 
                                                 font=self.FONTS['label_small'], 
                                                 foreground=self.COLORS['gray_text'])
        self.executable_status_label.pack(anchor="w")
        
        # Update initial status
        self.update_executable_status()
    
    def create_server_scrollable_parameters(self, parent):
        """Create scrollable area for server parameter configuration"""
        section = self.create_section(parent, "Server Parameter Configuration")
        section.pack(fill=tk.BOTH, expand=True)
        self.apply_card_padding(section)

        main_frame, canvas, self.server_scrollable_frame = self.scroll_manager.create_scrollable_frame(section)

        count_frame = ttk.Frame(section, style='Content.TFrame')
        count_frame.pack(fill=tk.X, pady=(5, 0))
        self.server_param_count_label = ttk.Label(
            count_frame,
            text="Server Parameters: 0 enabled / 0 total", 
            font=self.FONTS['label_small'],
            foreground=self.COLORS.get('text_secondary')
        )
        self.server_param_count_label.pack(anchor="w")

        self.server_scrollable_frame.grid_columnconfigure(0, weight=0, minsize=220)
        self.server_scrollable_frame.grid_columnconfigure(1, weight=1)

        row = 0
        for category_name, category_params in self.server_config.schema.items():
            header_frame = ttk.Frame(self.server_scrollable_frame, style='Content.TFrame')
            header_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 2))
            ttk.Label(header_frame, text=category_name.upper(), style='Header.TLabel').pack(anchor="w")
            row += 1
            for param_name, param_def in category_params.items():
                self.create_simple_server_parameter_row(row, param_name, param_def)
                row += 1

        return main_frame

    
    
    def create_simple_server_parameter_row(self, row: int, param_name: str, param_def: dict):
        """Create a simple server parameter row with CLI flag name and text field"""
        # param_name is now the CLI flag directly
        cli_flag = param_name
        
        # CLI flag name (column 0 & 1 combined - no toggle needed)
        # Parameter highlighting removed for cleaner UI
        name_label = ttk.Label(self.server_scrollable_frame, text=cli_flag, 
                             font=self.FONTS['label_normal'])
        name_label.grid(row=row, column=0, padx=(5, 10), pady=1, sticky="w")
        
        # Add comprehensive hover tooltip to parameter name
        self.create_comprehensive_tooltip(name_label, param_name, param_def)
        
        # Simple value input (column 1)
        param_type = param_def.get("type", "string")
        
        if param_type == "bool":
            # Check if this is a special case parameter that needs 0/1 values
            special_params = ["--cpu-strict", "--cpu-strict-batch", "--poll-batch"]
            
            if param_name in special_params:
                # Special case: 3-button control for 0/1 values
                button_frame = ttk.Frame(self.server_scrollable_frame)
                button_frame.grid(row=row, column=1, padx=(0, 10), pady=1, sticky="w")
                
                # Determine current state
                current_enabled = self.server_config.enabled.get(param_name, False)
                current_value = self.server_config.values.get(param_name, "0") if current_enabled else None
                
                # Create variable for button state: 0=Disabled, 1=Send:0, 2=Send:1
                button_var = tk.IntVar()
                if not current_enabled:
                    button_var.set(0)  # Disabled
                elif str(current_value) == "0":
                    button_var.set(1)  # Send:0
                else:
                    button_var.set(2)  # Send:1
                
                # Three radio buttons for special parameters
                disabled_btn = ttk.Radiobutton(button_frame, text="Disabled", variable=button_var, value=0,
                                             command=lambda: self.on_server_boolean_parameter_changed(param_name, 0, True))
                disabled_btn.grid(row=0, column=0, padx=(0, 5))
                
                zero_btn = ttk.Radiobutton(button_frame, text="Send:0", variable=button_var, value=1,
                                         command=lambda: self.on_server_boolean_parameter_changed(param_name, 1, True))
                zero_btn.grid(row=0, column=1, padx=(0, 5))
                
                one_btn = ttk.Radiobutton(button_frame, text="Send:1", variable=button_var, value=2,
                                        command=lambda: self.on_server_boolean_parameter_changed(param_name, 2, True))
                one_btn.grid(row=0, column=2, padx=(0, 5))
                
                button_frame.button_var = button_var
                value_widget = button_frame
            else:
                # Regular boolean: 2-button control for presence flags
                button_frame = ttk.Frame(self.server_scrollable_frame)
                button_frame.grid(row=row, column=1, padx=(0, 10), pady=1, sticky="w")
                
                # Determine current state
                current_enabled = self.server_config.enabled.get(param_name, False)
                
                # Create variable for button state: 0=Disabled, 1=Send:True
                button_var = tk.IntVar()
                button_var.set(1 if current_enabled else 0)
                
                # Two radio buttons for regular boolean flags
                disabled_btn = ttk.Radiobutton(button_frame, text="Disabled", variable=button_var, value=0,
                                             command=lambda: self.on_server_boolean_parameter_changed(param_name, 0, False))
                disabled_btn.grid(row=0, column=0, padx=(0, 5))
                
                enabled_btn = ttk.Radiobutton(button_frame, text="Send", variable=button_var, value=1,
                                            command=lambda: self.on_server_boolean_parameter_changed(param_name, 1, False))
                enabled_btn.grid(row=0, column=1, padx=(0, 5))
                
                button_frame.button_var = button_var
                value_widget = button_frame
        elif param_type == "file_path":
            # File path parameters get entry field + browse button
            path_frame = ttk.Frame(self.server_scrollable_frame)
            path_frame.grid(row=row, column=1, padx=(0, 10), pady=1, sticky="ew")
            path_frame.grid_columnconfigure(0, weight=1)  # Entry expands
            
            # Entry field (reduced width to fit browse button)
            entry_widget = ttk.Entry(path_frame, width=40, 
                                   font=self.FONTS['code_small'])
            current_value = self.server_config.values.get(param_name, "")
            if current_value is not None and str(current_value).strip():
                entry_widget.insert(0, str(current_value))
            entry_widget.bind('<KeyRelease>', lambda e: self.on_simple_parameter_changed(param_name, entry_widget.get()))
            entry_widget.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            
            # Browse button (fix lambda closure bug)
            browse_btn = ttk.Button(path_frame, text="Browse...",
                                  command=lambda pn=param_name, ew=entry_widget, pd=param_def: 
                                      self.browse_file_path(pn, ew, pd))
            browse_btn.grid(row=0, column=1, sticky="w")
            
            # Store the entry widget for refresh (like sequence parameters)
            value_widget = entry_widget
        else:
            # All other parameters get a simple text field
            entry_widget = ttk.Entry(self.server_scrollable_frame, width=get_dimension('entry_width'), 
                                   font=self.FONTS['code_small'])
            current_value = self.server_config.values.get(param_name, "")
            if current_value is not None and str(current_value).strip():
                entry_widget.insert(0, str(current_value))
            entry_widget.bind('<KeyRelease>', lambda e: self.on_simple_parameter_changed(param_name, entry_widget.get()))
            entry_widget.grid(row=row, column=1, padx=(0, 10), pady=1, sticky="w")
            value_widget = entry_widget
        
        # Comprehensive tooltip is already added to parameter name above
        
        # Store widgets (simple UI)
        self.server_widgets[param_name] = {
            "widget": value_widget,
            "definition": param_def
        }
    
    def create_comprehensive_tooltip(self, widget, param_name: str, param_def: dict):
        """Create simple tooltip using just the description"""
        tooltip_text = param_def.get('tooltip', f'No description available for {param_name}')
        self.create_hover_tooltip(widget, tooltip_text)
    
    
    def on_simple_parameter_changed(self, param_name: str, value):
        """Handle changes to simple UI parameters"""
        # For boolean parameters, enable/disable based on checkbox state
        param_def = self.server_config.schema.get(param_name, {})
        for category in self.server_config.schema.values():
            if param_name in category:
                param_def = category[param_name]
                break
        
        if param_def.get("type") == "bool":
            # Boolean parameters now use button system, this shouldn't be called
            pass
        else:
            # Non-boolean: if has value = enabled + send, if empty = disabled + don't send
            if value and str(value).strip():
                self.server_config.enabled[param_name] = True
                self.server_config.values[param_name] = value
            else:
                self.server_config.enabled[param_name] = False
                self.server_config.values[param_name] = ""
        
        # Update command preview
        self.update_server_command_preview()
        self.update_server_parameter_count()
    
    def on_server_boolean_parameter_changed(self, param_name: str, state: int, is_special: bool):
        """Handle server boolean parameter changes
        Args:
            param_name: Parameter name (CLI flag)
            state: 0=Disabled, 1=Send:True/Send:0, 2=Send:1
            is_special: True if this is a special 0/1 parameter
        """
        if state == 0:
            # Disabled: don't send parameter at all
            self.server_config.enabled[param_name] = False
            self.server_config.values[param_name] = None
        elif state == 1:
            # Send:True (regular) or Send:0 (special)
            self.server_config.enabled[param_name] = True
            if is_special:
                self.server_config.values[param_name] = "0"  # Special case: explicit 0 value
            else:
                self.server_config.values[param_name] = True  # Regular case: presence flag
        elif state == 2:
            # Send:1 (special parameters only)
            if is_special:
                self.server_config.enabled[param_name] = True
                self.server_config.values[param_name] = "1"  # Explicit 1 value
        
        # Update command preview
        self.update_server_command_preview()
        self.update_server_parameter_count()
    
    def create_server_control_buttons(self, parent):
        """Create server control buttons"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, padx=5, pady=(5, 10))
        
        ttk.Button(button_frame, text="Save Server Config", 
                  command=self.save_server_config).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Load Server Config", 
                  command=self.load_server_config).pack(side=tk.LEFT, padx=5)
        # Use a custom-drawn accent "button" built from a Frame+Label to avoid ttk HiDPI baseline quirks
        launch_btn = self._create_accent_button(
            button_frame,
            text="Launch/Reload Server",
            command=self.launch_reload_server,
        )
        launch_btn.pack(side=tk.LEFT, padx=(15, 5))

    def _create_accent_button(self, parent, text: str, command):
        """Create a composite accent button using tk widgets to avoid ttk label clipping on HiDPI.

        This isolates the fix to a single control and preserves the overall theme.
        """
        bg = self.COLORS.get('accent', '#C2410C')
        bg_hover = self.COLORS.get('accent_hover', '#9A3412')
        fg = '#FFFFFF'

        container = tk.Frame(parent, bg=bg, bd=0, highlightthickness=0, relief='flat', cursor='hand2')
        label = tk.Label(
            container,
            text=text,
            bg=bg,
            fg=fg,
            font=self.FONTS.get('label_bold'),
            padx=16,
            pady=10,
        )
        label.pack()

        def _on_enter(_e=None):
            try:
                container.configure(bg=bg_hover)
                label.configure(bg=bg_hover)
            except Exception:
                pass

        def _on_leave(_e=None):
            try:
                container.configure(bg=bg)
                label.configure(bg=bg)
            except Exception:
                pass

        def _on_click(_e=None):
            try:
                if callable(command):
                    command()
            except Exception:
                pass

        for w in (container, label):
            w.bind('<Enter>', _on_enter)
            w.bind('<Leave>', _on_leave)
            w.bind('<Button-1>', _on_click)
        return container
    
    
    
    def update_server_command_preview(self):
        """Update server command preview"""
        try:
            # Try to generate full command
            command = self.server_config.generate_server_command()
            command_str = ' '.join(command) if command else "No executable path configured"
            
        except ValueError as e:
            # Handle missing executable path gracefully - show what command would be
            if "Executable path not configured" in str(e):
                command_str = self._generate_preview_command_without_executable()
            else:
                command_str = f"Configuration error: {e}"
        except Exception as e:
            command_str = f"Error generating command: {e}"
        
        if self.server_command_text:
            self.server_command_text.delete("1.0", tk.END)
            self.server_command_text.insert("1.0", command_str)
    
    def _generate_preview_command_without_executable(self):
        """Generate command preview without executable path for display purposes"""
        try:
            command_parts = ["<executable-path>"]  # Placeholder for executable
            
            # Process enabled parameters using the same logic as generate_server_command
            for param_name, enabled in self.server_config.enabled.items():
                if not enabled:
                    continue
                    
                # For boolean flags, we don't need a value - enabled state is enough
                if param_name in self.server_config.BOOLEAN_FLAGS:
                    # Boolean flags only need enabled=True  
                    pass
                else:
                    # Non-boolean parameters need a value
                    value = self.server_config.values.get(param_name)
                    if value is None or (isinstance(value, str) and not value.strip()):
                        continue
                    
                # Use direct CLI flag (param_name IS the CLI flag)
                if param_name in self.server_config.BOOLEAN_FLAGS:
                    # Boolean flags: enabled=True means add the flag
                    command_parts.append(param_name)
                else:
                    # Value parameter - get the value we checked above  
                    value = self.server_config.values.get(param_name)
                    command_parts.append(param_name)
                    command_parts.append(str(value))
            
            if len(command_parts) == 1:
                return "Set executable path and enable parameters to see command preview"
            else:
                return ' '.join(command_parts) + "\n\n(Set executable path in server configuration to launch)"
                
        except Exception as e:
            return f"Preview error: {e}"
    
    def update_server_parameter_count(self):
        """Update server parameter count display"""
        enabled_count = sum(1 for enabled in self.server_config.enabled.values() if enabled)
        total_count = len(self.server_config.enabled)
        
        if self.server_param_count_label:
            self.server_param_count_label.config(text=f"Server Parameters: {enabled_count} enabled / {total_count} total")
    
    def save_server_config(self):
        """Save server configuration"""
        try:
            filename = self.ask_save_file(
                title="Save Server Configuration",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=self.server_config.save_dir
            )
            
            if filename:
                # Extract just the filename without extension for backend compatibility
                import os
                base_filename = os.path.splitext(os.path.basename(filename))[0]
                
                self.server_config.save_config(base_filename)
                messagebox.showinfo("Success", f"Server configuration saved to {filename}")
                self.log_info(f"Server configuration saved to {filename}")
                
        except Exception as e:
            self.log_error(f"Failed to save server configuration: {e}")
            messagebox.showerror("Error", f"Failed to save server configuration: {e}")
    
    def load_server_config(self):
        """Load server configuration"""
        try:
            filename = self.ask_open_file(
                title="Load Server Configuration",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=self.server_config.save_dir
            )
            
            if filename:
                # Validate content kind to prevent loading wrong JSON
                try:
                    from utils.config_utils import load_json_config, detect_config_kind
                    ok, data = load_json_config(filename, "server configuration")
                    kind = detect_config_kind(data) if ok else 'unknown'
                except Exception:
                    kind = 'unknown'
                if kind != 'server':
                    messagebox.showerror(
                        "Invalid File",
                        f"Selected file is not a Server Configuration JSON:\n{os.path.basename(filename)}"
                    )
                    return

                # Extract just the filename without extension for backend compatibility  
                import os
                base_filename = os.path.splitext(os.path.basename(filename))[0]
                self.server_config.load_config(base_filename)
                
                # Update API client to match loaded server configuration
                if self.api_client:
                    server_url = self.server_config.get_server_url()
                    timeouts = self.server_config.get_connection_timeouts()
                    
                    self.api_client.configure(
                        base_url=server_url,
                        timeout=timeouts['connection_timeout'],
                        request_timeout=timeouts['request_timeout']
                    )
                    self.log_info(f"API client updated to match server config: {server_url}")
                
                self.refresh_server_ui()
                messagebox.showinfo("Success", f"Server configuration loaded from {filename}")
                self.log_info(f"Server configuration loaded from {filename}")
                
        except Exception as e:
            self.log_error(f"Failed to load server configuration: {e}")
            messagebox.showerror("Error", f"Failed to load server configuration: {e}")
    
    def refresh_server_ui(self):
        """Refresh server UI to reflect current configuration"""
        # Update all server parameter widgets - simple UI version
        for param_name, widget_info in self.server_widgets.items():
            # No toggle in simple UI - just update value widget
            value = self.server_config.values.get(param_name, "")
            widget = widget_info["widget"]
            
            # Update value widget based on type
            param_def = widget_info["definition"]
            param_type = param_def.get("type", "string")
            
            if param_type == "bool":
                # Server boolean parameters now use button controls - refresh handled by button_var
                if hasattr(widget, 'button_var'):
                    current_enabled = self.server_config.enabled.get(param_name, False)
                    current_value = self.server_config.values.get(param_name, True) if current_enabled else None
                    
                    # Check if this is a special 0/1 parameter
                    special_params = ["--cpu-strict", "--cpu-strict-batch", "--poll-batch"]
                    if param_name in special_params:
                        # 3-button special parameter
                        if not current_enabled:
                            widget.button_var.set(0)  # Disabled
                        elif str(current_value) == "0":
                            widget.button_var.set(1)  # Send:0
                        else:
                            widget.button_var.set(2)  # Send:1
                    else:
                        # 2-button regular parameter
                        widget.button_var.set(1 if current_enabled else 0)
            elif isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
                if value is not None and str(value).strip():
                    widget.insert(0, str(value))
        
        # Update executable path
        if hasattr(self, 'executable_path_var') and self.executable_path_var:
            self.executable_path_var.set(self.server_config.executable_path or "")
            if hasattr(self, 'update_executable_status'):
                self.update_executable_status()
        
        # Update displays
        self.update_server_command_preview()
        self.update_server_parameter_count()
    
    def launch_reload_server(self):
        """Launch/reload the llama.cpp server with current configuration (always kills existing server first)"""
        try:
            command = self.server_config.generate_server_command()
            if not command:
                messagebox.showerror("Error", "No executable path configured. Please set the server executable path.")
                return
            
            command_str = ' '.join(command)
            
            # Update status immediately to show we're working
            if self.server_status_text:
                self.server_status_text.delete("1.0", tk.END)
                self.server_status_text.insert("1.0", "Stopping existing server...\n")
                self.server_status_text.insert(tk.END, f"Command: {command_str}\n\n")
                self.parent.root.update()  # Force UI update to show message immediately
            
            def server_operation():
                """Run server kill and launch operations in background thread"""
                try:
                    # Kill existing servers (centralized via server manager)
                    from utils.server_manager import cleanup_all_servers
                    cleanup_all_servers()
                    
                    # Update UI from thread (use after to ensure thread safety)
                    if self.server_status_text and self.parent.root:
                        self.parent.root.after(0, lambda: self.server_status_text.insert(tk.END, "Starting fresh server...\n"))
                    
                    # Launch server in new process with visible console window
                    self.server_process = subprocess.Popen(command)
                    
                    # Update UI with success message
                    if self.server_status_text and self.parent.root:
                        pid = self.server_process.pid
                        self.parent.root.after(0, lambda: self.server_status_text.insert(tk.END, 
                            f"Server launched with PID {pid}\n"
                            f"Server console window opened - check taskbar for llama-server window\n"))
                    
                except Exception as e:
                    # Show error in UI thread
                    if self.parent.root:
                        error_msg = f"Failed to launch server: {e}"
                        self.parent.root.after(0, lambda: messagebox.showerror("Error", error_msg))
            
            # Start operation in background thread
            thread = threading.Thread(target=server_operation, daemon=True)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to prepare server launch: {e}")
    
    def set_scroll_sensitivity(self, sensitivity: int):
        """Update scroll sensitivity"""
        if self.scroll_manager:
            self.scroll_manager.scroll_units_per_wheel = sensitivity
    
    def _cleanup_server_process(self):
        """Clean up server process when application closes"""
        if self.server_process and self.server_process.poll() is None:
            try:
                # Terminate the server process
                self.server_process.terminate()
                
                # Wait for process to end, with timeout
                try:
                    self.server_process.wait(timeout=5)  # 5 second timeout
                except subprocess.TimeoutExpired:
                    # Force kill if termination didn't work
                    self.server_process.kill()
                    self.server_process.wait()
                
                self.log_info(f"Server process {self.server_process.pid} terminated successfully")
                
            except Exception as e:
                self.log_warning(f"Could not terminate server process: {e}")
            finally:
                self.server_process = None
    
    
    def browse_executable_path(self):
        """Browse for server executable file"""
        # Get initial directory - prioritize in this order:
        # 1. Current executable's directory (if file exists)
        # 2. Last used executable directory
        # 3. Default from persistent state
        initial_dir = None
        current_path = self.server_config.executable_path
        
        if current_path and os.path.exists(current_path):
            # Use current executable's directory
            initial_dir = os.path.dirname(current_path)
        else:
            # Use last executable directory
            initial_dir = self.last_executable_dir
        
        filename = self.ask_open_file(
            title="Select Server Executable",
            filetypes=[("All files", "*.*")],
            initialdir=initial_dir
        )
        
        if filename:
            self.executable_path_var.set(filename)
            self.server_config.executable_path = filename
            
            # Remember this directory for next time and persist it
            selected_dir = os.path.dirname(filename)
            self.last_executable_dir = selected_dir
            self._save_server_ui_state()
            
            self.update_executable_status()
            self.update_server_command_preview()
    
    def browse_file_path(self, param_name: str, entry_widget, param_def: dict):
        """Browse for file path parameters with last path memory"""
        
        # Determine file types based on parameter
        if param_name == "--model" or param_name == "--model-draft":
            title = "Select Model File"
            filetypes = [
                ("GGUF model files", "*.gguf"),
                ("All files", "*.*")
            ]
        elif "vocoder" in param_name.lower():
            title = "Select Vocoder Model File"
            filetypes = [
                ("GGUF model files", "*.gguf"),
                ("All files", "*.*")
            ]
        elif "lora" in param_name.lower():
            title = "Select LoRA Adapter File"
            filetypes = [
                ("GGUF files", "*.gguf"),
                ("All files", "*.*")
            ]
        elif "control" in param_name.lower():
            title = "Select Control Vector File"
            filetypes = [
                ("GGUF files", "*.gguf"),
                ("All files", "*.*")
            ]
        elif "template" in param_name.lower():
            title = "Select Chat Template File"
            filetypes = [
                ("Template files", "*.jinja"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        else:
            title = f"Select File for {param_name}"
            filetypes = [("All files", "*.*")]
        
        # Get initial directory - prioritize in this order:
        # 1. Current value's directory (if file exists)
        # 2. Last used directory for this file type
        # 3. Default from persistent state
        initial_dir = None
        current_value = entry_widget.get().strip()
        
        if current_value and os.path.exists(current_value):
            # Use current file's directory
            initial_dir = os.path.dirname(current_value)
        elif param_name in ["--model", "--model-draft"]:
            # Use last model directory if available
            initial_dir = self.last_model_dir
        else:
            # Use last general file directory if available
            initial_dir = self.last_file_dir
        
        
        # Use the determined initial directory
        filename = self.ask_open_file(
            title=title,
            filetypes=filetypes,
            initialdir=initial_dir
        )
        
        # Remember the directory for next time if a file was selected
        if filename:
            # Update the entry widget
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)
            
            # Remember this directory for next time and persist it
            selected_dir = os.path.dirname(filename)
            if param_name in ["--model", "--model-draft"]:
                self.last_model_dir = selected_dir
            else:
                self.last_file_dir = selected_dir
            
            # Save the updated directories to persistent state
            self._save_server_ui_state()
            
            # Update server config
            self.on_simple_parameter_changed(param_name, filename)
        # (Directory is only saved on successful file selection)
    
    def on_executable_path_changed(self, *args):
        """Handle executable path change"""
        path = self.executable_path_var.get().strip()
        self.server_config.executable_path = path if path else None
        self.update_executable_status()
        self.update_server_command_preview()
    
    def update_executable_status(self):
        """Update the executable status label"""
        path = self.server_config.executable_path
        
        if not path:
            self.executable_status_label.config(
                text="WARNING: No executable selected - server cannot be launched",
                foreground=self.COLORS.get('modified_value', 'orange')
            )
        elif os.path.exists(path):
            # Get file info
            file_size = os.path.getsize(path)
            file_size_mb = file_size / (1024 * 1024)
            self.executable_status_label.config(
                text=f"Valid executable found ({file_size_mb:.1f} MB) - ready to launch",
                foreground=self.COLORS.get('green_text', 'green')
            )
        else:
            self.executable_status_label.config(
                text=f"ERROR: File not found: {path}",
                foreground=self.COLORS.get('red_text', 'red')
            )
