"""
Core interfaces and data structures for the unified ACO optimization system.

This module defines the contracts that all optimization components must follow,
enabling clean separation of concerns and easy extensibility.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Protocol
from abc import ABC, abstractmethod
from pathlib import Path
import time
from datetime import datetime


@dataclass
class ParameterArrayInfo:
    """Information about a parameter array for optimization"""
    values: List[str]  # String values from array parsing
    recommended_indices: List[int]  # Indices of ((recommended)) values


@dataclass
class TestCase:
    """Represents a single question x parameter combination to test"""
    test_id: int
    question_id: int
    question: Dict[str, Any]  # Full question object with ground_truth, etc.
    parameters: Dict[str, Any]  # Parameter name -> converted value
    
    # Results (filled after execution)
    response: Optional[str] = None
    score: Optional[float] = None
    response_time: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None


@dataclass
class TestResult:
    """Result of executing a single test case"""
    test_case: TestCase
    success: bool = True
    response: Optional[str] = None
    score: Optional[float] = None
    response_time: Optional[float] = None
    slots_data: Optional[Dict[str, Any]] = None
    full_api_response: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProgressStats:
    """Progress statistics from an optimization algorithm"""
    completed_tests: int
    total_estimated: int  # May be unknown (-1) for dynamic algorithms
    current_phase: str
    current_message: str
    best_score: float = 0.0
    algorithm_specific_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationConfig:
    """Complete configuration for an optimization run"""
    # Core configuration
    run_name: str
    dataset_path: str
    questions: List[int]  # Question indices to test
    parameter_arrays: Dict[str, ParameterArrayInfo]
    
    # System configuration
    api_config: Any  # ParameterConfig object
    server_config: Any  # ServerConfig object
    endpoint_type: str = "chat_completions"
    algorithm: str = "Thompson Sampling Bandit"
    
    # Run options
    resume: bool = False
    auto_save_enabled: bool = True
    # Metadata for reliable resume
    api_config_path: Optional[str] = None
    server_config_path: Optional[str] = None


@dataclass
class OptimizationSummary:
    """Summary of completed optimization run"""
    run_name: str
    algorithm: str
    start_time: str
    end_time: str
    total_runtime_seconds: float
    
    completed_tests: int
    total_tests: Optional[int]  # None for dynamic algorithms
    
    best_score: float
    best_parameters: Dict[str, Any]
    
    status: str  # "completed", "stopped", "error"
    error_message: Optional[str] = None


class OptimizationCallbacks(Protocol):
    """Callback interface for optimization progress and results"""
    
    def on_progress_update(self, current: int, total: int, message: str) -> None:
        """Called when optimization progress updates"""
        pass
    
    def on_status_message(self, message: str) -> None:
        """Called for general status messages"""
        pass
    
    def on_test_result(self, result: TestResult) -> None:
        """Called when individual test completes"""
        pass
    
    def on_optimization_complete(self, summary: OptimizationSummary) -> None:
        """Called when optimization finishes"""
        pass
    
    def on_optimization_error(self, error: Exception) -> None:
        """Called when optimization encounters fatal error"""
        pass


class OptimizationAlgorithm(ABC):
    """Base interface for all optimization algorithms"""
    
    @abstractmethod
    def initialize(self, config: OptimizationConfig, database: 'OptimizationDatabase') -> None:
        """Initialize algorithm with configuration and database"""
        pass
    
    @abstractmethod
    def get_next_test_case(self, available_questions: List[Dict[str, Any]]) -> Optional[TestCase]:
        """Get next test case to execute, or None if algorithm is complete"""
        pass
    
    @abstractmethod
    def update_with_result(self, test_case: TestCase, result: TestResult) -> None:
        """Update algorithm state with test result"""
        pass
    
    @abstractmethod
    def get_progress_stats(self) -> ProgressStats:
        """Get current progress statistics"""
        pass
    
    @abstractmethod
    def save_state(self) -> Dict[str, Any]:
        """Save algorithm state for resume"""
        pass
    
    @abstractmethod
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Restore algorithm from saved state"""
        pass
    
    @abstractmethod
    def is_complete(self) -> bool:
        """Check if algorithm has completed all testing"""
        pass


@dataclass
class RunMetadata:
    """Metadata for an optimization run"""
    run_name: str
    algorithm: str
    start_time: str
    status: str  # "running", "paused", "completed", "error"
    
    # Configuration info
    dataset_path: str
    selected_questions: List[int]
    total_questions: int
    endpoint_type: str
    
    # Progress info
    total_combinations: Optional[int]  # None for dynamic algorithms
    completed_combinations: int
    
    # Results info
    best_score: Optional[float] = None
    best_parameters: Optional[Dict[str, Any]] = None
    
    # System info
    last_save_time: Optional[str] = None
    end_time: Optional[str] = None
    error_message: Optional[str] = None
    # Config paths used for this run
    api_config_path: Optional[str] = None
    server_config_path: Optional[str] = None


class OptimizationDatabase(ABC):
    """Database interface for optimization persistence"""
    
    @abstractmethod
    def save_test_result(self, test_case: TestCase, result: TestResult) -> None:
        """Save completed test result"""
        pass
    
    @abstractmethod
    def get_top_combinations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top performing parameter combinations"""
        pass
    
    @abstractmethod
    def get_progress_summary(self) -> Dict[str, int]:
        """Get summary of completed vs total test cases"""
        pass
    
    @abstractmethod
    def get_incomplete_test_cases(self) -> List[TestCase]:
        """Get test cases that haven't been completed (for resume)"""
        pass
    
    @abstractmethod
    def save_algorithm_state(self, algorithm_name: str, state: Dict[str, Any]) -> None:
        """Save algorithm-specific state"""
        pass
    
    @abstractmethod
    def load_algorithm_state(self, algorithm_name: str) -> Dict[str, Any]:
        """Load algorithm-specific state"""
        pass
    
    @abstractmethod
    def save_run_metadata(self, metadata: RunMetadata) -> None:
        """Save run metadata"""
        pass
    
    @abstractmethod
    def load_run_metadata(self) -> Optional[RunMetadata]:
        """Load run metadata"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close database connections"""
        pass


class ParameterConverter:
    """Utility class for converting parameter values"""
    
    @staticmethod
    def convert_parameter_value(param_name: str, value: str) -> Any:
        """Convert string parameter value to appropriate Python type"""
        value = value.strip()
        
        # Try boolean
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        
        # Try integer
        try:
            if '.' not in value:
                return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Return as string
        return value
    
    @staticmethod
    def make_hashable_key(parameters: Dict[str, Any]) -> tuple:
        """Convert parameter dictionary to hashable key"""
        items = []
        for key, value in sorted(parameters.items()):
            if isinstance(value, list):
                items.append((key, tuple(value)))
            elif isinstance(value, dict):
                items.append((key, tuple(sorted(value.items()))))
            else:
                items.append((key, value))
        return tuple(items)


class ValidationError(Exception):
    """Raised when optimization configuration is invalid"""
    pass


class OptimizationError(Exception):
    """Raised when optimization encounters a fatal error"""
    pass
