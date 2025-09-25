"""
ACO Data Viewer Tab
Provides manual/history view and statistical analysis of ACO optimization runs
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from managers.path_manager import app_paths
from benchmarking.interfaces import ParameterConverter
from ui.base_components import BaseUIComponent, ScrollableFrameManager, ThemedScrolledText
from ui.aco_database_viewer import StandaloneACODatabaseViewer

class ACODataViewerTab(BaseUIComponent):

    """ACO optimization data viewer with manual history and analysis views"""
    def __init__(self, parent, api_client, **kwargs):
        super().__init__(parent, config_manager=None, api_client=api_client)
        
        # Database viewer
        self.db_viewer = None
        self.current_db_path = None
        
        # Test cases data
        self.all_test_cases = []
        self.filtered_test_cases = []
        self.current_page = 0
        self.items_per_page = 20
        
        # UI elements references
        self.db_label = None
        self.summary_label = None
        self.test_case_frames = []
        self.page_label = None
        self.sort_mode = tk.StringVar(value="Correct Answers")  # Insights sorting
        
        # Filter variables
        self.filter_question = tk.StringVar(value="All")
        self.filter_score = tk.StringVar(value="All")
        # Correlation controls
        self.corr_view_mode = tk.StringVar(value="Values")
        self.corr_sort_mode = tk.StringVar(value="Correct Answers")
        self.corr_min_coverage = tk.StringVar(value="5")
        self.corr_phase = tk.StringVar(value="ACO only")
        self.scroll_manager = ScrollableFrameManager(self)

    @staticmethod
    def _beta_ci_approx(k: int, n: int, alpha: float = 1.0, beta: float = 1.0, z: float = 1.96) -> tuple:
        """Approximate 95% credible interval for Bernoulli accuracy via Beta(a,b) normal approx.

        Uses posterior Beta(k+alpha, n-k+beta), returns (lo, hi) clipped to [0,1].
        """
        try:
            a = k + alpha
            b = (n - k) + beta
            denom = a + b
            if denom <= 0:
                return (0.0, 1.0)
            mean = a / denom
            var = (a * b) / (denom * denom * (denom + 1.0))
            std = var ** 0.5
            lo = max(0.0, min(1.0, mean - z * std))
            hi = max(0.0, min(1.0, mean + z * std))
            return (lo, hi)
        except Exception:
            return (0.0, 1.0)
    
    def extract_question_number(self, test_case: Dict) -> str:
        """extract the actual question number from database"""
        # Use the question_number field directly from database
        if 'question_number' in test_case and test_case['question_number']:
            return str(test_case['question_number'])
        
        # Fallback to database question_id
        return str(test_case['question_id'])
    
    def setup_ui(self):
        """Initialize the viewer layout with modern sections."""
        wrapper, _, scrollable = self.scroll_manager.create_scrollable_frame(self.parent)
        wrapper.pack(fill=tk.BOTH, expand=True)
        scrollable.configure(style='Content.TFrame')

        main_frame = ttk.Frame(scrollable, style='Content.TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=self.content_pad_x, pady=self.content_pad_y)

        source_section = self.create_section(main_frame, "Data Source")
        source_section.pack(fill=tk.X, pady=(0, self.section_pad_y // 2))
        self.apply_card_padding(source_section)
        self._build_source_section(source_section)

        best_section = self.create_section(main_frame, "Best Recommendation")
        best_section.pack(fill=tk.X, pady=(0, self.section_pad_y // 2))
        self.apply_card_padding(best_section)
        self._build_best_recommendation_section(best_section)

        insights_section = self.create_section(main_frame, "Insights")
        insights_section.pack(fill=tk.BOTH, expand=True, pady=(0, self.section_pad_y // 2))
        self.apply_card_padding(insights_section)
        self._build_insights_section(insights_section)

        filters_section = self.create_section(main_frame, "Filters")
        filters_section.pack(fill=tk.X, pady=(0, self.section_pad_y // 2))
        self.apply_card_padding(filters_section)
        self._build_filter_section(filters_section)

        history_section = self.create_section(main_frame, "Test Case History")
        history_section.pack(fill=tk.BOTH, expand=True)
        self.apply_card_padding(history_section)
        self._build_test_cases_section(history_section)

        footer_frame = ttk.Frame(main_frame, style='Content.TFrame')
        footer_frame.pack(fill=tk.X, pady=(self.section_pad_y // 2, 0))
        self._build_footer_section(footer_frame)

    def _build_best_recommendation_section(self, parent):
        """Create the best recommendation banner and actions."""
        content = ttk.Frame(parent, style='Content.TFrame')
        content.pack(fill=tk.X)

        self.best_label = ttk.Label(content,
                                   text="Load a database to see the current best combo.",
                                   font=self.FONTS['label_normal'])
        self.best_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        action_row = ttk.Frame(parent, style='Content.TFrame')
        action_row.pack(fill=tk.X, pady=(self.section_internal_pad // 2, 0))
        ttk.Button(action_row, text="Export API Config", command=self._export_best_config).pack(side=tk.LEFT)
    @staticmethod
    def _sanitize_ascii(text: str) -> str:
        """Return ASCII-only version of text (drop non-ASCII)."""
        try:
            return (text or "").encode('ascii', 'ignore').decode('ascii')
        except Exception:
            return str(text)

    def _sanitize_widget_tree_texts(self, root_widget):
        """Walk child widgets and sanitize their 'text' content to ASCII-only."""
        try:
            children = root_widget.winfo_children()
        except Exception:
            children = []
        for w in children:
            try:
                if 'text' in w.keys():
                    t = w.cget('text')
                    st = self._sanitize_ascii(t)
                    if st != t:
                        w.config(text=st)
            except Exception:
                pass
            # Recurse
            self._sanitize_widget_tree_texts(w)
    
    def _build_source_section(self, parent):
        """Create the database selection and summary controls."""
        button_row = ttk.Frame(parent, style='Content.TFrame')
        button_row.pack(fill=tk.X)

        load_btn = ttk.Button(button_row, text="Load Database", command=self.load_database, style='Accent.TButton')
        load_btn.pack(side=tk.LEFT)

        ttk.Button(button_row, text="Export Historical Knowledge...",
                  command=self._export_historical_knowledge).pack(side=tk.LEFT, padx=(12, 0))

        self.db_label = ttk.Label(
            button_row,
            text="No database loaded",
            font=self.FONTS['label_normal'],
            foreground=self.COLORS.get('text_secondary')
        )
        self.db_label.pack(side=tk.LEFT, padx=(12, 0))

        summary_row = ttk.Frame(parent, style='Content.TFrame')
        summary_row.pack(fill=tk.X, pady=(self.section_internal_pad // 2, 0))
        self.summary_label = ttk.Label(summary_row, text="", font=self.FONTS['label_bold'])
        self.summary_label.pack(anchor='w')
    def _build_insights_section(self, parent):
        """Create insights view for top parameter combos and correlations."""
        controls = ttk.Frame(parent, style='Content.TFrame')
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Top Combinations Sort:").pack(side=tk.LEFT)
        sort_combo = ttk.Combobox(
            controls,
            textvariable=self.sort_mode,
            values=["Correct Answers", "Average Score"],
            width=18,
            state='readonly'
        )
        sort_combo.pack(side=tk.LEFT, padx=(6, 12))
        sort_combo.bind('<<ComboboxSelected>>', lambda e: self.update_insights())
        legend = ttk.Label(
            controls,
            text="Correct Answers: orders by total correct then coverage; Average Score: orders by mean score.",
            font=self.FONTS['label_small'],
            foreground=self.COLORS.get('text_secondary')
        )
        legend.pack(side=tk.LEFT)

        pane = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, pady=(self.section_internal_pad, 0))

        left_frame = ttk.Frame(pane, style='Content.TFrame')
        pane.add(left_frame, weight=1)
        ttk.Label(left_frame, text="Top Parameter Combinations", font=self.FONTS['label_bold']).pack(anchor='w')
        self.top_combos_text = ThemedScrolledText(left_frame, font=self.FONTS['code_normal'])
        self.top_combos_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.style_text_widget(self.top_combos_text.text, variant='surface')
        self.top_combos_text.config(state='disabled')

        right_frame = ttk.Frame(pane, style='Content.TFrame')
        pane.add(right_frame, weight=1)
        header = ttk.Frame(right_frame, style='Content.TFrame')
        header.pack(fill=tk.X)
        ttk.Label(header, text="Value & Pair Correlations", font=self.FONTS['label_bold']).pack(anchor='w')

        corr_controls = ttk.Frame(right_frame, style='Content.TFrame')
        corr_controls.pack(fill=tk.X, pady=(4, 4))
        ttk.Label(corr_controls, text="View:").pack(side=tk.LEFT)
        view_combo = ttk.Combobox(corr_controls, textvariable=self.corr_view_mode,
                                 values=["Values", "Pairs"], width=10, state='readonly')
        view_combo.pack(side=tk.LEFT, padx=(4, 12))
        view_combo.bind('<<ComboboxSelected>>', lambda e: self.update_insights())
        ttk.Label(corr_controls, text="Sort:").pack(side=tk.LEFT)
        corr_sort_combo = ttk.Combobox(corr_controls, textvariable=self.corr_sort_mode,
                                       values=["Correct Answers", "Average Score"], width=16, state='readonly')
        corr_sort_combo.pack(side=tk.LEFT, padx=(4, 12))
        corr_sort_combo.bind('<<ComboboxSelected>>', lambda e: self.update_insights())
        ttk.Label(corr_controls, text="Min coverage:").pack(side=tk.LEFT)
        cov_combo = ttk.Combobox(corr_controls, textvariable=self.corr_min_coverage,
                                 values=["1", "3", "5", "10", "15"], width=6, state='readonly')
        cov_combo.pack(side=tk.LEFT, padx=(4, 12))
        cov_combo.bind('<<ComboboxSelected>>', lambda e: self.update_insights())
        ttk.Label(corr_controls, text="Phase:").pack(side=tk.LEFT)
        phase_combo = ttk.Combobox(corr_controls, textvariable=self.corr_phase,
                                   values=["ACO only", "All phases"], width=12, state='readonly')
        phase_combo.pack(side=tk.LEFT, padx=(4, 12))
        phase_combo.bind('<<ComboboxSelected>>', lambda e: self.update_insights())

        self.correlations_text = ThemedScrolledText(right_frame, font=self.FONTS['code_normal'])
        self.correlations_text.pack(fill=tk.BOTH, expand=True)
        self.style_text_widget(self.correlations_text.text, variant='surface')
        self.correlations_text.config(state='disabled')
    def _build_filter_section(self, parent):
        """Create filter controls section."""
        row = ttk.Frame(parent, style='Content.TFrame')
        row.pack(fill=tk.X)

        ttk.Label(row, text="Question:").pack(side=tk.LEFT)
        self.question_combo = ttk.Combobox(
            row,
            textvariable=self.filter_question,
            values=["All"],
            width=14,
            state='readonly'
        )
        self.question_combo.pack(side=tk.LEFT, padx=(6, 24))
        self.question_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filters())

        ttk.Label(row, text="Score:").pack(side=tk.LEFT)
        score_combo = ttk.Combobox(
            row,
            textvariable=self.filter_score,
            values=["All", "Correct (1.0)", "Incorrect (0.0)", "Partial"],
            width=18,
            state='readonly'
        )
        score_combo.pack(side=tk.LEFT, padx=(6, 0))
        score_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filters())
    def _build_test_cases_section(self, parent):
        """Create scrollable test cases display section."""
        wrapper, canvas, scrollable = self.scroll_manager.create_scrollable_frame(parent)
        wrapper.pack(fill=tk.BOTH, expand=True)
        self.test_canvas = canvas
        self.scrollable_frame = scrollable
    def _build_footer_section(self, parent):
        """Create bottom section with pagination controls."""
        pagination_frame = ttk.Frame(parent, style='Content.TFrame')
        pagination_frame.pack(side=tk.RIGHT)

        self.prev_btn = ttk.Button(
            pagination_frame,
            text="<< Prev Page",
            command=self.prev_page,
            state='disabled'
        )
        self.prev_btn.pack(side=tk.LEFT, padx=4)

        self.page_label = ttk.Label(pagination_frame, text="Page 0 of 0", font=self.FONTS['label_normal'])
        self.page_label.pack(side=tk.LEFT, padx=8)

        self.next_btn = ttk.Button(
            pagination_frame,
            text="Next Page >>",
            command=self.next_page,
            state='disabled'
        )
        self.next_btn.pack(side=tk.LEFT, padx=4)
    def load_database(self):
        """Load an ACO run database file"""
        # open file dialog starting in ACO runs directory
        initial_dir = app_paths.aco_runs if app_paths.aco_runs.exists() else Path.home()
        
        db_path = self.ask_open_file(
            title="Select ACO Run Database",
            initialdir=str(initial_dir),
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
        )
        
        if not db_path:
            return
        
        self._load_database_file(db_path)
    
    def _load_database_file(self, db_path: str):
        """Load a specific database file"""
        try:
            # Create database viewer for the run directory
            db_run_dir = Path(db_path).parent
            self.db_viewer = StandaloneACODatabaseViewer(db_run_dir)
            
            # Store path
            self.current_db_path = db_path
            
            # Check if database exists
            if not self.db_viewer.database_exists():
                messagebox.showerror("Database Error", f"Database file not found: {db_path}")
                return
            
            # Update UI
            db_name = db_run_dir.name
            # ttk.Label does not accept 'fg'; use 'foreground'
            self.db_label.config(
                text=f"Database: {db_name} OK",
                foreground=self.COLORS.get('green_text', '#16A34A')
            )
            
            # Load test cases
            self.load_test_cases()
            
            # Update summary
            self.update_summary()

            # Update insights
            self.update_insights()
            # Update best recommendation
            self.update_best_recommendation()
            
            # Update question filter options
            self.update_question_filter()
            
            # Display first page
            self.current_page = 0
            self.display_current_page()
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load database:\n{str(e)}")
    
    def load_test_cases(self):
        """Load all test cases from database"""
        if not self.db_viewer:
            return
        
        try:
            # Get all test cases from the database viewer
            self.all_test_cases = self.db_viewer.get_all_test_cases()
            
            # Initially show all test cases
            self.filtered_test_cases = self.all_test_cases.copy()
            
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load test cases:\n{str(e)}")
    
    def update_summary(self):
        """Update the summary label with database statistics"""
        if not self.all_test_cases:
            self.summary_label.config(text="")
            return
        
        total = len(self.all_test_cases)
        completed = len([tc for tc in self.all_test_cases if tc.get('score') is not None])
        correct = len([tc for tc in self.all_test_cases if (tc.get('score') or 0.0) == 1.0])
        
        pct_done = (completed / total * 100.0) if total > 0 else 0.0
        accuracy = (correct / completed * 100.0) if completed > 0 else 0.0
        
        summary = f"Summary: {completed}/{total} tests completed ({pct_done:.1f}%) | "
        summary += f"- {correct} correct ({accuracy:.1f}% accuracy)"
        
        self.summary_label.config(text=summary)

    def _get_latest_snapshot_text(self) -> str:
        if not self.db_viewer:
            return ""
        try:
            snap = self.db_viewer.get_latest_snapshot()
            if not snap:
                return ""
            return f" | Contenders: {snap.get('contenders_count', 0)} | Target coverage: {snap.get('target_coverage', 0)}"
        except Exception:
            return ""

    def _estimate_question_total(self) -> int:
        try:
            meta = self.db_viewer.get_run_metadata()
            ds_path = meta.get('dataset_path')
            if ds_path and Path(ds_path).exists():
                try:
                    content = Path(ds_path).read_text(encoding='utf-8', errors='ignore')
                    return max(0, content.count('--- Question '))
                except Exception:
                    pass
            return int(meta.get('total_questions') or 0)
        except Exception:
            return 0

    def update_best_recommendation(self):
        # Compute top combo by Correct Answers sorting
        try:
            records = self.db_viewer._load_all_completed()
        except Exception:
            records = []
        if not records:
            self.best_label.config(text="No completed tests yet.")
            return
        # Group by parameters
        from collections import defaultdict
        groups = defaultdict(lambda: {'scores': [], 'tested_questions': set(), 'params': {}})
        for r in records:
            key = ParameterConverter.make_hashable_key(r.get('parameters') or {})
            g = groups[key]
            g['scores'].append(float(r.get('score') or 0.0))
            if r.get('question_number') is not None:
                try:
                    g['tested_questions'].add(int(r['question_number']))
                except Exception:
                    pass
            if not g['params']:
                g['params'] = dict(r.get('parameters') or {})
        entries = []
        question_total = self._estimate_question_total()
        for g in groups.values():
            tested = len(g['scores'])
            correct = sum(1 for s in g['scores'] if s >= 1.0)
            acc = (correct/tested) if tested else 0.0
            lo, hi = self._beta_ci_approx(correct, tested)
            entries.append({
                'parameters': g['params'],
                'tested': tested,
                'correct': correct,
                'acc': acc,
                'lo': lo,
                'hi': hi,
                'tested_questions': sorted(list(g['tested_questions'])),
                'question_total': question_total,
            })
        # Sort by Correct Answers then tested then acc
        entries.sort(key=lambda e: (e['correct'], e['tested'], e['acc']), reverse=True)
        best = entries[0]
        validated = (best['question_total'] and best['tested'] >= best['question_total'])
        rel = 'High' if best['tested'] >= 15 else ('Medium' if best['tested'] >= 5 else 'Low')
        ci_pct = f"[{best['lo']*100:.0f}–{best['hi']*100:.0f}%]"
        snap_text = self._get_latest_snapshot_text()
        txt = f"Best: correct {best['correct']} of {best['tested']} ({best['acc']*100:.0f}% {ci_pct}) | coverage {best['tested']}/{best['question_total']} | reliability {rel}{'  [VALIDATED]' if validated else ''}{snap_text}"
        self.best_label.config(text=txt)

    def _export_best_config(self):
        # Extract current best from DB
        try:
            records = self.db_viewer._load_all_completed()
        except Exception:
            messagebox.showerror("Export", "Load a database with results first.")
            return
        if not records:
            messagebox.showinfo("Export", "No results to export.")
            return
        from collections import defaultdict
        groups = defaultdict(lambda: {'scores': 0, 'count': 0, 'params': {}})
        for r in records:
            key = ParameterConverter.make_hashable_key(r.get('parameters') or {})
            g = groups[key]
            g['scores'] += 1.0 if (r.get('score') or 0.0) >= 1.0 else 0.0
            g['count'] += 1
            if not g['params']:
                g['params'] = dict(r.get('parameters') or {})
        best = None
        for g in groups.values():
            if best is None or (g['scores'], g['count']) > (best['scores'], best['count']):
                best = g
        if not best:
            messagebox.showinfo("Export", "No best combination found.")
            return
        initial_dir = str(app_paths.saved_configs) if app_paths.saved_configs.exists() else str(Path.home())
        os.makedirs(initial_dir, exist_ok=True)
        path = self.ask_save_file(
            title="Export API Config",
            initialdir=initial_dir,
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
            initialfile="best_aco_config.json",
        )
        if not path:
            return
        payload = {
            "values": best['params'],
            "enabled": {k: True for k in best['params'].keys()},
            "array_values": {},
            "_meta": {
                "source": "ACO Data Viewer export",
                "from_run": Path(self.current_db_path).parent.name if self.current_db_path else None,
            }
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
            messagebox.showinfo("Export", f"Saved API config to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Export", f"Failed to save: {e}")

    def _export_historical_knowledge(self):
        """Export baseline, ACO results, and aggregates into a portable JSON file."""
        try:
            if not self.db_viewer or not self.db_viewer.database_exists():
                messagebox.showerror("Export", "Load a database with results first.")
                return
            # Read extended run metadata
            import sqlite3, json as _json, hashlib
            meta = {}
            with sqlite3.connect(str(self.db_viewer.db_path)) as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA table_info(run_metadata)")
                cols = [r[1] for r in cur.fetchall()]
                cur.execute("SELECT * FROM run_metadata WHERE id = 1")
                row = cur.fetchone()
                if row:
                    meta = {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
                # Baseline rows
                baseline = []
                cur.execute("SELECT question_number, score, response_time FROM test_cases WHERE phase='baseline' AND completed=1")
                for qn, sc, rt in cur.fetchall():
                    baseline.append({
                        'question_number': int(qn) if qn is not None else None,
                        'score': float(sc) if sc is not None else None,
                        'response_time': float(rt) if rt is not None else None
                    })
                # ACO results
                aco_results = []
                cur.execute("SELECT question_number, parameters_json, score, error_message FROM test_cases WHERE phase='aco' AND completed=1")
                for qn, pjson, sc, err in cur.fetchall():
                    try:
                        params = _json.loads(pjson) if pjson else {}
                    except Exception:
                        params = {}
                    aco_results.append({
                        'question_number': int(qn) if qn is not None else None,
                        'parameters': params,
                        'score': float(sc) if sc is not None else None,
                        'completed': True,
                        'error_message': err or None
                    })
                # Aggregates (per-combo)
                aggregates = []
                cur.execute("SELECT parameters_json, AVG(score), COUNT(*), SUM(CASE WHEN score>=1.0 THEN 1 ELSE 0 END) FROM test_cases WHERE phase='aco' AND completed=1 AND score IS NOT NULL GROUP BY parameters_json")
                for pjson, avg_sc, cnt, corr in cur.fetchall():
                    try:
                        params = _json.loads(pjson) if pjson else {}
                    except Exception:
                        params = {}
                    aggregates.append({
                        'parameters': params,
                        'tested_count': int(cnt or 0),
                        'mean_score': float(avg_sc or 0.0),
                        'correct_count': int(corr or 0)
                    })

            dataset_path = meta.get('dataset_path') or ''
            # Dataset hash
            dataset_id = None
            try:
                if dataset_path and os.path.exists(dataset_path):
                    h = hashlib.sha256()
                    with open(dataset_path, 'rb') as df:
                        for chunk in iter(lambda: df.read(8192), b''):
                            h.update(chunk)
                    dataset_id = h.hexdigest()
            except Exception:
                dataset_id = None

            # Samplers from API config if available (best-effort)
            samplers = None
            api_config_path = meta.get('api_config_path') or ''
            try:
                if api_config_path and os.path.exists(api_config_path):
                    with open(api_config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                    vals = (cfg or {}).get('values') or {}
                    sm = vals.get('samplers')
                    if isinstance(sm, list) and sm:
                        samplers = sm
            except Exception:
                samplers = None

            export_obj = {
                'schema_version': 1,
                'exported_at': datetime.now().isoformat(),
                'dataset': {
                    'path': dataset_path,
                    'id': dataset_id,
                    'total_questions': int(meta.get('total_questions') or 0)
                },
                'run_meta': {
                    'endpoint_type': meta.get('endpoint_type') or '',
                    'samplers': samplers,
                    'api_config_path': api_config_path,
                    'server_config_path': meta.get('server_config_path') or ''
                },
                'baseline': baseline,
                'aco_results': aco_results,
                'aggregates': aggregates
            }

            # Save file
            suggested = f"historical_{(meta.get('run_name') or 'export').replace(' ', '_')}.json"
            out = self.ask_save_file(
                title="Save Historical Knowledge",
                initialdir=str(Path(self.current_db_path).parent if self.current_db_path else app_paths.aco_runs),
                initialfile=suggested,
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("All Files", "*.*")],
            )
            if not out:
                return
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(export_obj, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Export", f"Saved historical knowledge to:\n{out}")
        except Exception as e:
            messagebox.showerror("Export", f"Export failed: {e}")

    def _rerun_validation(self):
        if not self.db_viewer:
            messagebox.showerror("Validation", "Load a database first.")
            return
        meta = self.db_viewer.get_run_metadata()
        ds_path = meta.get('dataset_path')
        if not ds_path or not Path(ds_path).exists():
            messagebox.showerror("Validation", "Dataset path missing in run metadata; cannot run validation.")
            return
        # Compute best params
        try:
            recs = self.db_viewer._load_all_completed()
        except Exception:
            recs = []
        if not recs:
            messagebox.showinfo("Validation", "No results to validate.")
            return
        from collections import defaultdict
        groups = defaultdict(lambda: {'scores': 0, 'count': 0, 'params': {}})
        for r in recs:
            key = ParameterConverter.make_hashable_key(r.get('parameters') or {})
            g = groups[key]
            g['scores'] += 1.0 if (r.get('score') or 0.0) >= 1.0 else 0.0
            g['count'] += 1
            if not g['params']:
                g['params'] = dict(r.get('parameters') or {})
        best = None
        for g in groups.values():
            if best is None or (g['scores'], g['count']) > (best['scores'], best['count']):
                best = g
        if not best:
            messagebox.showinfo("Validation", "No best combination found.")
            return
        if not messagebox.askyesno("Validation", "Run validation for best combo across the full dataset? Results will be saved into this DB as phase='validation'."):
            return
        def _worker():
            try:
                from benchmarking.runner import BenchmarkExecutor
                from benchmarking.database import SQLiteOptimizationDatabase, create_test_case_from_parameters
                from benchmarking.scorer import FlexibleScorer
                be = BenchmarkExecutor(self.api_client)
                db = SQLiteOptimizationDatabase(Path(self.current_db_path).parent)
                def _stream(question_obj, record):
                    try:
                        qnum = record.get('q_id') or record.get('question_number')
                        gt = record.get('ground_truth', '')
                        ans = record.get('response', '')
                        score = FlexibleScorer().score_answer(gt, ans, scoring_mode='EXACT')
                        q_struct = {
                            'question_number': int(qnum) if qnum else 0,
                            'ground_truth': gt,
                            'turns': None
                        }
                        tc = create_test_case_from_parameters(question_id=int(qnum) if qnum else 0, question=q_struct, parameters=best['params'])
                        from benchmarking.interfaces import TestResult
                        tr = TestResult(test_case=tc, success=True, response=ans, score=score, response_time=record.get('response_time', 0.0), slots_data=None, full_api_response={'_raw': record.get('raw_completions_response', '')})
                        db.save_test_result(tc, tr, phase='validation')
                    except Exception as ee:
                        self.log_error(f"validation stream error: {ee}")
                total = self._estimate_question_total()
                selected = list(range(1, total+1)) if total > 0 else None
                be.run_benchmark_enhanced(
                    dataset_path=ds_path,
                    config_data=best['params'],
                    selected_questions=selected,
                    run_name=f"validation_{Path(self.current_db_path).parent.name}",
                    system_prompt=best['params'].get('system_prompt',''),
                    server_config_path=None,
                    api_config_path=None,
                    per_question_callback=_stream,
                )
                self._on_status_update("Validation complete; refresh viewer to see results.")
            except Exception as e:
                messagebox.showerror("Validation", f"Validation failed: {e}")
        import threading
        threading.Thread(target=_worker, daemon=True).start()
    
    def update_question_filter(self):
        """Update question filter dropdown with available questions"""
        if not self.all_test_cases:
            return
        
        # Get unique actual question numbers from content
        actual_question_numbers = set()
        for tc in self.all_test_cases:
            actual_num = self.extract_question_number(tc)
            actual_question_numbers.add(actual_num)
        
        # Sort numerically
        try:
            sorted_questions = sorted(actual_question_numbers, key=lambda o: int(o))
        except ValueError:
            # If some aren't numbers, sort alphabetically
            sorted_questions = sorted(actual_question_numbers)
        
        question_options = ["All"] + [f"Q{qnum}" for qnum in sorted_questions]
        
        self.question_combo['values'] = question_options
    
    def display_current_page(self):
        """Display the current page of test cases"""
        # Clear eoisting test case frames
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.test_case_frames = []
        
        # Calculate page boundaries
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.filtered_test_cases))
        
        if not self.filtered_test_cases:
            tk.Label(
                self.scrollable_frame,
                text="No test cases to display",
                font=('Arial', 12),
                fg='gray'
            ).pack(pady=20)
            self.update_pagination_controls()
            return
        
        # Display test cases for current page
        for i in range(start_idx, end_idx):
            test_case = self.filtered_test_cases[i]
            frame = self.create_test_case_frame(test_case)
            frame.pack(fill='x', padx=10, pady=5)
            self.test_case_frames.append(frame)
        
        # Update pagination controls
        self.update_pagination_controls()
        
        # Scroll to top
        self.test_canvas.yview_moveto(0)
    

    def create_test_case_frame(self, test_case: Dict) -> ttk.Frame:
        """Create a frame displaying a single test case"""
        container = ttk.Frame(self.scrollable_frame, style='Content.TFrame', padding=(12, 10))
        container.configure(borderwidth=1, relief='solid')
        container.columnconfigure(0, weight=1)

        header = ttk.Frame(container, style='Content.TFrame')
        header.grid(row=0, column=0, sticky='ew')

        s_val = test_case.get('score')
        status_icon = "OK" if s_val == 1.0 else "X" if s_val == 0.0 else "~"
        status_text = "Correct" if s_val == 1.0 else "Incorrect" if s_val == 0.0 else "Partial"
        status_color = (
            self.COLORS.get('green_text', '#16A34A') if s_val == 1.0
            else self.COLORS.get('red_text', '#DC2626') if s_val == 0.0
            else self.COLORS.get('text_secondary', '#475467')
        )

        actual_question_num = self.extract_question_number(test_case)
        score_disp = f"{float(s_val):.1f}" if isinstance(s_val, (int, float)) else "N/A"
        header_text = f"{status_icon} Test #{test_case['test_id']} - Q{actual_question_num} {status_text} (Score: {score_disp})"
        if test_case.get('response_time') is not None:
            try:
                header_text += f" | {float(test_case.get('response_time')):.1f}s (total)"
            except Exception:
                pass

        ttk.Label(
            header,
            text=self._sanitize_ascii(header_text),
            font=self.FONTS['label_bold'],
            foreground=status_color
        ).grid(row=0, column=0, sticky='w')

        content = ttk.Frame(container, style='Content.TFrame')
        content.grid(row=1, column=0, sticky='ew', pady=(8, 0))
        content.columnconfigure(0, weight=1)

        row_idx = 0
        parameters = test_case.get('parameters') or {}
        params_text = "Parameters: " + ", ".join([f"{k}={v}" for k, v in parameters.items()]) if parameters else "Parameters: (none)"
        ttk.Label(
            content,
            text=self._sanitize_ascii(params_text),
            font=self.FONTS['code_small'],
            foreground=self.COLORS.get('text_secondary', '#475467'),
            wraplength=780,
            justify='left'
        ).grid(row=row_idx, column=0, sticky='w', pady=(0, 4))
        row_idx += 1

        if test_case.get('timestamp'):
            ttk.Label(
                content,
                text=f"Timestamp: {test_case['timestamp']}",
                font=self.FONTS['label_small'],
                foreground=self.COLORS.get('text_secondary', '#475467')
            ).grid(row=row_idx, column=0, sticky='w', pady=(0, 4))
            row_idx += 1

        question_text = test_case.get('question_content', 'No question content available')
        truncated_question = question_text[:120] + "..." if len(question_text) > 120 else question_text
        question_frame = ttk.Frame(content, style='Content.TFrame')
        question_frame.grid(row=row_idx, column=0, sticky='ew', pady=(2, 4))
        question_frame.columnconfigure(0, weight=1)

        ttk.Label(
            question_frame,
            text=self._sanitize_ascii(f"Question: {truncated_question}"),
            font=self.FONTS['label_normal'],
            wraplength=780,
            justify='left'
        ).grid(row=0, column=0, sticky='w')

        if len(question_text) > 120:
            ttk.Button(
                question_frame,
                text="Show Full",
                command=lambda qt=question_text: self.show_full_text("Question", qt)
            ).grid(row=0, column=1, padx=(8, 0), sticky='w')
        row_idx += 1

        ttk.Label(
            content,
            text=self._sanitize_ascii(f"Ground Truth: {test_case['ground_truth']}"),
            font=self.FONTS['label_bold'],
            foreground=self.COLORS.get('green_text', '#16A34A'),
            wraplength=780,
            justify='left'
        ).grid(row=row_idx, column=0, sticky='w', pady=(0, 4))
        row_idx += 1

        response_text = test_case['response'] or "No response"
        truncated_response = response_text[:120] + "..." if len(response_text) > 120 else response_text
        response_frame = ttk.Frame(content, style='Content.TFrame')
        response_frame.grid(row=row_idx, column=0, sticky='ew', pady=(2, 4))
        response_frame.columnconfigure(0, weight=1)

        response_color = self.COLORS.get('blue_text', '#2563EB') if s_val == 1.0 else self.COLORS.get('red_text', '#DC2626')
        ttk.Label(
            response_frame,
            text=self._sanitize_ascii(f"LLM Response: {truncated_response}"),
            font=self.FONTS['label_normal'],
            foreground=response_color,
            wraplength=780,
            justify='left'
        ).grid(row=0, column=0, sticky='w')

        if len(response_text) > 120:
            ttk.Button(
                response_frame,
                text="Show Full",
                command=lambda rt=response_text: self.show_full_text("LLM Response", rt)
            ).grid(row=0, column=1, padx=(8, 0), sticky='w')
        row_idx += 1

        data_frame = ttk.Frame(content, style='Content.TFrame')
        data_frame.grid(row=row_idx, column=0, sticky='w', pady=(4, 6))

        if test_case.get('slots_data'):
            ttk.Button(
                data_frame,
                text="View /slots Data",
                command=lambda sd=test_case['slots_data']: self.show_json_data("Server Slots Data", sd),
                style='Accent.TButton'
            ).grid(row=0, column=0, padx=(0, 8), sticky='w')

        if test_case.get('full_api_response'):
            ttk.Button(
                data_frame,
                text="View Full API Response",
                command=lambda fr=test_case['full_api_response']: self.show_json_data("Full API Response", fr)
            ).grid(row=0, column=1, sticky='w')
        row_idx += 1

        score_text = "EXACT MATCH" if s_val == 1.0 else (f"Score: {float(s_val):.2f}" if isinstance(s_val, (int, float)) else "Score unavailable")
        ttk.Label(
            content,
            text=score_text,
            font=self.FONTS['label_bold'],
            foreground=status_color
        ).grid(row=row_idx, column=0, sticky='w', pady=(4, 2))
        row_idx += 1

        if test_case.get('error_message'):
            ttk.Label(
                content,
                text=f"Error: {test_case['error_message']}",
                font=self.FONTS['label_small'],
                foreground=self.COLORS.get('red_text', '#DC2626'),
                wraplength=780,
                justify='left'
            ).grid(row=row_idx, column=0, sticky='w', pady=(0, 2))

        try:
            self._sanitize_widget_tree_texts(container)
        except Exception:
            pass

        return container
    def show_full_text(self, title: str, text: str):
        """Show full text in a popup window"""
        popup = tk.Toplevel(self.parent)
        popup.title(title)
        popup.geometry("800x600")
        
        text_widget = scrolledtext.ScrolledText(popup, wrap='word', font=('Arial', 10))
        self.style_text_widget(text_widget)
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)
        text_widget.insert('1.0', self._sanitize_ascii(text))
        text_widget.config(state='disabled')
        
        ttk.Button(popup, text="Close", command=popup.destroy).pack(pady=5)
    
    def show_json_data(self, title: str, data: dict):
        """Show JSON data in a formatted popup window"""
        popup = tk.Toplevel(self.parent)
        popup.title(title)
        popup.geometry("1000x700")
        
        text_widget = scrolledtext.ScrolledText(popup, wrap='word', font=('Courier', 9))
        self.style_text_widget(text_widget)
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Pretty print JSON data
        try:
            formatted_json = json.dumps(data, indent=2, ensure_ascii=True)
            text_widget.insert('1.0', formatted_json)
        except Exception as e:
            text_widget.insert('1.0', self._sanitize_ascii(f"Error formatting JSON: {e}\n\nRaw data:\n{data}"))
        
        text_widget.config(state='disabled')
        
        ttk.Button(popup, text="Close", command=popup.destroy).pack(pady=5)
    
    def apply_filters(self):
        """Apply all active filters to test cases"""
        self.filtered_test_cases = self.all_test_cases.copy()
        
        # Question filter
        if self.filter_question.get() != "All":
            target_question_num = self.filter_question.get().replace("Q", "")
            self.filtered_test_cases = [
                tc for tc in self.filtered_test_cases
                if self.extract_question_number(tc) == target_question_num
            ]
        
        # Score filter
        score_filter = self.filter_score.get()
        if score_filter == "Correct (1.0)":
            self.filtered_test_cases = [tc for tc in self.filtered_test_cases if tc['score'] == 1.0]
        elif score_filter == "Incorrect (0.0)":
            self.filtered_test_cases = [tc for tc in self.filtered_test_cases if tc['score'] == 0.0]
        elif score_filter == "Partial":
            self.filtered_test_cases = [
                tc for tc in self.filtered_test_cases 
                if tc['score'] is not None and 0.0 < tc['score'] < 1.0
            ]
        
        # Reset to first page and display
        self.current_page = 0
        self.display_current_page()

    def update_insights(self):
        """Populate insights text areas using database viewer helpers"""
        if not self.db_viewer:
            return
        
        # Determine which parameter keys actually varied across the run
        variable_keys = []
        try:
            value_sets = {}
            for tc in self.all_test_cases:
                for k, v in (tc.get('parameters') or {}).items():
                    s = value_sets.setdefault(k, set())
                    s.add(str(v))
            # Keep only keys with more than one unique value observed
            variable_keys = [k for k, s in value_sets.items() if len(s) > 1]
            # Sort for stable display
            variable_keys.sort()
        except Exception:
            variable_keys = []
        # Top combos (with explicit sort and clearer display)
        try:
            # Load all completed to compute reliable ordering by chosen sort
            records = self.db_viewer._load_all_completed()
        except Exception:
            records = []
        # Apply phase filter (reuse correlations control)
        phase_mode = (self.corr_phase.get() or "ACO only")
        if records and phase_mode == "ACO only":
            try:
                records = [r for r in records if str(r.get('phase') or '').lower() == 'aco']
            except Exception:
                pass
        # Determine total questions in dataset for coverage display
        question_total = 0
        try:
            meta = self.db_viewer.get_run_metadata()
            ds_path = meta.get('dataset_path')
            if ds_path and Path(ds_path).exists():
                try:
                    content = Path(ds_path).read_text(encoding='utf-8', errors='ignore')
                    question_total = max(0, content.count('--- Question '))
                except Exception:
                    question_total = 0
        except Exception:
            question_total = 0
        if question_total <= 0:
            # Fallback: unique questions observed
            try:
                all_q = {int(r['question_number']) if r['question_number'] is not None else int(r['question_id']) for r in records if (r['question_number'] is not None or r['question_id'] is not None)}
                question_total = len(all_q)
            except Exception:
                question_total = 0
        # Group by parameters
        groups = {}
        for r in records:
            key = ParameterConverter.make_hashable_key(r['parameters'] or {})
            g = groups.setdefault(key, { 'parameters': r['parameters'], 'scores': [], 'correct_q': set(), 'tested_q': set() })
            s = r.get('score')
            if s is not None:
                g['scores'].append(float(s))
                # Track distinct tested questions for coverage
                qn_any = r.get('question_number') if r.get('question_number') is not None else r.get('question_id')
                if qn_any is not None:
                    try:
                        g['tested_q'].add(int(qn_any))
                    except Exception:
                        pass
                if float(s) >= 1.0:
                    qn = r.get('question_number') or r.get('question_id')
                    if qn is not None:
                        try:
                            g['correct_q'].add(int(qn))
                        except Exception:
                            pass
        # Build entries
        entries = []
        for g in groups.values():
            # Use distinct-coverage tested count
            tested = len(g.get('tested_q', []))
            if tested <= 0:
                continue
            avg = sum(g['scores'])/tested
            # Use distinct correct question count
            correct = len(g.get('correct_q', []))
            entries.append({
                'parameters': g['parameters'],
                'tested': tested,
                'correct_count': correct,
                'avg_score': avg,
                'correct_questions': sorted(list(g['correct_q'])),
                'question_total': question_total
            })
        # Sort by selected mode
        mode = self.sort_mode.get()
        if mode == 'Correct Answers':
            entries.sort(key=lambda e: (e['correct_count'], e['tested'], e['avg_score']), reverse=True)
        else:
            entries.sort(key=lambda e: (e['avg_score'], e['correct_count'], e['tested']), reverse=True)
        # Limit to top 10 for display
        top_combos = entries[:10]

        self.top_combos_text.config(state='normal')
        self.top_combos_text.delete('1.0', tk.END)
        if not top_combos:
            self.top_combos_text.insert('1.0', 'No completed test cases yet.')
        else:
            for i, c in enumerate(top_combos, 1):
                # Show only variable parameters when possible; fall back to all
                if variable_keys:
                    items = [(k, c['parameters'].get(k)) for k in variable_keys if k in c['parameters']]
                else:
                    items = list(c['parameters'].items())
                params_disp = ", ".join([f"{k}={v}" for k, v in items])
                tested = c['tested']
                correct = c['correct_count']
                acc = (correct/tested*100.0) if tested > 0 else 0.0
                # Reliability badge
                if tested >= 15:
                    rel = 'High'
                elif tested >= 5:
                    rel = 'Medium'
                else:
                    rel = 'Low'
                ci_lo, ci_hi = self._beta_ci_approx(correct, tested)
                ci_pct = f"[{ci_lo*100:.0f}–{ci_hi*100:.0f}%]"
                validated_flag = "  [VALIDATED]" if c['question_total'] and tested >= c['question_total'] else ""
                self.top_combos_text.insert('end', f"{i:02d}. correct {correct} of {tested} tested ({acc:.0f}% {ci_pct}) | coverage {tested}/{c['question_total']} | reliability {rel}{validated_flag}\n")
                self.top_combos_text.insert('end', f"    {params_disp}\n")
                if c['correct_questions']:
                    qlist = ", ".join([f"q{int(q)}" for q in c['correct_questions']])
                    self.top_combos_text.insert('end', f"    correct questions: {qlist}\n")
                self.top_combos_text.insert('end', "\n")
        self.top_combos_text.config(state='disabled')

        # Correlations (facelift with coverage-aware sorting and reliability)
        try:
            records = self.db_viewer._load_all_completed()
        except Exception:
            records = []
        # Optional phase filter
        phase_mode = (self.corr_phase.get() or "ACO only")
        if records and phase_mode == "ACO only":
            try:
                records = [r for r in records if str(r.get('phase') or '').lower() == 'aco']
            except Exception:
                pass
        # Determine variable keys
        value_sets_corr = {}
        for r in records:
            for k, v in (r.get('parameters') or {}).items():
                s = value_sets_corr.setdefault(k, set())
                s.add(str(v))
        variable_keys_corr = [k for k, s in value_sets_corr.items() if len(s) > 1]
        variable_keys_corr.sort()

        def reliability_label(n: int) -> str:
            if n >= 15:
                return 'High'
            if n >= 5:
                return 'Medium'
            return 'Low'

        def bar(pct: float, width: int = 10) -> str:
            try:
                n = int(round(max(0.0, min(1.0, pct)) * width))
            except Exception:
                n = 0
            return '[' + ('#' * n) + ('.' * (width - n)) + ']'

        # Build entries
        try:
            min_cov = int(self.corr_min_coverage.get())
        except Exception:
            min_cov = 5
        view_mode = (self.corr_view_mode.get() or 'Values')
        sort_mode = (self.corr_sort_mode.get() or 'Correct Answers')

        def make_value_entries(recs):
            stats = {}
            for r in recs:
                params = r.get('parameters') or {}
                s = r.get('score')
                if s is None:
                    continue
                for k, v in params.items():
                    if variable_keys_corr and k not in variable_keys_corr:
                        continue
                    key = (k, str(v))
                    arr = stats.setdefault(key, [])
                    arr.append(float(s))
            entries_local = []
            for (k, v), arr in stats.items():
                tested = len(arr)
                if tested < min_cov:
                    continue
                correct = sum(1 for s in arr if s >= 1.0)
                avg = sum(arr)/tested if tested else 0.0
                entries_local.append({'param': k, 'value': v, 'tested': tested, 'correct': correct, 'avg': avg})
            if sort_mode == 'Correct Answers':
                entries_local.sort(key=lambda e: (e['correct'], e['tested'], e['avg']), reverse=True)
            else:
                entries_local.sort(key=lambda e: (e['avg'], e['correct'], e['tested']), reverse=True)
            return entries_local

        def make_pair_entries(recs):
            stats = {}
            for r in recs:
                params = r.get('parameters') or {}
                items = sorted([(k, str(v)) for k, v in params.items() if (not variable_keys_corr or k in variable_keys_corr)])
                s = r.get('score')
                if s is None:
                    continue
                for i in range(len(items)):
                    for j in range(i+1, len(items)):
                        a = items[i]; b = items[j]
                        key = (a, b)
                        arr = stats.setdefault(key, [])
                        arr.append(float(s))
            entries_local = []
            for key, arr in stats.items():
                tested = len(arr)
                if tested < min_cov:
                    continue
                correct = sum(1 for s in arr if s >= 1.0)
                avg = sum(arr)/tested if tested else 0.0
                (p1, v1), (p2, v2) = key
                entries_local.append({'pair': ((p1, v1), (p2, v2)), 'tested': tested, 'correct': correct, 'avg': avg})
            if sort_mode == 'Correct Answers':
                entries_local.sort(key=lambda e: (e['correct'], e['tested'], e['avg']), reverse=True)
            else:
                entries_local.sort(key=lambda e: (e['avg'], e['correct'], e['tested']), reverse=True)
            return entries_local

        self.correlations_text.config(state='normal')
        self.correlations_text.delete('1.0', tk.END)
        if not records:
            self.correlations_text.insert('end', 'No completed test cases yet.')
        else:
            if view_mode == 'Values':
                vals = make_value_entries(records)
                top_vals = vals[:5]
                worst_vals = list(reversed(vals[-5:])) if vals else []
                self.correlations_text.insert('end', 'Top Values (by chosen sort):\n')
                if not top_vals:
                    self.correlations_text.insert('end', '  (none meet coverage)\n')
                for e in top_vals:
                    acc = (e['correct']/e['tested']) if e['tested'] else 0.0
                    lo, hi = self._beta_ci_approx(e['correct'], e['tested'])
                    self.correlations_text.insert('end', f"  {e['param']}={e['value']}  correct {e['correct']} of {e['tested']} ({acc*100:.0f}% [{lo*100:.0f}–{hi*100:.0f}%])  acc {bar(acc)}  {reliability_label(e['tested'])}\n")
                self.correlations_text.insert('end', '\nWorst Values (by chosen sort):\n')
                if not worst_vals:
                    self.correlations_text.insert('end', '  (none meet coverage)\n')
                for e in worst_vals:
                    acc = (e['correct']/e['tested']) if e['tested'] else 0.0
                    lo, hi = self._beta_ci_approx(e['correct'], e['tested'])
                    self.correlations_text.insert('end', f"  {e['param']}={e['value']}  correct {e['correct']} of {e['tested']} ({acc*100:.0f}% [{lo*100:.0f}–{hi*100:.0f}%])  acc {bar(acc)}  {reliability_label(e['tested'])}\n")
            else:
                pairs = make_pair_entries(records)
                top_pairs = pairs[:5]
                worst_pairs = list(reversed(pairs[-5:])) if pairs else []
                self.correlations_text.insert('end', 'Top Pairs (by chosen sort):\n')
                if not top_pairs:
                    self.correlations_text.insert('end', '  (none meet coverage)\n')
                for e in top_pairs:
                    (p1, v1), (p2, v2) = e['pair']
                    acc = (e['correct']/e['tested']) if e['tested'] else 0.0
                    lo, hi = self._beta_ci_approx(e['correct'], e['tested'])
                    self.correlations_text.insert('end', f"  {p1}={v1} & {p2}={v2}  correct {e['correct']} of {e['tested']} ({acc*100:.0f}% [{lo*100:.0f}–{hi*100:.0f}%])  acc {bar(acc)}  {reliability_label(e['tested'])}\n")
                self.correlations_text.insert('end', '\nWorst Pairs (by chosen sort):\n')
                if not worst_pairs:
                    self.correlations_text.insert('end', '  (none meet coverage)\n')
                for e in worst_pairs:
                    (p1, v1), (p2, v2) = e['pair']
                    acc = (e['correct']/e['tested']) if e['tested'] else 0.0
                    lo, hi = self._beta_ci_approx(e['correct'], e['tested'])
                    self.correlations_text.insert('end', f"  {p1}={v1} & {p2}={v2}  correct {e['correct']} of {e['tested']} ({acc*100:.0f}% [{lo*100:.0f}–{hi*100:.0f}%])  acc {bar(acc)}  {reliability_label(e['tested'])}\n")
        self.correlations_text.config(state='disabled')
    
    def update_pagination_controls(self):
        """Update pagination buttons and label"""
        total_pages = (len(self.filtered_test_cases) - 1) // self.items_per_page + 1 if self.filtered_test_cases else 0
        
        self.page_label.config(text=f"Page {self.current_page + 1} of {total_pages}")
        
        # Enable/disable navigation buttons
        self.prev_btn.config(state='normal' if self.current_page > 0 else 'disabled')
        self.next_btn.config(state='normal' if self.current_page < total_pages - 1 else 'disabled')
    
    def prev_page(self):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.display_current_page()
    
    def next_page(self):
        """Go to Next Page"""
        total_pages = (len(self.filtered_test_cases) - 1) // self.items_per_page + 1
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.display_current_page()
    
    def cleanup(self):
        """Cleanup when tab is closed or switched"""
        # The StandaloneACODatabaseViewer uses context managers,
        # so no eoplicit cleanup is needed
        self.db_viewer = None
        self.current_db_path = None

