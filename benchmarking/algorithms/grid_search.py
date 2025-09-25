"""
Grid Search algorithm for ACO optimization.

This algorithm performs traditional exhaustive search through all possible
parameter combinations, testing each systematically.
"""

from typing import Dict, List, Any, Optional
import random
from datetime import datetime

from ..interfaces import (
    OptimizationAlgorithm, OptimizationConfig, OptimizationDatabase,
    TestCase, TestResult, ProgressStats, ParameterConverter
)
from ..database import create_test_case_from_parameters
from ..combinations import generate_all_combinations


class GridSearchAlgorithm(OptimizationAlgorithm):
    """
    Traditional exhaustive grid search algorithm.
    
    Tests all possible parameter combinations systematically,
    with optional prioritization of recommended values first.
    """
    
    def __init__(self):
        self.config: Optional[OptimizationConfig] = None
        self.database: Optional[OptimizationDatabase] = None
        
        # Algorithm state
        self.all_combinations: List[Dict[str, Any]] = []
        self.current_index = 0
        self.completed_tests = 0
        
    def initialize(self, config: OptimizationConfig, database: OptimizationDatabase) -> None:
        """Initialize algorithm with configuration and database"""
        self.config = config
        self.database = database
        
        # Generate all possible combinations (shared helper)
        self.all_combinations = generate_all_combinations(self.config.parameter_arrays)
        
        # Prioritize recommended combinations first
        self.all_combinations = self._prioritize_recommended_combinations()
        
        # Try to restore existing state from database
        saved_state = database.load_algorithm_state("Grid Search")
        if saved_state:
            self.restore_state(saved_state)
    
    # Note: combination generation delegated to shared helper
    
    def _prioritize_recommended_combinations(self) -> List[Dict[str, Any]]:
        """Sort combinations to prioritize those with recommended starting values"""
        def combination_priority(combination):
            score = 0
            for param_name, value in combination.items():
                if param_name in self.config.parameter_arrays:
                    param_info = self.config.parameter_arrays[param_name]
                    try:
                        value_index = param_info.values.index(str(value))
                        if value_index in param_info.recommended_indices:
                            score += 1  # Higher score for recommended values
                    except ValueError:
                        pass  # Value not found in list
            return -score  # Negative because we want higher scores first
        
        return sorted(self.all_combinations, key=combination_priority)
    
    def get_next_test_case(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Get next test case from systematic grid search"""
        if self.current_index >= len(self.all_combinations):
            return None  # All combinations tested
        
        # Get the next combination
        combination = self.all_combinations[self.current_index]
        self.current_index += 1
        
        # Create test case with a random question
        question = random.choice(available_questions)
        question_id = question.get('question_number', len(available_questions))
        
        return create_test_case_from_parameters(
            question_id=question_id,
            question=question,
            parameters=combination
        )
    
    def update_with_result(self, test_case: TestCase, result: TestResult) -> None:
        """Update algorithm state with test result"""
        self.completed_tests += 1
        
        # Save state to database periodically
        if self.completed_tests % 10 == 0:  # Save every 10 tests
            self.database.save_algorithm_state("Grid Search", self.save_state())
    
    def get_progress_stats(self) -> ProgressStats:
        """Get current progress statistics"""
        total_combinations = len(self.all_combinations)
        progress_percentage = (self.current_index / max(total_combinations, 1)) * 100
        
        # Determine current phase based on progress
        if progress_percentage < 20:
            current_phase = "Grid Search - Starting"
        elif progress_percentage < 80:
            current_phase = "Grid Search - In Progress"
        else:
            current_phase = "Grid Search - Finishing"
        
        return ProgressStats(
            completed_tests=self.completed_tests,
            total_estimated=total_combinations,
            current_phase=current_phase,
            current_message=f"Testing combination {self.current_index}/{total_combinations}",
            best_score=0.0,  # Grid search doesn't track best score internally
            algorithm_specific_info={
                "current_index": self.current_index,
                "total_combinations": total_combinations,
                "progress_percentage": progress_percentage,
                "remaining_combinations": total_combinations - self.current_index
            }
        )
    
    def save_state(self) -> Dict[str, Any]:
        """Save algorithm state for resume"""
        return {
            "type": "GridSearch",
            "current_index": self.current_index,
            "completed_tests": self.completed_tests,
            "total_combinations": len(self.all_combinations),
            "last_updated": datetime.now().isoformat()
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore algorithm from saved state"""
        if state.get("type") != "GridSearch":
            return  # Incompatible state
        
        # Restore progress
        self.current_index = state.get("current_index", 0)
        self.completed_tests = state.get("completed_tests", 0)
        
        # Validate restored state
        if self.current_index > len(self.all_combinations):
            self.current_index = len(self.all_combinations)
    
    def is_complete(self) -> bool:
        """Check if algorithm has completed all testing"""
        return self.current_index >= len(self.all_combinations)
    
    def get_remaining_combinations(self) -> List[Dict[str, Any]]:
        """Get list of remaining combinations for resume functionality"""
        if self.current_index < len(self.all_combinations):
            return self.all_combinations[self.current_index:]
        return []
    
    def get_completion_summary(self) -> Dict[str, Any]:
        """Get summary of grid search completion"""
        total_combinations = len(self.all_combinations)
        
        return {
            "algorithm": "Grid Search",
            "total_combinations": total_combinations,
            "completed_combinations": self.current_index,
            "completed_tests": self.completed_tests,
            "progress_percentage": (self.current_index / max(total_combinations, 1)) * 100,
            "is_complete": self.is_complete(),
            "remaining_combinations": max(0, total_combinations - self.current_index)
        }
    
    def preview_combinations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Preview first few combinations for UI display"""
        return self.all_combinations[:limit]
    
    def get_recommended_combinations(self) -> List[Dict[str, Any]]:
        """Get combinations that use recommended parameter values"""
        recommended_combos = []
        
        for combination in self.all_combinations:
            has_recommended = False
            for param_name, value in combination.items():
                if param_name in self.config.parameter_arrays:
                    param_info = self.config.parameter_arrays[param_name]
                    try:
                        value_index = param_info.values.index(str(value))
                        if value_index in param_info.recommended_indices:
                            has_recommended = True
                            break
                    except ValueError:
                        pass
            
            if has_recommended:
                recommended_combos.append(combination)
        
        return recommended_combos
