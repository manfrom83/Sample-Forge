import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import os
from typing import Dict, Any, Optional
from .base_components import BaseUIComponent, ScrollableFrameManager, ThemedScrolledText
from .ui_config import get_dimension


class ParameterTabUI(BaseUIComponent):
    
    def __init__(self, parent, config_manager, api_client):
        super().__init__(parent, config_manager, api_client)
        self.parent = parent
        
        # UI components
        self.system_prompt_text = None
        self.llm_input_text = None
        self.json_text = None
        self.slots_text = None
        self.llm_output_text = None
        self.show_metadata_checkbox = None
        self.current_response_details = None  # Store full API response
        self.param_count_label = None
        self.scrollable_frame = None
        
        # Scrollable frame manager
        self.scroll_manager = ScrollableFrameManager(self)
        
        # Thinking block state tracking
        self._thinking_states = {}
        
    
    def create_parameter_tab(self, notebook):
        """Create the parameter configuration tab"""
        config_tab = ttk.Frame(notebook, style='Content.TFrame')
        notebook.add(config_tab, text="API Parameters")

        config_tab.columnconfigure(0, weight=1)
        config_tab.rowconfigure(1, weight=1)

        # Prompt input and output sections
        prompt_section = self.create_section(config_tab, "Test Input & Output")
        prompt_section.grid(row=0, column=0, sticky="ew", padx=self.content_pad_x,
                            pady=(self.content_pad_y, self.section_pad_y))

        prompt_body = ttk.Frame(prompt_section, style='Content.TFrame')
        prompt_body.pack(fill=tk.BOTH, expand=True)

        main_container = ttk.Frame(prompt_body, style='Content.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True)

        # Configure columns: left for input fields, right for output
        main_container.grid_columnconfigure(0, weight=5)
        main_container.rowconfigure(0, weight=1)
        main_container.grid_columnconfigure(1, weight=3)

        # Left column: System Prompt above LLM Input
        left_frame = ttk.Frame(main_container, style='Content.TFrame')
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        system_prompt_header = ttk.Frame(left_frame, style='Content.TFrame')
        system_prompt_header.pack(fill=tk.X, anchor="w")

        ttk.Label(system_prompt_header, text="System Prompt:", font=self.FONTS['label_bold']).pack(side=tk.LEFT, anchor="w")

        tab_frame = ttk.Frame(system_prompt_header, style='Content.TFrame')
        tab_frame.pack(side=tk.RIGHT, anchor="e")

        self.system_prompt_mode = tk.StringVar(value="llm_input")
        self.llm_input_tab = ttk.Button(tab_frame, text="LLM Input",
                                       command=lambda: self.switch_system_prompt_mode("llm_input"))
        self.llm_input_tab.pack(side=tk.LEFT, padx=(0, 2))

        self.auto_mode_array_tab = ttk.Button(tab_frame, text="Auto Mode Array",
                                       command=lambda: self.switch_system_prompt_mode("auto_mode_array"))
        self.auto_mode_array_tab.pack(side=tk.LEFT)

        auto_mode_tooltip = ("Multiple system prompts for Auto Mode optimization\n"
                              "Use #~ to separate prompts\n"
                              "Example: Prompt1#~((Prompt2))#~Prompt3")
        self.create_hover_tooltip(self.auto_mode_array_tab, auto_mode_tooltip)

        self.system_prompt_text = tk.Text(
            left_frame,
            height=self.ui_config.SYSTEM_PROMPT_HEIGHT,
            width=get_dimension('text_width'),
            font=self.FONTS['code_normal'],
            wrap=tk.WORD,
        )
        self.system_prompt_text.pack(fill=tk.X, pady=(0, 4))
        self.style_text_widget(self.system_prompt_text)
        self.system_prompt_text.bind('<KeyRelease>', lambda e: self.update_json_preview())

        self.system_prompt_llm_content = ""
        self.system_prompt_auto_mode_content = ""
        self.update_tab_appearance()

        ttk.Label(left_frame, text="LLM Input (User Message):", font=self.FONTS['label_bold']).pack(anchor='w')
        self.llm_input_text = tk.Text(
            left_frame,
            height=self.ui_config.LLM_INPUT_HEIGHT,
            width=get_dimension('text_width'),
            font=self.FONTS['code_normal'],
            wrap=tk.WORD,
        )
        self.llm_input_text.pack(fill=tk.X, pady=(0, 2))
        self.style_text_widget(self.llm_input_text)
        self.llm_input_text.bind('<KeyRelease>', lambda e: self.update_json_preview())

        # Right column: LLM Output surface
        output_frame = ttk.Frame(main_container, style='Content.TFrame')
        output_frame.grid(row=0, column=1, sticky='nsew', padx=(8, 0))

        output_header_frame = ttk.Frame(output_frame, style='Content.TFrame')
        output_header_frame.pack(fill=tk.X, anchor='w')
        ttk.Label(output_header_frame, text='LLM Output:', font=self.FONTS['label_bold']).pack(side=tk.LEFT, anchor='w')

        self.show_metadata_checkbox = tk.BooleanVar()
        metadata_checkbox = ttk.Checkbutton(
            output_header_frame,
            text='Show Full Metadata',
            variable=self.show_metadata_checkbox,
            command=self.refresh_output_display,
        )
        metadata_checkbox.pack(side=tk.RIGHT, anchor='e', padx=(10, 0))

        display_width = max(get_dimension('json_width') - 8, 30)

        from .base_components import ThemedScrolledText
        self.llm_output_text = ThemedScrolledText(
            output_frame,
            height=self.ui_config.LLM_OUTPUT_HEIGHT,
            width=display_width,
            font=self.FONTS['code_normal'],
            wrap=tk.WORD,
        )
        self.llm_output_text.pack(fill=tk.BOTH, expand=True, pady=(0, 2))
        self.style_text_widget(self.llm_output_text.text)

        # Main content split (parameters + previews)
        content_container = ttk.Frame(config_tab, style='Content.TFrame')
        content_container.grid(row=1, column=0, sticky='nsew', padx=self.content_pad_x, pady=(4, self.section_pad_y // 2))
        content_container.columnconfigure(0, weight=1)

        split_frame = ttk.Frame(content_container, style='Content.TFrame')
        split_frame.pack(fill=tk.BOTH, expand=True)
        split_frame.columnconfigure(0, weight=5, uniform='api_content')
        split_frame.columnconfigure(1, weight=3, uniform='api_content')
        split_frame.rowconfigure(0, weight=1)

        left_column = ttk.Frame(split_frame, style='Content.TFrame')
        left_column.grid(row=0, column=0, sticky='nsew', padx=(0, self.content_pad_x // 2))
        self.create_scrollable_parameters(left_column)

        right_column = ttk.Frame(split_frame, style='Content.TFrame')
        right_column.grid(row=0, column=1, sticky='nsew', padx=(self.content_pad_x // 2, 0))
        right_column.columnconfigure(0, weight=1)
        right_column.rowconfigure(0, weight=3)
        right_column.rowconfigure(1, weight=2)

        json_frame = ttk.Frame(right_column, style='Content.TFrame')
        json_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 3))
        ttk.Label(json_frame, text='JSON Preview (API-Ready)', font=self.FONTS['label_bold']).pack(anchor='w')
        self.json_text = ThemedScrolledText(
            json_frame,
            height=self.ui_config.JSON_PREVIEW_HEIGHT,
            width=display_width,
            font=self.FONTS['json_preview'],
        )
        self.json_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.style_text_widget(self.json_text.text)

        slots_frame = ttk.Frame(right_column, style='Content.TFrame')
        slots_frame.grid(row=1, column=0, sticky='nsew', pady=(3, 0))
        ttk.Label(slots_frame, text='/slots Endpoint Response', font=self.FONTS['label_bold']).pack(anchor='w')
        self.slots_text = ThemedScrolledText(
            slots_frame,
            height=self.ui_config.SLOTS_DISPLAY_HEIGHT,
            width=display_width,
            font=self.FONTS['json_preview'],
        )
        self.slots_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.style_text_widget(self.slots_text.text)
        self.slots_text.insert('1.0', "No API call made yet - click 'Test Current Config'")
        self.slots_text.config(state=tk.DISABLED)

        button_container = ttk.Frame(config_tab, style='Content.TFrame')
        # Reduce bottom padding so the footer sits closer to the window edge (~5px)
        button_container.grid(
            row=2,
            column=0,
            sticky='ew',
            padx=self.content_pad_x,
            pady=(0, 5)
        )
        self.create_control_buttons(button_container)

        self.update_json_preview()
        self.update_parameter_count()
        
    def create_scrollable_parameters(self, parent):
        """Create scrollable area for parameter configuration"""
        # Create label for parameter section
        ttk.Label(parent, text="Parameter Configuration", font=self.FONTS['label_bold']).pack(anchor="w", pady=(0, 5))
        
        # Create scrollable frame
        main_frame, canvas, self.scrollable_frame = self.scroll_manager.create_scrollable_frame(parent)
        
        # Add parameter count label
        count_frame = ttk.Frame(parent)
        count_frame.pack(fill=tk.X, pady=(5, 0))
        self.param_count_label = ttk.Label(count_frame, text="Parameters: 0 enabled / 0 total", font=self.FONTS['label_small'])
        self.param_count_label.pack(anchor="w")
        
        # Configure the scrollable frame's grid columns to prevent excessive stretching
        # Row frames will handle individual parameter layout
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        
        # Create compact parameter rows
        row = 0
        for category_name, category_params in self.config.schema.items():
            # Category header
            header_frame = ttk.Frame(self.scrollable_frame)
            header_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(5, 2))
            
            ttk.Label(header_frame, text=f"--- {category_name.upper()} ---", 
                     font=self.FONTS['label_bold'], foreground=self.COLORS['blue_text']).pack(anchor="w")
            row += 1
            
            for param_name, param_def in category_params.items():
                self.create_simple_api_parameter_row(row, param_name, param_def)
                row += 1
        
        return main_frame
    
    

    def create_simple_api_parameter_row(self, row: int, param_name: str, param_def: Dict[str, Any]):
        """Create a simple API parameter row with direct parameter name and text field"""
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.grid(row=row, column=0, sticky="ew", pady=1)
        row_frame.grid_columnconfigure(0, weight=0, minsize=220)  # Parameter name
        row_frame.grid_columnconfigure(1, weight=1)  # Value input expands

        name_label = ttk.Label(row_frame, text=param_name, font=self.FONTS['label_normal'])
        name_label.grid(row=0, column=0, padx=(5, 10), sticky="w")

        param_type = param_def.get("type", "string")
        array_help_text = ("Use #~ to separate array values for Auto Mode optimization\n"
                          "Example: value1#~value2#~value3")

        def _create_array_entry(parent, column: int, *, padx=(6, 0)):
            parent.grid_columnconfigure(column, weight=1)
            array_entry = ttk.Entry(parent, font=self.FONTS['code_small'], width=32)
            current_array = getattr(self.config, 'array_values', {}).get(param_name, "")
            if current_array:
                array_entry.insert(0, str(current_array))
            array_entry.grid(row=0, column=column, sticky='ew', padx=padx)
            array_entry.bind('<KeyRelease>', lambda e: self.on_array_parameter_changed(param_name, array_entry.get()))
            self.create_hover_tooltip(array_entry, array_help_text)
            return array_entry

        if param_type == "sequence":
            container_frame = ttk.Frame(row_frame)
            container_frame.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            container_frame.grid_columnconfigure(0, weight=1)
            container_frame.grid_columnconfigure(1, weight=1)

            entry_widget = ttk.Entry(container_frame, font=self.FONTS['code_small'])
            current_value = self.config.values.get(param_name, param_def.get("default", ""))
            if current_value:
                entry_widget.insert(0, str(current_value))
            entry_widget.grid(row=0, column=0, sticky='ew', padx=(0, 6))

            array_entry = _create_array_entry(container_frame, 1, padx=(0, 0))

            preview_frame = ttk.Frame(row_frame)
            preview_frame.grid(row=1, column=1, padx=(0, 10), pady=(2, 0), sticky='ew')
            preview_frame.grid_columnconfigure(0, weight=1)
            preview_label = ttk.Label(
                preview_frame,
                text="",
                font=self.FONTS['code_small'],
                foreground=self.COLORS.get('text_secondary', 'gray')
            )
            preview_label.grid(row=0, column=0, sticky='w')

            def update_preview():
                seq = entry_widget.get().strip()
                if seq:
                    samplers = [s.strip() for s in seq.split(',') if s.strip()]
                    preview_label.config(text=f"-> Sending: {json.dumps(samplers)}")
                else:
                    preview_label.config(text="-> No samplers (will use defaults)")

            def handle_sequence_change(event=None):
                self.on_simple_api_parameter_changed(param_name, entry_widget.get())
                update_preview()

            entry_widget.bind('<KeyRelease>', handle_sequence_change)
            update_preview()
            value_widget = (entry_widget, array_entry)

        elif param_type == "bool":
            container_frame = ttk.Frame(row_frame)
            container_frame.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            container_frame.grid_columnconfigure(0, weight=0)
            container_frame.grid_columnconfigure(1, weight=1)

            button_frame = ttk.Frame(container_frame)
            button_frame.grid(row=0, column=0, sticky='w')

            button_var = tk.IntVar()
            current_enabled = bool(self.config.enabled.get(param_name, False))
            raw_value = self.config.values.get(param_name)

            def _coerce_bool(value, default=True):
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "1", "yes", "on"}:
                        return True
                    if lowered in {"false", "0", "no", "off"}:
                        return False
                if isinstance(value, (int, float)):
                    return bool(value)
                return bool(default)

            if not current_enabled:
                button_var.set(0)
            else:
                default_value = param_def.get("default", True)
                bool_value = _coerce_bool(raw_value, default=default_value)
                button_var.set(1 if bool_value else 2)

            def _bind_bool(state):
                return lambda pn=param_name, st=state: self.on_boolean_parameter_changed(pn, st)

            ttk.Radiobutton(
                button_frame,
                text="Disabled",
                variable=button_var,
                value=0,
                command=_bind_bool(0)
            ).grid(row=0, column=0, padx=(0, 4))
            ttk.Radiobutton(
                button_frame,
                text="Send:True",
                variable=button_var,
                value=1,
                command=_bind_bool(1)
            ).grid(row=0, column=1, padx=(0, 4))
            ttk.Radiobutton(
                button_frame,
                text="Send:False",
                variable=button_var,
                value=2,
                command=_bind_bool(2)
            ).grid(row=0, column=2, padx=(0, 4))

            button_frame.button_var = button_var

            array_entry = _create_array_entry(container_frame, 1)
            value_widget = (button_frame, array_entry)

        else:
            value_widget = None
            if param_type in ["int", "float", "enum", "string", "object", "sequence", "array"]:
                container_frame = ttk.Frame(row_frame)
                container_frame.grid(row=0, column=1, padx=(0, 10), sticky="ew")
                container_frame.grid_columnconfigure(0, weight=1)
                container_frame.grid_columnconfigure(1, weight=1)

                entry_widget = ttk.Entry(container_frame, font=self.FONTS['code_small'])
                current_value = self.config.values.get(param_name, "")
                if current_value:
                    entry_widget.insert(0, str(current_value))
                entry_widget.grid(row=0, column=0, sticky='ew', padx=(0, 6))
                entry_widget.bind('<KeyRelease>', lambda e: self.on_simple_api_parameter_changed(param_name, entry_widget.get()))

                array_entry = _create_array_entry(container_frame, 1, padx=(0, 0))
                value_widget = (entry_widget, array_entry)
            else:
                entry_widget = ttk.Entry(row_frame, font=self.FONTS['code_small'])
                current_value = self.config.values.get(param_name, "")
                if current_value:
                    entry_widget.insert(0, str(current_value))
                entry_widget.grid(row=0, column=1, padx=(0, 10), sticky='ew')
                entry_widget.bind('<KeyRelease>', lambda e: self.on_simple_api_parameter_changed(param_name, entry_widget.get()))
                value_widget = entry_widget

        self.create_comprehensive_tooltip(name_label, param_name, param_def)
        self.widgets[param_name] = {
            "widget": value_widget,
            "definition": param_def
        }

    def create_comprehensive_tooltip(self, widget, param_name: str, param_def: Dict[str, Any]):
        """Create simple tooltip using parameter description"""
        tooltip_text = param_def.get('tooltip', f'No description available for {param_name}')
        self.create_hover_tooltip(widget, tooltip_text)
    
    
    def on_simple_api_parameter_changed(self, param_name: str, value):
        """Handle changes to simple UI API parameters"""
        # Get parameter definition from config manager
        param_def = self.config.get_parameter_info(param_name)
        param_type = param_def.get("type", "string")
        
        if param_type == "bool":
            # Boolean parameters now use 3-button system, this shouldn't be called
            pass
        else:
            # Non-boolean: if has value = enabled + send, if empty = disabled + don't send
            if value and str(value).strip():
                self.config.enabled[param_name] = True
                
                # Convert to proper type - exactly as if typed manually in JSON
                if param_type == "int":
                    try:
                        self.config.values[param_name] = int(value)
                    except ValueError:
                        self.config.values[param_name] = value  # Keep as-is if invalid
                elif param_type == "float":
                    try:
                        self.config.values[param_name] = float(value)
                    except ValueError:
                        self.config.values[param_name] = value  # Keep as-is if invalid
                else:
                    self.config.values[param_name] = value
            else:
                self.config.enabled[param_name] = False
                self.config.values[param_name] = ""
        
        # Update JSON preview
        self.update_json_preview()
        self.update_parameter_count()
    
    def on_boolean_parameter_changed(self, param_name: str, state: int):
        """Handle 3-button boolean parameter changes
        Args:
            param_name: Parameter name 
            state: 0=Disabled, 1=Send:True, 2=Send:False
        """
        if state == 0:
            # Disabled: don't send parameter at all
            self.config.enabled[param_name] = False
            self.config.values[param_name] = None
        elif state == 1:
            # Send:True: enable parameter and set value to True
            self.config.enabled[param_name] = True
            self.config.values[param_name] = True
        elif state == 2:
            # Send:False: enable parameter and set value to False
            self.config.enabled[param_name] = True
            self.config.values[param_name] = False
        
        # Update JSON preview
        self.update_json_preview()
        self.update_parameter_count()
    
    def on_array_parameter_changed(self, param_name: str, value: str):
        """Handle changes to array input fields (for Auto Mode feature)
        Args:
            param_name: Parameter name (e.g., "temperature")
            value: Array string value (e.g., "0.2#~((0.4))#~0.8#~1.0")
        """
        # Store array value as-is (no parsing or validation for now)
        # This is just for storage - Auto Mode will handle parsing later
        if not hasattr(self.config, 'array_values'):
            self.config.array_values = {}
        
        self.config.array_values[param_name] = value.strip()
        
        # Note: We don't update JSON preview or affect API calls
        # Array values are "ghosted" for now and consumed by Auto Mode
    
    def switch_system_prompt_mode(self, mode: str):
        """Switch between LLM Input and ACO Array modes for system prompt"""
        if mode == self.system_prompt_mode.get():
            return  # Already in this mode
        
        # Save current content before switching
        current_content = self.system_prompt_text.get("1.0", tk.END)[:-1]  # Remove extra \n
        if self.system_prompt_mode.get() == "llm_input":
            self.system_prompt_llm_content = current_content
        else:
            self.system_prompt_auto_mode_content = current_content
        
        # Switch mode
        self.system_prompt_mode.set(mode)
        
        # Load content for new mode
        if mode == "llm_input":
            new_content = self.system_prompt_llm_content
        else:
            new_content = self.system_prompt_auto_mode_content
        
        # Update text area
        self.system_prompt_text.delete("1.0", tk.END)
        if new_content:
            self.system_prompt_text.insert("1.0", new_content)
        
        # Update tab appearance
        self.update_tab_appearance()
        
        # Update JSON preview
        self.update_json_preview()
    
    def update_tab_appearance(self):
        """Update tab button appearance based on current mode"""
        current_mode = self.system_prompt_mode.get()
        
        # Configure active/inactive tab styles (using tkinter styling approach)
        if current_mode == "llm_input":
            try:
                self.llm_input_tab.configure(state="disabled")  # Active tab appears pressed
                self.auto_mode_array_tab.configure(state="normal")
            except:
                pass  # Fallback if styling not available
        else:
            try:
                self.llm_input_tab.configure(state="normal") 
                self.auto_mode_array_tab.configure(state="disabled")  # Active tab appears pressed
            except:
                pass  # Fallback if styling not available
    
    def save_current_system_prompt_content(self):
        """Save current system prompt content to the appropriate storage"""
        current_content = self.system_prompt_text.get("1.0", tk.END)[:-1]  # Remove extra \n
        if self.system_prompt_mode.get() == "llm_input":
            self.system_prompt_llm_content = current_content
        else:
            self.system_prompt_auto_mode_content = current_content
    
    def create_control_buttons(self, parent):
        """Create control buttons for configuration management"""
        button_frame = ttk.Frame(parent, style='Content.TFrame')
        # Remove extra bottom padding so the footer sits near the frame edge
        button_frame.pack(fill=tk.X, pady=(0, 0))
        button_frame.columnconfigure(0, weight=1)

        left_group = ttk.Frame(button_frame, style='Content.TFrame')
        left_group.grid(row=0, column=0, sticky='w')

        ttk.Button(left_group, text="Save Config", command=self.save_config).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(left_group, text="Load Config", command=self.load_config).grid(row=0, column=1, padx=5)
        ttk.Button(left_group, text="Reset", command=self.reset_to_defaults).grid(row=0, column=2, padx=5)

        ttk.Button(button_frame, text="Test Current Config", command=self.test_connection,
                  style="Accent.TButton").grid(row=0, column=1, sticky='e', padx=(12, 0))


    def update_json_preview(self):
        """Update the JSON preview with current configuration"""
        try:
            # Build API payload
            api_payload = self.config.get_api_payload()
            
            # Build proper messages array with system and user messages
            # No stripping - preserve exact content including trailing newlines
            system_prompt = self.system_prompt_text.get("1.0", tk.END)[:-1] if self.system_prompt_text else ""  # [:-1] removes the extra \n that tk.END adds
            user_message = self.llm_input_text.get("1.0", tk.END)[:-1] if self.llm_input_text else ""  # [:-1] removes the extra \n that tk.END adds
            
            # Build messages array in correct format for llama.cpp
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            if user_message:
                messages.append({"role": "user", "content": user_message})
            
            if messages:
                api_payload["messages"] = messages
            
            # Format as JSON
            json_str = json.dumps(api_payload, indent=2)
            
            # Update JSON preview
            if self.json_text:
                self.json_text.delete("1.0", tk.END)
                self.json_text.insert("1.0", json_str)
                
        except Exception as e:
            if self.json_text:
                self.json_text.delete("1.0", tk.END)
                self.json_text.insert("1.0", f"Error generating JSON: {e}")
    
    def update_parameter_count(self):
        """Update parameter count display"""
        enabled_count = sum(1 for enabled in self.config.enabled.values() if enabled)
        total_count = len(self.config.enabled)
        
        if self.param_count_label:
            self.param_count_label.config(text=f"Parameters: {enabled_count} enabled / {total_count} total")
    
    def save_config(self):
        """Save current configuration to a file"""
        try:
            filename = self.ask_save_file(
                title="Save Configuration",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=self.config.save_dir
            )
            
            if filename:
                # Save config with system prompt and user message
                # No stripping - preserve exact content including trailing newlines
                # Save current system prompt content before getting it
                self.save_current_system_prompt_content()
                system_prompt = self.system_prompt_llm_content  # Always save LLM Input content for regular use
                user_message = self.llm_input_text.get("1.0", tk.END)[:-1] if self.llm_input_text else ""  # [:-1] removes the extra \n that tk.END adds
                
                # BUGFIX: Copy system prompt ACO content to array_values section where ACO extraction expects it
                if self.system_prompt_auto_mode_content.strip():
                    self.config.array_values["system_prompt_auto_mode"] = self.system_prompt_auto_mode_content
                else:
                    # Remove from array_values if empty (important for clearing old values)
                    self.config.array_values.pop("system_prompt_auto_mode", None)
                
                # Save directly to user-selected path
                config_data = {
                    "values": self.config.values,
                    "enabled": self.config.enabled,
                    "array_values": self.config.array_values,
                    "system_prompt": system_prompt,
                    "system_prompt_auto_mode": self.system_prompt_auto_mode_content,  # NEW: Save Auto Mode array content
                    "user_input": user_message,
                    "api_payload": self.config.get_api_payload()
                }
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2)
                
                # Save as last used config via ParameterConfig manager
                config_name = os.path.splitext(os.path.basename(filename))[0]
                self.config.save_last_config(config_name)
                
                messagebox.showinfo("Success", f"Configuration saved to {filename}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {e}")
    
    def load_config(self):
        """Load configuration from a file"""
        try:
            filename = self.ask_open_file(
                title="Load Configuration",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=self.config.save_dir
            )
            
            if filename:
                with open(filename, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                # Content-based validation: ensure this is an API Parameters config
                try:
                    from utils.config_utils import detect_config_kind
                    kind = detect_config_kind(config_data)
                except Exception:
                    kind = 'unknown'
                if kind != 'api':
                    messagebox.showerror(
                        "Invalid File",
                        f"Selected file is not an API Parameters configuration:\n{os.path.basename(filename)}"
                    )
                    return
                
                # Load configuration
                self.config.enabled = config_data.get("enabled", {})
                self.config.values = config_data.get("values", {})
                self.config.array_values = config_data.get("array_values", {})  # NEW: Load array values
                
                # NOTE: API client connection settings now come from server config
                # No longer loading api_settings from API config files
                
                # Load prompts if available
                if "system_prompt" in config_data and self.system_prompt_text:
                    # Load regular system prompt
                    self.system_prompt_llm_content = config_data["system_prompt"]
                    
                    # BUGFIX: Load ACO system prompt from BOTH possible locations for compatibility with Auto Mode
                    # First check array_values (new location after fix)
                    if "system_prompt_auto_mode" in config_data.get("array_values", {}):
                        self.system_prompt_auto_mode_content = config_data["array_values"]["system_prompt_auto_mode"]
                    # Fallback to top level (old location for backward compatibility)
                    elif "system_prompt_auto_mode" in config_data:
                        self.system_prompt_auto_mode_content = config_data["system_prompt_auto_mode"]
                    # If not found anywhere, clear it
                    else:
                        self.system_prompt_auto_mode_content = ""
                    
                    # Update current display based on active mode
                    if self.system_prompt_mode.get() == "llm_input":
                        self.system_prompt_text.delete("1.0", tk.END)
                        self.system_prompt_text.insert("1.0", self.system_prompt_llm_content)
                    else:
                        self.system_prompt_text.delete("1.0", tk.END)
                        self.system_prompt_text.insert("1.0", self.system_prompt_auto_mode_content)
                
                # Try both "user_message" (old format) and "user_input" (new ParameterConfig format)
                # Always update field, even when empty, to avoid stale UI state
                user_content = config_data.get("user_input", config_data.get("user_message", ""))
                if self.llm_input_text:
                    self.llm_input_text.delete("1.0", tk.END)
                    if user_content is not None:
                        self.llm_input_text.insert("1.0", user_content)
                
                # Save as last used config via ParameterConfig manager
                config_name = os.path.splitext(os.path.basename(filename))[0]
                self.config.save_last_config(config_name)
                
                # Refresh UI
                self.refresh_ui()
                messagebox.showinfo("Success", f"Configuration loaded from {filename}")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")
    
    def reset_to_defaults(self):
        """Reset all parameters to default values"""
        self.config.reset_to_defaults()
        self.refresh_ui()
    
    def refresh_ui(self, system_prompt: str = None, user_input: str = None):
        """Refresh UI to reflect current configuration state"""
        # Update prompt text areas if provided
        if system_prompt is not None and self.system_prompt_text:
            self.system_prompt_text.delete("1.0", tk.END)
            self.system_prompt_text.insert("1.0", system_prompt)
        
        if user_input is not None and self.llm_input_text:
            self.llm_input_text.delete("1.0", tk.END)
            self.llm_input_text.insert("1.0", user_input)
        
        # Update all parameter widgets - simple UI version
        for param_name, widget_info in self.widgets.items():
            # No toggle in simple UI - just update value widget
            value = self.config.values.get(param_name, "")
            widget = widget_info["widget"]
            
            # Update value widget based on type
            param_def = widget_info["definition"]
            param_type = param_def.get("type", "string")
            
            if param_type == "bool":
                def _coerce_bool(value, default=True):
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        lowered = value.strip().lower()
                        if lowered in {"true", "1", "yes", "on"}:
                            return True
                        if lowered in {"false", "0", "no", "off"}:
                            return False
                    if isinstance(value, (int, float)):
                        return bool(value)
                    return bool(default)

                if isinstance(widget, tuple):
                    button_frame, array_entry = widget
                    button_var = getattr(button_frame, 'button_var', None)
                    current_enabled = bool(self.config.enabled.get(param_name, False))
                    raw_value = self.config.values.get(param_name)
                    default_value = param_def.get("default", True)

                    if button_var is not None:
                        if not current_enabled:
                            button_var.set(0)
                        else:
                            bool_value = _coerce_bool(raw_value, default=default_value)
                            button_var.set(1 if bool_value else 2)

                    array_value = getattr(self.config, 'array_values', {}).get(param_name, "")
                    array_entry.delete(0, tk.END)
                    if array_value:
                        array_entry.insert(0, str(array_value))
                elif hasattr(widget, 'button_var'):
                    button_var = widget.button_var
                    current_enabled = bool(self.config.enabled.get(param_name, False))
                    raw_value = self.config.values.get(param_name)
                    default_value = param_def.get("default", True)

                    if not current_enabled:
                        button_var.set(0)
                    else:
                        bool_value = _coerce_bool(raw_value, default=default_value)
                        button_var.set(1 if bool_value else 2)
            elif isinstance(widget, ttk.Entry):
                widget.delete(0, tk.END)
                widget.insert(0, str(value))
            elif isinstance(widget, tuple):
                # Special handling for parameters with array fields (int/float/enum/string/object/sequence/array)
                entry_widget, array_entry = widget
                
                # Update regular value field
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, str(value))
                
                # Update array field
                array_value = getattr(self.config, 'array_values', {}).get(param_name, "")
                array_entry.delete(0, tk.END)
                if array_value:
                    array_entry.insert(0, str(array_value))
                
                # Special handling for sequence parameters: update preview
                if param_def.get("type") == "sequence":
                    self._update_sequence_preview(param_name, entry_widget)
        
        # Update displays
        self.update_json_preview()
        self.update_parameter_count()
        
        # Simplified refresh - no indicators to update
    
    def _update_sequence_preview(self, param_name: str, entry_widget):
        """Update preview label for sequence parameters"""
        try:
            # Find the parent frame containing both entry and preview label
            parent_frame = entry_widget.master
            
            # Find the preview label (should be the second widget in the frame)
            for widget in parent_frame.winfo_children():
                if isinstance(widget, ttk.Label) and hasattr(widget, 'grid_info'):
                    grid_info = widget.grid_info()
                    if grid_info and grid_info.get('row') == 1:  # Preview label is on row 1
                        # Update preview using same logic as during creation
                        seq = entry_widget.get().strip()
                        if seq:
                            samplers = [s.strip() for s in seq.split(',') if s.strip()]
                            preview_text = f"-> Sending: {json.dumps(samplers)}"
                            widget.config(text=preview_text)
                        else:
                            widget.config(text="-> No samplers (will use defaults)")
                        break
        except Exception as e:
            self.log_warning(f"Could not update sequence preview for {param_name}: {e}")
    
    def on_endpoint_changed(self, endpoint_type: str):
        """Handle endpoint type change notification"""
        # Update any UI elements that might need to reflect the endpoint change
        # For now, just update the JSON preview in case it needs to change format
        self.update_json_preview()
    
    def test_connection(self):
        """Test connection to LLM server and send current config"""
        if not self.llm_output_text:
            messagebox.showwarning("Warning", "LLM output area not available")
            return
            
        
        self.llm_output_text.delete("1.0", tk.END)
        
        def run_test():
            try:
                self.llm_output_text.insert("1.0", "Testing configuration...\n")
                if hasattr(self.parent, 'root'):
                    self.parent.root.update()
                
                # Cache server configuration to avoid redundant calls
                if not hasattr(self.parent, 'server_config'):
                    error_msg = "[ERROR] No server configuration available - cannot determine server URL\n\nPlease configure and start server in Server Config tab first."
                    self.llm_output_text.delete("1.0", tk.END)
                    self.llm_output_text.insert("1.0", error_msg)
                    return
                
                # Get configuration values once
                server_url = self.parent.server_config.get_server_url()
                timeouts = self.parent.server_config.get_connection_timeouts()
                self.log_info(f"Using server URL from configuration: {server_url}")

                # Configure client and use unified health check
                self.api_client.configure(
                    base_url=server_url,
                    timeout=timeouts['connection_timeout'],
                    request_timeout=timeouts['request_timeout']
                )
                ok, msg = self.api_client.health_check()

                if not ok:
                    self.llm_output_text.insert(tk.END, f"Server not running - attempting auto-start...\n")
                    if hasattr(self.parent, 'root'):
                        self.parent.root.update()
                    
                    if not self._auto_start_server(server_url):
                        return
                    
                    # Verify health after auto-start
                    ok, msg = self.api_client.health_check()
                    self.llm_output_text.insert(tk.END, f"API client configured for {server_url}\n")
                    self.log_info(f"API client configured after auto-start: {server_url}")
                    if not ok:
                        error_msg = f"[ERROR] Auto-started server failed health check"
                        self.llm_output_text.delete("1.0", tk.END)
                        self.llm_output_text.insert("1.0", error_msg)
                        return
                else:
                    self.log_info(f"API client configured for inference: {server_url}")
                
                self.llm_output_text.insert(tk.END, "[OK] Server connected! Running inference...\n\n")
                if hasattr(self.parent, 'root'):
                    self.parent.root.update()
                
                import time
                start_time = time.time()
                
                # Get current configuration and build proper messages array
                # No stripping - preserve exact content including trailing newlines
                system_msg = self.system_prompt_text.get("1.0", tk.END)[:-1] if self.system_prompt_text else ""  # [:-1] removes the extra \n that tk.END adds
                user_msg = self.llm_input_text.get("1.0", tk.END)[:-1] if self.llm_input_text else ""  # [:-1] removes the extra \n that tk.END adds
                
                # Get current endpoint type
                endpoint_type = self.parent.get_current_endpoint_type()
                
                if endpoint_type == "completions":
                    # Text completions - raw text continuation without any formatting
                    # Just send whatever text the user provides and let the model continue it
                    prompt = user_msg if user_msg else ""
                    # Note: System prompts don't really apply to raw text completions
                    
                    # Get API payload without adding any defaults
                    api_payload = self.config.get_api_payload(False)
                    
                    # Use unified endpoint call (raw text completions)
                    content = prompt
                    success, details = self.api_client.unified_completion(endpoint_type, content, api_payload)
                else:
                    # Build messages array for /v1/chat/completions
                    messages = []
                    if system_msg:
                        messages.append({"role": "system", "content": system_msg})
                    if user_msg:
                        messages.append({"role": "user", "content": user_msg})
                    
                    # Use unified endpoint call (chat completions)
                    content = messages
                    success, details = self.api_client.unified_completion(endpoint_type, content, self.config.get_api_payload(False))
                
                if success:
                    try:
                        if endpoint_type == "completions":
                            # Extract text from /v1/completions response
                            response = details['choices'][0]['text']
                        else:
                            # Extract content from /v1/chat/completions response
                            response = details['choices'][0]['message']['content']
                    except (KeyError, IndexError) as e:
                        success = False
                        response = f"Error extracting response from API result: {str(e)}"
                        details = {"error": f"Invalid response format for {endpoint_type} endpoint: {str(e)}"}
                else:
                    response = details.get('error', 'Unknown error')
                
                end_time = time.time()
                response_time = end_time - start_time
                
                if success:
                    # Store full response details for metadata display
                    self.current_response_details = details
                    
                    # Display based on checkbox state
                    self.refresh_output_display()
                    
                    # Update /slots display after successful API call
                    self.update_slots_display()
                else:
                    # Clear stored details on error
                    self.current_response_details = None
                    
                    self.llm_output_text.delete("1.0", tk.END)
                    self.llm_output_text.insert("1.0", f"[ERROR] Request failed: {response}")
                    
                    # Still try to update /slots display to show server state
                    self.update_slots_display()
                    
            except Exception as e:
                self.llm_output_text.insert(tk.END, f"[ERROR] Test error: {str(e)}")
        
        # Run in thread to avoid blocking UI
        import threading
        threading.Thread(target=run_test, daemon=True).start()
    
    def _auto_start_server(self, server_url: str = None) -> bool:
        """
        Attempt to auto-start server using last loaded server config
        
        Args:
            server_url: Pre-cached server URL to avoid redundant config calls
        
        Returns:
            bool: True if server started successfully, False if failed
        """
        try:
            # Check if we have access to server config
            if not hasattr(self.parent, 'server_config'):
                error_msg = "[ERROR] Cannot auto-start server: No server configuration available.\n\nPlease start server in Server Config tab first."
                self.llm_output_text.delete("1.0", tk.END)
                self.llm_output_text.insert("1.0", error_msg)
                return False
            
            server_config = self.parent.server_config
            
            # Try to auto-load last used server config
            self.llm_output_text.insert(tk.END, "Loading last used server configuration...\n")
            if hasattr(self.parent, 'root'):
                self.parent.root.update()
                
            if not server_config.auto_load_last_config():
                error_msg = "[ERROR] Cannot auto-start server: No server configuration was previously loaded.\n\nPlease load and start a server configuration in the Server Config tab first."
                self.llm_output_text.delete("1.0", tk.END)
                self.llm_output_text.insert("1.0", error_msg)
                return False
            
            # Generate server command
            self.llm_output_text.insert(tk.END, "Starting server with loaded configuration...\n")
            if hasattr(self.parent, 'root'):
                self.parent.root.update()
                
            command = server_config.generate_server_command()
            if not command:
                error_msg = "[ERROR] Cannot start server: No executable path configured.\n\nPlease configure server executable in Server Config tab."
                self.llm_output_text.delete("1.0", tk.END)
                self.llm_output_text.insert("1.0", error_msg)
                return False
            
            from utils.server_manager import cleanup_all_servers
            cleanup_all_servers()
            
            # Start server
            import subprocess
            import time
            
            self.llm_output_text.insert(tk.END, f"Launching server...\n")
            if hasattr(self.parent, 'root'):
                self.parent.root.update()
            
            server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Wait for server to become ready (with timeout)
            self.llm_output_text.insert(tk.END, "Waiting for server to start...\n")
            if hasattr(self.parent, 'root'):
                self.parent.root.update()
            
            # Use cached server_url if provided, otherwise get from config
            if server_url is None:
                server_url = server_config.get_server_url()
            # Configure API client for health checks
            timeouts = server_config.get_connection_timeouts()
            self.api_client.configure(
                base_url=server_url,
                timeout=timeouts['connection_timeout'],
                request_timeout=timeouts['request_timeout']
            )
            # No arbitrary startup timeout - wait for server to actually respond
            start_time = time.time()
            
            # Wait for server startup - no artificial timeout limit
            max_attempts = 150  # 150 attempts * 2s = 5min maximum (reasonable for very large models)
            attempt = 0
            while attempt < max_attempts:
                # Check if process is still running
                if server_process.poll() is not None:
                    error_msg = "[ERROR] Server process terminated during startup.\n\nCheck server configuration and model path."
                    self.llm_output_text.delete("1.0", tk.END)
                    self.llm_output_text.insert("1.0", error_msg)
                    return False
                
                # Try health check via unified client
                ok, _ = self.api_client.health_check()
                if ok:
                    self.llm_output_text.insert(tk.END, f"Server started successfully at {server_url}\n")
                    return True
                
                # Brief pause before next check
                time.sleep(2)
                attempt += 1
            
            # Timeout - kill the server we started
            try:
                server_process.terminate()
                server_process.wait(timeout=3)
            except:
                pass
            
            error_msg = f"[ERROR] Server failed to start after {max_attempts} health check attempts.\n\nCheck server configuration and try starting manually in Server Config tab."
            self.llm_output_text.delete("1.0", tk.END)
            self.llm_output_text.insert("1.0", error_msg)
            return False
            
        except Exception as e:
            error_msg = f"[ERROR] Failed to auto-start server: {str(e)}\n\nPlease start server manually in Server Config tab."
            self.llm_output_text.delete("1.0", tk.END)
            self.llm_output_text.insert("1.0", error_msg)
            return False
    
    def refresh_output_display(self):
        """Refresh LLM output display based on metadata checkbox state"""
        if not self.llm_output_text or not self.current_response_details:
            return
            
        self.llm_output_text.delete("1.0", tk.END)
        
        # Reset thinking block states for new response
        self._thinking_states = {}
        
        if self.show_metadata_checkbox.get():
            # Show RAW server response as received (before any parsing)
            try:
                if '_raw_server_response' in self.current_response_details:
                    # Show the actual raw JSON string from server
                    raw_server_response = self.current_response_details['_raw_server_response']
                    self.llm_output_text.insert("1.0", raw_server_response)
                else:
                    # Fallback to formatted dict if raw response not available
                    import json
                    fallback_display = json.dumps(self.current_response_details, indent=2, ensure_ascii=False)
                    self.llm_output_text.insert("1.0", fallback_display)
            except Exception as e:
                self.llm_output_text.insert("1.0", f"Error displaying raw metadata: {str(e)}")
        else:
            # Show clean response text with collapsible thinking sections
            if self.current_response_details:
                try:
                    # Get current endpoint type to extract response correctly
                    endpoint_type = self.parent.get_current_endpoint_type()
                    
                    if endpoint_type == "completions":
                        # Extract text from /v1/completions response
                        response_text = self.current_response_details['choices'][0]['text']
                    else:
                        # Extract content from /v1/chat/completions response with GPT-OSS reasoning support
                        message = self.current_response_details['choices'][0]['message']
                        content = message.get('content', '')
                        reasoning = message.get('reasoning_content', '')
                        
                        # Convert GPT-OSS format to <think> format for unified display
                        if reasoning and reasoning.strip():
                            response_text = f"<think>{reasoning}</think>\n{content}"
                        else:
                            response_text = content
                    
                    # Process and insert response with collapsible thinking sections
                    self._insert_response_with_collapsible_thinking(response_text)
                except (KeyError, IndexError, TypeError):
                    self.llm_output_text.insert("1.0", "Error extracting response text from metadata")
    
    def _insert_response_with_collapsible_thinking(self, response_text: str):
        """Insert response text with collapsible <think>...</think> sections"""
        import re
        
        # Find all <think>...</think> blocks
        think_pattern = r'<think>(.*?)</think>'
        think_matches = list(re.finditer(think_pattern, response_text, re.DOTALL))
        
        if not think_matches:
            # No thinking blocks, insert normally
            self.llm_output_text.insert("1.0", response_text)
            return
        
        # Process text with thinking blocks
        current_pos = 0
        thinking_block_id = 0
        
        for match in think_matches:
            thinking_block_id += 1
            
            # Insert text before thinking block
            before_text = response_text[current_pos:match.start()]
            if before_text:
                # If this text comes after a previous thinking block, clean up leading newlines
                if current_pos > 0:  # We've processed content before (likely a thinking block)
                    cleaned_before = before_text.lstrip('\n')
                    if cleaned_before:
                        self.llm_output_text.insert(tk.END, cleaned_before)
                else:
                    # First piece of content - preserve original formatting
                    self.llm_output_text.insert(tk.END, before_text)
            
            # Insert collapsible thinking section
            thinking_content = match.group(1).strip()
            self._insert_collapsible_thinking_block(thinking_content, thinking_block_id)
            
            current_pos = match.end()
        
        # Insert remaining text after last thinking block (clean up leading whitespace)
        remaining_text = response_text[current_pos:]
        if remaining_text:
            # Strip excessive leading newlines but preserve intentional formatting
            cleaned_remaining = remaining_text.lstrip('\n')
            if cleaned_remaining:
                self.llm_output_text.insert(tk.END, cleaned_remaining)
    
    def _insert_collapsible_thinking_block(self, thinking_content: str, block_id: int):
        """Insert a single collapsible thinking block with arrow toggle"""
        # Create unique tag names for this block
        arrow_tag = f"thinking_arrow_{block_id}"
        content_tag = f"thinking_content_{block_id}"
        
        # Insert collapsed arrow (just the symbol)
        arrow_start = self.llm_output_text.index(tk.INSERT)
        self.llm_output_text.insert(tk.END, "[+]\n")
        arrow_end = self.llm_output_text.index(tk.INSERT)
        
        # Insert thinking content (initially hidden) - on new line below arrow
        content_start = self.llm_output_text.index(tk.INSERT)
        self.llm_output_text.insert(tk.END, f"{thinking_content}\n")
        content_end = self.llm_output_text.index(tk.INSERT)
        
        # Configure tags
        self.llm_output_text.tag_add(arrow_tag, arrow_start, arrow_end)
        self.llm_output_text.tag_add(content_tag, content_start, content_end)
        
        # Style the arrow as clickable
        self.llm_output_text.tag_config(arrow_tag, foreground="blue", underline=True)
        
        # Style the thinking content
        self.llm_output_text.tag_config(content_tag, foreground="gray", background="#f0f0f0")
        
        # Hide content initially (collapsed by default)
        self.llm_output_text.tag_config(content_tag, elide=True)
        
        # Bind click event to toggle
        def toggle_thinking(event):
            self._toggle_thinking_block(arrow_tag, content_tag, block_id)
        
        self.llm_output_text.tag_bind(arrow_tag, "<Button-1>", toggle_thinking)
        
        # Store state (collapsed = True initially)
        if not hasattr(self, '_thinking_states'):
            self._thinking_states = {}
        self._thinking_states[block_id] = True  # True = collapsed
    
    def _toggle_thinking_block(self, arrow_tag: str, content_tag: str, block_id: int):
        """Toggle visibility of a thinking block"""
        # Get current state
        is_collapsed = self._thinking_states.get(block_id, True)
        
        if is_collapsed:
            # Expand: show content, change arrow to down
            self.llm_output_text.tag_config(content_tag, elide=False)
            self._update_arrow_text(arrow_tag, "[-]\n")
            self._thinking_states[block_id] = False
        else:
            # Collapse: hide content, change arrow to right
            self.llm_output_text.tag_config(content_tag, elide=True)
            self._update_arrow_text(arrow_tag, "[+]\n")
            self._thinking_states[block_id] = True
    
    def _update_arrow_text(self, arrow_tag: str, new_text: str):
        """Update the text of an arrow element"""
        # Get the range of the arrow tag
        ranges = self.llm_output_text.tag_ranges(arrow_tag)
        if ranges:
            start, end = ranges[0], ranges[1]
            # Replace the text while preserving the tag
            self.llm_output_text.delete(start, end)
            self.llm_output_text.insert(start, new_text)
            # Reapply the tag to the new text
            new_end = f"{start} + {len(new_text)}c"
            self.llm_output_text.tag_add(arrow_tag, start, new_end)
    
    def update_slots_display(self):
        """Update the /slots endpoint display with current server state and validation"""
        if not self.slots_text:
            return
            
        def fetch_slots_and_validate():
            try:
                # Update display to show loading state
                self.slots_text.config(state=tk.NORMAL)
                self.slots_text.delete("1.0", tk.END)
                self.slots_text.insert("1.0", "Fetching /slots data...")
                self.slots_text.config(state=tk.DISABLED)
                
                
                if hasattr(self.parent, 'root'):
                    self.parent.root.update()
                
                # Fetch raw /slots HTTP response
                raw_slots_response = self.api_client.get_slots_info_raw()
                
                if raw_slots_response:
                    # Display raw HTTP response exactly as received from server
                    self.slots_text.config(state=tk.NORMAL)
                    self.slots_text.delete("1.0", tk.END)
                    self.slots_text.insert("1.0", raw_slots_response)
                    self.slots_text.config(state=tk.DISABLED)
                    
                    # Raw HTTP response displayed - no post-processing
                    
                else:
                    # Show error state
                    self.slots_text.config(state=tk.NORMAL)
                    self.slots_text.delete("1.0", tk.END)
                    self.slots_text.insert("1.0", "Unable to fetch /slots data\n(server offline or endpoint unavailable)")
                    self.slots_text.config(state=tk.DISABLED)
                    
                    
            except Exception as e:
                # Handle any errors
                self.slots_text.config(state=tk.NORMAL)
                self.slots_text.delete("1.0", tk.END)
                self.slots_text.insert("1.0", f"Error fetching /slots data:\n{str(e)}")
                self.slots_text.config(state=tk.DISABLED)
                
        
        # Run in thread to avoid blocking UI
        import threading
        threading.Thread(target=fetch_slots_and_validate, daemon=True).start()
    
    def set_scroll_sensitivity(self, sensitivity: int):
        """Update scroll sensitivity"""
        if self.scroll_manager:
            self.scroll_manager.scroll_units_per_wheel = sensitivity



