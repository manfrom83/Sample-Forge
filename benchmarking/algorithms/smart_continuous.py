"""
Smart Continuous Search algorithm for ACO optimization.

This algorithm intelligently explores the parameter space in three phases:
1. Recommended values first (smart start)
2. Local exploitation around best results
3. Wild card random exploration for surprises
"""

import random
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

from ..interfaces import (
    OptimizationAlgorithm, OptimizationConfig, OptimizationDatabase,
    TestCase, TestResult, ProgressStats, ParameterConverter
)
from ..database import create_test_case_from_parameters


class SmartContinuousAlgorithm(OptimizationAlgorithm):
    """
    Smart Continuous Search algorithm with intelligent phase progression.
    
    Phase 1: Test recommended values first for quick wins
    Phase 2: Local exploitation around best-scoring combinations
    Phase 3: Wild card random exploration for surprises
    """
    
    def __init__(self):
        self.config: Optional[OptimizationConfig] = None
        self.database: Optional[OptimizationDatabase] = None
        
        # Algorithm state
        self.tested_combinations: Set[tuple] = set()
        self.results_history: List[Dict[str, Any]] = []
        self.best_results: List[Dict[str, Any]] = []
        
        # Phase management
        self.current_phase = "recommended"  # then "exploitation" -> "exploration"
        self.phase_attempt_count = 0
        self.max_phase_attempts = 100
        
        # Cached data
        self.recommended_combinations: List[Dict[str, Any]] = []
        self.all_possible_combinations: List[Dict[str, Any]] = []
        self.total_possible_combinations = 0
        
    def initialize(self, config: OptimizationConfig, database: OptimizationDatabase) -> None:
        """Initialize algorithm with configuration and database"""
        self.config = config
        self.database = database
        
        # Pre-calculate all possible combinations for boundary checking
        self.all_possible_combinations = self._generate_all_combinations()
        self.total_possible_combinations = len(self.all_possible_combinations)
        
        # Extract recommended combinations first
        self.recommended_combinations = self._extract_recommended_combinations()
        
        # Try to restore existing state from database
        saved_state = database.load_algorithm_state("Smart Continuous Search")
        if saved_state:
            self.restore_state(saved_state)
    
    def _generate_all_combinations(self) -> List[Dict[str, Any]]:
        """Generate all possible parameter combinations (delegated to helper)"""
        from ..combinations import generate_all_combinations
        return generate_all_combinations(self.config.parameter_arrays)
    
    def _extract_recommended_combinations(self) -> List[Dict[str, Any]]:
        """Extract combinations that use recommended starting points"""
        recommended_combos = []
        
        # Build combination using only recommended values
        recommended_params = {}
        for param_name, param_info in self.config.parameter_arrays.items():
            if param_info.recommended_indices:
                # Use first recommended value for this parameter
                recommended_idx = param_info.recommended_indices[0]
                if recommended_idx < len(param_info.values):
                    value = param_info.values[recommended_idx]
                    recommended_params[param_name] = ParameterConverter.convert_parameter_value(param_name, value)
            else:
                # No recommended value, use first value in array
                if param_info.values:
                    value = param_info.values[0]
                    recommended_params[param_name] = ParameterConverter.convert_parameter_value(param_name, value)
        
        if recommended_params:
            recommended_combos.append(recommended_params)
        
        # Also generate combinations with each recommended value individually
        for param_name, param_info in self.config.parameter_arrays.items():
            for rec_idx in param_info.recommended_indices:
                if rec_idx < len(param_info.values):
                    combo = {}
                    for other_param, other_info in self.config.parameter_arrays.items():
                        if other_param == param_name:
                            # Use recommended value for this parameter
                            value = other_info.values[rec_idx]
                            combo[other_param] = ParameterConverter.convert_parameter_value(other_param, value)
                        else:
                            # Use first value for other parameters
                            if other_info.values:
                                value = other_info.values[0]
                                combo[other_param] = ParameterConverter.convert_parameter_value(other_param, value)
                    
                    if combo and combo not in recommended_combos:
                        recommended_combos.append(combo)
        
        return recommended_combos
    
    def get_next_test_case(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Get next test case based on current search phase"""
        if len(self.tested_combinations) >= self.total_possible_combinations:
            return None  # All combinations tested
        
        max_attempts = 1000
        self.phase_attempt_count += 1
        
        for attempt in range(max_attempts):
            candidate = None
            
            if self.current_phase == "recommended":
                candidate = self._sample_recommended()
            elif self.current_phase == "exploitation":
                candidate = self._sample_near_best_results()
            else:  # exploration phase
                candidate = self._sample_random_combination()
            
            if candidate is None:
                break
            
            # Check if this combination was already tested
            combo_key = ParameterConverter.make_hashable_key(candidate)
            if combo_key not in self.tested_combinations:
                self.tested_combinations.add(combo_key)
                
                # Create test case with a random question
                question = random.choice(available_questions)
                question_id = question.get('question_number', len(available_questions))
                
                return create_test_case_from_parameters(
                    question_id=question_id,
                    question=question,
                    parameters=candidate
                )
        
        # If we can't find untested combination, try advancing phase
        if self._should_advance_phase():
            self._advance_to_next_phase()
            self.phase_attempt_count = 0
            return self.get_next_test_case(available_questions)  # Recursive try with new phase
        
        # Fallback: sample any untested combination
        return self._sample_any_untested_combination(available_questions)
    
    def _sample_recommended(self) -> Optional[Dict[str, Any]]:
        """Sample from recommended starting combinations"""
        untested_recommended = [
            combo for combo in self.recommended_combinations
            if ParameterConverter.make_hashable_key(combo) not in self.tested_combinations
        ]
        
        if untested_recommended:
            return random.choice(untested_recommended)
        return None
    
    def _sample_near_best_results(self) -> Optional[Dict[str, Any]]:
        """Sample combinations similar to best results found so far"""
        if not self.best_results:
            return self._sample_random_combination()
        
        # Pick a high-scoring result to base sampling on
        base_result = random.choice(self.best_results[:min(5, len(self.best_results))])
        base_combo = base_result['parameters']
        
        # Create variation by changing 1-2 parameters
        new_combo = base_combo.copy()
        params_to_change = random.sample(
            list(self.config.parameter_arrays.keys()),
            min(2, len(self.config.parameter_arrays))
        )
        
        for param_name in params_to_change:
            param_info = self.config.parameter_arrays[param_name]
            if param_info.values:
                new_value = random.choice(param_info.values)
                new_combo[param_name] = ParameterConverter.convert_parameter_value(param_name, new_value)
        
        return new_combo
    
    def _sample_random_combination(self) -> Optional[Dict[str, Any]]:
        """Pure random sampling from parameter space"""
        combination = {}
        for param_name, param_info in self.config.parameter_arrays.items():
            if param_info.values:
                random_value = random.choice(param_info.values)
                combination[param_name] = ParameterConverter.convert_parameter_value(param_name, random_value)
        
        return combination if combination else None
    
    def _sample_any_untested_combination(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Fallback: find any untested combination"""
        for combo in self.all_possible_combinations:
            combo_key = ParameterConverter.make_hashable_key(combo)
            if combo_key not in self.tested_combinations:
                self.tested_combinations.add(combo_key)
                
                # Create test case with a random question
                question = random.choice(available_questions)
                question_id = question.get('question_number', len(available_questions))
                
                return create_test_case_from_parameters(
                    question_id=question_id,
                    question=question,
                    parameters=combo
                )
        
        return None
    
    def _should_advance_phase(self) -> bool:
        """Decide if we should advance to the next search phase"""
        if self.current_phase == "recommended":
            # Move to exploitation when all recommended combinations tested
            untested_recommended = [
                combo for combo in self.recommended_combinations
                if ParameterConverter.make_hashable_key(combo) not in self.tested_combinations
            ]
            return len(untested_recommended) == 0
        
        elif self.current_phase == "exploitation":
            # Move to exploration after reasonable exploitation attempts
            return self.phase_attempt_count > self.max_phase_attempts
        
        # Always stay in exploration phase (until all combinations tested)
        return False
    
    def _advance_to_next_phase(self) -> str:
        """Advance to the next search phase"""
        if self.current_phase == "recommended":
            self.current_phase = "exploitation"
            return "Phase 2: Exploring promising regions..."
        elif self.current_phase == "exploitation":
            self.current_phase = "exploration"
            return "Phase 3: Wild card discovery mode..."
        # Stay in exploration phase
        return "Phase 3: Continuing wild card discovery..."
    
    def update_with_result(self, test_case: TestCase, result: TestResult) -> None:
        """Update algorithm state with test result"""
        result_entry = {
            'parameters': test_case.parameters.copy(),
            'score': result.score or 0.0,
            'test_case': test_case,
            'timestamp': result.timestamp
        }
        
        self.results_history.append(result_entry)
        
        # Update best results (keep top 10)
        if result.score is not None:
            self.best_results.append(result_entry)
            self.best_results.sort(key=lambda x: x.get('score', 0), reverse=True)
            self.best_results = self.best_results[:10]  # Keep top 10
        
        # Save state to database
        self.database.save_algorithm_state("Smart Continuous Search", self.save_state())
    
    def get_progress_stats(self) -> ProgressStats:
        """Get current progress statistics"""
        phase_name = {
            "recommended": "Smart Start",
            "exploitation": "Local Exploitation", 
            "exploration": "Wild Card Discovery"
        }.get(self.current_phase, self.current_phase)
        
        best_score = max([r.get('score', 0) for r in self.best_results], default=0.0)
        
        return ProgressStats(
            completed_tests=len(self.tested_combinations),
            total_estimated=self.total_possible_combinations,
            current_phase=phase_name,
            current_message=f"Phase {self.phase_attempt_count} attempts",
            best_score=best_score,
            algorithm_specific_info={
                "phase": self.current_phase,
                "phase_attempts": self.phase_attempt_count,
                "recommended_remaining": len([
                    c for c in self.recommended_combinations
                    if ParameterConverter.make_hashable_key(c) not in self.tested_combinations
                ]),
                "best_results_count": len(self.best_results)
            }
        )
    
    def save_state(self) -> Dict[str, Any]:
        """Save algorithm state for resume"""
        # Convert tested combinations to serializable format
        tested_combos_list = []
        for combo_tuple in self.tested_combinations:
            tested_combos_list.append(dict(combo_tuple))
        
        return {
            "type": "SmartContinuousSearch",
            "tested_combinations": tested_combos_list,
            "current_phase": self.current_phase,
            "phase_attempt_count": self.phase_attempt_count,
            "results_history": self.results_history,
            "best_results": self.best_results,
            "last_updated": datetime.now().isoformat()
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore algorithm from saved state"""
        if state.get("type") != "SmartContinuousSearch":
            return  # Incompatible state
        
        # Restore tested combinations
        self.tested_combinations = set()
        for combo_dict in state.get("tested_combinations", []):
            combo_tuple = ParameterConverter.make_hashable_key(combo_dict)
            self.tested_combinations.add(combo_tuple)
        
        # Restore phase information
        self.current_phase = state.get("current_phase", "recommended")
        self.phase_attempt_count = state.get("phase_attempt_count", 0)
        
        # Restore results history
        self.results_history = state.get("results_history", [])
        self.best_results = state.get("best_results", [])
    
    def is_complete(self) -> bool:
        """Check if algorithm has completed all testing"""
        return len(self.tested_combinations) >= self.total_possible_combinations
    
    def get_current_phase(self) -> str:
        """Get current search phase for UI display"""
        return self.current_phase
    
    def get_phase_summary(self) -> Dict[str, Any]:
        """Get summary of phase progress"""
        return {
            "current_phase": self.current_phase,
            "phase_attempts": self.phase_attempt_count,
            "total_tested": len(self.tested_combinations),
            "total_possible": self.total_possible_combinations,
            "progress_percentage": (len(self.tested_combinations) / max(self.total_possible_combinations, 1)) * 100,
            "best_score": max([r.get('score', 0) for r in self.best_results], default=0.0),
            "phase_description": {
                "recommended": "Testing recommended parameter values for quick wins",
                "exploitation": "Exploring variations of best-performing combinations",
                "exploration": "Random exploration for unexpected discoveries"
            }.get(self.current_phase, "Unknown phase")
        }
