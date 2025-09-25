"""
Benchmark Runner UI Module
Provides interface for running benchmarks on exported datasets with chain support
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import json
import threading
import time
import re
import hashlib
from datetime import datetime
from typing import Optional, List
from .base_components import BaseUIComponent, ThemedScrolledText
from benchmarking.runner import BenchmarkExecutor, DatasetParser
from .benchmark_helpers import run_benchmark_enhanced_common
from managers.path_manager import app_paths
from managers.benchmark_runner_state import BenchmarkRunnerState
from managers.server_config_manager import ServerConfig
from managers.api_config_manager import ParameterConfig
# Health checks use LLMClient via self.api_client
from utils.config_utils import load_parameter_config_from_file


class BenchmarkRunnerUI(BaseUIComponent):
    """UI for benchmark execution tab"""
    
    # Constants
    INITIAL_PROGRESS_VALUE = 0
    DEFAULT_RUN_NAME = "Run 1"
    INITIAL_RUN_NUMBER = 2
    PROGRESS_SEPARATOR = "-" * 50
    
    def __init__(self, parent, config_manager, api_client):
        super().__init__(parent, config_manager, api_client)
        self.parent = parent
        
        # Initialize benchmark executor (no complex server manager needed)
        self.executor = BenchmarkExecutor(api_client)
        
        # UI state
        self.selected_dataset_path = None
        self.selected_api_config = None
        self.selected_server_config = None
        self.selected_api_config_path = None
        self.selected_server_config_path = None
        self.total_questions = 0
        self.selected_questions = []
        self.current_thread = None
        
        # Chain system state
        self.run_configs = {self.DEFAULT_RUN_NAME: {}}  # Dictionary of run configurations
        self.current_run = self.DEFAULT_RUN_NAME
        self.next_run_number = self.INITIAL_RUN_NUMBER
        
        # File selection persistence handled by ui_state
        
        # UI components
        self.custom_name_entry = None
        self.run_dropdown = None
        self.dataset_label = None
        self.api_config_label = None
        self.server_config_label = None
        self.question_entry = None
        self.status_label = None
        self.chain_progress_bar = None
        self.chain_progress_label = None
        self.start_btn = None
        self.pause_btn = None
        self.stop_btn = None
        self.resume_btn = None
        self.progress_bar = None
        self.progress_label = None
        self.detailed_progress_label = None
        self.status_text = None
        
        # Prompt control UI components
        self.system_prompt_override_var = None
        self.system_prompt_override_entry = None
        self.system_prefix_entry = None
        self.system_suffix_entry = None
        self.user_prefix_entry = None
        self.user_suffix_entry = None
        
        # Use centralized path management
        self.app_paths = app_paths
        
        # Initialize UI state manager
        self.ui_state = BenchmarkRunnerState()
        
        # Ensure directories exist
        os.makedirs(str(app_paths.exported_datasets), exist_ok=True)
        os.makedirs(str(app_paths.server_configs), exist_ok=True)
        os.makedirs(str(app_paths.saved_configs), exist_ok=True)
        os.makedirs(str(app_paths.benchmark_runs), exist_ok=True)
    
    def create_benchmark_runner_tab(self, notebook):
        """Create the Run Benchmark tab with 50/50 split layout"""
        runner_tab = ttk.Frame(notebook)
        notebook.add(runner_tab, text="Run Benchmark")
        
        # Create horizontal split container
        main_container = ttk.Frame(runner_tab, style='Content.TFrame')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left half - scrollable configuration and control sections
        left_container = ttk.Frame(main_container, style='Content.TFrame')
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Create scrollable canvas for left side content
        left_canvas = tk.Canvas(left_container, highlightthickness=0, bd=0,
                                background=self.COLORS.get('surface_bg'))
        left_scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=left_canvas.yview)
        left_scrollable_frame = ttk.Frame(left_canvas)
        
        # Configure scrolling
        left_scrollable_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        )
        
        left_canvas.create_window((0, 0), window=left_scrollable_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        left_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Pack canvas and scrollbar
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")
        
        # Use scrollable_frame as the new left_frame
        left_frame = left_scrollable_frame
        
        # Right side - status display with controlled width (reduce ~30%)
        try:
            _rfw = int(self.DIMENSIONS.get('right_frame_width', 440) * 0.7)
        except Exception:
            _rfw = 308
        right_frame = ttk.Frame(main_container, width=_rfw, style='Content.TFrame')
        # Do not expand: preserve a fixed status column and give more space to the left panel
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(5, 0))
        
        # Dataset and Configuration Section (moved to left frame)
        selection_frame = self.create_section(left_frame, "Benchmark Configuration", padding=5)
        selection_frame.pack(fill=tk.X, pady=(0, 3))
        self.apply_card_padding(selection_frame)
        
        # Run selection dropdown row
        run_selector_row = ttk.Frame(selection_frame)
        run_selector_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(run_selector_row, text="Current Run:", width=12).pack(side=tk.LEFT)
        self.run_dropdown = ttk.Combobox(run_selector_row, values=[self.DEFAULT_RUN_NAME], state="readonly", width=15)
        self.run_dropdown.set(self.DEFAULT_RUN_NAME)
        self.run_dropdown.pack(side=tk.LEFT, padx=(5, 10))
        self.run_dropdown.bind("<<ComboboxSelected>>", self.on_run_changed)
        
        ttk.Button(run_selector_row, text="+ Add", width=8, 
                   command=self.add_run).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(run_selector_row, text="Remove", width=8,
                   command=self.remove_run).pack(side=tk.LEFT)
        
        # Custom run name row
        run_name_row = ttk.Frame(selection_frame)
        run_name_row.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(run_name_row, text="Run Name:", width=12).pack(side=tk.LEFT)
        self.custom_name_entry = ttk.Entry(run_name_row, width=30, font=self.FONTS['code_normal'])
        self.custom_name_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.custom_name_entry.bind('<KeyRelease>', self._on_custom_name_changed)
        ttk.Label(run_name_row, text="(optional prefix)", foreground="gray", 
                  font=self.FONTS['label_small']).pack(side=tk.LEFT)
        
        # Dataset row
        dataset_row = ttk.Frame(selection_frame)
        dataset_row.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Button(dataset_row, text="Browse...", 
                   command=self.browse_dataset).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(dataset_row, text="Dataset File:", width=15).pack(side=tk.LEFT)
        self.dataset_label = ttk.Label(dataset_row, text="No dataset selected", 
                                       foreground="gray", font=self.FONTS['code_normal'])
        self.dataset_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Server Configuration row
        server_config_row = ttk.Frame(selection_frame)
        server_config_row.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Button(server_config_row, text="Browse...", 
                   command=self.browse_server_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(server_config_row, text="Server Config:", width=15).pack(side=tk.LEFT)
        self.server_config_label = ttk.Label(server_config_row, text="No server config selected", 
                                             foreground="gray", font=self.FONTS['code_normal'])
        self.server_config_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # API Configuration row
        api_config_row = ttk.Frame(selection_frame)
        api_config_row.pack(fill=tk.X)
        
        ttk.Button(api_config_row, text="Browse...", 
                   command=self.browse_api_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(api_config_row, text="API Config:", width=15).pack(side=tk.LEFT)
        self.api_config_label = ttk.Label(api_config_row, text="No API config selected (required)", 
                                          foreground="red", font=self.FONTS['code_normal'])
        self.api_config_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # Question Selection Section (moved to left frame)
        question_frame = self.create_section(left_frame, "Question Selection", padding=5)
        question_frame.pack(fill=tk.X, pady=3)
        self.apply_card_padding(question_frame)
        
        # Question input row
        input_row = ttk.Frame(question_frame)
        input_row.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Label(input_row, text="Questions:", width=12).pack(side=tk.LEFT)
        self.question_entry = ttk.Entry(input_row, width=20, font=self.FONTS['code_normal'])
        self.question_entry.pack(side=tk.LEFT, padx=(5, 10))
        self.question_entry.bind('<KeyRelease>', lambda e: self._on_question_entry_changed())
        
        # Quick selection buttons
        ttk.Button(input_row, text="All", width=8,
                   command=lambda: self.set_question_range("all")).pack(side=tk.LEFT, padx=2)
        
        # Help text
        help_label = ttk.Label(question_frame, text="Examples: 'all' or '1' or '1,3,5' or '1-10'", 
                               foreground="gray", font=self.FONTS['label_small'])
        help_label.pack(anchor='w', padx=(95, 0))
        
        # Status text
        self.status_label = ttk.Label(question_frame, text="Select dataset, server config, and API config to begin", 
                                      foreground="gray")
        self.status_label.pack(anchor='w', pady=(3, 0))
        
        # Prompt Control Section (moved to left frame)
        self.create_prompt_control_section(left_frame)
        
        # Chain Control Section
        chain_frame = self.create_section(left_frame, "Chain Control", padding=5)
        chain_frame.pack(fill=tk.X, pady=3)
        self.apply_card_padding(chain_frame)
        
        chain_btn_frame = ttk.Frame(chain_frame)
        chain_btn_frame.pack(fill=tk.X)
        
        ttk.Button(chain_btn_frame, text="Save Chain", width=12,
                   command=self.save_chain).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(chain_btn_frame, text="Load Chain", width=12,
                   command=self.load_chain).pack(side=tk.LEFT, padx=(0, 5))
        
        # Execution Control Section (split between left and right)
        # Left side - Control buttons and progress
        exec_frame = self.create_section(left_frame, "Execution Control", padding=5)
        exec_frame.pack(fill=tk.X, pady=3)
        self.apply_card_padding(exec_frame)
        
        # Control buttons
        btn_frame = ttk.Frame(exec_frame)
        btn_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(btn_frame, text="Start", width=10, 
                                    command=self.start_benchmark, state='disabled')
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.pause_btn = ttk.Button(btn_frame, text="Pause", width=10,
                                    command=self.pause_benchmark, state='disabled')
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop", width=10,
                                   command=self.stop_benchmark, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.resume_btn = ttk.Button(btn_frame, text="Resume", width=10,
                                     command=self.resume_benchmark, state='disabled')
        self.resume_btn.pack(side=tk.LEFT)
        
        # Right side - Status display with progress bar
        status_frame = self.create_section(right_frame, "Benchmark Status", padding=10)
        status_frame.pack(fill=tk.BOTH, expand=True)
        
        # Progress bar section (top of status frame)
        progress_section = ttk.Frame(status_frame)
        progress_section.pack(fill=tk.X, pady=(0, 5))
        
        # Chain progress bar (initially hidden)
        self.chain_progress_bar = ttk.Progressbar(progress_section, mode='determinate')
        self.chain_progress_label = ttk.Label(progress_section, text="", font=self.FONTS['label_small'])
        # Hidden by default - will be shown when running chains
        
        # Current run progress bar
        self.progress_bar = ttk.Progressbar(progress_section, mode='determinate')
        self.progress_bar.pack(fill=tk.X)
        
        self.progress_label = ttk.Label(progress_section, text="Ready to start", 
                                        font=self.FONTS['label_normal'])
        self.progress_label.pack(anchor='w', pady=(3, 0))
        
        self.detailed_progress_label = ttk.Label(progress_section, text="", 
                                                 foreground="gray", font=self.FONTS['label_small'])
        self.detailed_progress_label.pack(anchor='w')
        
        # Status text (below progress bar)
        from .base_components import ThemedScrolledText
        self.status_text = ThemedScrolledText(status_frame, font=self.FONTS['code_small'])
        self.style_text_widget(self.status_text.text)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        # Load previous selections from state
        self._load_previous_selections()
    
    def browse_dataset(self):
        """Browse for dataset text file"""
        # Use last directory from persistent state or default to centralized datasets path
        last_dir = self.ui_state.get_last_dataset_dir()
        initial_dir = last_dir if last_dir else str(self.app_paths.exported_datasets)
        
        filename = self.ask_open_file(
            title="Select Dataset File",
            initialdir=initial_dir,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                # Save directory and file path to persistent state
                self.ui_state.set_last_dataset_dir(os.path.dirname(filename))
                self.ui_state.set_last_dataset_path(filename)
                
                # Parse to get question count
                questions = DatasetParser.parse_dataset_file(filename)
                self.total_questions = len(questions)
                self.selected_dataset_path = filename
                
                # Update UI
                self.dataset_label.config(
                    text=f"{os.path.basename(filename)} ({self.total_questions} questions)",
                    foreground="black"
                )
                
                # Enable question selection
                self.question_entry.config(state='normal')
                self.validate_question_selection()
                self.validate_benchmark_readiness()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load dataset: {str(e)}")
                self.selected_dataset_path = None
                self.total_questions = 0
    
    def browse_server_config(self):
        """Browse for server configuration file"""
        # Use last directory from persistent state or default to centralized server configs path
        last_dir = self.ui_state.get_last_server_config_dir()
        initial_dir = last_dir if last_dir else str(self.app_paths.server_configs)
        
        filename = self.ask_open_file(
            title="Select Server Configuration File",
            initialdir=initial_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                # Save directory and file path to persistent state
                self.ui_state.set_last_server_config_dir(os.path.dirname(filename))
                self.ui_state.set_last_server_config_path(filename)
                
                # Validate content kind FIRST to avoid silent fallbacks
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

                # Use parent's server config (same instance as API Parameters tab)
                if not hasattr(self.parent, 'server_config'):
                    raise ValueError("Parent server configuration not available")
                
                config_name = os.path.basename(filename)
                success = self.parent.server_config.load_config(config_name)
                
                if success:
                    # Configure API client to match parent's server config
                    server_url = self.parent.server_config.get_server_url()
                    timeouts = self.parent.server_config.get_connection_timeouts()
                    
                    self.api_client.configure(
                        base_url=server_url,
                        timeout=timeouts['connection_timeout'],
                        request_timeout=timeouts['request_timeout']
                    )
                    
                    self.selected_server_config = self.parent.server_config
                    self.selected_server_config_path = filename
                    self.server_config_label.config(
                        text=f"{config_name} -> {server_url}",
                        foreground="green"
                    )
                    self.validate_benchmark_readiness()
                else:
                    raise ValueError("Failed to load server configuration")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load server configuration: {str(e)}")
                self.selected_server_config = None
                self.selected_server_config_path = None
                self.server_config_label.config(
                    text="No server config selected",
                    foreground="gray"
                )
    
    def browse_api_config(self):
        """Browse for API configuration file"""
        # Use last directory from persistent state or default to centralized saved configs path
        last_dir = self.ui_state.get_last_api_config_dir()
        initial_dir = last_dir if last_dir else str(self.app_paths.saved_configs)
        
        filename = self.ask_open_file(
            title="Select API Configuration File",
            initialdir=initial_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                # Save directory and file path to persistent state
                self.ui_state.set_last_api_config_dir(os.path.dirname(filename))
                self.ui_state.set_last_api_config_path(filename)
                
                # Load and validate API config using centralized utility
                success, temp_api_config, _, _ = load_parameter_config_from_file(filename)
                if not success:
                    raise ValueError("Selected file is not a valid API Parameters configuration")
                
                self.selected_api_config = temp_api_config
                self.selected_api_config_path = filename
                self.api_config_label.config(
                    text=os.path.basename(filename),
                    foreground="green"
                )
                self.validate_benchmark_readiness()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load API configuration: {str(e)}")
                self.selected_api_config = None
                self.selected_api_config_path = None
                self.api_config_label.config(
                    text="No API config selected (required)",
                    foreground="red"
                )
    
    
    def set_question_range(self, range_str: str):
        """Set question range from All button"""
        if not self.selected_dataset_path:
            messagebox.showwarning("No Dataset", "Please select a dataset first")
            return
            
        self.question_entry.delete(0, tk.END)
        self.question_entry.insert(0, range_str)
        self.validate_question_selection()
    
    def validate_question_selection(self):
        """Validate question range and update UI"""
        if not self.selected_dataset_path:
            self.status_label.config(text="Select a dataset first", foreground="gray")
            self.start_btn.config(state='disabled')
            return
            
        range_str = self.question_entry.get().strip()
        if not range_str:
            self.status_label.config(text="Enter question numbers", foreground="gray")
            self.start_btn.config(state='disabled')
            return
            
        try:
            # Parse question range
            self.selected_questions = self.executor.parse_question_range(range_str, self.total_questions)
            
            # Update status and validate benchmark readiness
            self._update_question_status()
            self.validate_benchmark_readiness()
                
        except ValueError as e:
            self.status_label.config(text=str(e), foreground="red")
            self.start_btn.config(state='disabled')
            self.selected_questions = []
    
    def _update_question_status(self):
        """Update question selection status"""
        if self.selected_questions:
            self.status_label.config(
                text=f"{len(self.selected_questions)} questions selected",
                foreground="green"
            )
        else:
            self.status_label.config(text="Enter question numbers", foreground="gray")
    
    def validate_benchmark_readiness(self):
        """Check if benchmark is ready to start and update UI accordingly"""
        ready = (self.selected_dataset_path and 
                self.selected_server_config and 
                self.selected_api_config and
                self.selected_questions)
        
        if ready:
            self.start_btn.config(state='normal')
            # Update status to show readiness with configuration summary
            if hasattr(self, 'selected_questions') and self.selected_questions:
                dataset_name = os.path.basename(self.selected_dataset_path) if self.selected_dataset_path else "Unknown"
                self.status_label.config(
                    text=f"Ready to start - {len(self.selected_questions)} questions from {dataset_name}",
                    foreground="green"
                )
        else:
            self.start_btn.config(state='disabled')
            if not self.selected_dataset_path:
                self.status_label.config(text="Select dataset to begin", foreground="gray")
            elif not self.selected_server_config:
                self.status_label.config(text="Select server config to continue", foreground="gray")
            elif not self.selected_api_config:
                self.status_label.config(text="Select API config to continue", foreground="gray")
            elif not self.selected_questions:
                self.status_label.config(text="Enter question numbers", foreground="gray")
        
        # Update start button text
        if hasattr(self, 'update_start_button'):
            self.update_start_button()
    
    
    def start_benchmark(self):
        """Start benchmark execution - handles both single runs and chains"""
        # Save current UI state to current run
        self.save_current_ui_to_run()
        
        # Check if this is a chain (multiple runs) or single run
        if len(self.run_configs) > 1:
            self._start_benchmark_chain()
        else:
            self._start_single_benchmark()
    
    def _start_single_benchmark(self):
        """Start single benchmark execution with explicit configuration requirements"""
        # Validate prerequisites - ALL configurations must be explicitly loaded
        if not self.selected_dataset_path:
            messagebox.showerror("Configuration Required", 
                               "Please select a dataset file before starting the benchmark.")
            return
            
        if not self.selected_server_config:
            messagebox.showerror("Configuration Required", 
                               "Please load a server configuration file before starting the benchmark.\n\n"
                               "This ensures the server runs with your exact specifications.")
            return
            
        if not self.selected_api_config:
            messagebox.showerror("Configuration Required", 
                               "Please load an API configuration file before starting the benchmark.\n\n"
                               "This ensures your API parameters are used exactly as configured.")
            return
            
        if not self.selected_questions:
            messagebox.showerror("Configuration Required", 
                               "Please select which questions to run before starting the benchmark.")
            return
            
        # Generate unique run name with custom prefix from UI
        custom_prefix = self.custom_name_entry.get().strip() if self.custom_name_entry else ''
        run_name = self.generate_unique_run_name(custom_prefix)
            
        # Use established ParameterConfig system (same as API Parameters tab)
        # All API configs now loaded as ParameterConfig objects for consistent processing
        api_config_data = self.selected_api_config.get_api_payload(False)
        
        # Extract system prompt from API config (for override system)
        api_system_prompt = self._extract_system_prompt_from_api_config(
            self.selected_api_config, self.selected_api_config_path)
            
        # Prepare UI for execution (hide chain progress for single runs)
        self.chain_progress_bar.pack_forget()
        self.chain_progress_label.pack_forget()
        self.start_btn.config(state='disabled')
        self.pause_btn.config(state='normal')
        self.stop_btn.config(state='normal')
        self.resume_btn.config(state='disabled')
        
        # Clear status
        self.status_text.delete("1.0", tk.END)
        self.progress_bar['value'] = 0
        
        # Start execution thread with server management
        self.current_thread = threading.Thread(
            target=self._run_benchmark_with_server_management,
            args=(self.selected_dataset_path, self.selected_server_config, 
                  api_config_data, self.selected_questions, run_name, api_system_prompt)
        )
        self.current_thread.start()
        
    def _start_benchmark_chain(self):
        """Start benchmark chain execution"""
        # Validate all runs in chain are configured
        for run_name, config in self.run_configs.items():
            if not config.get('dataset_path'):
                messagebox.showerror("Chain Validation Error", 
                                   f"Run '{run_name}' is missing dataset configuration.\n\n"
                                   "Please configure all runs before starting the chain.")
                return
            if not config.get('server_config_path'):
                messagebox.showerror("Chain Validation Error",
                                   f"Run '{run_name}' is missing server configuration.\n\n"
                                   "Please configure all runs before starting the chain.")
                return
            if not config.get('api_config_path'):
                messagebox.showerror("Chain Validation Error",
                                   f"Run '{run_name}' is missing API configuration.\n\n"
                                   "Please configure all runs before starting the chain.")
                return
            if not config.get('questions'):
                messagebox.showerror("Chain Validation Error",
                                   f"Run '{run_name}' is missing question selection.\n\n"
                                   "Please configure all runs before starting the chain.")
                return
        
        # Show chain progress bars
        self.chain_progress_bar.pack(fill=tk.X, pady=(0, 2))
        self.chain_progress_label.pack(anchor='w')
        
        # Prepare UI for chain execution
        self.start_btn.config(state='disabled')
        self.pause_btn.config(state='normal')
        self.stop_btn.config(state='normal')  
        self.resume_btn.config(state='disabled')
        
        # Clear status and reset progress bars
        self.status_text.delete("1.0", tk.END)
        self.progress_bar['value'] = 0
        self.chain_progress_bar['value'] = 0
        
        # Start chain execution thread
        self.current_thread = threading.Thread(target=self._run_benchmark_chain_execution)
        self.current_thread.start()
    
    def _run_benchmark_chain_execution(self):
        """Execute benchmark chain with smart server management"""
        try:
            total_runs = len(self.run_configs)
            current_run_index = 0
            previous_server_config_hash = None
            
            self._log_status(f"Starting benchmark chain: {total_runs} runs")
            self._log_status("=" * 60)
            
            for run_name, config in self.run_configs.items():
                current_run_index += 1
                
                # Update chain progress
                chain_percent = ((current_run_index - 1) / total_runs) * 100
                self.parent.root.after(0, lambda p=chain_percent: self.chain_progress_bar.configure(value=p))
                self.parent.root.after(0, lambda i=current_run_index, t=total_runs: 
                                     self.chain_progress_label.config(text=f"Chain: Run {i}/{t}"))
                
                # Reset individual run progress
                self.parent.root.after(0, lambda: self.progress_bar.configure(value=0))
                
                self._log_status(f"Starting Run {current_run_index}/{total_runs}: {run_name}")
                
                # Smart server restart: only if server config content changed
                server_config_path = config['server_config_path']
                current_server_config_hash = self._get_server_config_content_hash(server_config_path)
                needs_server_restart = current_server_config_hash != previous_server_config_hash
                
                if needs_server_restart:
                    if previous_server_config_hash is None:
                        self._log_status(f"First run - starting server with configuration...")
                    else:
                        self._log_status(f"Server configuration content changed - restarting server...")
                    previous_server_config_hash = current_server_config_hash
                else:
                    self._log_status(f"Server configuration unchanged - reusing existing server...")
                
                # Execute individual run
                success = self._execute_chain_run(
                    run_name=run_name,
                    config=config,
                    run_index=current_run_index,
                    total_runs=total_runs,
                    force_server_restart=needs_server_restart
                )
                
                if not success:
                    self._log_status(f"Chain execution failed at run {current_run_index}")
                    self.parent.root.after(0, self._benchmark_error, f"Chain failed at run: {run_name}")
                    return
                    
                self._log_status(f"Completed Run {current_run_index}/{total_runs}: {run_name}")
                self._log_status("-" * 40)
            
            # Update final chain progress
            self.parent.root.after(0, lambda: self.chain_progress_bar.configure(value=100))
            self.parent.root.after(0, lambda: self.chain_progress_label.config(text=f"Chain completed: {total_runs}/{total_runs} runs"))
            
            self._log_status("Benchmark chain completed successfully!")
            
            # Create chain completion results dictionary
            from managers.path_manager import app_paths
            chain_results = {
                'status': 'completed',
                'completed_questions': f'Chain of {total_runs} runs',  # Different format for chains
                'total_questions': f'{total_runs} runs',
                'run_directory': str(app_paths.benchmark_runs)  # Directory where all run results are stored
            }
            self.parent.root.after(0, self._benchmark_completed, chain_results)
            
        except Exception as e:
            self.parent.root.after(0, self._benchmark_error, f"Chain execution error: {str(e)}")
    
    def _execute_chain_run(self, run_name: str, config: dict, run_index: int, total_runs: int, force_server_restart: bool = False) -> bool:
        """Execute a single run within a chain"""
        try:
            # Load configurations for this run
            dataset_path = config['dataset_path']
            server_config_path = config['server_config_path'] 
            api_config_path = config['api_config_path']
            questions_text = config['questions']
            
            # Parse questions string to list of integers (like single benchmark does)
            questions = config.get('selected_questions', [])
            if not questions and questions_text:
                # Parse questions text if selected_questions not available
                from benchmarking.runner import DatasetParser
                total_questions = config.get('total_questions', 0)
                if total_questions > 0:
                    questions = DatasetParser.parse_question_range(questions_text.strip(), total_questions)
                else:
                    # Fallback: try to get total questions from dataset file
                    try:
                        dataset_questions = DatasetParser.parse_dataset_file(dataset_path)
                        questions = DatasetParser.parse_question_range(questions_text.strip(), len(dataset_questions))
                    except Exception as e:
                        raise ValueError(f"Cannot parse questions '{questions_text}' for run {run_name}: {e}")
            
            if not questions:
                raise ValueError(f"No questions configured for run {run_name}")
            
            # Load server and API configs
            
            # Load server config
            server_config = ServerConfig()
            server_config.load_config(server_config_path)
            
            # Load API config using centralized utility
            success, temp_config, _, _ = load_parameter_config_from_file(api_config_path)
            if not success:
                raise Exception(f"Failed to load API config from {api_config_path}")
            api_config_data = temp_config.get_api_payload(False)
            
            # Generate unique run name with custom name prefix if available
            custom_name = config.get('run_name', '').strip()
            unique_run_name = self.generate_unique_run_name(custom_name)
            
            # Execute benchmark using existing infrastructure
            self._log_status(f"Run {run_index}: Starting execution with {len(questions)} questions")
            
            # Server management: restart if config changed or forced
            server_needs_restart = force_server_restart or not self._validate_server_health(
                server_config, log_success=False, raise_on_failure=False)
            
            if server_needs_restart:
                if not self._auto_start_server(server_config):
                    raise RuntimeError(f"Failed to start server for run: {run_name}")
                    
            # Extract system prompt from API config file
            api_system_prompt = self._extract_system_prompt_from_api_config(
                None, api_config_path)
            
            # Get prompt overrides from config
            prompt_overrides = config.get('prompt_overrides', {})
            
            # Execute benchmark
            results = run_benchmark_enhanced_common(
                self.executor,
                dataset_path=dataset_path,
                config_data=api_config_data,
                selected_questions=questions,
                run_name=unique_run_name,
                system_prompt=api_system_prompt,
                server_config_path=server_config_path,
                api_config_path=api_config_path,
                progress_callback=self._chain_progress_callback,
                detailed_progress_callback=self._chain_detailed_progress_callback,
                system_prompt_override_enabled=prompt_overrides.get('system_override_enabled', False),
                system_prompt_override_text=prompt_overrides.get('system_override_text', ''),
                system_prefix=prompt_overrides.get('system_prefix', ''),
                system_suffix=prompt_overrides.get('system_suffix', ''),
                user_prefix=prompt_overrides.get('user_prefix', ''),
                user_suffix=prompt_overrides.get('user_suffix', ''),
                endpoint_type=self.parent.get_current_endpoint_type(),
            )
            
            self._log_status(f"Run {run_index}: Completed successfully")
            return True
            
        except Exception as e:
            self._log_status(f"Run {run_index}: Failed with error: {str(e)}")
            return False
    
    def _progress_callback(self, message: str):
        """Unified progress callback for both single and chain execution"""
        self.parent.root.after(0, lambda: self.progress_label.config(text=message))
        self._log_status(message)
    
    def _detailed_progress_callback(self, completed_count: int, total: int, details: str, mode: str = "single"):
        """
        Unified detailed progress callback for both single and chain execution
        
        Args:
            completed_count: Number of completed questions
            total: Total number of questions  
            details: Current question details or completion message
            mode: "single" or "chain" for different label formatting
        """
        # Update progress bar (same for both modes)
        completed_percent = (completed_count / total) * 100 if total > 0 else 0
        self.parent.root.after(0, lambda: self.progress_bar.configure(value=completed_percent))
        
        # Update detailed label with mode-specific formatting
        if mode == "chain":
            percent_text = f"{completed_count}/{total} questions ({completed_percent:.1f}%)"
        else:  # single mode
            percent_text = f"{completed_count}/{total} questions completed ({completed_percent:.1f}%)"
        
        self.parent.root.after(0, lambda: self.progress_label.config(text=percent_text))
        
        # Update current question preview (same logic for both modes)
        if details.startswith("Completed"):
            self.parent.root.after(0, lambda: self.detailed_progress_label.config(text=details))
        else:
            self.parent.root.after(0, lambda: self.detailed_progress_label.config(text=f"Current: {details}"))
    
    # Chain execution uses the unified callbacks with chain mode
    def _chain_progress_callback(self, message: str):
        """Chain progress callback - delegates to unified method"""
        self._progress_callback(message)
    
    def _chain_detailed_progress_callback(self, completed_count: int, total: int, details: str):
        """Chain detailed progress callback - delegates to unified method"""
        self._detailed_progress_callback(completed_count, total, details, mode="chain")
    
    def _run_benchmark_with_server_management(self, dataset_path: str, server_config,
                                             api_config_data: dict, selected_questions: List[int], run_name: str, api_system_prompt: str):
        """Execute benchmark with intelligent server management"""
        try:
            # Log to status
            self._log_status(f"Starting benchmark run: {run_name}")
            self._log_status(f"Dataset: {os.path.basename(dataset_path)}")
            self._log_status(f"Questions: {len(selected_questions)} selected")
            self._log_status("-" * 50)
            
            # Restart server with clean configuration
            self._log_status("Restarting server with benchmark configuration...")
            
            if not self._auto_start_server(server_config):
                raise RuntimeError("Failed to start server for benchmark")
            
            self._validate_server_health(server_config, "after restart")
            
            # Execute benchmark
            
            self._log_status("Starting benchmark execution...")
            results = run_benchmark_enhanced_common(
                self.executor,
                dataset_path=dataset_path,
                config_data=api_config_data,
                selected_questions=selected_questions,
                run_name=run_name,
                system_prompt=api_system_prompt,
                server_config_path=self.selected_server_config_path,
                api_config_path=self.selected_api_config_path,
                progress_callback=self._progress_callback,
                detailed_progress_callback=self._detailed_progress_callback,
                system_prompt_override_enabled=self.ui_state.get_system_prompt_override_enabled(),
                system_prompt_override_text=self.ui_state.get_system_prompt_override_text(),
                system_prefix=self.ui_state.get_system_prefix(),
                system_suffix=self.ui_state.get_system_suffix(),
                user_prefix=self.ui_state.get_user_prefix(),
                user_suffix=self.ui_state.get_user_suffix(),
                endpoint_type=self.parent.get_current_endpoint_type(),
            )
            
            # Update UI on completion
            self.parent.root.after(0, self._benchmark_completed, results)
            
        except Exception as e:
            # Update UI on error
            self.parent.root.after(0, self._benchmark_error, str(e))
    
    def _log_status(self, message: str):
        """Log message to status text widget and shared logger"""
        self.log_info(message)
        self.parent.root.after(0, lambda: self._append_status(f"{message}\n"))
    
    def _append_status(self, text: str):
        """Append text to status widget (must be called from main thread)"""
        self.status_text.insert(tk.END, text)
        self.status_text.see(tk.END)
    
    def _benchmark_completed(self, results: dict):
        """Handle benchmark completion"""
        self._log_status("-" * 50)
        self._log_status(f"Benchmark {results['status']}")
        self._log_status(f"Completed: {results['completed_questions']}/{results['total_questions']} questions")
        self._log_status(f"Results saved to: {results['run_directory']}")
        
        # Reset UI
        self.start_btn.config(state='normal')
        self.pause_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.resume_btn.config(state='disabled')
        
        # Hide chain progress bars (in case this was a chain)
        self.chain_progress_bar.pack_forget()
        self.chain_progress_label.pack_forget()
        
        # Notify main UI that benchmark completed (for auto-refresh of scoring tab)
        if hasattr(self.parent, 'on_benchmark_completed'):
            self.parent.on_benchmark_completed()
        
        # Ask to open results folder
        if messagebox.askyesno("Benchmark Complete", 
                               f"Benchmark completed successfully!\n\n"
                               f"Completed: {results['completed_questions']}/{results['total_questions']} questions\n\n"
                               f"Would you like to open the results folder?"):
            os.startfile(results['run_directory'])
    
    def on_endpoint_changed(self, endpoint_type: str):
        """Handle endpoint type change notification"""
        # Update status to show which endpoint will be used
        current_status = self.status_text.get("1.0", tk.END).strip()
        if not current_status:
            self._log_status(f"Endpoint switched to: {endpoint_type}")
    
    def _benchmark_error(self, error_msg: str):
        """Handle benchmark error"""
        self._log_status(f"ERROR: {error_msg}")
        
        # Check if paused or stopped
        if self.executor.is_paused:
            # Enable resume button
            self.pause_btn.config(state='disabled')
            self.resume_btn.config(state='normal')
            messagebox.showwarning("Benchmark Paused", 
                                   f"Benchmark paused due to error:\n\n{error_msg}\n\n"
                                   "Fix the issue and click Resume to continue.")
        else:
            # Reset UI
            self.start_btn.config(state='normal')
            self.pause_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')
            self.resume_btn.config(state='disabled')
            
            # Hide chain progress bars (in case this was a chain)
            self.chain_progress_bar.pack_forget()
            self.chain_progress_label.pack_forget()
            
            messagebox.showerror("Benchmark Error", f"Benchmark failed:\n\n{error_msg}")
    
    def pause_benchmark(self):
        """Pause benchmark execution"""
        self.executor.pause_benchmark()
        self.pause_btn.config(state='disabled')
        self.resume_btn.config(state='normal')
        self._log_status("Benchmark paused by user")
    
    def resume_benchmark(self):
        """Resume benchmark execution"""
        self.executor.resume_benchmark()
        self.pause_btn.config(state='normal')
        self.resume_btn.config(state='disabled')
        self._log_status("Benchmark resumed")
    
    def stop_benchmark(self):
        """Stop benchmark execution"""
        if messagebox.askyesno("Stop Benchmark", "Are you sure you want to stop the benchmark?"):
            self.executor.stop_benchmark()
            self._log_status("Benchmark stopped by user")
            
            # Reset UI
            self.start_btn.config(state='normal')
            self.pause_btn.config(state='disabled')
            self.stop_btn.config(state='disabled')
            self.resume_btn.config(state='disabled')
    
    def _auto_start_server(self, server_config) -> bool:
        """Clean server restart with exact user configuration for benchmark isolation"""
        try:
            self._log_status("Generating server command with benchmark configuration...")
            command = server_config.generate_server_command()
            if not command:
                self._log_status("ERROR: No server executable configured")
                return False
            
            from utils.server_manager import cleanup_all_servers
            self._log_status("Terminating any existing servers to ensure clean state...")
            cleanup_all_servers()
            
            self._log_status("Starting fresh server process with exact configuration...")
            import subprocess
            import time
            
            server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Wait for server startup
            self._log_status("Waiting for server to become ready...")
            server_url = server_config.get_server_url()
            # Configure API client for health checks
            timeouts = server_config.get_connection_timeouts()
            self.api_client.configure(
                base_url=server_url,
                timeout=timeouts['connection_timeout'],
                request_timeout=timeouts['request_timeout']
            )
            max_attempts = 75  # 2.5 minutes
            attempt = 0
            
            while attempt < max_attempts:
                if server_process.poll() is not None:
                    self._log_status("ERROR: Server process terminated during startup")
                    return False
                
                ok, _ = self.api_client.health_check()
                if ok:
                    self._log_status(f"Clean server ready at {server_url} with benchmark configuration")
                    return True
                
                time.sleep(2)
                attempt += 1
            
            # Timeout - kill server
            try:
                server_process.terminate()
                server_process.wait(timeout=3)
            except:
                pass
            
            self._log_status(f"ERROR: Server failed to start after {max_attempts} attempts")
            return False
            
        except Exception as e:
            self._log_status(f"ERROR: Failed to auto-start server: {str(e)}")
            return False
    
    def create_prompt_control_section(self, parent):
        """Create the prompt control section with override and formatting options"""
        prompt_frame = self.create_section(parent, "Prompt Control (Benchmark Only)", padding=5)
        prompt_frame.pack(fill=tk.X, pady=3)
        self.apply_card_padding(prompt_frame)
        
        # System Prompt Override Section
        override_frame = ttk.Frame(prompt_frame)
        override_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Override checkbox
        self.system_prompt_override_var = tk.BooleanVar()
        self.system_prompt_override_var.set(self.ui_state.get_system_prompt_override_enabled())
        
        override_checkbox = ttk.Checkbutton(
            override_frame, 
            text="Override system prompt from API config",
            variable=self.system_prompt_override_var,
            command=self._on_system_prompt_override_changed
        )
        override_checkbox.pack(anchor='w')
        
        # Override text field - multi-line like API Parameters
        ttk.Label(override_frame, text="Override with:", font=self.FONTS['label_bold']).pack(anchor="w", pady=(5, 0))
        self.system_prompt_override_entry = tk.Text(
            override_frame, 
            height=self.ui_config.SYSTEM_PROMPT_HEIGHT,
            font=self.FONTS['code_normal'], 
            wrap=tk.WORD
        )
        self.system_prompt_override_entry.pack(fill=tk.X, pady=(2, 5))
        self.style_text_widget(self.system_prompt_override_entry)
        self.system_prompt_override_entry.insert("1.0", self.ui_state.get_system_prompt_override_text())
        self.system_prompt_override_entry.bind('<KeyRelease>', self._on_system_prompt_override_text_changed)
        
        # Set initial state of override entry based on checkbox
        initial_state = 'normal' if self.ui_state.get_system_prompt_override_enabled() else 'disabled'
        self.system_prompt_override_entry.config(state=initial_state)
        
        # Help text for override
        help_override = ttk.Label(override_frame, 
                                text="(Leave empty to remove system prompt entirely)", 
                                foreground="gray", font=self.FONTS['label_small'])
        help_override.pack(anchor='w', padx=(95, 0))
        
        # Separator
        ttk.Separator(prompt_frame, orient='horizontal').pack(fill=tk.X, pady=5)
        
        # Prompt Formatting Section
        format_label = ttk.Label(prompt_frame, text="Prompt Formatting Control:", 
                                font=self.FONTS['label_bold'])
        format_label.pack(anchor='w', pady=(0, 5))
        
        # System prompt formatting
        sys_format_frame = ttk.Frame(prompt_frame)
        sys_format_frame.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Label(sys_format_frame, text="System Prompt", width=15).pack(side=tk.LEFT)
        ttk.Label(sys_format_frame, text="Prefix:", width=8).pack(side=tk.LEFT)
        self.system_prefix_entry = ttk.Entry(sys_format_frame, width=15, font=('Consolas', 9))
        self.system_prefix_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.system_prefix_entry.insert(0, self.ui_state.get_system_prefix())
        self.system_prefix_entry.bind('<KeyRelease>', self._on_system_prefix_changed)
        
        ttk.Label(sys_format_frame, text="Suffix:", width=8).pack(side=tk.LEFT)
        self.system_suffix_entry = ttk.Entry(sys_format_frame, width=15, font=('Consolas', 9))
        self.system_suffix_entry.pack(side=tk.LEFT)
        self.system_suffix_entry.insert(0, self.ui_state.get_system_suffix())
        self.system_suffix_entry.bind('<KeyRelease>', self._on_system_suffix_changed)
        
        # User input formatting
        user_format_frame = ttk.Frame(prompt_frame)
        user_format_frame.pack(fill=tk.X, pady=(0, 3))
        
        ttk.Label(user_format_frame, text="User Input", width=15).pack(side=tk.LEFT)
        ttk.Label(user_format_frame, text="Prefix:", width=8).pack(side=tk.LEFT)
        self.user_prefix_entry = ttk.Entry(user_format_frame, width=15, font=('Consolas', 9))
        self.user_prefix_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.user_prefix_entry.insert(0, self.ui_state.get_user_prefix())
        self.user_prefix_entry.bind('<KeyRelease>', self._on_user_prefix_changed)
        
        ttk.Label(user_format_frame, text="Suffix:", width=8).pack(side=tk.LEFT)
        self.user_suffix_entry = ttk.Entry(user_format_frame, width=15, font=('Consolas', 9))
        self.user_suffix_entry.pack(side=tk.LEFT)
        self.user_suffix_entry.insert(0, self.ui_state.get_user_suffix())
        self.user_suffix_entry.bind('<KeyRelease>', self._on_user_suffix_changed)
        
        # Help text for formatting
        help_format = ttk.Label(prompt_frame, 
                               text="Type actual spaces/newlines - use \\n for newlines", 
                               foreground="gray", font=self.FONTS['label_small'])
        help_format.pack(anchor='w', pady=(5, 0))
    
    def _on_system_prompt_override_changed(self):
        """Handle system prompt override checkbox change"""
        enabled = self.system_prompt_override_var.get()
        self.ui_state.set_system_prompt_override_enabled(enabled)
        # Enable/disable the text field based on checkbox
        state = 'normal' if enabled else 'disabled'
        self.system_prompt_override_entry.config(state=state)
    
    def _on_system_prompt_override_text_changed(self, event=None):
        """Handle system prompt override text change"""
        # Use Text widget API - get all text and remove the extra \n that tk.END adds
        text = self.system_prompt_override_entry.get("1.0", tk.END)[:-1]
        self.ui_state.set_system_prompt_override_text(text)
    
    def _on_system_prefix_changed(self, event=None):
        """Handle system prefix change"""
        # Convert literal \n to actual newlines
        text = self.system_prefix_entry.get().replace('\\n', '\n')
        self.ui_state.set_system_prefix(text)
    
    def _on_system_suffix_changed(self, event=None):
        """Handle system suffix change"""
        text = self.system_suffix_entry.get().replace('\\n', '\n')
        self.ui_state.set_system_suffix(text)
    
    def _on_user_prefix_changed(self, event=None):
        """Handle user prefix change"""
        text = self.user_prefix_entry.get().replace('\\n', '\n')
        self.ui_state.set_user_prefix(text)
    
    def _on_user_suffix_changed(self, event=None):
        """Handle user suffix change"""
        text = self.user_suffix_entry.get().replace('\\n', '\n')
        self.ui_state.set_user_suffix(text)
    
    def _on_question_entry_changed(self):
        """Handle question entry change and save to persistent state"""
        # Save the current question selection to state
        questions_text = self.question_entry.get()
        self.ui_state.set_last_questions(questions_text)
        # Also run validation
        self.validate_question_selection()
    
    def _load_previous_selections(self):
        """Load previous file selections and questions from persistent state"""
        try:
            # Load previous dataset selection
            last_dataset = self.ui_state.get_last_dataset_path()
            if last_dataset and os.path.exists(last_dataset):
                try:
                    # Parse to get question count
                    questions = DatasetParser.parse_dataset_file(last_dataset)
                    self.total_questions = len(questions)
                    self.selected_dataset_path = last_dataset
                    
                    # Update UI
                    self.dataset_label.config(
                        text=f"{os.path.basename(last_dataset)} ({self.total_questions} questions)",
                        foreground="black"
                    )
                    
                    # Enable question selection
                    self.question_entry.config(state='normal')
                    
                except Exception as e:
                    self._log_warning(f"Could not load previous dataset {last_dataset}", e)
            
            # Load previous server config selection
            last_server_config = self.ui_state.get_last_server_config_path()
            if last_server_config and os.path.exists(last_server_config):
                try:
                    # Use parent's server config (same as API Parameters tab)
                    if hasattr(self.parent, 'server_config'):
                        config_name = os.path.basename(last_server_config)
                        success = self.parent.server_config.load_config(config_name)
                        
                        if success:
                            # Configure API client to match parent's server config
                            server_url = self.parent.server_config.get_server_url()
                            timeouts = self.parent.server_config.get_connection_timeouts()
                            
                            self.api_client.configure(
                                base_url=server_url,
                                timeout=timeouts['connection_timeout'],
                                request_timeout=timeouts['request_timeout']
                            )
                            
                            self.selected_server_config = self.parent.server_config
                            self.selected_server_config_path = last_server_config
                            
                            # Update UI
                            self.server_config_label.config(
                                text=f"{config_name}",
                                foreground="black"
                            )
                        
                except Exception as e:
                    self._log_warning(f"Could not load previous server config {last_server_config}", e)
            
            # Load previous API config selection
            last_api_config = self.ui_state.get_last_api_config_path()
            if last_api_config and os.path.exists(last_api_config):
                try:
                    # Load and validate API config using centralized utility
                    success, temp_api_config, _, _ = load_parameter_config_from_file(last_api_config)
                    if not success:
                        raise ValueError("Failed to load API configuration through ParameterConfig")
                    
                    self.selected_api_config = temp_api_config
                    self.selected_api_config_path = last_api_config
                    
                    # Update UI
                    config_name = os.path.basename(last_api_config)
                    self.api_config_label.config(
                        text=f"{config_name}",
                        foreground="black"
                    )
                    
                except Exception as e:
                    self._log_warning(f"Could not load previous API config {last_api_config}", e)
            
            # Load previous question selection
            last_questions = self.ui_state.get_last_questions()
            if last_questions:
                self.question_entry.delete(0, tk.END)
                self.question_entry.insert(0, last_questions)
            
            # Validate everything after loading
            self.validate_question_selection()
            self.validate_benchmark_readiness()
            
        except Exception as e:
            self._log_warning("Error loading previous selections", e)
    
    # Chain System Methods
    
    def add_run(self):
        """Add new blank run to dropdown"""
        # Save current work before creating new run
        self.save_current_ui_to_run()
        
        # Create new run
        run_name = f"Run {self.next_run_number}"
        self.run_configs[run_name] = {}
        self.run_dropdown['values'] = list(self.run_configs.keys())
        self.run_dropdown.set(run_name)  # Switch to new blank run
        self.current_run = run_name  # Update current run tracker
        self.next_run_number += 1
        self.clear_ui()  # Clear UI for new run
        self.update_start_button()
    
    def remove_run(self):
        """Remove current run from dropdown"""
        if len(self.run_configs) <= 1:
            messagebox.showwarning("Cannot Remove", "Cannot remove the last run")
            return
            
        # Remove current run
        del self.run_configs[self.current_run]
        
        # Renumber all runs to be consecutive (Run 1, Run 2, Run 3...)
        old_configs = list(self.run_configs.values())
        self.run_configs.clear()
        
        for i, config in enumerate(old_configs, 1):
            run_name = f"Run {i}"
            self.run_configs[run_name] = config
            
        # Update next_run_number to be consecutive
        self.next_run_number = len(self.run_configs) + 1
        
        # Update dropdown and switch to first available run
        remaining_runs = list(self.run_configs.keys())
        self.run_dropdown['values'] = remaining_runs
        self.run_dropdown.set(remaining_runs[0])
        self.current_run = remaining_runs[0]
        self.load_run_to_ui()
        self.update_start_button()
    
    def on_run_changed(self, event=None):
        """Switch between runs"""
        # Save current UI to previous run
        self.save_current_ui_to_run()
        
        # Switch to selected run
        selected_run = self.run_dropdown.get()
        self.current_run = selected_run
        
        # Load selected run to UI
        self.load_run_to_ui()
        self.update_start_button()
    
    def _get_current_ui_values(self):
        """Extract current UI values into dictionary"""
        return {
            'custom_name': self.custom_name_entry.get().strip() if self.custom_name_entry else '',
            'questions_text': self.question_entry.get().strip() if self.question_entry else '',
            'dataset_path': self.selected_dataset_path or '',
            'server_path': self.selected_server_config_path or '',
            'api_path': self.selected_api_config_path or ''
        }
    
    def _should_save_run_config(self, ui_values):
        """Determine if run config should be saved based on content and previous configuration"""
        has_content = any([
            ui_values['custom_name'], 
            ui_values['questions_text'], 
            ui_values['dataset_path'], 
            ui_values['server_path'], 
            ui_values['api_path']
        ])
        was_configured = bool(self.run_configs.get(self.current_run, {}))
        return has_content or was_configured
    
    def _build_prompt_overrides(self):
        """Build prompt overrides dictionary from UI state"""
        return {
            'system_override_enabled': self.ui_state.get_system_prompt_override_enabled(),
            'system_override_text': self.ui_state.get_system_prompt_override_text(),
            'system_prefix': self.ui_state.get_system_prefix(),
            'system_suffix': self.ui_state.get_system_suffix(),
            'user_prefix': self.ui_state.get_user_prefix(),
            'user_suffix': self.ui_state.get_user_suffix()
        }
    
    def _build_run_config(self, ui_values):
        """Build complete run configuration dictionary"""
        return {
            'run_name': ui_values['custom_name'],
            'dataset_path': ui_values['dataset_path'],
            'server_config_path': ui_values['server_path'],
            'api_config_path': ui_values['api_path'],
            'questions': ui_values['questions_text'],
            'selected_api_config': self.selected_api_config,
            'selected_server_config': self.selected_server_config,
            'total_questions': self.total_questions,
            'selected_questions': self.selected_questions,
            'prompt_overrides': self._build_prompt_overrides()
        }
    
    def save_current_ui_to_run(self):
        """Save current UI state to current run config"""
        if self.current_run not in self.run_configs:
            return
            
        ui_values = self._get_current_ui_values()
        
        if self._should_save_run_config(ui_values):
            self.run_configs[self.current_run] = self._build_run_config(ui_values)
    
    def load_run_to_ui(self):
        """Load run config to UI"""
        if self.current_run not in self.run_configs:
            return
            
        config = self.run_configs[self.current_run]
        
        # Load run name
        if self.custom_name_entry:
            self.custom_name_entry.delete(0, tk.END)
            self.custom_name_entry.insert(0, config.get('run_name', ''))
        
        # Load dataset
        dataset_path = config.get('dataset_path', '')
        if dataset_path and os.path.exists(dataset_path):
            self.selected_dataset_path = dataset_path
            try:
                questions = DatasetParser.parse_dataset_file(dataset_path)
                self.total_questions = len(questions)
                self.dataset_label.config(
                    text=f"{os.path.basename(dataset_path)} ({self.total_questions} questions)",
                    foreground="black"
                )
                self.question_entry.config(state='normal')
            except:
                self.clear_dataset()
        else:
            self.clear_dataset()
        
        # Load server config
        server_path = config.get('server_config_path', '')
        if server_path and os.path.exists(server_path):
            self.selected_server_config_path = server_path
            
            # Load actual server config from file (not from saved data)
            try:
                temp_server_config = ServerConfig()
                if temp_server_config.load_config(os.path.basename(server_path)):
                    self.selected_server_config = temp_server_config
                    self.server_config_label.config(
                        text=os.path.basename(server_path),
                        foreground="green"
                    )
                else:
                    raise Exception(f"Failed to load server config from {server_path}")
            except Exception as e:
                self._log_warning(f"Could not load server config {server_path}", e)
                self.clear_server_config()
        else:
            self.clear_server_config()
        
        # Load API config
        api_path = config.get('api_config_path', '')
        if api_path and os.path.exists(api_path):
            self.selected_api_config_path = api_path
            
            # Load actual API config from file (not from saved data)
            try:
                success, temp_api_config, _, _ = load_parameter_config_from_file(api_path)
                if success:
                    self.selected_api_config = temp_api_config
                    self.api_config_label.config(
                        text=os.path.basename(api_path),
                        foreground="green"
                    )
                else:
                    raise Exception(f"Failed to load API config from {api_path}")
            except Exception as e:
                self._log_warning(f"Could not load API config {api_path}", e)
                self.clear_api_config()
        else:
            self.clear_api_config()
        
        # Load questions
        questions_text = config.get('questions', '')
        if self.question_entry:
            self.question_entry.delete(0, tk.END)
            self.question_entry.insert(0, questions_text)
            
        # Restore selected questions and total
        self.selected_questions = config.get('selected_questions', [])
        self.total_questions = config.get('total_questions', 0)
        
        # Restore prompt override settings from chain config to UI state and UI fields
        prompt_overrides = config.get('prompt_overrides', {})
        if prompt_overrides:
            # Update UI state manager
            self.ui_state.set_system_prompt_override_enabled(prompt_overrides.get('system_override_enabled', False))
            self.ui_state.set_system_prompt_override_text(prompt_overrides.get('system_override_text', ''))
            self.ui_state.set_system_prefix(prompt_overrides.get('system_prefix', ''))
            self.ui_state.set_system_suffix(prompt_overrides.get('system_suffix', ''))
            self.ui_state.set_user_prefix(prompt_overrides.get('user_prefix', ''))
            self.ui_state.set_user_suffix(prompt_overrides.get('user_suffix', ''))
            
            # Update UI fields if they exist (they might not be created yet)
            if hasattr(self, 'system_prompt_override_var') and self.system_prompt_override_var:
                self.system_prompt_override_var.set(prompt_overrides.get('system_override_enabled', False))
            
            if hasattr(self, 'system_prompt_override_entry') and self.system_prompt_override_entry:
                self.system_prompt_override_entry.delete("1.0", tk.END)
                self.system_prompt_override_entry.insert("1.0", prompt_overrides.get('system_override_text', ''))
                # Update entry state based on checkbox
                state = 'normal' if prompt_overrides.get('system_override_enabled', False) else 'disabled'
                self.system_prompt_override_entry.config(state=state)
            
            if hasattr(self, 'system_prefix_entry') and self.system_prefix_entry:
                self.system_prefix_entry.delete(0, tk.END)
                self.system_prefix_entry.insert(0, prompt_overrides.get('system_prefix', ''))
            
            if hasattr(self, 'system_suffix_entry') and self.system_suffix_entry:
                self.system_suffix_entry.delete(0, tk.END)
                self.system_suffix_entry.insert(0, prompt_overrides.get('system_suffix', ''))
            
            if hasattr(self, 'user_prefix_entry') and self.user_prefix_entry:
                self.user_prefix_entry.delete(0, tk.END)
                self.user_prefix_entry.insert(0, prompt_overrides.get('user_prefix', ''))
            
            if hasattr(self, 'user_suffix_entry') and self.user_suffix_entry:
                self.user_suffix_entry.delete(0, tk.END)
                self.user_suffix_entry.insert(0, prompt_overrides.get('user_suffix', ''))
        
        # Validate everything
        self.validate_question_selection()
        self.validate_benchmark_readiness()
    
    def clear_ui(self):
        """Clear all UI fields for new run"""
        self.clear_dataset()
        self.clear_server_config()
        self.clear_api_config()
        
        if self.custom_name_entry:
            self.custom_name_entry.delete(0, tk.END)
        if self.question_entry:
            self.question_entry.delete(0, tk.END)
            self.question_entry.config(state='disabled')
            
        self.selected_questions = []
        self.total_questions = 0
        self.status_label.config(text="Configure this run", foreground="gray")
    
    def clear_dataset(self):
        """Clear dataset selection"""
        self.selected_dataset_path = None
        self.dataset_label.config(text="No dataset selected", foreground="gray")
    
    def clear_server_config(self):
        """Clear server config selection"""
        self.selected_server_config = None
        self.selected_server_config_path = None
        self.server_config_label.config(text="No server config selected", foreground="gray")
    
    def clear_api_config(self):
        """Clear API config selection"""
        self.selected_api_config = None
        self.selected_api_config_path = None
        self.api_config_label.config(text="No API config selected (required)", foreground="red")
    
    def update_start_button(self):
        """Update start button text to reflect single run or chain"""
        configured_runs = sum(1 for config in self.run_configs.values() 
                            if self.is_run_configured(config))
        
        if len(self.run_configs) > 1:
            self.start_btn.config(text=f"Start Chain ({configured_runs} runs)")
        else:
            self.start_btn.config(text="Start")
    
    def is_run_configured(self, config):
        """Check if a run configuration is complete"""
        return (config.get('dataset_path') and 
                config.get('server_config_path') and 
                config.get('api_config_path') and 
                config.get('questions'))
    
    def save_chain(self):
        """Save chain configuration to JSON file"""
        if not any(self.run_configs.values()):
            messagebox.showwarning("No Chain", "No runs configured to save")
            return
            
        # Save current UI to current run first
        self.save_current_ui_to_run()
        
        # Build chain data
        chain_data = {
            "chain_name": f"chain_{len(self.run_configs)}_runs",
            "created": datetime.now().isoformat(),
            "runs": []
        }
        
        for run_name, config in self.run_configs.items():
            if config:  # Only save non-empty configs
                # Create serializable config (exclude complex objects)
                serializable_config = {
                    'run_name': config.get('run_name', ''),
                    'dataset_path': config.get('dataset_path', ''),
                    'server_config_path': config.get('server_config_path', ''),
                    'api_config_path': config.get('api_config_path', ''),
                    'questions': config.get('questions', ''),
                    'selected_questions': config.get('selected_questions', []),
                    'total_questions': config.get('total_questions', 0),
                    'prompt_overrides': config.get('prompt_overrides', {})
                }
                chain_data["runs"].append(serializable_config)
        
        # Save to file
        filename = self.ask_save_file(
            title="Save Chain Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.app_paths.data)
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(chain_data, f, indent=2)
                messagebox.showinfo("Success", f"Chain saved to {os.path.basename(filename)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save chain: {str(e)}")
    
    def load_chain(self):
        """Load chain configuration from JSON file"""
        filename = self.ask_open_file(
            title="Load Chain Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(self.app_paths.data)
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    chain_data = json.load(f)
                
                runs = chain_data.get("runs", [])
                if not runs:
                    messagebox.showwarning("Invalid Chain", "No runs found in chain file")
                    return
                
                # Clear existing runs and create new ones
                self.run_configs = {}
                self.next_run_number = 1
                
                for i, run_config in enumerate(runs):
                    run_name = f"Run {i + 1}"
                    self.run_configs[run_name] = run_config
                    self.next_run_number = i + 2
                
                # Update dropdown
                self.run_dropdown['values'] = list(self.run_configs.keys())
                self.run_dropdown.set(self.DEFAULT_RUN_NAME)
                self.current_run = self.DEFAULT_RUN_NAME
                
                # Load first run to UI
                self.load_run_to_ui()
                self.update_start_button()
                
                messagebox.showinfo("Success", f"Chain loaded: {len(runs)} runs")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load chain: {str(e)}")
    
    def _on_custom_name_changed(self, event=None):
        """Handle custom name entry change"""
        # Save to current run config
        if hasattr(self, 'current_run') and self.current_run in self.run_configs:
            if not self.run_configs[self.current_run]:
                self.run_configs[self.current_run] = {}
            self.run_configs[self.current_run]['run_name'] = self.custom_name_entry.get().strip()
    
    def _log_warning(self, message: str, exception: Exception = None):
        """
        Log warning message with consistent formatting and optional exception details
        
        Args:
            message: Warning message to display
            exception: Optional exception for additional context
        """
        warning_text = f"Warning: {message}"
        if exception:
            warning_text += f" - {str(exception)}"
        
        self._log_status(warning_text)
        self.log_warning(warning_text)

    def _validate_server_health(self, server_config, context="", log_success=True, raise_on_failure=True):
        """
        Validate server health with consistent error handling and logging
        
        Args:
            server_config: Server configuration object with get_server_url() method
            context: Additional context for error messages (e.g., "after restart")
            log_success: Whether to log success message when server is healthy
            raise_on_failure: Whether to raise RuntimeError on health check failure
            
        Returns:
            bool: True if server is healthy, False otherwise (only if raise_on_failure=False)
        """
        server_url = server_config.get_server_url()
        # Configure API client (ensures consistent timeouts)
        try:
            timeouts = server_config.get_connection_timeouts()
            self.api_client.configure(
                base_url=server_url,
                timeout=timeouts['connection_timeout'],
                request_timeout=timeouts['request_timeout']
            )
        except Exception:
            pass

        ok, _ = self.api_client.health_check()
        if ok:
            if log_success:
                success_msg = f"Server ready at {server_url}"
                if context:
                    success_msg += f" {context}"
                self._log_status(success_msg)
            return True
        else:
            error_msg = f"Server health check failed"
            if context:
                error_msg += f" {context}"
                
            if raise_on_failure:
                raise RuntimeError(error_msg)
            else:
                return False

    def _extract_system_prompt_from_api_config(self, api_config=None, api_config_path=None) -> str:
        """
        Extract system prompt from ParameterConfig object
        
        Args:
            api_config: ParameterConfig object, or None
            api_config_path: Path to API config file for loading if api_config is None
            
        Returns:
            System prompt string, empty if not found or error
        """
        if api_config is not None:
            # Extract from ParameterConfig object: reload from file to get system prompt
            if not api_config_path:
                return ""
                
            try:
                success, _, system_prompt, _ = load_parameter_config_from_file(api_config_path)
                if success:
                    return system_prompt.strip()
            except Exception as e:
                self._log_warning("Could not extract system prompt from API config", e)
                
            return ""
        else:
            # api_config is None, load directly from file path
            if not api_config_path:
                return ""
                
            try:
                success, _, system_prompt, _ = load_parameter_config_from_file(api_config_path)
                if success:
                    return system_prompt.strip()
            except Exception as e:
                self._log_warning(f"Could not extract system prompt from API config {api_config_path}", e)
                
            return ""

    def generate_unique_run_name(self, custom_prefix=None):
        """Generate unique run name with optional custom prefix"""
        timestamp = datetime.now()
        # Use readable format: YYYY-MM-DD_HH-MM-SS for user-friendliness
        base_name = timestamp.strftime('%Y-%m-%d_%H-%M-%S')
        
        if custom_prefix and custom_prefix.strip():
            # Simple sanitization - replace problematic characters with underscore
            safe_prefix = re.sub(r'[<>:"/\\|?*]', '_', custom_prefix.strip())
            return f"{safe_prefix}_{base_name}"
        else:
            return f"run_{base_name}"
    
    def _get_server_config_content_hash(self, config_path: str) -> str:
        """Get hash of server config file content for comparison"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            # Create hash of normalized content (ignores whitespace differences)
            normalized_content = json.dumps(json.loads(content), sort_keys=True, separators=(',', ':'))
            return hashlib.md5(normalized_content.encode('utf-8')).hexdigest()
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as e:
            # If we can't read/parse the file, return the file path as fallback
            # This ensures different unreadable files are treated as different
            return f"ERROR:{config_path}:{str(e)}"
