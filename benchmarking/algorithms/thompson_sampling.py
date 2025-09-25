"""
Thompson Sampling Bandit algorithm for ACO optimization.

This implementation uses Bayesian learning with Beta distributions to balance
exploration vs exploitation. Each parameter value is treated as a separate bandit arm.
"""

import random
from typing import Dict, List, Any, Optional, Set
from datetime import datetime

from ..interfaces import (
    OptimizationAlgorithm, OptimizationConfig, OptimizationDatabase,
    TestCase, TestResult, ProgressStats, ParameterConverter
)
from ..database import create_test_case_from_parameters


class ThompsonSamplingAlgorithm(OptimizationAlgorithm):
    """
    Thompson Sampling bandit algorithm for discrete parameter optimization.
    
    Each parameter value is treated as a separate bandit arm with Beta distribution.
    Uses epsilon-greedy exploration with adaptive decay and strong priors for recommended values.
    """
    
    def __init__(self):
        self.config: Optional[OptimizationConfig] = None
        self.database: Optional[OptimizationDatabase] = None
        
        # Algorithm state
        self.bandit_stats: Dict[str, Dict[str, Dict[str, float]]] = {}
        self.tested_combinations: Set[tuple] = set()
        self.evaluations = 0
        
        # Configuration
        self.initial_exploration_prob = 0.05  # Start with 5% random exploration
        self.min_exploration_prob = 0.01      # Decay to 1% minimum
        self.total_possible_combinations = 0
        
    def initialize(self, config: OptimizationConfig, database: OptimizationDatabase) -> None:
        """Initialize algorithm with configuration and database"""
        self.config = config
        self.database = database
        
        # Calculate total possible combinations
        self.total_possible_combinations = 1
        for param_info in config.parameter_arrays.values():
            self.total_possible_combinations *= len(param_info.values)
        
        # Try to restore existing bandit stats from database
        saved_state = database.load_algorithm_state("Thompson Sampling Bandit")
        if saved_state:
            self.restore_state(saved_state)
        else:
            # Initialize fresh bandit statistics
            self._initialize_bandit_stats()
    
    def _initialize_bandit_stats(self) -> None:
        """Initialize bandit statistics with priors"""
        self.bandit_stats = {}
        
        for param_name, param_info in self.config.parameter_arrays.items():
            if param_name not in self.bandit_stats:
                self.bandit_stats[param_name] = {}
            
            for i, value in enumerate(param_info.values):
                if str(value) not in self.bandit_stats[param_name]:
                    # Give recommended values stronger positive priors
                    if i in param_info.recommended_indices:
                        prior_success, prior_fail = 3.0, 1.0  # Strong positive prior Beta(3,1)
                    else:
                        prior_success, prior_fail = 1.0, 1.0  # Neutral prior Beta(1,1)
                    
                    self.bandit_stats[param_name][str(value)] = {
                        "success": prior_success,
                        "fail": prior_fail
                    }
    
    def get_next_test_case(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Get next test case using Thompson Sampling + epsilon-greedy"""
        if len(self.tested_combinations) >= self.total_possible_combinations:
            return None  # All combinations tested
        
        max_attempts = 1000  # Prevent infinite loops
        
        for attempt in range(max_attempts):
            # Sample parameter combination
            combination = self._sample_combination()
            if combination is None:
                break
            
            # Check if this combination was already tested
            combo_key = ParameterConverter.make_hashable_key(combination)
            if combo_key not in self.tested_combinations:
                self.tested_combinations.add(combo_key)
                
                # Create test case with a random question
                question = random.choice(available_questions)
                question_id = question.get('question_number', len(available_questions))
                
                test_case = create_test_case_from_parameters(
                    question_id=question_id,
                    question=question,
                    parameters=combination
                )
                
                return test_case
        
        # Fallback: find any untested combination systematically
        return self._get_any_untested_combination(available_questions)
    
    def _sample_combination(self) -> Optional[Dict[str, Any]]:
        """Sample parameter combination using Thompson Sampling + epsilon-greedy"""
        combination = {}
        
        # Get current exploration probability (adaptive decay)
        current_exploration_prob = self._get_exploration_prob()
        
        if random.random() < current_exploration_prob:
            # Epsilon-greedy: Pure random exploration
            for param_name, param_info in self.config.parameter_arrays.items():
                random_value = random.choice(param_info.values)
                combination[param_name] = ParameterConverter.convert_parameter_value(param_name, random_value)
        else:
            # Thompson Sampling: Sample from Beta distributions
            for param_name, param_info in self.config.parameter_arrays.items():
                # Sample expected reward for each value from its Beta distribution
                samples = {}
                for value, stats in self.bandit_stats[param_name].items():
                    alpha = stats["success"]
                    beta = stats["fail"]
                    # Sample from Beta(alpha, beta) distribution
                    samples[value] = random.betavariate(alpha, beta)
                
                # Pick value with highest sampled expected reward
                best_value = max(samples, key=samples.get)
                combination[param_name] = ParameterConverter.convert_parameter_value(param_name, best_value)
        
        return combination
    
    def _get_any_untested_combination(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Fallback to find any untested combination systematically"""
        import itertools
        
        param_names = list(self.config.parameter_arrays.keys())
        param_value_lists = [self.config.parameter_arrays[name].values for name in param_names]
        
        for combination_values in itertools.product(*param_value_lists):
            combination = {}
            for param_name, value in zip(param_names, combination_values):
                combination[param_name] = ParameterConverter.convert_parameter_value(param_name, value)
            
            combo_key = ParameterConverter.make_hashable_key(combination)
            if combo_key not in self.tested_combinations:
                self.tested_combinations.add(combo_key)
                
                # Create test case with a random question
                question = random.choice(available_questions)
                question_id = question.get('question_number', len(available_questions))
                
                return create_test_case_from_parameters(
                    question_id=question_id,
                    question=question,
                    parameters=combination
                )
        
        return None  # All combinations truly exhausted
    
    def _get_exploration_prob(self) -> float:
        """Get current exploration probability with adaptive decay"""
        # Decay exploration over time: start high, decay to minimum
        decay_factor = max(0.01, 100 / (self.evaluations + 100))
        current_prob = max(
            self.min_exploration_prob,
            self.initial_exploration_prob * decay_factor
        )
        return current_prob
    
    def update_with_result(self, test_case: TestCase, result: TestResult) -> None:
        """Update bandit statistics with test result"""
        if result.score is None:
            return  # Skip results without scores
        
        # Update bandit stats for each parameter value used
        for param_name, value in test_case.parameters.items():
            if param_name in self.bandit_stats and str(value) in self.bandit_stats[param_name]:
                stats = self.bandit_stats[param_name][str(value)]
                
                # Treat score as success probability (0.0 to 1.0)
                stats["success"] += result.score
                stats["fail"] += (1.0 - result.score)
        
        self.evaluations += 1
        
        # Save updated bandit stats to database
        self.database.save_algorithm_state("Thompson Sampling Bandit", self.save_state())
    
    def get_progress_stats(self) -> ProgressStats:
        """Get current progress statistics"""
        current_exploration = self._get_exploration_prob()
        best_score = self._get_best_expected_score()
        
        return ProgressStats(
            completed_tests=self.evaluations,
            total_estimated=self.total_possible_combinations,
            current_phase=f"Thompson Sampling (epsilon={current_exploration:.3f})",
            current_message=f"Bayesian learning with {self.evaluations} evaluations",
            best_score=best_score,
            algorithm_specific_info={
                "exploration_probability": current_exploration,
                "tested_combinations": len(self.tested_combinations),
                "bandit_arms_count": sum(len(values) for values in self.bandit_stats.values())
            }
        )
    
    def _get_best_expected_score(self) -> float:
        """Calculate best expected score from bandit statistics"""
        best_expected = 0.0
        
        for param_name, value_stats in self.bandit_stats.items():
            for value, stats in value_stats.items():
                alpha = stats["success"]
                beta = stats["fail"]
                # Expected value of Beta distribution is alpha / (alpha + beta)
                expected_reward = alpha / (alpha + beta)
                best_expected = max(best_expected, expected_reward)
        
        return best_expected
    
    def save_state(self) -> Dict[str, Any]:
        """Save algorithm state for resume"""
        # Convert tested combinations (frozenset tuples) to serializable format
        tested_combos_list = []
        for combo_tuple in self.tested_combinations:
            tested_combos_list.append(dict(combo_tuple))
        
        return {
            "type": "ThompsonSamplingBandit",
            "bandit_stats": self.bandit_stats,
            "tested_combinations": tested_combos_list,
            "evaluations": self.evaluations,
            "total_possible_combinations": self.total_possible_combinations,
            "last_updated": datetime.now().isoformat()
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore algorithm from saved state"""
        if state.get("type") != "ThompsonSamplingBandit":
            return  # Incompatible state
        
        # Restore bandit statistics
        self.bandit_stats = state.get("bandit_stats", {})
        
        # Restore tested combinations
        self.tested_combinations = set()
        for combo_dict in state.get("tested_combinations", []):
            combo_tuple = ParameterConverter.make_hashable_key(combo_dict)
            self.tested_combinations.add(combo_tuple)
        
        # Restore evaluation count and metadata
        self.evaluations = state.get("evaluations", 0)
        self.total_possible_combinations = state.get("total_possible_combinations", 0)
        
        # If bandit_stats is empty, initialize fresh
        if not self.bandit_stats and self.config:
            self._initialize_bandit_stats()
    
    def is_complete(self) -> bool:
        """Check if algorithm has completed all testing"""
        return len(self.tested_combinations) >= self.total_possible_combinations
    
    def get_bandit_summary(self) -> Dict[str, Any]:
        """Get summary of bandit statistics for analysis"""
        summary = {}
        for param_name, value_stats in self.bandit_stats.items():
            summary[param_name] = {}
            for value, stats in value_stats.items():
                alpha = stats["success"]
                beta = stats["fail"]
                # Calculate expected reward (mean of Beta distribution)
                expected_reward = alpha / (alpha + beta)
                # Calculate confidence (total samples)
                confidence = alpha + beta
                
                summary[param_name][str(value)] = {
                    "expected_reward": expected_reward,
                    "confidence": confidence,
                    "success_count": alpha,
                    "fail_count": beta
                }
        
        return summary


