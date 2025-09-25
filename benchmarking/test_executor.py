"""
Unified test execution engine for ACO optimization.

This module consolidates all test execution logic into a single,
clean implementation, eliminating code duplication across the old system.
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from utils.logger import logger

from .interfaces import TestCase, TestResult, OptimizationConfig, OptimizationError
from .scorer import FlexibleScorer


class TestExecutor:
    """
    Single unified test execution engine for all optimization algorithms.
    
    This class consolidates all the duplicate API execution logic from the old
    system into one clean, maintainable implementation.
    """
    
    def __init__(self, benchmark_executor):
        """
        Initialize test executor with benchmark executor dependency.
        
        Args:
            benchmark_executor: BenchmarkExecutor instance for API calls
        """
        self.benchmark_executor = benchmark_executor
        self.scorer = FlexibleScorer()
    
    def execute_test_case(self, test_case: TestCase, config: OptimizationConfig) -> TestResult:
        """
        Execute a single test case and return comprehensive results.
        
        This is the single execution path for ALL optimization algorithms,
        eliminating the previous duplicate execution methods.
        
        Args:
            test_case: Test case to execute
            config: Optimization configuration
            
        Returns:
            TestResult with success status and detailed results
        """
        try:
            # 1. Create modified API config with test case parameters
            modified_api_config = self._create_modified_api_config(config.api_config, test_case.parameters)
            
            # 2. Execute API call using appropriate endpoint
            success, response, response_time, slots_data, full_response = self._execute_api_call(
                test_case.question, modified_api_config, config.server_config, config.endpoint_type
            )
            
            if success:
                # 3. Score the response using unified scorer
                ground_truth = test_case.question.get('ground_truth', '')
                score = self.scorer.score_answer(ground_truth, response, scoring_mode='EXACT')
                
                # 4. Create successful result
                result = TestResult(
                    test_case=test_case,
                    success=True,
                    response=response,
                    score=score,
                    response_time=response_time,
                    slots_data=slots_data,
                    full_api_response=full_response,
                    timestamp=datetime.now().isoformat()
                )
                
                # Update test case with results (for database storage)
                test_case.response = response
                test_case.score = score
                test_case.response_time = response_time
                test_case.timestamp = result.timestamp
                
                return result
            else:
                # 5. Handle API call failure
                return TestResult(
                    test_case=test_case,
                    success=False,
                    error_message=f"API call failed: {response}",
                    timestamp=datetime.now().isoformat()
                )
                
        except Exception as e:
            # 6. Handle execution exception
            return TestResult(
                test_case=test_case,
                success=False,
                error_message=f"Execution error: {str(e)}",
                timestamp=datetime.now().isoformat()
            )
    
    def _create_modified_api_config(self, base_api_config, parameters: Dict[str, Any]):
        """
        Create modified API config with test case parameters.
        
        This consolidates the parameter application logic that was
        duplicated across multiple methods in the old system.
        """
        # Create a copy of the base config
        modified_config = type(base_api_config)()
        modified_config.schema = base_api_config.schema
        modified_config.values = base_api_config.values.copy()
        modified_config.enabled = base_api_config.enabled.copy()
        
        # Apply test case parameters with proper type handling
        for param_name, value in parameters.items():
            # Get parameter type info for proper processing
            param_info = base_api_config.get_parameter_info(param_name)
            param_type = param_info.get("type", "string")
            
            if param_type == "object":
                # Handle JSON object parameters (like chat_template_kwargs)
                if value is not None and isinstance(value, str) and value.strip():
                    try:
                        # Parse JSON string to object
                        parsed_object = json.loads(value)
                        modified_config.values[param_name] = parsed_object
                    except json.JSONDecodeError as e:
                        # Keep as string if JSON parsing fails (transparency principle)
                        logger.warning(f"Failed to parse JSON for {param_name}: {e}")
                        modified_config.values[param_name] = value
                else:
                    modified_config.values[param_name] = value
            else:
                # For non-object parameters, use value as-is
                modified_config.values[param_name] = value
            
            # Enable the parameter
            modified_config.enabled[param_name] = True
        
        return modified_config
    
    def _execute_api_call(self, question: Dict[str, Any], api_config, server_config, endpoint_type: str) -> Tuple[bool, str, float, dict, dict]:
        """
        Execute API call with unified endpoint handling.
        
        This consolidates the endpoint-specific logic that was duplicated
        across the old system.
        
        Returns:
            Tuple of (success, response_text, response_time, slots_data, full_api_response)
        """
        try:
            # Extract question content and system prompt
            question_text = question.get('turns', '')
            # Prefer ACO-specific system prompt, fallback to general system_prompt
            system_prompt = api_config.values.get('system_prompt_aco', api_config.values.get('system_prompt', ''))

            # Build content for unified endpoint call
            if endpoint_type == "completions":
                content = question_text
            else:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if question_text:
                    messages.append({"role": "user", "content": question_text})
                content = messages

            # Normalize parameters for API (align with Run Benchmark expectations)
            params = dict(api_config.values or {})
            try:
                # Ensure samplers is a list (server expects array)
                if 'samplers' in params and isinstance(params['samplers'], str):
                    raw = params['samplers']
                    params['samplers'] = [s.strip() for s in raw.split(',') if s.strip()]
            except Exception:
                pass

            # Single unified call
            success, response_data = self.benchmark_executor.api_client.unified_completion(
                endpoint_type, content, params
            )
            
            if success:
                # Extract response text based on endpoint type
                if endpoint_type == "completions":
                    response_text = response_data['choices'][0]['text']
                else:
                    response_text = response_data['choices'][0]['message']['content']
                
                # Extract response time
                response_time = response_data.get('response_time', 0.0)
                
                # Fetch /slots data for server state information
                slots_data = {}
                try:
                    slots_raw = self.benchmark_executor.api_client.get_slots_info_raw()
                    if slots_raw:
                        slots_data = json.loads(slots_raw)
                except Exception as e:
                    logger.warning(f"Could not fetch slots data: {e}")
                
                return True, response_text, response_time, slots_data, response_data
            else:
                # API call failed
                error_msg = response_data.get('error', 'Unknown API error')
                return False, str(error_msg), 0.0, {}, {}
                
        except Exception as e:
            return False, f"Exception in API call: {str(e)}", 0.0, {}, {}
    
    def validate_test_case(self, test_case: TestCase, config: OptimizationConfig) -> Optional[str]:
        """
        Validate test case before execution.
        
        Returns:
            None if valid, error message string if invalid
        """
        # Check if question has required fields
        if not test_case.question:
            return "Test case missing question data"
        
        if 'turns' not in test_case.question:
            return "Question missing 'turns' field"
        
        if 'ground_truth' not in test_case.question:
            return "Question missing 'ground_truth' field"
        
        # Check if parameters are valid
        if not test_case.parameters:
            return "Test case missing parameters"
        
        # Validate parameter names against config
        for param_name in test_case.parameters:
            if param_name not in config.parameter_arrays:
                return f"Unknown parameter '{param_name}' in test case"
        
        return None  # Valid
    
    def batch_execute_test_cases(self, test_cases: List[TestCase], config: OptimizationConfig, 
                                progress_callback: Optional[callable] = None) -> List[TestResult]:
        """
        Execute multiple test cases in batch with progress tracking.
        
        This provides an efficient way to execute multiple test cases
        while providing progress feedback.
        
        Args:
            test_cases: List of test cases to execute
            config: Optimization configuration
            progress_callback: Optional callback for progress updates (current, total, message)
            
        Returns:
            List of test results in same order as input
        """
        results = []
        total_cases = len(test_cases)
        
        for i, test_case in enumerate(test_cases):
            # Progress callback
            if progress_callback:
                progress_callback(i, total_cases, f"Executing test case {i+1}/{total_cases}")
            
            # Execute test case
            result = self.execute_test_case(test_case, config)
            results.append(result)
            
            # Final progress callback
            if progress_callback:
                progress_callback(i+1, total_cases, f"Completed test case {i+1}/{total_cases}")
        
        return results
    
    def get_execution_summary(self, results: List[TestResult]) -> Dict[str, Any]:
        """
        Generate summary statistics from test results.
        
        Args:
            results: List of test results to summarize
            
        Returns:
            Dictionary with execution summary statistics
        """
        if not results:
            return {
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
                "average_score": 0.0,
                "average_response_time": 0.0,
                "error_rate": 0.0
            }
        
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        scored_results = [r for r in successful_results if r.score is not None]
        
        # Calculate statistics
        total_tests = len(results)
        successful_tests = len(successful_results)
        failed_tests = len(failed_results)
        
        average_score = sum(r.score for r in scored_results) / len(scored_results) if scored_results else 0.0
        
        timed_results = [r for r in successful_results if r.response_time is not None]
        average_response_time = sum(r.response_time for r in timed_results) / len(timed_results) if timed_results else 0.0
        
        error_rate = (failed_tests / total_tests) * 100 if total_tests > 0 else 0.0
        
        return {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": (successful_tests / total_tests) * 100 if total_tests > 0 else 0.0,
            "error_rate": error_rate,
            "average_score": average_score,
            "average_response_time": average_response_time,
            "score_distribution": self._calculate_score_distribution(scored_results),
            "common_errors": self._extract_common_errors(failed_results)
        }
    
    def _calculate_score_distribution(self, scored_results: List[TestResult]) -> Dict[str, int]:
        """Calculate distribution of scores"""
        distribution = {
            "perfect_1.0": 0,
            "high_0.8-0.99": 0, 
            "medium_0.5-0.79": 0,
            "low_0.1-0.49": 0,
            "zero_0.0": 0
        }
        
        for result in scored_results:
            if result.score == 1.0:
                distribution["perfect_1.0"] += 1
            elif result.score >= 0.8:
                distribution["high_0.8-0.99"] += 1
            elif result.score >= 0.5:
                distribution["medium_0.5-0.79"] += 1
            elif result.score > 0.0:
                distribution["low_0.1-0.49"] += 1
            else:
                distribution["zero_0.0"] += 1
        
        return distribution
    
    def _extract_common_errors(self, failed_results: List[TestResult]) -> List[Dict[str, Any]]:
        """Extract and count common error patterns"""
        error_counts = {}
        
        for result in failed_results:
            error_msg = result.error_message or "Unknown error"
            
            # Simplify error message for grouping
            if "timeout" in error_msg.lower():
                simplified = "API timeout"
            elif "connection" in error_msg.lower():
                simplified = "Connection error"
            elif "json" in error_msg.lower():
                simplified = "JSON parsing error" 
            elif "server" in error_msg.lower():
                simplified = "Server error"
            else:
                simplified = "Other error"
            
            error_counts[simplified] = error_counts.get(simplified, 0) + 1
        
        # Convert to list sorted by frequency
        common_errors = [
            {"error_type": error_type, "count": count, "percentage": (count / len(failed_results)) * 100}
            for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        
        return common_errors[:5]  # Top 5 most common errors
