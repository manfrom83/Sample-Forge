"""
Benchmark Runner Module
Handles benchmark execution with dataset parsing and enhanced validation
Supports both chat completions and text completions endpoints
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from utils.api_client import LLMClient
from utils.logger import logger


class DatasetParser:
    """Parse exported dataset text files into question objects"""
    
    @staticmethod
    def parse_dataset_file(file_path: str)-> List[Dict[str, Any]]:
        """
        Parse exported dataset text file into question objects
        Expects format: --- Question N ---
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dataset file not found: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8')as f:
            content = f.read()
        
        # Split by question separator
        questions = []
        sections = content.split('--- Question ')
        
        for section in sections[1:]:  # Skip header
            try:
                # Extract question number and content
                parts = section.split(' ---', 1)
                if len(parts)!= 2:
                    continue
                    
                question_num = int(parts[0].strip())
                question_content = parts[1].strip()
                
                # Parse question data
                question_data = DatasetParser._parse_question_section(question_content, question_num)
                questions.append(question_data)
                
            except Exception as e:
                logger.error(f"Error parsing question section: {e}")
                continue
                
        return questions
    
    @staticmethod
    def _parse_question_section(section: str, question_num: int)-> Dict[str, Any]:
        """Parse individual question section"""
        lines = section.strip().split('\n')
        question_data = {
            'question_number': question_num,
            'question_id': None,
            'ground_truth': None,
            'turns': None,
            'category': None,
            'task': None
        }
        
        # Track if we're in multi-line content (like turns)
        in_turns = False
        turns_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            if line_stripped.startswith('question_id:'):
                question_data['question_id'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('category:'):
                question_data['category'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('ground_truth:'):
                question_data['ground_truth'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith('turns:'):
                # Start collecting multi-line turns content
                in_turns = True
                turns_content = line_stripped.split(':', 1)[1].strip()
                if turns_content:  # Add first line if it has content
                    turns_lines.append(turns_content)
            elif line_stripped.startswith('task:'):
                # End of turns, save what we collected
                if in_turns and turns_lines:
                    # Strip trailing empty lines (they're just separators in the dataset)
                    while turns_lines and not turns_lines[-1]:
                        turns_lines.pop()
                    question_data['turns'] = '\n'.join(turns_lines)
                in_turns = False
                question_data['task'] = line_stripped.split(':', 1)[1].strip()
            elif line_stripped.startswith(('livebench_', 'level:')):
                # End of question section
                if in_turns and turns_lines:
                    # Strip trailing empty lines (they're just separators in the dataset)
                    while turns_lines and not turns_lines[-1]:
                        turns_lines.pop()
                    question_data['turns'] = '\n'.join(turns_lines)
                break
            elif in_turns:
                # Continue collecting turns content (preserve blank lines for exact fidelity)
                turns_lines.append(line_stripped)
                
        # Final check - if we ended while still in turns
        if in_turns and turns_lines:
            # Strip trailing empty lines (they're just separators in the dataset)
            while turns_lines and not turns_lines[-1]:
                turns_lines.pop()
            question_data['turns'] = '\n'.join(turns_lines)
            
        # Validate required fields
        if not question_data['question_id']:
            raise ValueError("Missing question_id")
        if not question_data['turns']:
            raise ValueError("Missing turns (question content)")
            
        return question_data


class BenchmarkExecutor:
    """Execute benchmark runs with enhanced parameter validation"""
    
    def __init__(self, api_client: LLMClient):
        self.api_client = api_client
        self.current_run_data = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.current_question_index = 0
        self.run_directory = None
        
    def parse_question_range(self, range_str: str, total_questions: int)-> List[int]:
        """
        Parse question range string into list of question numbers
        Examples: 'all', '1', '1,3,5', '1-10', '1,3,5-10'
        """
        range_str = range_str.strip().lower()
        
        if range_str == 'all':
            return list(range(1, total_questions + 1))
            
        question_numbers = []
        
        # Split by comma
        parts = range_str.split(',')
        
        for part in parts:
            part = part.strip()
            
            # Check if it's a range (contains -)
            if '-' in part:
                try:
                    start, end = part.split('-')
                    start = int(start.strip())
                    end = int(end.strip())
                    
                    # Validate range
                    if start < 1 or end > total_questions or start > end:
                        raise ValueError(f"Invalid range: {start}-{end}")
                        
                    question_numbers.extend(range(start, end + 1))
                except Exception:
                    raise ValueError(f"Invalid range format: {part}")
            else:
                # Single number
                try:
                    num = int(part.strip())
                    if num < 1 or num > total_questions:
                        raise ValueError(f"Question number {num} out of range (1-{total_questions})")
                    question_numbers.append(num)
                except ValueError:
                    raise ValueError(f"Invalid question number: {part}")
                    
        # Remove duplicates and sort
        question_numbers = sorted(list(set(question_numbers)))
        
        return question_numbers
    
    def _create_run_directory(self, run_name: str)-> str:
        """Create directory for benchmark run"""
        from managers.path_manager import app_paths
        base_dir = str(app_paths.benchmark_runs)
        os.makedirs(base_dir, exist_ok=True)
        
        run_dir = os.path.join(base_dir, run_name)
        os.makedirs(run_dir, exist_ok=True)
        
        return run_dir
    
    
    def run_benchmark_enhanced(self, dataset_path: str, config_data: Dict, 
                              selected_questions: List[int], run_name: str,
                              system_prompt: str = "", server_config_path: str = None, api_config_path: str = None,
                              progress_callback=None, detailed_progress_callback=None, per_question_callback=None,
                              system_prompt_override_enabled: bool = False, system_prompt_override_text: str = "",
                              system_prefix: str = "", system_suffix: str = "",
                              user_prefix: str = "", user_suffix: str = "", endpoint_type: str = "chat_completions")-> Dict[str, Any]:
        """
        Enhanced benchmark execution with parameter validation and JSONL saving
        
        Args:
            dataset_path: Path to exported dataset text file
            config_data: Configuration dictionary (not file path)
            selected_questions: List of question numbers to run
            run_name: Name for this benchmark run
            system_prompt: System prompt from API config (will be overridden if override_enabled=True)
            server_config_path: Path to server configuration file for traceability
            api_config_path: Path to API configuration file for traceability
            progress_callback: Function(message)for status updates
            detailed_progress_callback: Function(current, total, details)for progress
            system_prompt_override_enabled: Whether to override system prompt
            system_prompt_override_text: Text to use as system prompt override (if enabled)
            system_prefix: Text to prepend to system prompt
            system_suffix: Text to append to system prompt
            user_prefix: Text to prepend to user input
            user_suffix: Text to append to user input
            endpoint_type: API endpoint type ("chat_completions" or "completions")
            
        Returns:
            Dictionary with run results
        """
        try:
            # Parse dataset
            if progress_callback:
                progress_callback("Loading dataset...")
                
            all_questions = DatasetParser.parse_dataset_file(dataset_path)
            
            # Filter to selected questions
            questions_to_run = []
            for q_num in selected_questions:
                if 1 <= q_num <= len(all_questions):
                    question = all_questions[q_num - 1].copy()
                    question['selected_number'] = q_num
                    questions_to_run.append(question)
                    
            if not questions_to_run:
                raise ValueError("No valid questions selected")
            
            # Create run directory
            self.run_directory = self._create_run_directory(run_name)
            
            # Server is ready - we'll get slots after each API call for validation
            
            # Prepare unified metadata structure - single file with all data
            metadata = {
                'run_info': {
                    'run_name': run_name,
                    'dataset_path': dataset_path,
                    'selected_questions': selected_questions,
                    'total_selected': len(questions_to_run),
                    'start_time': datetime.now().isoformat(),
                    'status': 'running',
                    'server_config_path': server_config_path,
                    'api_config_path': api_config_path,
                    'server_config_name': os.path.basename(server_config_path)if server_config_path else None,
                    'api_config_name': os.path.basename(api_config_path)if api_config_path else None
                },
                'questions': []  # Will store all question data in single structure
            }
            
            # Save initial metadata
            metadata_path = os.path.join(self.run_directory, 'metadata.json')
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Execute questions
            self.is_running = True
            self.is_paused = False
            self.should_stop = False
            self.current_question_index = 0
            
            completed_count = 0
            
            for i, question in enumerate(questions_to_run):
                self.current_question_index = i
                
                # Check for pause/stop
                while self.is_paused and not self.should_stop:
                    time.sleep(0.1)
                    
                if self.should_stop:
                    break
                    
                if progress_callback:
                    progress_callback(f"Processing question {i+1} of {len(questions_to_run)}")
                    
                # Show current question before processing
                if detailed_progress_callback:
                    preview = question['turns'][:50] + "..." if len(question['turns'])> 50 else question['turns']
                    # Pass completed count (i)instead of current question (i+1)
                    detailed_progress_callback(i, len(questions_to_run), 
                                             f"Q{question['selected_number']}: {preview}")
                    
                # Execute single question
                try:
                    start_time = time.time()
                    
                    # UI-level preprocessing: apply system prompt override and prefix/suffix formatting
                    raw_system_prompt = system_prompt_override_text if system_prompt_override_enabled else system_prompt
                    # Preserve whitespace exactly as provided (no .strip())
                    complete_system_prompt = (system_prefix + raw_system_prompt + system_suffix)
                    complete_user_input = (user_prefix + question['turns'] + user_suffix)
                    
                    # Build endpoint content once, then use unified call
                    if endpoint_type == "completions":
                        content = complete_user_input
                    else:
                        messages = []
                        if complete_system_prompt:
                            messages.append({"role": "system", "content": complete_system_prompt})
                        if complete_user_input:
                            messages.append({"role": "user", "content": complete_user_input})
                        content = messages

                    # Single unified client call
                    success, response_data = self.api_client.unified_completion(
                        endpoint_type, content, config_data
                    )
                    
                    end_time = time.time()
                    
                    if not success:
                        # Auto-pause on error for investigation
                        error_msg = f"API Error on Question {question['selected_number']}: {response_data.get('error', 'Unknown error')}"
                        logger.error(f"BENCHMARK ERROR: {error_msg}")
                        
                        self.is_paused = True
                        if progress_callback:
                            progress_callback(f"ERROR: {error_msg} - PAUSED")
                        raise RuntimeError(error_msg)
                    
                    # Get raw slots response after execution
                    raw_slots_response = self.api_client.get_slots_info_raw()
                    
                    # Extract response text from parsed data based on endpoint type
                    response_text = ""
                    if 'choices' in response_data and response_data['choices']:
                        if endpoint_type == "completions":
                            response_text = response_data['choices'][0].get('text', '')
                        else:
                            response_text = response_data['choices'][0].get('message', {}).get('content', '')
                        
                    # Create unified question record with logical field ordering
                    question_record = {
                        # Question identification
                        'q_id': question['selected_number'],
                        'question_id': question['question_id'],
                        
                        # Raw responses - what parameters were used and what we got
                        'raw_slots_response': raw_slots_response or '',
                        'ground_truth': question['ground_truth'],
                        'response': response_text,
                        'raw_completions_response': response_data.get('_raw_server_response', ''),
                        
                        # Classification and timing
                        'category': question.get('category', 'unknown'),
                        'task': question.get('task', 'unknown'),
                        'response_time': end_time - start_time,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Add to unified metadata structure
                    metadata['questions'].append(question_record)
                    
                    # Optional per-question callback for external consumers (e.g., DB import)
                    try:
                        if per_question_callback is not None:
                            per_question_callback(question, question_record)
                    except Exception as cb_e:
                        logger.warning(f"per_question_callback failed: {cb_e}")
                    
                    # Save updated metadata immediately (single file approach)
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2)
                    
                    completed_count += 1
                    logger.info(f"Completed question {question['selected_number']} ({completed_count}/{len(questions_to_run)})")
                    
                    # Update progress after completion
                    if detailed_progress_callback:
                        detailed_progress_callback(completed_count, len(questions_to_run), 
                                                 f"Completed Q{question['selected_number']}")
                    
                except Exception as question_error:
                    # Error handling - auto-pause
                    self.is_paused = True
                    error_msg = f"Failed on question {question['selected_number']}: {question_error}"
                    logger.warning(f"BENCHMARK PAUSED: {error_msg}")
                    
                    # Update metadata with error status
                    metadata['run_info']['status'] = 'paused_on_error'
                    metadata['run_info']['error'] = error_msg
                    metadata['run_info']['paused_at_question'] = i
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2)
                    
                    if progress_callback:
                        progress_callback(f"PAUSED: {error_msg}")
                    
                    raise  # Re-raise to be caught by UI
                    
            # Complete the run
            final_status = 'completed' if completed_count == len(questions_to_run)else 'stopped'
            if self.should_stop:
                final_status = 'stopped'
                
            metadata['run_info']['status'] = final_status
            metadata['run_info']['end_time'] = datetime.now().isoformat()
            metadata['run_info']['completed_questions'] = completed_count
            
            # Save final metadata (single source of truth - no separate summary needed)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            if progress_callback:
                progress_callback(f"Benchmark {final_status}: {completed_count}/{len(questions_to_run)} questions")
                
            return {
                'status': final_status,
                'completed_questions': completed_count,
                'total_questions': len(questions_to_run),
                'run_directory': self.run_directory
            }
            
        except Exception as e:
            self.is_running = False
            logger.error(f"Benchmark execution failed: {e}")
            raise
    
    def pause_benchmark(self):
        """Pause the currently running benchmark"""
        if self.is_running:
            self.is_paused = True
    
    def resume_benchmark(self):
        """Resume a paused benchmark"""
        if self.is_running:
            self.is_paused = False
    
    def stop_benchmark(self):
        """Stop the currently running benchmark"""
        self.should_stop = True
        self.is_running = False
    











