"""
Auto Mode Tab

Minimal, brain-dead automation path that orchestrates:
- Baseline sweep
- Exploration with budget
- Promotion sweep to reach min coverage on top combos
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from ui.base_components import BaseUIComponent, ScrollableFrameManager
from managers.path_manager import app_paths
from managers.api_config_manager import ParameterConfig
from managers.server_config_manager import ServerConfig
from managers.global_settings import global_settings

from benchmarking.auto_mode import AutoModeOrchestrator, AutoModeConfig, AutoModeCallbacks
from benchmarking.database import SQLiteOptimizationDatabase
from benchmarking.interfaces import ParameterArrayInfo


class AutoModeUI(BaseUIComponent):
    """Simple Auto Mode UI for unattended optimization."""

    def __init__(self, parent, config_manager, api_client):
        super().__init__(parent, config_manager, api_client)
        self.parent = parent
        # State
        self.dataset_path = None
        self.api_config_path = None
        self.server_config_path = None
        # Share configuration instances with the main window when available
        if isinstance(self.config, ParameterConfig):
            self.api_config = self.config
        else:
            self.api_config = ParameterConfig()

        if hasattr(parent, 'server_config') and isinstance(parent.server_config, ServerConfig):
            self.server_config = parent.server_config
        else:
            self.server_config = ServerConfig()

        self.force_clean_var = tk.BooleanVar(value=True)
        # Defaults: Stop-when-confident OFF, Full Auto ON
        self.auto_validate_var = tk.BooleanVar(value=False)
        self.full_auto_var = tk.BooleanVar(value=True)
        # Full Auto mode selection (legacy vs new scheduler)
        self.full_auto_mode_var = tk.StringVar(value="Legacy (Current)")

        # UI refs
        self.dataset_label = None
        self.server_label = None
        self.api_label = None
        self.start_btn = None
        self.stop_btn = None
        self.btn_browse_dataset = None
        self.btn_browse_server = None
        self.btn_browse_api = None
        # No separate resume controls -- Start/Resume handles both
        self.resume_btn = None
        self.resume_label = None
        self.log = None
        # Display variables for selection and status labels
        self.dataset_display = None
        self.server_display = None
        self.api_display = None
        self.resume_display = None
        self.knowledge_display = None
        # Explicit resume target (directory containing optimization.db)
        self.resume_db_dir = None
        # Historical knowledge import
        self.historical_knowledge = None

        # Orchestrator
        self._orchestrator = AutoModeOrchestrator(api_client)

    def create_auto_mode_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Auto Mode")
        self._build(tab)

    def _build(self, parent):
        container = ttk.Frame(parent, style='Content.TFrame')
        container.pack(fill=tk.BOTH, expand=True)

        # Scrollable content area
        main_frame, _, scrollable = ScrollableFrameManager(self).create_scrollable_frame(container)
        content = ttk.Frame(scrollable, style='Content.TFrame')
        content.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=self.content_pad_y)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        # Initialize display variables once widgets can bind to them
        self.dataset_display = tk.StringVar(value="No dataset selected")
        self.server_display = tk.StringVar(value="No server config selected")
        self.api_display = tk.StringVar(value="No API config selected")
        self.resume_display = tk.StringVar(value="No run DB loaded")
        self.knowledge_display = tk.StringVar(value="No knowledge loaded")

        config_section = self.create_section(content, "Run Configuration")
        config_section.grid(row=0, column=0, sticky='ew')
        self.apply_card_padding(config_section)
        config_section.columnconfigure(1, weight=1)

        self._build_selector_row(
            config_section,
            row=0,
            label_text="Dataset",
            browse_command=self._browse_dataset,
            button_attr="btn_browse_dataset",
            label_attr="dataset_label",
            display_var=self.dataset_display,
        )

        self._build_selector_row(
            config_section,
            row=1,
            label_text="Server Config",
            browse_command=self._browse_server,
            button_attr="btn_browse_server",
            label_attr="server_label",
            display_var=self.server_display,
        )

        self._build_selector_row(
            config_section,
            row=2,
            label_text="API Config",
            browse_command=self._browse_api,
            button_attr="btn_browse_api",
            label_attr="api_label",
            display_var=self.api_display,
        )

        toggle_frame = ttk.Frame(config_section, style='Content.TFrame')
        toggle_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        toggle_frame.columnconfigure(0, weight=1)
        toggle_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(toggle_frame, text="Force clean start", variable=self.force_clean_var).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(toggle_frame, text="Stop when confident (Auto Validate)", variable=self.auto_validate_var).grid(row=0, column=1, sticky='w', padx=(12, 0))
        ttk.Checkbutton(toggle_frame, text="Full Auto (sampler-managed)", variable=self.full_auto_var, command=self._on_full_auto_toggle).grid(row=1, column=0, sticky='w', pady=(6, 0))

        self.full_auto_mode_dropdown = ttk.Combobox(
            toggle_frame,
            textvariable=self.full_auto_mode_var,
            values=["Legacy (Current)", "New Scheduler (Converge + Validate)"],
            state="readonly",
            width=32,
        )
        self.full_auto_mode_dropdown.grid(row=1, column=1, sticky='w', padx=(12, 0), pady=(6, 0))
        self._update_full_auto_mode_visibility()

        controls_section = self.create_section(content, "Run Controls")
        controls_section.grid(row=1, column=0, sticky='ew', pady=(self.section_pad_y // 2, 0))
        self.apply_card_padding(controls_section)

        button_row = ttk.Frame(controls_section, style='Content.TFrame')
        button_row.grid(row=0, column=0, sticky='w')
        self.start_btn = ttk.Button(button_row, text="Start / Resume", command=self._start, state='disabled', style='Accent.TButton')
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(button_row, text="Stop", command=self._stop, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        resume_row = ttk.Frame(controls_section, style='Content.TFrame')
        resume_row.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        resume_row.columnconfigure(2, weight=1)
        ttk.Button(resume_row, text="Load Run DB...", command=self._browse_run_db).grid(row=0, column=0, sticky='w')
        ttk.Button(resume_row, text="Clear", command=self._clear_run_db).grid(row=0, column=1, sticky='w', padx=(8, 0))
        self.resume_label = ttk.Label(
            resume_row,
            textvariable=self.resume_display,
            font=self.FONTS['label_small'],
            foreground=self.COLORS.get('text_secondary'),
            wraplength=self.DIMENSIONS.get('tooltip_wrap', 400),
            justify='left',
        )
        self.resume_label.grid(row=0, column=2, sticky='w', padx=(12, 0))

        knowledge_row = ttk.Frame(controls_section, style='Content.TFrame')
        knowledge_row.grid(row=2, column=0, sticky='ew', pady=(8, 0))
        knowledge_row.columnconfigure(1, weight=1)
        ttk.Button(knowledge_row, text="Load Knowledge...", command=self._browse_knowledge).grid(row=0, column=0, sticky='w')
        self.knowledge_label = ttk.Label(
            knowledge_row,
            textvariable=self.knowledge_display,
            font=self.FONTS['label_small'],
            foreground=self.COLORS.get('text_secondary'),
            wraplength=self.DIMENSIONS.get('tooltip_wrap', 400),
            justify='left',
        )
        self.knowledge_label.grid(row=0, column=1, sticky='w', padx=(12, 0))

        activity_section = self.create_section(content, "Activity Log")
        activity_section.grid(row=2, column=0, sticky='nsew')
        self.apply_card_padding(activity_section)
        activity_section.columnconfigure(0, weight=1)
        activity_section.rowconfigure(0, weight=1)

        from .base_components import ThemedScrolledText
        self.log = ThemedScrolledText(
            activity_section,
            height=self.ui_config.AUTO_LOG_HEIGHT,
            font=self.FONTS['code_normal'],
            wrap=tk.WORD,
        )
        self.log.grid(row=0, column=0, sticky='nsew')
        self.style_text_widget(self.log.text)
        self.log.config(state=tk.DISABLED)

        self._refresh_start_state()

    def _build_selector_row(self, parent, *, row: int, label_text: str, browse_command, button_attr: str, label_attr: str, display_var: tk.StringVar):
        ttk.Label(parent, text=f"{label_text}:", font=self.FONTS['label_bold']).grid(row=row, column=0, sticky='nw', pady=(0, 4))
        row_frame = ttk.Frame(parent, style='Content.TFrame')
        row_frame.grid(row=row, column=1, sticky='ew', pady=(0, 2))
        row_frame.columnconfigure(1, weight=1)

        button = ttk.Button(row_frame, text="Browse...", command=browse_command, width=14)
        button.grid(row=0, column=0, sticky='w')

        info_label = ttk.Label(
            row_frame,
            textvariable=display_var,
            font=self.FONTS['code_small'],
            foreground=self.COLORS.get('text_secondary'),
            wraplength=self.DIMENSIONS.get('tooltip_wrap', 400),
            justify='left',
        )
        info_label.grid(row=0, column=1, sticky='ew', padx=(10, 0))

        setattr(self, button_attr, button)
        setattr(self, label_attr, info_label)

    def _update_selection_display(self, label_widget, string_var, text: str, *, is_default: bool = False):
        if string_var is not None:
            string_var.set(text)
        if label_widget is not None:
            color_key = 'text_secondary' if is_default else 'text_primary'
            fallback = 'gray' if is_default else 'black'
            label_widget.configure(foreground=self.COLORS.get(color_key, fallback))

    # --------------- Handlers -----------------

    def _browse_dataset(self):
        initial_dir = str(app_paths.exported_datasets) if app_paths.exported_datasets.exists() else os.getcwd()
        p = self.ask_open_file(
            title="Select Dataset",
            initialdir=initial_dir,
            filetypes=[("Text", "*.txt"), ("All Files", "*.*")],
        )
        if p:
            self.dataset_path = p
            self._update_selection_display(self.dataset_label, self.dataset_display, os.path.basename(p))
            self.log_info(f"Dataset selected: {p}")
            self._refresh_start_state()

    def _browse_server(self):
        initial_dir = str(app_paths.server_configs) if app_paths.server_configs.exists() else os.getcwd()
        p = self.ask_open_file(
            title="Select Server Config",
            initialdir=initial_dir,
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if p:
            self.server_config_path = p
            ok, msg = self._load_server_config(p)
            if ok:
                self._update_selection_display(self.server_label, self.server_display, os.path.basename(p))
                self.log_info(f"Server config loaded: {p}")
            else:
                self.log_error(f"Failed to load server config {p}: {msg}")
                messagebox.showerror("Server Config", msg)
            self._refresh_start_state()

    def _browse_api(self):
        initial_dir = str(app_paths.saved_configs) if app_paths.saved_configs.exists() else os.getcwd()
        p = self.ask_open_file(
            title="Select API Config",
            initialdir=initial_dir,
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
        )
        if p:
            self.api_config_path = p
            ok, msg = self._load_api_config(p)
            if ok:
                self._update_selection_display(self.api_label, self.api_display, os.path.basename(p))
                self.log_info(f"API config loaded: {p}")
            else:
                self.log_error(f"Failed to load API config {p}: {msg}")
                messagebox.showerror("API Config", msg)
            self._refresh_start_state()

    def _load_server_config(self, path: str):
        try:
            server_config = self.server_config if isinstance(self.server_config, ServerConfig) else ServerConfig()
            name = os.path.basename(path)
            # If the file lives in our managed dir, use the manager's loader.
            if os.path.dirname(path) == str(app_paths.server_configs):
                ok = server_config.load_config(name)
                if not ok:
                    return False, f"Failed to parse {path}"
                return True, "OK"
            # Otherwise, parse JSON directly to avoid copying/locks on Windows.
            from utils.config_utils import load_json_config
            ok, data = load_json_config(path, "server configuration")
            if not ok or not isinstance(data, dict):
                return False, f"Failed to parse {path}"
            values = data.get("values", {}) or {}
            enabled = data.get("enabled", {}) or {}
            exe = data.get("executable_path") or data.get("executable") or data.get("exe")
            server_config.initialize_blank_config()
            server_config.values.update(values)
            server_config.enabled.update(enabled)
            if exe:
                server_config.executable_path = exe
            # Validate and normalize
            try:
                server_config._validate_loaded_config()
            except Exception:
                pass
            if server_config is not self.server_config:
                self.server_config = server_config
            return True, "OK"
        except Exception as e:
            return False, str(e)

    def _load_api_config(self, path: str):
        """Load API config from any location without copying to saved_configs (Windows-safe)."""
        try:
            from utils.config_utils import load_parameter_config_from_file
            success, temp_config, _sys, _user = load_parameter_config_from_file(path)
            if not success or temp_config is None:
                return False, f"Failed to parse {path}"
            # Adopt the loaded config object directly
            # Align with Run Benchmark/API Parameters: inject top-level system_prompt into values for downstream use
            try:
                if _sys is not None and _sys != "":
                    temp_config.values = temp_config.values or {}
                    temp_config.values['system_prompt'] = _sys
            except Exception:
                pass
            target_config = self.api_config if isinstance(self.api_config, ParameterConfig) else self.config
            if isinstance(target_config, ParameterConfig):
                target_config.initialize_blank_config()
                target_config.values.update(temp_config.values or {})
                target_config.enabled.update(temp_config.enabled or {})
                target_config.array_values.update(temp_config.array_values or {})
                self.api_config = target_config
            else:
                self.api_config = temp_config
            return True, "OK"
        except Exception as e:
            return False, str(e)

    def _refresh_start_state(self):
        # When resuming from a DB, allow start with auto-loaded configs
        if self.resume_db_dir:
            can = bool(self.dataset_path and self.api_config and self.server_config)
        else:
            # When Full Auto is on, arrays are not required; otherwise ensure arrays exist
            arrays_ok = True if self.full_auto_var.get() else self._has_arrays()
            can = bool(self.dataset_path and self.api_config and self.server_config and arrays_ok)
        if self.start_btn:
            self.start_btn.config(state='normal' if can else 'disabled')

    def _has_arrays(self) -> bool:
        # True if any array_values have non-empty values
        return any(v and str(v).strip() for v in (self.api_config.array_values or {}).values())

    def _parse_arrays(self) -> Dict[str, ParameterArrayInfo]:
        out: Dict[str, ParameterArrayInfo] = {}
        for name, arr in (self.api_config.array_values or {}).items():
            if not arr or not str(arr).strip():
                continue
            values = [v.strip() for v in str(arr).split('#~') if v.strip()]
            processed = []
            rec_idx = []
            for i, val in enumerate(values):
                if val.startswith('((') and val.endswith('))'):
                    processed.append(val[2:-2])
                    rec_idx.append(i)
                else:
                    processed.append(val)
            out[name] = ParameterArrayInfo(values=processed, recommended_indices=rec_idx)
        return out

    def _start(self):
        # Validate
        if not self.dataset_path:
            messagebox.showerror("Auto Mode", "Select a dataset")
            return
        if not self.full_auto_var.get() and not self._has_arrays():
            messagebox.showerror("Auto Mode", "API config must define array values (#~)")
            return
        arrays = self._parse_arrays() if not self.full_auto_var.get() else {}
        run_name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # Map mode to internal key
        famode = 'legacy'
        try:
            sel = (self.full_auto_mode_var.get() or '').lower()
            if 'scheduler' in sel:
                famode = 'scheduler'
        except Exception:
            pass

        cfg = AutoModeConfig(
            run_name=run_name,
            dataset_path=self.dataset_path,
            api_config=self.api_config,
            server_config=self.server_config,
            endpoint_type=global_settings.get_endpoint_type(),
            parameter_arrays=arrays,
            force_clean=self.force_clean_var.get(),
            auto_validate=bool(self.auto_validate_var.get()),
            full_auto=bool(self.full_auto_var.get()),
            full_auto_mode=famode,
            audit_wrong_sample=60,
            audit_right_sample=20,
            # Explicit resume only
            resume_directory=self.resume_db_dir,
            # Preserve original config paths for metadata
            api_config_path=self.api_config_path,
            server_config_path=self.server_config_path,
            historical_knowledge=self.historical_knowledge,
        )

        self._append_log("Starting Auto Mode...")
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')

        cbs = AutoModeCallbacks(
            on_status=lambda m: self._append_log(m),
            on_progress=lambda m: self._append_log(m),
            on_error=lambda m: self._append_log(f"ERROR: {m}")
        )
        self._orchestrator.start(cfg, cbs)

    def _on_full_auto_toggle(self):
        """Handle enabling/disabling of Full Auto and show mode dropdown accordingly."""
        self._update_full_auto_mode_visibility()
        self._refresh_start_state()

    def _update_full_auto_mode_visibility(self):
        try:
            if self.full_auto_var.get():
                self.full_auto_mode_dropdown.configure(state='readonly')
            else:
                self.full_auto_mode_dropdown.configure(state='disabled')
        except Exception:
            pass

    # Manual resume picker removed -- Start/Resume auto-resumes when possible

    def _stop(self):
        try:
            self._orchestrator.stop()
            self._append_log("Stop requested.")
        finally:
            self.stop_btn.config(state='disabled')
            self.start_btn.config(state='normal')

    def _append_log(self, text: str):
        if not self.log:
            return
        def _do_insert(msg: str):
            try:
                sanitized = self._sanitize_text(msg)
                if not isinstance(sanitized, str):
                    sanitized = str(sanitized)
                self.log.config(state=tk.NORMAL)
                self.log.insert(tk.END, sanitized + "\n")
                self.log.see(tk.END)
                self.log.config(state=tk.DISABLED)
            except Exception:
                pass
        try:
            # Schedule on UI thread for thread-safety
            self.log.after(0, _do_insert, text)
        except Exception:
            _do_insert(text)

    def _browse_run_db(self):
        initial_dir = str(app_paths.aco_runs) if app_paths.aco_runs.exists() else os.getcwd()
        p = self.ask_open_file(
            title="Select optimization.db",
            initialdir=initial_dir,
            filetypes=[("SQLite DB", "optimization.db"), ("All Files", "*.*")],
        )
        if p and os.path.basename(p) == "optimization.db":
            self._apply_resume_db(os.path.dirname(p))
            self.log_info(f"Loaded run database: {os.path.dirname(p)}")
        else:
            if p:
                self.log_warning(f"Invalid run DB selection: {p}")
                messagebox.showerror("Load Run DB", "Please select an optimization.db file.")

    def _clear_run_db(self):
        self.resume_db_dir = None
        self._update_selection_display(self.resume_label, self.resume_display, "No run DB loaded", is_default=True)
        # Re-enable manual selection controls
        try:
            self.btn_browse_dataset.config(state='normal')
            self.btn_browse_server.config(state='normal')
            self.btn_browse_api.config(state='normal')
        except Exception:
            pass
        self._refresh_start_state()

    def _browse_knowledge(self):
        try:
            initial_dir = str(app_paths.aco_runs) if app_paths.aco_runs.exists() else os.getcwd()
            p = self.ask_open_file(
                title="Load Historical Knowledge",
                initialdir=initial_dir,
                filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
            )
            if not p:
                return
            import json
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Basic schema check
            if not isinstance(data, dict) or 'schema_version' not in data:
                messagebox.showerror("Knowledge", "Invalid knowledge file format.")
                return
            self.historical_knowledge = data
            self.log_info(f"Loaded historical knowledge from {p}")
            self._update_selection_display(
                self.knowledge_label,
                self.knowledge_display,
                f"Loaded knowledge: {os.path.basename(p)}"
            )
            self._append_log(f"Loaded historical knowledge from {os.path.basename(p)}")
        except Exception as e:
            self.log_error(f"Failed to load knowledge file {p}: {e}")
            messagebox.showerror("Knowledge", str(e))

    def _apply_resume_db(self, run_dir: str):
        """Populate fields from selected run DB and lock controls for safe resume."""
        try:
            self.resume_db_dir = run_dir
            self.log_info(f"Resume database applied: {run_dir}")
            base = os.path.basename(run_dir)
            self._update_selection_display(self.resume_label, self.resume_display, f"Loaded: {base}")

            # Read run metadata from optimization.db
            try:
                db = SQLiteOptimizationDatabase(Path(run_dir))
                meta = db.load_run_metadata()
            except Exception:
                meta = None

            # Populate dataset path from DB if present
            ds_path = getattr(meta, 'dataset_path', None) if meta else None
            if ds_path and os.path.exists(ds_path):
                self.dataset_path = ds_path
                self._update_selection_display(self.dataset_label, self.dataset_display, os.path.basename(ds_path))

            # Apply endpoint type from DB if present
            try:
                ep = getattr(meta, 'endpoint_type', None)
                if ep:
                    global_settings.set_endpoint_type(ep)
            except Exception:
                pass

            # Load original server/API config paths from DB metadata if present; fallback to last-used
            loaded_any = False
            try:
                scp = getattr(meta, 'server_config_path', None) if meta else None
                if scp and os.path.exists(scp):
                    ok, msg = self._load_server_config(scp)
                    if ok:
                        self.server_config_path = scp
                        self._update_selection_display(self.server_label, self.server_display, os.path.basename(scp))
                        loaded_any = True
            except Exception:
                pass
            if not loaded_any:
                try:
                    if self.server_config.auto_load_last_config() and self.server_label:
                        try:
                            name = open(os.path.join(app_paths.server_configs, '.last_config'), 'r').read().strip()
                        except Exception:
                            name = 'Last used'
                        display_name = name or 'Last used'
                        self._update_selection_display(self.server_label, self.server_display, display_name)
                except Exception:
                    pass

            loaded_any = False
            try:
                acp = getattr(meta, 'api_config_path', None) if meta else None
                if acp and os.path.exists(acp):
                    ok, msg = self._load_api_config(acp)
                    if ok:
                        self.api_config_path = acp
                        self._update_selection_display(self.api_label, self.api_display, os.path.basename(acp))
                        loaded_any = True
            except Exception:
                pass
            if not loaded_any:
                try:
                    last = self.api_config.load_last_config()
                    if last:
                        ok, _sp, _ui = self.api_config.load_config(last)
                        if ok:
                            self._update_selection_display(self.api_label, self.api_display, last)
                except Exception:
                    pass

            # Disable manual browsing to avoid mismatched resume inputs
            try:
                self.btn_browse_dataset.config(state='disabled')
                self.btn_browse_server.config(state='disabled')
                self.btn_browse_api.config(state='disabled')
            except Exception:
                pass
        finally:
            self._refresh_start_state()

