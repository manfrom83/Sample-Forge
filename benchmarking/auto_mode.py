"""
Auto Mode Orchestrator

Provides a minimal, resumable pipeline that:
- Runs a baseline to identify incorrect questions
- Explores with a bandit algorithm for a test budget
- Promotes top-K combinations to a minimum coverage on baseline-incorrect

This composes existing components without changing algorithms.
"""

from dataclasses import dataclass
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

from .interfaces import OptimizationConfig, ParameterArrayInfo, TestCase, TestResult
from .clean_aco_runner import CleanACORunner
from .database import SQLiteOptimizationDatabase, create_test_case_from_parameters
from .runner import BenchmarkExecutor
from .combinations import generate_all_combinations
from managers.path_manager import app_paths
from managers.global_settings import global_settings
from utils.server_manager import app_server_manager
from benchmarking.scorer import FlexibleScorer
from .interfaces import ParameterConverter
from .full_auto_scheduler import FullAutoScheduler


@dataclass
class AutoModeConfig:
    run_name: str
    dataset_path: str
    api_config: Any  # ParameterConfig
    server_config: Any  # ServerConfig
    endpoint_type: str
    parameter_arrays: Dict[str, ParameterArrayInfo]
    
    # Policy toggles
    force_clean: bool = True              # Clean server start
    auto_validate: bool = False           # Prefer manual validation via Run Benchmark
    resume_directory: Optional[str] = None  # If provided, resume this run directory
    # Full Auto: orchestrator manages sampler sequence and arrays internally
    full_auto: bool = False
    # Full Auto mode selector: 'legacy' (current behavior) or 'scheduler' (converge+validate)
    full_auto_mode: str = 'legacy'
    # Audit budget for uplift estimation
    audit_wrong_sample: int = 60
    audit_right_sample: int = 20
    # New: persist original config paths for reliable resume
    api_config_path: Optional[str] = None
    server_config_path: Optional[str] = None
    # Branch scheduler (Full Auto)
    iterate_branches: bool = True
    branch_order: List[str] = None  # e.g., ['A', 'B', 'C']
    # Historical knowledge import (portable JSON)
    historical_knowledge: Optional[Dict[str, Any]] = None


class AutoModeCallbacks:
    """Callback container with light text sanitization for orchestrator messages."""
    def __init__(self,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_progress: Optional[Callable[[str], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        # Store the provided functions
        self._on_status = on_status or (lambda msg: None)
        self._on_progress = on_progress or (lambda msg: None)
        self._on_error = on_error or (lambda msg: None)

    @staticmethod
    def _clean_text(text: Any) -> Any:
        try:
            if isinstance(text, str):
                # Remove Unicode replacement chars and fix known artifact sequences
                cleaned = text.replace("\uFFFD", "").replace("\ufffd", "")
                cleaned = cleaned.replace("�?\"", " - ")
                return cleaned
        except Exception:
            pass
        return text

    # Expose callable attributes that apply cleaning before invoking user callbacks
    def on_status(self, message: str):
        self._on_status(self._clean_text(message))

    def on_progress(self, message: str):
        self._on_progress(self._clean_text(message))

    def on_error(self, message: str):
        self._on_error(self._clean_text(message))


class AutoModeOrchestrator:
    """
    Orchestrates Auto Mode phases using existing components.

    Phases:
    1) Baseline: run default API config on all selected questions; write phase='baseline'
    2) Explore: run CleanACORunner (Thompson Sampling) with a test budget; write phase='aco'
    3) Promote: pick top-K by correct answers and fill coverage on baseline-incorrect to min_coverage; write phase='aco'
    """

    def __init__(self, api_client):
        self.api_client = api_client
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._db: Optional[SQLiteOptimizationDatabase] = None
        self._run_dir: Optional[Path] = None
        self._callbacks: AutoModeCallbacks = AutoModeCallbacks()
        self._baseline_executor: Optional[BenchmarkExecutor] = None
        self._explore_runner: Optional[CleanACORunner] = None
        self._scheduler: Optional[FullAutoScheduler] = None
        # Internal full-auto state
        self._full_auto_branch: Optional[str] = None  # 'A' nucleus, 'B' mirostat, 'C' dry+nucleus
        self._branch_index: int = 0

    def start(self, cfg: AutoModeConfig, callbacks: AutoModeCallbacks) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Auto Mode is already running")
        self._callbacks = callbacks
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run, args=(cfg,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag = True
        # Try to interrupt any ongoing phase
        try:
            if self._baseline_executor:
                self._baseline_executor.stop_benchmark()
            if self._explore_runner:
                try:
                    self._explore_runner.stop_optimization()
                except Exception:
                    pass
            if self._scheduler:
                try:
                    self._scheduler.stop()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self._explore_runner:
                self._explore_runner.stop_optimization()
        except Exception:
            pass

    # -------------------- Internal orchestration --------------------

    def _run(self, cfg: AutoModeConfig) -> None:
        try:
            # 0) Prep or resume run directory and DB (explicit resume only)
            rd = None
            if cfg.resume_directory:
                p = Path(cfg.resume_directory)
                if p.exists() and (p / "optimization.db").exists():
                    rd = p
            if rd is not None:
                # Tentatively resume, but verify dataset compatibility below
                self._run_dir = rd
                self._callbacks.on_status(f"Resuming Auto Mode in {rd.name}...")
                self._db = SQLiteOptimizationDatabase(self._run_dir)
                try:
                    meta = self._db.load_run_metadata()
                except Exception:
                    meta = None
                # Validate dataset path matches
                mismatch = False
                try:
                    if meta and getattr(meta, 'dataset_path', None):
                        if str(meta.dataset_path) != str(cfg.dataset_path):
                            mismatch = True
                except Exception:
                    pass
                if mismatch:
                    self._callbacks.on_status("Selected run DB dataset mismatches current dataset; starting a fresh run.")
                    rd = None  # force fresh run
            if rd is None:
                safe_name = "".join(c for c in (cfg.run_name or "auto_run") if c.isalnum() or c in ("-", "_")).strip() or "auto_run"
                ts = time.strftime("%Y-%m-%d_%H-%M-%S")
                self._run_dir = app_paths.aco_runs / f"auto_{safe_name}_{ts}"
                self._run_dir.mkdir(parents=True, exist_ok=True)
                self._db = SQLiteOptimizationDatabase(self._run_dir)

            # Load branch scheduler state (resume-safe)
            try:
                st = self._db.load_algorithm_state('auto_mode_state') if self._db else {}
                if isinstance(st, dict) and 'branch_index' in st:
                    self._branch_index = int(st['branch_index'])
            except Exception:
                pass

            # 1) Start/ensure server
            if cfg.force_clean:
                self._callbacks.on_status("Force clean start enabled: existing llama-server processes may be terminated for a clean slate.")
            self._callbacks.on_status("Starting server for Auto Mode...")
            ok = app_server_manager.start_server_for_aco(cfg.server_config, log_callback=self._callbacks.on_status, force_clean=cfg.force_clean)
            if not ok:
                raise RuntimeError("Failed to start server for Auto Mode")
            # Configure client
            try:
                timeouts = cfg.server_config.get_connection_timeouts()
                self.api_client.configure(
                    base_url=cfg.server_config.get_server_url(),
                    timeout=timeouts['connection_timeout'],
                    request_timeout=timeouts['request_timeout']
                )
                # Explicit preflight checks for transparency
                self._callbacks.on_status(f"API client configured for {self.api_client.base_url}")
                try:
                    ok_health, msg = self.api_client.health_check()
                    self._callbacks.on_status(f"Health check: {'OK' if ok_health else 'FAIL'} - {msg}")
                except Exception as _e:
                    self._callbacks.on_status(f"Health check error: {_e}")
                try:
                    slots = self.api_client.get_slots_info_raw()
                    if slots is None:
                        self._callbacks.on_status("Slots endpoint: no response (may be disabled or starting up)")
                    else:
                        preview = slots[:120].replace('\n', ' ')
                        self._callbacks.on_status(f"Slots endpoint: {len(slots)} bytes; preview: {preview}")
                except Exception as _e:
                    self._callbacks.on_status(f"Slots endpoint error: {_e}")
            except Exception:
                pass

            # 1c) If Full Auto, override parameter arrays and sampler sequence coherently
            if cfg.full_auto:
                try:
                    # Initialize default branch if not set
                    self._full_auto_branch = self._full_auto_branch or 'A'
                    self._apply_full_auto_defaults(cfg)
                except Exception as e:
                    self._callbacks.on_error(f"Full Auto setup failed: {e}")
                    return

            # 1b) Pre-flight coherence warnings (samplers vs arrays)
            try:
                self._warn_if_sampler_incoherent(cfg)
            except Exception:
                pass

            # 2) Baseline (skip already-completed baseline questions)
            if self._stop_flag:
                return
            # Apply historical knowledge (priors, optional baseline import)
            try:
                self._apply_historical_knowledge(cfg)
            except Exception as e:
                self._callbacks.on_status(f"Historical knowledge load warning: {e}")
            self._run_baseline(cfg)

            # 3) New Full Auto scheduler path (optional)
            try:
                famode = getattr(cfg, 'full_auto_mode', 'legacy')
            except Exception:
                famode = 'legacy'
            if cfg.full_auto and famode == 'scheduler':
                self._callbacks.on_status("Full Auto: New Scheduler mode engaged.")
                if not self._db:
                    self._callbacks.on_error("Scheduler: database not initialized; aborting.")
                    self._complete_run_metadata(cfg, status='error', error_message='scheduler_no_db')
                    return
                # Create and retain a scheduler so Stop can signal it
                self._scheduler = FullAutoScheduler(self.api_client)
                self._scheduler.run(
                    OptimizationConfig(
                        run_name=cfg.run_name,
                        dataset_path=cfg.dataset_path,
                        questions=[],
                        parameter_arrays=cfg.parameter_arrays,
                        api_config=cfg.api_config,
                        server_config=cfg.server_config,
                        endpoint_type=cfg.endpoint_type,
                        api_config_path=getattr(cfg, 'api_config_path', None),
                        server_config_path=getattr(cfg, 'server_config_path', None),
                    ),
                    self._db,
                    self._callbacks,
                    famode_params={},
                )
                self._complete_run_metadata(cfg, status='completed')
                return

            # Resume summary if resuming
            if rd is not None:
                try:
                    split = self._db.get_baseline_correct_incorrect()
                    wrong = len(split.get('incorrect', []))
                    cur = self._compute_combo_stats()
                    cont = len(self._contenders_by_ci(cur)) if cur else 0
                    target_cov = self._target_coverage(wrong)
                    self._callbacks.on_status(f"Resume state: ACO rows={len(cur)} | contenders={cont} | target coverage={target_cov}")
                except Exception:
                    pass

            # 3) Adaptive loop: explore -> promote -> (optional) gencheck -> stop/validate (legacy)
            if self._stop_flag:
                return
            self._adaptive_loop(cfg)

            self._callbacks.on_status("Auto Mode stopped.")
        except Exception as e:
            self._callbacks.on_error(str(e))

    # -------------------- Full Auto helpers --------------------
    def _apply_full_auto_defaults(self, cfg: AutoModeConfig) -> None:
        """Set coherent sampler sequence and small, curated parameter arrays internally.

        Starts with Branch A (nucleus family). Future: iterate B (mirostat), C (dry+nucleus).
        """
        # Choose branch if not set
        self._full_auto_branch = self._full_auto_branch or 'A'

        # Build arrays per branch
        arrays: Dict[str, ParameterArrayInfo] = {}
        if self._full_auto_branch == 'A':
            # Safer, slightly conservative sets to avoid pathological stalls
            arrays = {
                'temperature': ParameterArrayInfo(values=['0.7', '0.9', '1.1'], recommended_indices=[1]),
                'top_k': ParameterArrayInfo(values=['80', '160', '320'], recommended_indices=[1]),
                'top_p': ParameterArrayInfo(values=['0.9', '1.0'], recommended_indices=[0]),
                'min_p': ParameterArrayInfo(values=['0', '0.2', '0.4'], recommended_indices=[0]),
                'repeat_penalty': ParameterArrayInfo(values=['1.0', '1.1', '1.2'], recommended_indices=[1]),
            }
            sampler_seq = ['penalties', 'top_k', 'top_p', 'min_p', 'temperature']
        elif self._full_auto_branch == 'B':
            arrays = {
                'mirostat': ParameterArrayInfo(values=['2', '1'], recommended_indices=[0]),
                'mirostat_tau': ParameterArrayInfo(values=['4', '5', '6'], recommended_indices=[1]),
                'mirostat_eta': ParameterArrayInfo(values=['0.05', '0.1', '0.2'], recommended_indices=[1]),
                'temperature': ParameterArrayInfo(values=['0.6', '0.8', '1.0'], recommended_indices=[1]),
                'repeat_penalty': ParameterArrayInfo(values=['1.0', '1.1', '1.2'], recommended_indices=[1]),
            }
            sampler_seq = ['penalties', 'mirostat']
        else:  # 'C'
            arrays = {
                'temperature': ParameterArrayInfo(values=['0.6', '0.8', '1.0'], recommended_indices=[0]),
                'top_k': ParameterArrayInfo(values=['20', '80', '160', '320'], recommended_indices=[1]),
                'top_p': ParameterArrayInfo(values=['0.8', '1.0'], recommended_indices=[1]),
                'min_p': ParameterArrayInfo(values=['0', '0.2', '0.6', '1.0'], recommended_indices=[0]),
                'repeat_penalty': ParameterArrayInfo(values=['1.0', '1.1', '1.2'], recommended_indices=[1]),
                'dry_multiplier': ParameterArrayInfo(values=['0.5', '1.0'], recommended_indices=[0]),
            }
            sampler_seq = ['penalties', 'dry', 'top_k', 'top_p', 'min_p', 'temperature']

        cfg.parameter_arrays = arrays
        # Ensure API config has samplers enabled and set
        try:
            cfg.api_config.enabled['samplers'] = True
            # Use array form as expected by server
            cfg.api_config.values['samplers'] = list(sampler_seq)
        except Exception:
            pass
        # Log applied branch and sampler sequence for visibility
        try:
            self._callbacks.on_status(f"Full Auto: branch {self._full_auto_branch} | samplers: {sampler_seq}")
        except Exception:
            pass

    def _warn_if_sampler_incoherent(self, cfg: AutoModeConfig) -> None:
        """Log warnings if parameter arrays include sampler-dependent params but 'samplers' sequence omits them.

        Informational only — preserves user control of payload and sampler order.
        """
        # Build active samplers list from config values
        samplers_list = []
        try:
            enabled = getattr(cfg.api_config, 'enabled', {}) or {}
            values = getattr(cfg.api_config, 'values', {}) or {}
            if enabled.get('samplers', False):
                raw = values.get('samplers', '') or ''
                if isinstance(raw, list):
                    samplers_list = [str(s).strip() for s in raw if str(s).strip()]
                else:
                    samplers_list = [s.strip() for s in str(raw).split(',') if s.strip()]
        except Exception:
            samplers_list = []

        if not samplers_list:
            return  # user intentionally left sequence unset

        # Minimal mapping from parameter names/prefixes to required sampler token
        name_to_sampler = {
            'temperature': 'temperature',
            'top_p': 'top_p',
            'top_k': 'top_k',
            'min_p': 'min_p',
            'typical_p': 'typ_p',
            'top_n_sigma': 'top_n_sigma',
            'mirostat': 'mirostat',
            'repeat_penalty': 'penalties',
        }
        prefix_to_sampler = [
            ('dry_', 'dry'),
            ('xtc_', 'xtc'),
            ('dynatemp_', 'dynatemp'),
            ('penalty_', 'penalty'),
        ]

        missing = set()
        arrays = cfg.parameter_arrays or {}
        for pname in arrays.keys():
            required = name_to_sampler.get(pname)
            if not required:
                for pref, token in prefix_to_sampler:
                    if pname.startswith(pref):
                        required = token
                        break
            if required and required not in samplers_list:
                missing.add((pname, required))

        if missing:
            pairs = ", ".join([f"{p}->{s}" for p, s in sorted(missing)])
            self._callbacks.on_status(
                f"Warning: Some parameter arrays may be inactive due to sampler sequence. Missing samplers for: {pairs}."
            )

    def _apply_historical_knowledge(self, cfg: AutoModeConfig) -> None:
        hk = getattr(cfg, 'historical_knowledge', None)
        if not hk or not isinstance(hk, dict):
            return
        # Determine if we can skip pairs: dataset hash and samplers match (or samplers unknown)
        can_skip_pairs = False
        try:
            import hashlib
            ds_path = cfg.dataset_path
            cur_hash = None
            if ds_path and Path(ds_path).exists():
                h = hashlib.sha256()
                with open(ds_path, 'rb') as df:
                    for chunk in iter(lambda: df.read(8192), b''):
                        h.update(chunk)
                cur_hash = h.hexdigest()
            hk_hash = ((hk.get('dataset') or {}).get('id'))
            # Samplers check
            cur_samplers = []
            try:
                raw = cfg.api_config.values.get('samplers')
                if isinstance(raw, list):
                    cur_samplers = raw
            except Exception:
                pass
            hk_samplers = ((hk.get('run_meta') or {}).get('samplers')) or []
            if hk_hash and cur_hash and (hk_hash == cur_hash) and (not hk_samplers or hk_samplers == cur_samplers):
                can_skip_pairs = True
        except Exception:
            can_skip_pairs = False

        # Build priors from per-test results (value-level)
        value_trials: Dict[str, Dict[str, int]] = {}
        value_correct: Dict[str, Dict[str, int]] = {}
        for r in (hk.get('aco_results') or []):
            params = r.get('parameters') or {}
            score = r.get('score')
            is_correct = 1 if (score is not None and float(score) >= 1.0) else 0
            for k, v in params.items():
                vs = str(v)
                value_trials.setdefault(k, {})[vs] = value_trials.get(k, {}).get(vs, 0) + 1
                value_correct.setdefault(k, {})[vs] = value_correct.get(k, {}).get(vs, 0) + is_correct

        # Build combo -> seen questions for skipping
        combo_seen: Dict[str, set] = {}
        if can_skip_pairs:
            for r in (hk.get('aco_results') or []):
                params = r.get('parameters') or {}
                qn = r.get('question_number')
                try:
                    key = str(ParameterConverter.make_hashable_key(params))
                    s = combo_seen.setdefault(key, set())
                    if qn is not None:
                        s.add(int(qn))
                except Exception:
                    pass

        # Merge with existing algorithm state (HierarchicalTSBalanced)
        try:
            st = self._db.load_algorithm_state('HierarchicalTSBalanced') if self._db else {}
        except Exception:
            st = {}
        betas = st.get('betas', {}) if isinstance(st, dict) else {}
        for pname, trials_map in value_trials.items():
            for v_str, trials in trials_map.items():
                corr = (value_correct.get(pname, {}).get(v_str, 0))
                alpha = 1.0 + float(corr)
                beta = 1.0 + float(max(0, trials - corr))
                prev = betas.get(pname, {}).get(v_str)
                if prev:
                    pa, pb, pt = prev
                    if (pt or 0) > trials:
                        continue
                betas.setdefault(pname, {})[v_str] = (alpha, beta, int(trials))
        state_out = {
            'betas': betas,
            'combo_question_seen': {k: sorted(list(v)) for k, v in combo_seen.items()} if combo_seen else st.get('combo_question_seen', {}),
            'question_rr_index': int(st.get('question_rr_index', 0)) if isinstance(st, dict) else 0,
            'epsilon': float(st.get('epsilon', 0.1)) if isinstance(st, dict) else 0.1,
        }
        try:
            if self._db:
                self._db.save_algorithm_state('HierarchicalTSBalanced', state_out)
                if can_skip_pairs:
                    self._callbacks.on_status("Historical knowledge: seeded priors and enabled skip of known pairs (dataset+samplers match).")
                else:
                    self._callbacks.on_status("Historical knowledge: seeded priors (skip disabled due to dataset/samplers mismatch or unknown).")
        except Exception as e:
            self._callbacks.on_status(f"Historical knowledge save warning: {e}")

        # Optional: import baseline rows
        try:
            if can_skip_pairs and (hk.get('baseline')):
                for br in (hk.get('baseline') or []):
                    qn = br.get('question_number')
                    if qn is None:
                        continue
                    q_struct = {'question_number': int(qn), 'ground_truth': ''}
                    tc = create_test_case_from_parameters(question_id=int(qn), question=q_struct, parameters=dict(cfg.api_config.values or {}))
                    tr = TestResult(test_case=tc, success=True, response='', score=br.get('score') or 0.0, response_time=br.get('response_time') or 0.0)
                    self._db.save_test_result(tc, tr, phase='baseline')
                self._callbacks.on_status("Historical knowledge: baseline imported into DB (best-effort).")
        except Exception:
            pass

    def _run_baseline(self, cfg: AutoModeConfig) -> None:
        self._callbacks.on_status("Baseline: running across selected questions...")
        be = BenchmarkExecutor(self.api_client)
        self._baseline_executor = be
        # Load dataset questions to create selected list (use DatasetParser via executor)
        # The enhanced runner expects explicit selected_questions indices
        try:
            self._callbacks.on_status("Baseline: parsing dataset file...")
            from .runner import DatasetParser
            all_questions = DatasetParser.parse_dataset_file(cfg.dataset_path)
        except Exception as e:
            raise RuntimeError(f"Failed parsing dataset: {e}")
        selected_indices = list(range(1, len(all_questions) + 1))

        # Get already completed baseline questions
        completed_baseline = set()
        try:
            completed_baseline = set(self._db.get_completed_question_numbers_by_phase('baseline'))
        except Exception:
            completed_baseline = set()
        questions_for_baseline = [q for q in selected_indices if q not in completed_baseline]

        if not questions_for_baseline:
            self._callbacks.on_status("Baseline already complete; skipping.")
            return

        def _stream_to_db(question_obj, record):
            if self._stop_flag:
                # signal the runner to stop
                try:
                    be.stop_benchmark()
                except Exception:
                    pass
                return
            try:
                qnum = record.get('q_id') or record.get('question_number')
                gt = record.get('ground_truth', '')
                ans = record.get('response', '')
                score = FlexibleScorer().score_answer(gt, ans, scoring_mode='EXACT')
                # Progress line: Baseline result
                try:
                    status = 'OK' if float(score) >= 1.0 else 'X'
                    self._callbacks.on_progress(f"Baseline: Q{qnum} {status}")
                except Exception:
                    pass
                params = dict(cfg.api_config.values)
                q_struct = {
                    'question_number': int(qnum) if qnum else 0,
                    'ground_truth': gt,
                    'turns': None
                }
                tc = create_test_case_from_parameters(question_id=int(qnum) if qnum else 0, question=q_struct, parameters=params)
                tr = TestResult(test_case=tc, success=True, response=ans, score=score, response_time=record.get('response_time', 0.0), slots_data=None, full_api_response={'_raw': record.get('raw_completions_response', '')})
                self._db.save_test_result(tc, tr, phase='baseline')
            except Exception as _e:
                self._callbacks.on_status(f"Warn: baseline stream failed for q{qnum}: {_e}")

        # Forward runner progress to UI for better transparency
        def _progress_msg(msg: str):
            try:
                self._callbacks.on_progress(f"Baseline: {msg}")
            except Exception:
                pass
        def _detailed(cur, total, message):
            try:
                self._callbacks.on_progress(f"Baseline {cur}/{total}: {message}")
            except Exception:
                pass

        result = be.run_benchmark_enhanced(
            dataset_path=cfg.dataset_path,
            # Use current API config values (samplers list already applied in Full Auto)
            config_data=cfg.api_config.values,
            selected_questions=questions_for_baseline,
            run_name=f"baseline_{cfg.run_name}",
            system_prompt=cfg.api_config.values.get('system_prompt', ''),
            server_config_path=None,
            api_config_path=None,
            progress_callback=_progress_msg,
            detailed_progress_callback=_detailed,
            per_question_callback=_stream_to_db,
            endpoint_type=cfg.endpoint_type,
        )
        # Announce baseline outcome
        try:
            status = (result or {}).get('status')
        except Exception:
            status = None
        if self._stop_flag or status == 'stopped':
            self._callbacks.on_status("Baseline stopped.")
        else:
            self._callbacks.on_status("Baseline complete.")
        self._baseline_executor = None

    def _explore_with_budget(self, cfg: AutoModeConfig, max_tests: int) -> None:
        # Use baseline incorrect as target question set for exploration
        split = self._db.get_baseline_correct_incorrect() if self._db else {"incorrect": []}
        s_wrong = split.get('incorrect', [])
        if not s_wrong:
            # Fallback to entire dataset indices
            from .runner import DatasetParser
            all_questions = DatasetParser.parse_dataset_file(cfg.dataset_path)
            s_wrong = list(range(1, len(all_questions) + 1))

        # Configure CleanACORunner
        runner = CleanACORunner(self.api_client)
        self._explore_runner = runner
        # Reuse current run directory
        runner.resume_run_directory = self._run_dir

        ocfg = OptimizationConfig(
            run_name=cfg.run_name,
            dataset_path=cfg.dataset_path,
            questions=s_wrong,
            parameter_arrays=cfg.parameter_arrays,
            api_config=cfg.api_config,
            server_config=cfg.server_config,
            endpoint_type=cfg.endpoint_type,
            algorithm="Hierarchical TS (Balanced)",
            resume=False,
            auto_save_enabled=True,
            api_config_path=cfg.api_config_path,
            server_config_path=cfg.server_config_path,
        )

        # Simple callbacks to relay messages (capture outer orchestrator callbacks)
        outer = self
        class _CB:
            def on_progress_update(self, current, total, message):
                outer._callbacks.on_progress(f"Explore {current}/{total}: {message}")
            def on_status_message(self, message):
                outer._callbacks.on_status(message)
            def on_test_result(self, result):
                try:
                    status = 'OK' if (result.score or 0.0) >= 1.0 else 'X'
                    # Show only actively varied parameters (those in the current search space)
                    varied = set((cfg.parameter_arrays or {}).keys())
                    if varied:
                        items = sorted((k, v) for k, v in result.test_case.parameters.items() if k in varied)
                    else:
                        items = []
                    preview = ', '.join([f"{k}={v}" for k, v in items])
                    outer._callbacks.on_progress(f"ACO: Q{result.test_case.question_id} {status} | {preview}")
                except Exception:
                    pass
            def on_optimization_complete(self, summary):
                outer._callbacks.on_status("Explore phase complete")
            def on_optimization_error(self, error):
                outer._callbacks.on_error(str(error))

        runner.start_optimization(ocfg, _CB())

        # Monitor and stop on budget, with slots-based watchdog for Full Auto
        last_completed = 0
        # Slots progress tracking (activated only when a slot is processing)
        watch_active = False
        any_processing = False
        first_token_seen = False
        prefill_start = 0.0
        last_decoded_change = None
        last_slots_ok = time.time()
        max_ndecoded_seen = 0
        last_slots_poll = 0.0
        slots_poll_interval = 1.0  # seconds
        # Thresholds (aggressive but safe)
        prefill_grace = 20  # seconds to first token (only when processing)
        decode_idle = 10     # seconds without new token after first
        slots_fail_window = 5  # seconds of slots failing to respond
        last_restart = 0.0
        min_restart_interval = 20.0  # avoid rapid restart loops
        while True:
            if self._stop_flag:
                runner.stop_optimization()
                self._explore_runner = None
                return
            status = runner.get_current_status()
            completed = int(status.get('completed_tests', 0))
            if completed != last_completed:
                last_completed = completed
                self._callbacks.on_progress(f"Explore progress: {completed} tests")
                # Reset watchdog state for next test attempt
                watch_active = False
                any_processing = False
                first_token_seen = False
                prefill_start = 0.0
                last_decoded_change = None
                max_ndecoded_seen = 0
            if completed >= max_tests:
                self._callbacks.on_status(f"Reached explore budget ({max_tests}); stopping...")
                runner.stop_optimization()
                self._explore_runner = None
                break
            # If runner already completed, exit
            if status.get('status') == 'completed':
                self._explore_runner = None
                break
            # Full Auto only: slots-based progress watchdog (skip stuck generations without cutting long ones)
            if cfg.full_auto:
                now = time.time()
                if (now - last_slots_poll) >= slots_poll_interval:
                    last_slots_poll = now
                    try:
                        raw = self.api_client.get_slots_info_raw()
                        if raw:
                            import json as _json
                            try:
                                data = _json.loads(raw)
                            except Exception:
                                data = None
                            # Extract max n_decoded across any sequences
                            def _iter_ndecoded(obj):
                                if isinstance(obj, dict):
                                    for k, v in obj.items():
                                        if k == 'n_decoded' and isinstance(v, int):
                                            yield v
                                        else:
                                            for vv in _iter_ndecoded(v):
                                                yield vv
                                elif isinstance(obj, list):
                                    for it in obj:
                                        for vv in _iter_ndecoded(it):
                                            yield vv
                            cur_max = 0
                            # Detect if any slot is actively processing
                            def _iter_processing(obj):
                                if isinstance(obj, dict):
                                    if obj.get('is_processing') is True:
                                        return True
                                    for v in obj.values():
                                        if _iter_processing(v):
                                            return True
                                elif isinstance(obj, list):
                                    for it in obj:
                                        if _iter_processing(it):
                                            return True
                                return False
                            if isinstance(data, dict):
                                # Try common keys; else recursive scan
                                seq = data.get('slots') or data.get('data') or data
                                cur_vals = list(_iter_ndecoded(seq))
                                if cur_vals:
                                    cur_max = max(cur_vals)
                                any_processing = _iter_processing(seq)
                            elif isinstance(data, list):
                                cur_vals = list(_iter_ndecoded(data))
                                if cur_vals:
                                    cur_max = max(cur_vals)
                                any_processing = _iter_processing(data)
                            # Update slots ok timestamp
                            last_slots_ok = now
                            # Activate watchdog when a slot starts processing
                            if any_processing and not watch_active:
                                watch_active = True
                                prefill_start = now
                                first_token_seen = False
                                max_ndecoded_seen = 0
                                last_decoded_change = None
                            # Prefill vs decode tracking (only when watch is active)
                            if watch_active and cur_max > max_ndecoded_seen:
                                max_ndecoded_seen = cur_max
                                if not first_token_seen and cur_max > 0:
                                    first_token_seen = True
                                last_decoded_change = now
                        # raw is None: leave last_slots_ok as-is
                    except Exception:
                        pass

                # Evaluate watchdog thresholds
                stuck = False
                if watch_active and any_processing:
                    if not first_token_seen:
                        if prefill_start > 0 and (now - prefill_start) > prefill_grace:
                            stuck = True
                    else:
                        if last_decoded_change is not None and (now - last_decoded_change) > decode_idle:
                            stuck = True
                    # Treat slots unresponsive as stuck only if there is also no token progress
                    if (now - last_slots_ok) > slots_fail_window:
                        if (not first_token_seen) or (last_decoded_change is None) or ((now - last_decoded_change) > decode_idle):
                            stuck = True

                if stuck and (now - last_restart) > min_restart_interval:
                    last_restart = now
                    try:
                        self._callbacks.on_status("Slots watchdog: no decoding progress detected. Restarting server to skip stuck generation...")
                    except Exception:
                        pass
                    # Stop runner and restart server; this avoids a burst of 503s while the model loads
                    try:
                        runner.stop_optimization()
                    except Exception:
                        pass
                    self._explore_runner = None
                    try:
                        app_server_manager.stop_owned_server(log_callback=self._callbacks.on_status)
                    except Exception:
                        pass
                    try:
                        app_server_manager.start_server_for_aco(cfg.server_config, log_callback=self._callbacks.on_status, force_clean=cfg.force_clean)
                        tcfg = cfg.server_config.get_connection_timeouts()
                        self.api_client.configure(
                            base_url=cfg.server_config.get_server_url(),
                            timeout=tcfg['connection_timeout'],
                            request_timeout=tcfg['request_timeout']
                        )
                    except Exception:
                        pass
                    # Reset watchdog state for the next cycle and exit this explore cycle
                    first_token_seen = False
                    prefill_start = now
                    last_decoded_change = None
                    last_slots_ok = now
                    max_ndecoded_seen = 0
                    break
            time.sleep(0.5)

    def _promote_adaptive(self, cfg: AutoModeConfig, target_coverage: int) -> None:
        # Compute contenders by CI overlap
        stats = self._compute_combo_stats()
        contenders = self._contenders_by_ci(stats)
        if not contenders:
            self._callbacks.on_status("No contenders yet; skipping promotions.")
            return
        split = self._db.get_baseline_correct_incorrect() if self._db else {"incorrect": []}
        target_questions = split.get('incorrect', [])
        if not target_questions:
            self._callbacks.on_status("No baseline-incorrect questions; skipping promotions.")
            return

        be = BenchmarkExecutor(self.api_client)
        from .test_executor import TestExecutor
        texec = TestExecutor(be)
        # Build a cache of question objects to avoid reparsing
        from .runner import DatasetParser
        all_questions = DatasetParser.parse_dataset_file(cfg.dataset_path)

        for entry in contenders:
            params = entry['parameters']
            tested_set = set(entry['tested_questions'])
            remaining = [q for q in target_questions if q not in tested_set]
            need = max(0, target_coverage - len(tested_set))
            if need <= 0:
                self._callbacks.on_status("Promotion: combo already meets coverage target; skipping")
                continue
            # Cap to what's available
            promote_list = remaining[:min(need, 30)]  # modest per-cycle cap
            if not promote_list:
                continue
            self._callbacks.on_status(f"Promoting contenders to coverage {target_coverage}: running {len(promote_list)} tests for one combo...")
            for qnum in promote_list:
                if self._stop_flag:
                    return
                q = all_questions[qnum - 1]
                tc = create_test_case_from_parameters(question_id=qnum, question=q, parameters=params)
                # Execute via unified TestExecutor
                ocfg = OptimizationConfig(
                    run_name=cfg.run_name,
                    dataset_path=cfg.dataset_path,
                    questions=[qnum],
                    parameter_arrays=cfg.parameter_arrays,
                    api_config=cfg.api_config,
                    server_config=cfg.server_config,
                    endpoint_type=cfg.endpoint_type,
                    api_config_path=cfg.api_config_path,
                    server_config_path=cfg.server_config_path,
                )
                tr = texec.execute_test_case(tc, ocfg)
                # Save result
                self._db.save_test_result(tc, tr, phase='aco')

        self._callbacks.on_status("Promotion sweep complete.")

    # -------------------- Helpers --------------------

    def _query_top_combos(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Return top combos: parameters, tested count, correct count, tested_questions list."""
        import sqlite3, json
        with sqlite3.connect(str(self._db.db_path)) as conn:
            cur = conn.cursor()
            # Aggregate by parameters_json across all 'aco' phase entries
            cur.execute(
                """
                SELECT parameters_json,
                       COUNT(*) as tested,
                       SUM(CASE WHEN score >= 1.0 THEN 1 ELSE 0 END) as correct
                FROM test_cases
                WHERE completed = 1 AND score IS NOT NULL AND phase = 'aco'
                GROUP BY parameters_json
                ORDER BY correct DESC, tested DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cur.fetchall()
            out: List[Dict[str, Any]] = []
            for pjson, tested, correct in rows:
                try:
                    params = json.loads(pjson)
                except Exception:
                    params = {}
                # Gather tested questions for this combo
                cur.execute(
                    """
                    SELECT DISTINCT question_number
                    FROM test_cases
                    WHERE completed = 1 AND score IS NOT NULL AND phase = 'aco' AND parameters_json = ?
                    """,
                    (pjson,)
                )
                qrows = cur.fetchall()
                tested_questions = [int(r[0]) for r in qrows if r and r[0] is not None]
                out.append({
                    'parameters': params,
                    'tested': int(tested or 0),
                    'correct': int(correct or 0),
                    'tested_questions': tested_questions,
                })
            return out

    # ---- Adaptive stats & policies ----
    def _load_aco_records(self) -> List[Dict[str, Any]]:
        import sqlite3, json
        with sqlite3.connect(str(self._db.db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT question_number, parameters_json, score
                FROM test_cases
                WHERE completed = 1 AND score IS NOT NULL AND phase = 'aco'
                """
            )
            rows = cur.fetchall()
            recs = []
            for qn, pjson, s in rows:
                try:
                    params = json.loads(pjson) if pjson else {}
                except Exception:
                    params = {}
                recs.append({'question_number': int(qn) if qn else None, 'parameters': params, 'score': float(s)})
            return recs

    @staticmethod
    def _beta_ci(k: int, n: int, alpha: float = 1.0, beta: float = 1.0) -> Tuple[float, float, float]:
        # Normal approx to Beta(k+alpha, n-k+beta)
        if n <= 0:
            return 0.0, 0.0, 1.0
        a = k + alpha; b = (n - k) + beta; denom = a + b
        mean = a / denom
        var = (a * b) / (denom * denom * (denom + 1.0))
        import math
        std = math.sqrt(max(1e-12, var))
        lo = max(0.0, min(1.0, mean - 1.96 * std))
        hi = max(0.0, min(1.0, mean + 1.96 * std))
        return mean, lo, hi

    def _compute_combo_stats(self) -> List[Dict[str, Any]]:
        recs = self._load_aco_records()
        from collections import defaultdict
        buckets = defaultdict(list)
        qsets = defaultdict(set)
        for r in recs:
            key = tuple(sorted(r['parameters'].items()))
            buckets[key].append(r['score'])
            if r['question_number'] is not None:
                qsets[key].add(int(r['question_number']))
        stats = []
        for key, arr in buckets.items():
            tested = len(arr)
            correct = sum(1 for s in arr if s >= 1.0)
            mean, lo, hi = self._beta_ci(correct, tested)
            params = dict(key)
            stats.append({
                'parameters': params,
                'tested': tested,
                'correct': correct,
                'mean': mean,
                'lo': lo,
                'hi': hi,
                'tested_questions': sorted(qsets.get(key, set())),
            })
        # Sort by mean desc then tested
        stats.sort(key=lambda e: (e['mean'], e['tested']), reverse=True)
        return stats

    def _contenders_by_ci(self, stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not stats:
            return []
        best = stats[0]
        best_lo = best['lo']
        contenders = [s for s in stats if s['hi'] >= best_lo]
        return contenders

    def _target_coverage(self, total_wrong: int) -> int:
        # Adaptive target by progress (simple heuristic)
        # Progress ~ total ACO tests vs wrong set size
        import sqlite3
        with sqlite3.connect(str(self._db.db_path)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM test_cases WHERE phase='aco' AND completed=1 AND score IS NOT NULL")
            aco_tests = int(cur.fetchone()[0] or 0)
        if total_wrong <= 0:
            return 10
        ratio = aco_tests / float(total_wrong)
        if ratio < 0.5:
            return 10
        if ratio < 1.5:
            return 25
        if ratio < 2.5:
            return 40
        return min(100, total_wrong)

    def _should_stop_confident(self, stats: List[Dict[str, Any]]) -> bool:
        if not stats:
            return False
        best = stats[0]
        best_lo = best['lo']
        for s in stats[1:]:
            if s['hi'] > best_lo:
                return False
        # Also ensure some coverage
        return best['tested'] >= 10

    def _adaptive_loop(self, cfg: AutoModeConfig) -> None:
        # Fetch sets once
        split = self._db.get_baseline_correct_incorrect() if self._db else {"incorrect": [], "correct": []}
        s_wrong = split.get('incorrect', [])
        s_correct = split.get('correct', [])
        if not s_wrong:
            # Nothing to optimize; validate baseline and exit
            self._callbacks.on_status("No baseline-incorrect questions; nothing to optimize.")
            if cfg.auto_validate:
                self._final_validation(cfg)
            return
        # Loop until stop or confident
        while not self._stop_flag:
            # 1) Explore
            cycle_budget = max(20, min(100, len(s_wrong)))
            # Full Auto: rotate branches per cycle if enabled
            if cfg.full_auto and (cfg.iterate_branches if cfg.iterate_branches is not None else True):
                order = cfg.branch_order if cfg.branch_order else ['A', 'B', 'C']
                # pick branch and apply
                try:
                    self._full_auto_branch = order[self._branch_index % len(order)] if order else 'A'
                except Exception:
                    self._full_auto_branch = 'A'
                try:
                    self._apply_full_auto_defaults(cfg)
                except Exception as e:
                    self._callbacks.on_status(f"Warn: could not apply branch defaults: {e}")
                # advance and persist state
                self._branch_index = (self._branch_index + 1) % (len(order) or 1)
                try:
                    if self._db:
                        self._db.save_algorithm_state('auto_mode_state', {'branch_index': self._branch_index})
                except Exception:
                    pass
                self._callbacks.on_status(f"Explore cycle (Branch {self._full_auto_branch}): running ~{cycle_budget} tests...")
            else:
                self._callbacks.on_status(f"Explore cycle: running ~{cycle_budget} tests...")
            self._explore_with_budget(cfg, cycle_budget)

            # 2) Promote contenders to target coverage
            stats = self._compute_combo_stats()
            target_cov = self._target_coverage(len(s_wrong))
            contenders_count = len(self._contenders_by_ci(stats))
            self._callbacks.on_status(f"Contenders: {contenders_count} | Coverage target: {target_cov}")
            try:
                if self._db:
                    self._db.save_auto_mode_snapshot(contenders_count, target_cov)
            except Exception:
                pass
            self._promote_adaptive(cfg, target_cov)
            # Summarize best so far to the activity log
            stats2 = self._compute_combo_stats()
            if stats2:
                b = stats2[0]
                self._callbacks.on_status(
                    f"Best so far: acc {b['mean']*100:.0f}% [{b['lo']*100:.0f}–{b['hi']*100:.0f}%] | tested {b['tested']} | correct {b['correct']}"
                )

            # 3) Regression sentinels on baseline-correct (uplift auditing)
            if s_correct:
                sample = cfg.audit_right_sample if cfg.audit_right_sample > 0 else min(10, max(0, int(0.1 * len(s_correct))))
                if sample > 0:
                    self._generalization_check(cfg, sample_size=sample)

            # 4) Stop/validate if uplift confidence condition met
            if cfg.auto_validate:
                uplift = self._compute_uplift_for_best(cfg)
                if uplift:
                    self._callbacks.on_status(
                        f"Uplift check: p_fix={uplift['p_fix']:.2f} on wrong (tested {uplift['tested_wrong']}) | "
                        f"p_regress={uplift['p_regress']:.2f} on right (tested {uplift['tested_right']}) | "
                        f"E_gain_lo={uplift['e_gain_lo']:.1f}"
                    )
                    if uplift['tested_wrong'] >= max(20, int(0.4 * len(s_wrong))) and uplift['tested_right'] >= max(10, int(0.2 * len(s_correct))):
                        if uplift['e_gain_lo'] > 0:
                            self._callbacks.on_status("Uplift condition met; validating best combo...")
                            self._final_validation(cfg)
                            return
            # Small pause to avoid tight loops
            time.sleep(0.2)

    # --- directory helpers ---
    def _find_latest_auto_run_dir(self) -> Optional[str]:
        try:
            base = app_paths.aco_runs
            if not base.exists():
                return None
            # list candidate dirs that look like auto_* and contain optimization.db
            candidates = []
            for p in base.iterdir():
                if not p.is_dir():
                    continue
                name = p.name.lower()
                if not name.startswith('auto_'):
                    continue
                dbp = p / 'optimization.db'
                if dbp.exists():
                    candidates.append((dbp.stat().st_mtime, str(p)))
            if not candidates:
                return None
            candidates.sort(reverse=True)  # newest first
            return candidates[0][1]
        except Exception:
            return None

    def _pick_current_best(self) -> Optional[Dict[str, Any]]:
        """Return the single best combo dict from _query_top_combos or None."""
        top = self._query_top_combos(limit=1)
        return top[0] if top else None

    def _generalization_check(self, cfg: AutoModeConfig, sample_size: int = 10) -> None:
        best = self._pick_current_best()
        if not best:
            self._callbacks.on_status("GenCheck: no best combo yet; skipping.")
            return
        split = self._db.get_baseline_correct_incorrect() if self._db else {"correct": []}
        s_correct = split.get('correct', [])
        if not s_correct:
            self._callbacks.on_status("GenCheck: no baseline-correct questions; skipping.")
            return
        from .runner import DatasetParser
        from .test_executor import TestExecutor
        be = BenchmarkExecutor(self.api_client)
        texec = TestExecutor(be)
        all_q = DatasetParser.parse_dataset_file(cfg.dataset_path)
        # Take first N to keep deterministic; can randomize later
        sample = s_correct[:max(1, int(sample_size))]
        self._callbacks.on_status(f"GenCheck: testing best combo on {len(sample)} baseline-correct questions...")
        for qnum in sample:
            if self._stop_flag:
                return
            q = all_q[qnum - 1]
            tc = create_test_case_from_parameters(question_id=qnum, question=q, parameters=best['parameters'])
            ocfg = OptimizationConfig(
                run_name=cfg.run_name,
                dataset_path=cfg.dataset_path,
                questions=[qnum],
                parameter_arrays=cfg.parameter_arrays,
                api_config=cfg.api_config,
                server_config=cfg.server_config,
                endpoint_type=cfg.endpoint_type,
                api_config_path=cfg.api_config_path,
                server_config_path=cfg.server_config_path,
            )
            tr = texec.execute_test_case(tc, ocfg)
            self._db.save_test_result(tc, tr, phase='gencheck')
        self._callbacks.on_status("GenCheck complete.")

    def _final_validation(self, cfg: AutoModeConfig) -> None:
        best = self._pick_current_best()
        if not best:
            self._callbacks.on_status("Validation: no best combo; skipping.")
            return
        self._callbacks.on_status("Validation: running best combo across full dataset...")
        from .runner import DatasetParser
        from .test_executor import TestExecutor
        be = BenchmarkExecutor(self.api_client)
        texec = TestExecutor(be)
        all_q = DatasetParser.parse_dataset_file(cfg.dataset_path)
        for qnum in range(1, len(all_q) + 1):
            if self._stop_flag:
                return
            q = all_q[qnum - 1]
            tc = create_test_case_from_parameters(question_id=qnum, question=q, parameters=best['parameters'])
            ocfg = OptimizationConfig(
                run_name=cfg.run_name,
                dataset_path=cfg.dataset_path,
                questions=[qnum],
                parameter_arrays=cfg.parameter_arrays,
                api_config=cfg.api_config,
                server_config=cfg.server_config,
                endpoint_type=cfg.endpoint_type,
                api_config_path=cfg.api_config_path,
                server_config_path=cfg.server_config_path,
            )
            tr = texec.execute_test_case(tc, ocfg)
            self._db.save_test_result(tc, tr, phase='validation')
        self._callbacks.on_status("Validation complete.")

    def _compute_uplift_for_best(self, cfg: AutoModeConfig) -> dict:
        """Compute uplift stats (fixes/regressions) for current best combo across explored phases."""
        best = self._pick_current_best()
        if not best:
            return {}
        import sqlite3, json, math
        split = self._db.get_baseline_correct_incorrect() if self._db else {"incorrect": [], "correct": []}
        wrong = set(split.get('incorrect', [])); right = set(split.get('correct', []))
        pjson = json.dumps(best['parameters'], separators=(',', ':'))
        with sqlite3.connect(str(self._db.db_path)) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT question_number, score FROM test_cases
                WHERE completed = 1 AND score IS NOT NULL AND parameters_json = ?
                AND phase IN ('aco','gencheck','validation')
                """,
                (pjson,)
            )
            rows = cur.fetchall()
        tw = cw = tr = rr = 0
        for qn, s in rows:
            if qn is None:
                continue
            q = int(qn); sc = float(s)
            if q in wrong:
                tw += 1; cw += 1 if sc >= 1.0 else 0
            elif q in right:
                tr += 1; rr += 1 if sc < 1.0 else 0
        def ci(k, n):
            if n <= 0: return (0.0, 0.0, 1.0)
            a = k + 1.0; b = (n - k) + 1.0; den = a + b
            mean = a/den; var = (a*b)/(den*den*(den+1.0)); std = math.sqrt(max(1e-12, var))
            lo = max(0.0, min(1.0, mean - 1.96*std)); hi = max(0.0, min(1.0, mean + 1.96*std))
            return (mean, lo, hi)
        p_fix, p_fix_lo, p_fix_hi = ci(cw, tw)
        p_reg, p_reg_lo, p_reg_hi = ci(rr, tr)
        Nw = max(1, len(wrong)); Nr = max(1, len(right))
        eg_mean = p_fix*Nw - p_reg*Nr
        eg_lo = p_fix_lo*Nw - p_reg_hi*Nr
        eg_hi = p_fix_hi*Nw - p_reg_lo*Nr
        return {
            'tested_wrong': tw, 'correct_wrong': cw,
            'tested_right': tr, 'regress_right': rr,
            'p_fix': p_fix, 'p_regress': p_reg,
            'e_gain_mean': eg_mean, 'e_gain_lo': eg_lo, 'e_gain_hi': eg_hi,
            'wrong_total': Nw, 'right_total': Nr,
        }
