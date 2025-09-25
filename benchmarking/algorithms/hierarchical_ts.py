"""
Hierarchical Thompson Sampling (Balanced)

Budget-aware, indefinitely running algorithm that:
- Uses Beta-Bernoulli posteriors per parameter value (informative priors for recommended starts)
- Selects next combination via Thompson sampling with light negative weighting for consistently bad values
- Ensures fair, round-robin coverage across questions for each new combo (no duplicates)
- Keeps running until stopped; does not exhaust the space by design

This is a pragmatic first implementation aligned with the new Simple Mode.
"""

from __future__ import annotations

import random
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass

from ..interfaces import (
    OptimizationAlgorithm, OptimizationConfig, OptimizationDatabase,
    TestCase, ProgressStats, ParameterConverter
)
from ..database import create_test_case_from_parameters


@dataclass
class _AlgoState:
    # Beta(a, b) per parameter value: state[param][value_str] = (alpha, beta, trials)
    betas: Dict[str, Dict[str, Tuple[float, float, int]]]
    # Track which (combo_key -> set(question_ids)) have been tried to ensure no duplicates
    combo_question_seen: Dict[tuple, Set[int]]
    # Round-robin index into available questions
    question_rr_index: int = 0
    # Exploration rate; may be adapted over time
    epsilon: float = 0.1
    # Algorithm-specific message
    current_message: str = "Initializing"


class HierarchicalTSBalanced(OptimizationAlgorithm):
    def __init__(self):
        self.config: Optional[OptimizationConfig] = None
        self.db: Optional[OptimizationDatabase] = None
        self.state = _AlgoState(betas={}, combo_question_seen={})
        self.available_questions_cache: List[Dict[str, Any]] = []

        # Internal scheduling
        self._active_combos: List[Dict[str, Any]] = []  # currently promoted combos
        self._max_active = 5

        # Negative weighting thresholds
        self._bad_min_trials = 5
        self._bad_mean_threshold = 0.15

    def initialize(self, config: OptimizationConfig, database: OptimizationDatabase) -> None:
        self.config = config
        self.db = database
        # Initialize Beta priors from parameter arrays
        for pname, pinfo in self.config.parameter_arrays.items():
            self.state.betas.setdefault(pname, {})
            for idx, v in enumerate(pinfo.values):
                # Recommended indices get informative prior
                if idx in (pinfo.recommended_indices or []):
                    self.state.betas[pname][v] = (4.0, 2.0, 0)
                else:
                    self.state.betas[pname][v] = (1.0, 1.0, 0)

        # Try to restore prior state if any
        try:
            saved = database.load_algorithm_state(self.__class__.__name__)
            if saved:
                self._restore_state_dict(saved)
        except Exception:
            pass

        self.state.current_message = "Balanced TS initialized"

    def get_next_test_case(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        # Cache questions for RR scheduling
        if not self.available_questions_cache:
            self.available_questions_cache = list(available_questions)
        if not self.available_questions_cache:
            self.state.current_message = "No questions available"
            return None

        # Ensure we have a current combo to evaluate
        if not self._active_combos or random.random() < 0.25:
            # Periodically sample a new combo to keep exploration alive
            combo = self._sample_combo()
            self._active_combos.append(combo)
            # Limit active combos list length
            if len(self._active_combos) > self._max_active:
                self._active_combos.pop(0)

        # Pick the current combo (round-robin across active combos)
        if not self._active_combos:
            combo = self._sample_combo()
            self._active_combos.append(combo)
        combo = self._active_combos[0]
        # Rotate active combos list for fairness
        self._active_combos = self._active_combos[1:] + self._active_combos[:1]

        # Choose a question not yet seen for this combo
        combo_key = ParameterConverter.make_hashable_key(combo)
        seen = self.state.combo_question_seen.setdefault(combo_key, set())

        # Try up to N questions to find an unseen pair (avoid duplicates)
        N = len(self.available_questions_cache)
        for _ in range(N):
            qidx = self.state.question_rr_index % N
            self.state.question_rr_index += 1
            q = self.available_questions_cache[qidx]
            qid = int(q.get('question_number') or q.get('question_id') or 0)
            if qid and qid not in seen:
                seen.add(qid)
                # Build TestCase
                tc = create_test_case_from_parameters(
                    question_id=qid,
                    question=q,
                    parameters=combo
                )
                self.state.current_message = f"Testing combo on Q{qid}"
                return tc

        # If all questions seen for this combo, sample a new combo and try again
        combo = self._sample_combo()
        self._active_combos.append(combo)
        combo_key = ParameterConverter.make_hashable_key(combo)
        self.state.combo_question_seen.setdefault(combo_key, set())
        # Recurse once (will find a question or fail below)
        return self.get_next_test_case(self.available_questions_cache)

    def update_with_result(self, test_case: TestCase, result) -> None:
        # Consider a success when score >= 1.0
        success = bool(result.score is not None and result.score >= 1.0)
        # Update per-value betas
        for pname, val in test_case.parameters.items():
            v_str = str(val)
            alpha, beta, trials = self.state.betas.get(pname, {}).get(v_str, (1.0, 1.0, 0))
            if success:
                alpha += 1.0
            else:
                beta += 1.0
            trials += 1
            self.state.betas.setdefault(pname, {})[v_str] = (alpha, beta, trials)

        # Periodically persist state
        if (result.timestamp and result.test_case and result.test_case.test_id) or random.random() < 0.1:
            try:
                self.db.save_algorithm_state(self.__class__.__name__, self._to_state_dict())
            except Exception:
                pass

    def get_progress_stats(self) -> ProgressStats:
        # Estimate total unknown; provide rolling message
        return ProgressStats(
            completed_tests=0,  # unknown globally here
            total_estimated=-1,
            current_phase="optimize",
            current_message=self.state.current_message,
            best_score=0.0,
            algorithm_specific_info={
                'active_combos': len(self._active_combos),
                'epsilon': round(self.state.epsilon, 3)
            }
        )

    def save_state(self) -> Dict[str, Any]:
        return self._to_state_dict()

    def restore_state(self, state: Dict[str, Any]) -> None:
        self._restore_state_dict(state)

    def is_complete(self) -> bool:
        # Runs indefinitely until stopped
        return False

    # --- helpers ---

    def _to_state_dict(self) -> Dict[str, Any]:
        # Convert sets to lists for JSON serialization
        combo_seen_serializable = {str(k): list(v) for k, v in self.state.combo_question_seen.items()}
        return {
            'betas': self.state.betas,
            'combo_question_seen': combo_seen_serializable,
            'question_rr_index': self.state.question_rr_index,
            'epsilon': self.state.epsilon,
        }

    def _restore_state_dict(self, d: Dict[str, Any]) -> None:
        self.state.betas = d.get('betas', {})
        combo_seen = d.get('combo_question_seen', {})
        # combo keys stored as strings; keep empty to avoid mismatch
        self.state.combo_question_seen = {k: set(v) for k, v in combo_seen.items()}
        self.state.question_rr_index = int(d.get('question_rr_index', 0))
        self.state.epsilon = float(d.get('epsilon', 0.1))

    def _sample_combo(self) -> Dict[str, Any]:
        combo: Dict[str, Any] = {}
        for pname, pinfo in self.config.parameter_arrays.items():
            values = pinfo.values
            # Exploration
            if random.random() < self.state.epsilon:
                v = random.choice(values)
            else:
                v = self._thompson_choice(pname, values)
            # Convert to typed value
            combo[pname] = ParameterConverter.convert_parameter_value(pname, v)
        return combo

    def _thompson_choice(self, pname: str, values: List[str]) -> str:
        # Draw a sample from Beta posterior per value; apply light negative weighting
        best_v = None
        best_sample = -1.0
        betas = self.state.betas.get(pname, {})
        for v in values:
            alpha, beta, trials = betas.get(v, (1.0, 1.0, 0))
            # Negative weighting for consistently poor values
            mean = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
            penalty = 0.0
            if trials >= self._bad_min_trials and mean < self._bad_mean_threshold:
                penalty = 0.2  # reduce chance
            # Thompson sample
            import random as _r
            # Use Python's random.betavariate
            sample = _r.betavariate(alpha, beta)
            sample -= penalty
            if sample > best_sample:
                best_sample = sample
                best_v = v
        return best_v if best_v is not None else random.choice(values)


