"""
Full Auto Scheduler (Converge + Validate)

A lightweight policy layer that:
- Explores primarily on baseline-incorrect questions with small audits on baseline-correct
- Promotes the first positive-uplift contender
- Completes 100/100 coverage for that contender and validates against baseline

This module is intentionally compact and uses existing components:
- SQLiteOptimizationDatabase for persistence
- TestExecutor for unified execution
- DatasetParser to load questions
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, Set

from .runner import DatasetParser, BenchmarkExecutor
from .test_executor import TestExecutor
from .database import SQLiteOptimizationDatabase, create_test_case_from_parameters
from .combinations import generate_all_combinations
from .interfaces import OptimizationConfig


@dataclass
class SchedulerConfig:
    # Promotion thresholds
    min_wrong_samples: int = 25
    min_fix_rate: float = 0.20
    max_regress_rate: float = 0.08
    # Exploration sampling ratios
    wrong_ratio: float = 0.85
    right_ratio: float = 0.15
    # Cycle sizes
    cycle_combos: int = 20
    cycle_tests: int = 60
    # Scoring mode for exploration (PARTIAL densifies signal)
    exploration_scoring_mode: str = 'PARTIAL'


class FullAutoScheduler:
    def __init__(self, api_client):
        self.api_client = api_client
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self,
            cfg: OptimizationConfig,
            db: SQLiteOptimizationDatabase,
            callbacks,
            famode_params: Dict[str, Any],
            ) -> None:
        # Preconditions
        if not getattr(self.api_client, 'base_url', None):
            callbacks.on_status("Scheduler: No server configured; aborting.")
            return

        # Load dataset
        all_q = DatasetParser.parse_dataset_file(cfg.dataset_path)
        total_q = len(all_q)
        # Baseline split
        split = db.get_baseline_correct_incorrect() if db else {"incorrect": [], "correct": []}
        wrong = list(split.get('incorrect', []))
        right = list(split.get('correct', []))
        if not wrong:
            callbacks.on_status("Scheduler: No baseline-incorrect questions; validating baseline and exiting.")
            return

        # Build combinations (use provided arrays)
        combos = generate_all_combinations(cfg.parameter_arrays)
        random.shuffle(combos)
        if not combos:
            callbacks.on_status("Scheduler: No parameter combinations to explore.")
            return

        # Executors
        be = BenchmarkExecutor(self.api_client)
        texec = TestExecutor(be)

        # Track stats per combo
        stats: Dict[Tuple[Tuple[str, Any], ...], Dict[str, Any]] = {}

        def key_for(params: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
            return tuple(sorted(params.items()))

        def get_tested_questions_for_combo(params: Dict[str, Any]) -> Set[int]:
            try:
                pjson = json.dumps(params, separators=(',', ':'))
                import sqlite3
                with sqlite3.connect(str(db.db_path)) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT question_number FROM test_cases WHERE parameters_json=?", (pjson,))
                    return {int(r[0]) for r in cur.fetchall() if r and r[0] is not None}
            except Exception:
                return set()

        # Exploration cycles
        sched = SchedulerConfig()
        cycle_index = 0
        while not self._stop_flag:
            cycle_index += 1
            callbacks.on_status(f"Scheduler: Explore cycle {cycle_index}...")

            # Select a slice of combos to try this cycle
            sample_combos = combos[:sched.cycle_combos] if len(combos) > sched.cycle_combos else combos
            random.shuffle(sample_combos)

            tests_this_cycle = 0
            for params in sample_combos:
                if self._stop_flag or tests_this_cycle >= sched.cycle_tests:
                    break

                k = key_for(params)
                if k not in stats:
                    stats[k] = {
                        'params': params,
                        'tested_wrong': 0,
                        'correct_wrong': 0,
                        'tested_right': 0,
                        'regress_right': 0,
                    }

                tested = get_tested_questions_for_combo(params)

                # Determine which pool to draw from
                pool_choice = 'wrong' if random.random() < sched.wrong_ratio else 'right'
                qnum: Optional[int] = None
                if pool_choice == 'wrong':
                    candidates = [q for q in wrong if q not in tested]
                    if candidates:
                        qnum = random.choice(candidates)
                if qnum is None and right:
                    candidates = [q for q in right if q not in tested]
                    if candidates:
                        qnum = random.choice(candidates)
                # Fallback: any unanswered
                if qnum is None:
                    remaining = [q for q in range(1, total_q + 1) if q not in tested]
                    if remaining:
                        qnum = random.choice(remaining)
                if qnum is None:
                    continue

                # Execute test
                q = all_q[qnum - 1]
                tc = create_test_case_from_parameters(question_id=qnum, question=q, parameters=params)
                ocfg = OptimizationConfig(
                    run_name=cfg.run_name,
                    dataset_path=cfg.dataset_path,
                    questions=[qnum],
                    parameter_arrays=cfg.parameter_arrays,
                    api_config=cfg.api_config,
                    server_config=cfg.server_config,
                    endpoint_type=cfg.endpoint_type,
                    api_config_path=getattr(cfg, 'api_config_path', None),
                    server_config_path=getattr(cfg, 'server_config_path', None),
                )
                # Temporarily switch scorer mode if needed
                try:
                    texec.scorer_mode = sched.exploration_scoring_mode  # attribute not used by scorer, kept for future
                except Exception:
                    pass
                # Execute a single test (cannot cancel mid-request; stop flag applies next iteration)
                tr = texec.execute_test_case(tc, ocfg)
                db.save_test_result(tc, tr, phase='aco')
                tests_this_cycle += 1
                if self._stop_flag:
                    callbacks.on_status("Scheduler: Stop requested; exiting explore loop.")
                    return

                # Update stats
                correct = bool(tr.success and (tr.score or 0.0) >= 1.0)
                if qnum in wrong:
                    stats[k]['tested_wrong'] += 1
                    if correct:
                        stats[k]['correct_wrong'] += 1
                elif qnum in right:
                    stats[k]['tested_right'] += 1
                    if not correct:
                        stats[k]['regress_right'] += 1

                # Check promotion gate
                tw = stats[k]['tested_wrong']
                cw = stats[k]['correct_wrong']
                trn = stats[k]['tested_right']
                rr = stats[k]['regress_right']
                fix_rate = (cw / tw) if tw > 0 else 0.0
                regress_rate = (rr / trn) if trn > 0 else 0.0
                if tw >= sched.min_wrong_samples and fix_rate >= sched.min_fix_rate and regress_rate <= sched.max_regress_rate:
                    callbacks.on_status("Scheduler: Promoting contender; completing coverage...")
                    self._complete_coverage_and_validate(params, all_q, db, texec, cfg, callbacks)
                    return  # Stop after first validated candidate (policy choice)

            if tests_this_cycle == 0:
                callbacks.on_status("Scheduler: No more tests to run; exiting.")
                return

    def _complete_coverage_and_validate(self,
                                        params: Dict[str, Any],
                                        all_q: List[Dict[str, Any]],
                                        db: SQLiteOptimizationDatabase,
                                        texec: TestExecutor,
                                        cfg: OptimizationConfig,
                                        callbacks) -> None:
        total_q = len(all_q)
        # Already tested for this combo
        import sqlite3
        pjson = json.dumps(params, separators=(',', ':'))
        with sqlite3.connect(str(db.db_path)) as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT question_number FROM test_cases WHERE completed=1 AND parameters_json=?", (pjson,))
            tested = {int(r[0]) for r in cur.fetchall() if r and r[0] is not None}
        missing = [q for q in range(1, total_q + 1) if q not in tested]
        callbacks.on_status(f"Scheduler: Completing coverage for contender ({len(missing)} remaining)...")

        for qnum in missing:
            if self._stop_flag:
                callbacks.on_status("Scheduler: Stop requested during coverage; aborting coverage.")
                return
            q = all_q[qnum - 1]
            tc = create_test_case_from_parameters(question_id=qnum, question=q, parameters=params)
            ocfg = OptimizationConfig(
                run_name=cfg.run_name,
                dataset_path=cfg.dataset_path,
                questions=[qnum],
                parameter_arrays=cfg.parameter_arrays,
                api_config=cfg.api_config,
                server_config=cfg.server_config,
                endpoint_type=cfg.endpoint_type,
                api_config_path=getattr(cfg, 'api_config_path', None),
                server_config_path=getattr(cfg, 'server_config_path', None),
            )
            tr = texec.execute_test_case(tc, ocfg)
            db.save_test_result(tc, tr, phase='validation')

        # Summarize against baseline
        try:
            split = db.get_baseline_correct_incorrect() if db else {"incorrect": [], "correct": []}
            right = set(split.get('correct', []))
            import sqlite3
            with sqlite3.connect(str(db.db_path)) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT question_number, score FROM test_cases WHERE completed=1 AND parameters_json=?",
                    (pjson,)
                )
                rows = cur.fetchall()
            total_correct = sum(1 for qn, sc in rows if qn and (sc or 0.0) >= 1.0)
            baseline_correct = len(right)
            callbacks.on_status(f"Scheduler: Candidate total_correct={total_correct} vs baseline={baseline_correct}.")
        except Exception:
            pass
