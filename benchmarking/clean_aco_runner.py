"""
Clean ACO Runner - Unified optimization system.

This module replaces the 2,500+ line monolithic aco_runner.py with a clean,
maintainable architecture that eliminates ALL code duplication.

SINGLE ENTRY POINT for all optimization types.
"""

import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from .interfaces import (
    OptimizationConfig, OptimizationCallbacks, OptimizationSummary,
    TestCase, TestResult, RunMetadata, ValidationError, OptimizationError
)
from .database import SQLiteOptimizationDatabase
from .test_executor import TestExecutor
from .algorithms.factory import AlgorithmFactory
from .runner import BenchmarkExecutor, DatasetParser
from managers.path_manager import app_paths


class CleanACORunner:
    """
    Clean, unified ACO optimization runner.
    
    This class replaces the 2,500+ line monolithic aco_runner.py with:
    - Single entry point for ALL optimization types
    - Zero code duplication
    - Clean separation of concerns
    - Easy extensibility for new algorithms
    """
    
    def __init__(self, api_client=None):
        # Core components - initialized during optimization
        self.database: Optional[SQLiteOptimizationDatabase] = None
        self.algorithm: Optional[Any] = None  # OptimizationAlgorithm
        self.test_executor: Optional[TestExecutor] = None
        self.callbacks: Optional[OptimizationCallbacks] = None
        self.api_client = api_client  # Pre-configured API client
        
        # Optimization state
        self.config: Optional[OptimizationConfig] = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.optimization_thread: Optional[threading.Thread] = None
        
        # Progress tracking
        self.start_time: Optional[str] = None
        self.end_time: Optional[str] = None
        self.completed_tests = 0
        self.best_score = 0.0
        self.best_parameters: Dict[str, Any] = {}
        
        # Dataset cache
        self._dataset_questions: Optional[List[Dict[str, Any]]] = None
        self._selected_questions: Optional[List[Dict[str, Any]]] = None
        # Optional override to reuse an existing run directory when resuming
        self.resume_run_directory: Optional[Path] = None
    
    def start_optimization(self, config: OptimizationConfig, callbacks: OptimizationCallbacks) -> None:
        """
        SINGLE entry point for ALL optimization types.
        
        This replaces:
        - run_optimization()
        - run_individual_optimization() 
        - run_named_individual_optimization()
        
        All with ONE clean, unified method.
        """
        if self.is_running:
            raise OptimizationError("Optimization already running")
        
        # Validate configuration
        self._validate_config(config)
        
        # Store configuration and callbacks
        self.config = config
        self.callbacks = callbacks
        
        # Start optimization in background thread
        self.optimization_thread = threading.Thread(
            target=self._run_optimization_thread,
            name="CleanACOOptimization",
            daemon=True
        )
        self.optimization_thread.start()
    
    def _run_optimization_thread(self) -> None:
        """Main optimization execution thread"""
        try:
            self.is_running = True
            self.start_time = datetime.now().isoformat()
            
            # 1. Initialize components
            self._initialize_components()
            
            # 2. Load and prepare dataset
            self._prepare_dataset()
            
            # 3. Handle resume logic if needed
            self._handle_resume_logic()
            
            # 4. Save initial run metadata
            self._save_initial_metadata()
            
            # 5. Execute optimization loop
            self._execute_optimization_loop()
            
            # 6. Complete optimization
            self._complete_optimization("completed")
            
        except Exception as e:
            self._complete_optimization("error", str(e))
    
    def _initialize_components(self) -> None:
        """Initialize all optimization components"""
        # 1. Create run directory and database
        run_directory = self._create_run_directory()
        self.database = SQLiteOptimizationDatabase(run_directory)
        
        # 2. Create algorithm instance
        self.algorithm = AlgorithmFactory.create(self.config.algorithm, self.config, self.database)
        
        # 3. Create test executor with API client
        if not self.api_client:
            from utils.api_client import LLMClient
            self.api_client = LLMClient()  # Fallback if not provided
        
        benchmark_executor = BenchmarkExecutor(self.api_client)
        self.test_executor = TestExecutor(benchmark_executor)
        
        # Status callback
        if self.callbacks:
            self.callbacks.on_status_message(f"Initialized {self.config.algorithm} with clean architecture")
    
    def _prepare_dataset(self) -> None:
        """Load and prepare dataset questions"""
        try:
            # Parse dataset file
            self._dataset_questions = DatasetParser.parse_dataset_file(self.config.dataset_path)
            
            # Select specified questions
            self._selected_questions = []
            for question_idx in self.config.questions:
                if 1 <= question_idx <= len(self._dataset_questions):
                    question = self._dataset_questions[question_idx - 1]
                    self._selected_questions.append(question)
                else:
                    raise ValidationError(f"Question {question_idx} not found in dataset")
            
            if self.callbacks:
                self.callbacks.on_status_message(
                    f"Loaded dataset: {len(self._selected_questions)} questions ready for testing"
                )
                
        except Exception as e:
            raise OptimizationError(f"Failed to prepare dataset: {e}")
    
    def _handle_resume_logic(self) -> None:
        """Handle resume from existing run if configured"""
        if not self.config.resume:
            return
        
        # Load existing metadata
        existing_metadata = self.database.load_run_metadata()
        if existing_metadata and existing_metadata.status in ["running", "paused"]:
            # Resume from existing state
            self.completed_tests = existing_metadata.completed_combinations
            
            if existing_metadata.best_score:
                self.best_score = existing_metadata.best_score
            if existing_metadata.best_parameters:
                self.best_parameters = existing_metadata.best_parameters
            
            if self.callbacks:
                self.callbacks.on_status_message(
                    f"Resuming optimization: {self.completed_tests} tests already completed"
                )
        else:
            if self.callbacks:
                self.callbacks.on_status_message("No resumable run found, starting fresh optimization")
    
    def _save_initial_metadata(self) -> None:
        """Save initial run metadata to database"""
        metadata = RunMetadata(
            run_name=self.config.run_name,
            algorithm=self.config.algorithm,
            start_time=self.start_time,
            status="running",
            dataset_path=self.config.dataset_path,
            selected_questions=self.config.questions,
            total_questions=len(self.config.questions),
            endpoint_type=self.config.endpoint_type,
            total_combinations=None,  # Will be set by algorithm if known
            completed_combinations=0,
            api_config_path=getattr(self.config, 'api_config_path', None),
            server_config_path=getattr(self.config, 'server_config_path', None)
        )
        
        self.database.save_run_metadata(metadata)
    
    def _execute_optimization_loop(self) -> None:
        """Main optimization execution loop - SINGLE implementation for all algorithms"""
        test_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 10
        
        if self.callbacks:
            self.callbacks.on_status_message(f"Starting {self.config.algorithm} optimization loop...")
        
        while not self.should_stop:
            # Handle pause
            while self.is_paused and not self.should_stop:
                time.sleep(0.1)
            
            if self.should_stop:
                break
            
            # Get next test case from algorithm
            test_case = self.algorithm.get_next_test_case(self._selected_questions)
            if test_case is None:
                # Algorithm completed or exhausted
                if self.callbacks:
                    self.callbacks.on_status_message("Algorithm completed - no more test cases to run")
                break
            
            # Validate test case
            validation_error = self.test_executor.validate_test_case(test_case, self.config)
            if validation_error:
                if self.callbacks:
                    self.callbacks.on_status_message(f"Skipping invalid test case: {validation_error}")
                continue
            
            # Execute test case
            result = self.test_executor.execute_test_case(test_case, self.config)
            
            # Handle result
            if result.success:
                consecutive_failures = 0
                
                # Update algorithm with result
                self.algorithm.update_with_result(test_case, result)
                
                # Save result to database
                self.database.save_test_result(test_case, result)
                
                # Update best score tracking
                if result.score and result.score > self.best_score:
                    self.best_score = result.score
                    self.best_parameters = test_case.parameters.copy()
                
                # Update progress
                test_count += 1
                self.completed_tests += 1
                
                # Get progress stats from algorithm
                progress_stats = self.algorithm.get_progress_stats()
                
                # Callback updates
                if self.callbacks:
                    self.callbacks.on_progress_update(
                        current=test_count,
                        total=progress_stats.total_estimated if progress_stats.total_estimated > 0 else test_count + 100,
                        message=progress_stats.current_message
                    )
                    self.callbacks.on_test_result(result)
                
                # Periodic metadata save (crash-safe)
                if test_count % 10 == 0:
                    self._update_progress_metadata()
                    
            else:
                # Handle failure (count toward progress to avoid outer loops stalling)
                consecutive_failures += 1

                # Increment counters even on failure so budget-based loops can progress
                test_count += 1
                self.completed_tests += 1

                if self.callbacks:
                    msg = result.error_message or "Unknown error"
                    self.callbacks.on_status_message(f"Test failed: {msg}")
                    # Emit a progress update on failure to reflect movement
                    try:
                        self.callbacks.on_progress_update(
                            current=test_count,
                            total=test_count + 100,
                            message="failure"
                        )
                    except Exception:
                        pass

                # Stop if too many consecutive failures
                if consecutive_failures >= max_consecutive_failures:
                    error_msg = f"Stopping optimization after {max_consecutive_failures} consecutive failures"
                    if self.callbacks:
                        self.callbacks.on_status_message(error_msg)
                    raise OptimizationError(error_msg)
        
        # Final progress update
        if self.callbacks:
            progress_stats = self.algorithm.get_progress_stats()
            self.callbacks.on_progress_update(
                current=test_count,
                total=test_count,  # Set total = current for 100% completion
                message=f"Optimization completed: {test_count} tests executed"
            )
    
    def _update_progress_metadata(self) -> None:
        """Update progress in metadata (crash-safe periodic save)"""
        self.database.update_progress(
            completed_combinations=self.completed_tests,
            best_score=self.best_score if self.best_score > 0 else None,
            best_parameters=self.best_parameters if self.best_parameters else None
        )
    
    def _complete_optimization(self, status: str, error_message: str = None) -> None:
        """Complete optimization and send final callbacks"""
        self.end_time = datetime.now().isoformat()
        self.is_running = False
        
        # Calculate runtime
        if self.start_time:
            start_dt = datetime.fromisoformat(self.start_time)
            end_dt = datetime.fromisoformat(self.end_time)
            runtime_seconds = (end_dt - start_dt).total_seconds()
        else:
            runtime_seconds = 0.0
        
        # Final metadata save
        final_metadata = RunMetadata(
            run_name=self.config.run_name,
            algorithm=self.config.algorithm,
            start_time=self.start_time,
            status=status,
            dataset_path=self.config.dataset_path,
            selected_questions=self.config.questions,
            total_questions=len(self.config.questions),
            endpoint_type=self.config.endpoint_type,
            total_combinations=None,
            completed_combinations=self.completed_tests,
            best_score=self.best_score if self.best_score > 0 else None,
            best_parameters=self.best_parameters if self.best_parameters else None,
            end_time=self.end_time,
            error_message=error_message,
            api_config_path=getattr(self.config, 'api_config_path', None),
            server_config_path=getattr(self.config, 'server_config_path', None)
        )
        self.database.save_run_metadata(final_metadata)
        
        # Create optimization summary
        summary = OptimizationSummary(
            run_name=self.config.run_name,
            algorithm=self.config.algorithm,
            start_time=self.start_time,
            end_time=self.end_time,
            total_runtime_seconds=runtime_seconds,
            completed_tests=self.completed_tests,
            total_tests=None,  # Dynamic algorithms don't have fixed totals
            best_score=self.best_score,
            best_parameters=self.best_parameters,
            status=status,
            error_message=error_message
        )
        
        # Final callback
        if self.callbacks:
            if status == "error":
                self.callbacks.on_optimization_error(Exception(error_message))
            else:
                self.callbacks.on_optimization_complete(summary)
        
        # Cleanup
        if self.database:
            self.database.close()
    
    def _create_run_directory(self) -> Path:
        """Create or reuse a run directory"""
        # When resuming, reuse the provided run directory if available
        if getattr(self, 'resume_run_directory', None):
            run_directory = Path(self.resume_run_directory)
            run_directory.mkdir(parents=True, exist_ok=True)
            return run_directory

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_run_name = "".join(c for c in self.config.run_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_run_name = safe_run_name.replace(' ', '_') or "unnamed_run"
        
        run_dir_name = f"{safe_run_name}_{timestamp}"
        run_directory = app_paths.aco_runs / run_dir_name
        
        run_directory.mkdir(parents=True, exist_ok=True)
        return run_directory
    
    def pause_optimization(self) -> None:
        """Pause the running optimization"""
        if not self.is_running:
            return
        
        self.is_paused = True
        
        if self.callbacks:
            self.callbacks.on_status_message("Optimization paused")
    
    def resume_optimization(self) -> None:
        """Resume the paused optimization"""
        if not self.is_running:
            return
        
        self.is_paused = False
        
        if self.callbacks:
            self.callbacks.on_status_message("Optimization resumed")
    
    def stop_optimization(self) -> None:
        """Stop the running optimization"""
        self.should_stop = True
        self.is_paused = False
        
        if self.callbacks:
            self.callbacks.on_status_message("Stopping optimization...")
        
        # Wait for optimization thread to complete
        if self.optimization_thread and self.optimization_thread.is_alive():
            self.optimization_thread.join(timeout=5.0)  # Wait max 5 seconds
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current optimization status"""
        if not self.is_running and not hasattr(self, 'completed_tests'):
            return {"status": "not_started"}
        
        status_info = {
            "status": "running" if self.is_running else "completed",
            "is_paused": self.is_paused,
            "completed_tests": getattr(self, 'completed_tests', 0),
            "best_score": getattr(self, 'best_score', 0.0),
            "best_parameters": getattr(self, 'best_parameters', {}),
            "algorithm": self.config.algorithm if self.config else "Unknown",
            "start_time": getattr(self, 'start_time', None),
            "end_time": getattr(self, 'end_time', None)
        }
        
        # Add algorithm-specific stats if available
        if self.algorithm and hasattr(self.algorithm, 'get_progress_stats'):
            try:
                progress_stats = self.algorithm.get_progress_stats()
                status_info["algorithm_stats"] = {
                    "current_phase": progress_stats.current_phase,
                    "total_estimated": progress_stats.total_estimated,
                    "algorithm_specific": progress_stats.algorithm_specific_info
                }
            except Exception:
                pass  # Algorithm stats not available
        
        return status_info
    
    def _validate_config(self, config: OptimizationConfig) -> None:
        """Validate optimization configuration"""
        if not config.run_name:
            raise ValidationError("Run name is required")
        
        if not config.dataset_path:
            raise ValidationError("Dataset path is required")
        
        if not config.questions:
            raise ValidationError("At least one question must be selected")
        
        if not config.parameter_arrays:
            raise ValidationError("At least one parameter array must be defined")
        
        if config.algorithm not in AlgorithmFactory.get_available_algorithms():
            available = ", ".join(AlgorithmFactory.get_available_algorithms())
            raise ValidationError(f"Unknown algorithm '{config.algorithm}'. Available: {available}")
        
        # Validate parameter arrays have values
        for param_name, param_info in config.parameter_arrays.items():
            if not param_info.values:
                raise ValidationError(f"Parameter '{param_name}' has no values defined")
    
    @staticmethod
    def get_available_runs() -> List[Dict[str, Any]]:
        """Get list of available optimization runs"""
        available_runs = []
        aco_runs_dir = app_paths.aco_runs
        
        if not aco_runs_dir.exists():
            return available_runs
        
        for run_dir in aco_runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            try:
                # Try to load database and metadata
                db = SQLiteOptimizationDatabase(run_dir)
                metadata = db.load_run_metadata()
                # Note: do not call db methods after closing
                
                if metadata:
                    run_summary = {
                        "directory": str(run_dir),
                        "name": metadata.run_name,
                        "algorithm": metadata.algorithm,
                        "status": metadata.status,
                        "start_time": metadata.start_time,
                        "completed_tests": metadata.completed_combinations,
                        "best_score": metadata.best_score,
                        "dataset_name": Path(metadata.dataset_path).name if metadata.dataset_path else "Unknown",
                        "can_resume": metadata.status in ["running", "paused"]
                    }
                    
                    available_runs.append(run_summary)
                
                # Close DB after reading
                db.close()
                    
            except Exception as e:
                # Skip invalid runs
                continue
        
        # Sort by start time (most recent first)
        available_runs.sort(key=lambda x: x["start_time"], reverse=True)
        return available_runs
