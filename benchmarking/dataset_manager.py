"""
Benchmark Dataset Module
Handles HuggingFace dataset loading, navigation, and export functionality
Now with intelligent caching for fast startup and complete dataset support
"""

import os
import json
from typing import Dict, Any, List, Tuple, Optional, Callable
from datetime import datetime
from .cache_manager import CacheManager
from .dataset_loader import CompleteDatasetLoader
from utils.logger import logger


class HuggingFaceLoader:
    """Handles HuggingFace dataset loading with intelligent caching"""
    
    # Field name constants
    FIELD_NAMES = {
        'SUBCATEGORY': 'subcategory',
        'TASK': 'task',
        'TASK_TYPE': 'task_type', 
        'CATEGORY': 'category',
        'CATEGORY_DETAIL': 'category_detail',
        'QUESTION_ID': 'question_id',
        'GROUND_TRUTH': 'ground_truth',
        'TURNS': 'turns',
        'SPLIT_TEST': 'test',
        'ALL_FILTER': 'all'
    }
    
    def __init__(self, cache_manager: CacheManager, progress_callback: Callable = None):
        # Initialize cache and dataset loader
        self.cache_manager = cache_manager
        self.dataset_loader = CompleteDatasetLoader(self.cache_manager, progress_callback)
        
        # Lazy load HuggingFace dependencies - only import when actually needed
        self.load_dataset = None
        self._huggingface_checked = False
    
    def _ensure_huggingface_loaded(self):
        """Lazy load HuggingFace dependencies when first needed"""
        if not self._huggingface_checked:
            try:
                from datasets import load_dataset
                self.load_dataset = load_dataset
            except ImportError:
                raise ImportError("Missing required dependency: datasets. Please install with: pip install datasets")
            
            try:
                import huggingface_hub
            except ImportError:
                raise ImportError("Missing required dependency: huggingface_hub. Please install with: pip install huggingface_hub")
            
            self._huggingface_checked = True
    
    def get_available_categories(self) -> List[str]:
        """Get list of available LiveBench categories from cache"""
        # Use cached categories for fast startup
        categories = self.dataset_loader.get_categories()
        
        if not categories:
            # No cache available - return empty list
            # User will need to click "Load Dataset" to populate
            return []
        
        return categories
    
    def load_category_questions(self, category: str, subcategory: str = "all") -> Tuple[List[dict], Dict]:
        """
        Load all available questions for category/subcategory using HuggingFace
        Ported from reference implementation
        
        Args:
            category: Main LiveBench category (reasoning, math, etc.)
            subcategory: Optional subcategory filter ("all" for no filter)
            
        Returns:
            Tuple of (questions_list, metadata_dict)
        """
        # Ensure HuggingFace is loaded before using it
        self._ensure_huggingface_loaded()
        
        try:
            # Build dataset name dynamically
            dataset_name = f"livebench/{category}"
            
            logger.info(f"Loading {dataset_name} from HuggingFace...")
            
            # Load full category dataset
            ds = self.load_dataset(dataset_name, split=self.FIELD_NAMES['SPLIT_TEST'])
            
            # Convert to list of dictionaries
            questions_list = []
            for item in ds:
                questions_list.append(dict(item))
            
            logger.info(f"Loaded {len(questions_list)} questions from {category}")
            
            # Filter by subcategory if specified
            if subcategory and subcategory != self.FIELD_NAMES['ALL_FILTER']:
                original_count = len(questions_list)
                subcategory_fields = [self.FIELD_NAMES['SUBCATEGORY'], self.FIELD_NAMES['TASK'], 
                                      self.FIELD_NAMES['TASK_TYPE'], self.FIELD_NAMES['CATEGORY_DETAIL']]
                
                filtered_questions = []
                for question in questions_list:
                    for field in subcategory_fields:
                        if field in question and question[field] == subcategory:
                            filtered_questions.append(question)
                            break
                
                questions_list = filtered_questions
                logger.info(f"Filtered to {len(questions_list)} questions for subcategory '{subcategory}'")
            
            # Build metadata
            metadata = {
                self.FIELD_NAMES['CATEGORY']: category,
                self.FIELD_NAMES['SUBCATEGORY']: subcategory,
                'total_questions': len(questions_list),
                'dataset_name': dataset_name,
                'loaded_at': datetime.now().isoformat()
            }
            
            # Extract subcategories for metadata
            if len(questions_list) > 0:
                subcategories = set()
                for question in questions_list:
                    for field in [self.FIELD_NAMES['SUBCATEGORY'], self.FIELD_NAMES['TASK'], self.FIELD_NAMES['TASK_TYPE']]:
                        if field in question and question[field]:
                            subcategories.add(question[field])
                metadata['available_subcategories'] = sorted(list(subcategories))
            
            return questions_list, metadata
            
        except Exception as e:
            logger.error(f"Error loading category {category}: {e}")
            return [], {'error': str(e), self.FIELD_NAMES['CATEGORY']: category}
    
    def get_subcategories(self, category: str) -> List[str]:
        """Get available subcategories for a category from cache"""
        # Use cached subcategories for fast startup
        subcategories = self.dataset_loader.get_subcategories(category)
        
        if not subcategories:
            # No cache available - return empty list
            # User will need to click "Load Dataset" to populate
            return []
        
        return subcategories
    
    def load_complete_dataset(self) -> bool:
        """Load complete dataset metadata and build cache"""
        try:
            self.dataset_loader.load_complete_dataset_metadata()
            return True
        except Exception as e:
            logger.error(f"Error loading complete dataset: {e}")
            return False
    
    def has_cache(self) -> bool:
        """Check if we have cached data available"""
        return self.dataset_loader.has_valid_cache()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the cache"""
        return self.dataset_loader.get_cache_info()


class QuestionDisplayManager:
    """Handles question text extraction and ground truth display - ported from reference implementation"""
    
    # Field name constants (shared with HuggingFaceLoader)
    FIELD_NAMES = HuggingFaceLoader.FIELD_NAMES
    
    def extract_question_text(self, row: Dict[str, Any]) -> str:
        """
        Extract question text from dataset row
        Ported from reference implementation
        """
        question_text = ""
        
        # Primary method: Extract from 'turns' field (nested array structure)
        if self.FIELD_NAMES['TURNS'] in row:
            turns_data = row[self.FIELD_NAMES['TURNS']]
            if hasattr(turns_data, '__len__') and len(turns_data) > 0:
                # Handle nested list structure and extract clean text
                raw_text = turns_data[0]  # Get first element
                if isinstance(raw_text, list) and len(raw_text) > 0:
                    raw_text = raw_text[0]  # Handle deeper nesting
                
                # Clean the text
                if raw_text:
                    raw_text = str(raw_text).strip('\'"[]')  # Strip quotes and brackets
                    question_text = raw_text.replace('\\n', '\n')  # Convert escaped newlines
        
        # Fallback to other question fields if turns doesn't work
        if not question_text:
            question_fields = ['question', 'input', 'prompt', 'query', 'problem', 'text']
            for field in question_fields:
                if field in row and row[field]:
                    question_text = str(row[field])
                    break
        
        if not question_text:
            question_text = "Question text not available"
        
        return question_text
    
    def extract_ground_truth(self, row: Dict[str, Any]) -> str:
        """
        Extract ground truth answer from dataset row
        Ported from reference implementation
        """
        category = (row.get(self.FIELD_NAMES['CATEGORY'], '') or '').lower()
        answer_text = ""
        
        if category == 'coding':
            # Show test cases for coding category
            if 'public_test_cases' in row and row['public_test_cases']:
                try:
                    public_tests = row['public_test_cases']
                    if isinstance(public_tests, str):
                        test_cases = json.loads(public_tests)
                    else:
                        test_cases = public_tests
                    
                    answer_text = "Test Cases (Deterministic Evaluation):\n\n"
                    for i, test in enumerate(test_cases):
                        input_val = test.get('input', 'N/A')
                        output_val = test.get('output', 'N/A')
                        answer_text += f"* Test {i+1}: Input={input_val} -> Expected={output_val}\n"
                    
                    # Add note about private test cases if they exist
                    if 'private_test_cases' in row and row['private_test_cases']:
                        try:
                            private_count = len(row['private_test_cases']) if isinstance(row['private_test_cases'], list) else 1
                            answer_text += f"\n(+ {private_count} private test cases)"
                        except:
                            answer_text += "\n(+ private test cases available)"
                            
                except Exception as e:
                    answer_text = f"Error parsing test cases: {e}"
            else:
                answer_text = "No test cases available"
                
        elif category == 'instruction_following':
            # Special handling for instruction following
            answer_text = "Ground Truth: LLM Judge Required\n\n"
            answer_text += "This category requires automated LLM judging for evaluation.\n"
            answer_text += "Expected behavior/criteria will be defined in judging prompts."
            
        else:
            # Standard answer extraction for other categories
            answer_fields = ['answer', 'expected_answer', self.FIELD_NAMES['GROUND_TRUTH'], 'target', 'solution', 'correct_answer']
            for field in answer_fields:
                if field in row and row[field] is not None:
                    answer_text = str(row[field])
                    break
            
            if not answer_text:
                answer_text = "Ground truth not available"
        
        return answer_text


class BenchmarkDataset:
    """Main benchmark dataset class - coordinates all functionality following current architecture"""
    
    # Field name constants (shared)
    FIELD_NAMES = HuggingFaceLoader.FIELD_NAMES
    
    def __init__(self, cache_manager: CacheManager, progress_callback: Callable = None):
        # Initialize components with shared cache and progress callback support
        self.hf_loader = HuggingFaceLoader(cache_manager, progress_callback)
        self.display_manager = QuestionDisplayManager()
        
        # Current dataset state
        self.current_dataset = []
        self.current_metadata = {}
        self.current_question_index = 0
        
        # Use centralized path management for exported datasets
        from managers.path_manager import app_paths
        self.output_dir = str(app_paths.exported_datasets)
        os.makedirs(self.output_dir, exist_ok=True)
    
    def get_available_categories(self) -> List[str]:
        """Get list of available LiveBench categories"""
        return self.hf_loader.get_available_categories()
    
    def get_subcategories(self, category: str) -> List[str]:
        """Get available subcategories for a category"""
        return self.hf_loader.get_subcategories(category)
    
    def load_complete_dataset_cache(self) -> bool:
        """Load complete dataset metadata and build cache (called by 'Load Dataset' button)"""
        # Always clear any stale on-disk cache so users get fresh, correct categories
        try:
            self.hf_loader.cache_manager.clear_cache()
        except Exception:
            pass
        return self.hf_loader.load_complete_dataset()
    
    def has_cached_data(self) -> bool:
        """Check if we have cached dataset metadata"""
        return self.hf_loader.has_cache()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache"""
        return self.hf_loader.get_cache_info()
    
    def load_dataset(self, category: str, subcategory: str = "all") -> bool:
        """Load dataset for browsing and conversion"""
        try:
            self.current_dataset, self.current_metadata = self.hf_loader.load_category_questions(category, subcategory)
            self.current_question_index = 0
            
            if len(self.current_dataset) == 0:
                logger.warning(f"No questions found for category '{category}' subcategory '{subcategory}'")
                return False
            
            logger.info(f"Successfully loaded {len(self.current_dataset)} questions")
            return True
            
        except Exception as e:
            logger.error(f"Error loading dataset: {e}")
            return False
    
    def get_current_question_display(self) -> Tuple[str, str]:
        """Get current question and ground truth for display"""
        if not self.current_dataset or self.current_question_index >= len(self.current_dataset):
            return "No dataset loaded", "Load a dataset to see ground truth"
        
        row = self.current_dataset[self.current_question_index]
        question_text = self.display_manager.extract_question_text(row)
        ground_truth = self.display_manager.extract_ground_truth(row)
        
        return question_text, ground_truth
    
    def navigate_to_question(self, question_number: int) -> bool:
        """Navigate to specific question number (1-based)"""
        if not self.current_dataset:
            return False
        
        index = question_number - 1
        if 0 <= index < len(self.current_dataset):
            self.current_question_index = index
            return True
        return False
    
    def get_navigation_info(self) -> Dict[str, Any]:
        """Get current navigation state info"""
        return {
            'current_question': self.current_question_index + 1 if self.current_dataset else 0,
            'total_questions': len(self.current_dataset),
            self.FIELD_NAMES['CATEGORY']: self.current_metadata.get(self.FIELD_NAMES['CATEGORY'], 'Unknown'),
            self.FIELD_NAMES['SUBCATEGORY']: self.current_metadata.get(self.FIELD_NAMES['SUBCATEGORY'], self.FIELD_NAMES['ALL_FILTER'])
        }
    
    def export_to_text(self, output_filename: str = None, question_range: Optional[str] = None) -> Tuple[str, int]:
        """
        Export current dataset to text format matching reference implementation
        Returns (path, exported_count)
        """
        if not self.current_dataset:
            raise ValueError("No dataset loaded to export")
        
        # Determine subset to export
        selected_indices: List[int] = []
        total_q = len(self.current_dataset)
        
        def _parse_range_text(rng: str, total: int) -> List[int]:
            s = (rng or '').strip().lower()
            if not s or s == 'all':
                return list(range(1, total + 1))
            result: List[int] = []
            for part in s.split(','):
                part = part.strip()
                if not part:
                    continue
                if '-' in part:
                    try:
                        a, b = part.split('-', 1)
                        a = int(a.strip()); b = int(b.strip())
                        if a < 1 or b > total or a > b:
                            raise ValueError
                        result.extend(range(a, b + 1))
                    except Exception:
                        raise ValueError(f"Invalid range: '{part}'")
                else:
                    try:
                        n = int(part)
                        if n < 1 or n > total:
                            raise ValueError
                        result.append(n)
                    except Exception:
                        raise ValueError(f"Invalid question number: '{part}'")
            # unique + sorted
            return sorted(set(result))
        
        selected_indices = _parse_range_text(question_range or 'all', total_q)
        if not selected_indices:
            raise ValueError("No questions selected for export")
        
        # Build the selected subset in order
        subset = [self.current_dataset[i - 1] for i in selected_indices]
        
        # Generate filename if not provided
        if not output_filename:
            category = self.current_metadata.get(self.FIELD_NAMES['CATEGORY'], 'unknown')
            subcategory = self.current_metadata.get(self.FIELD_NAMES['SUBCATEGORY'], self.FIELD_NAMES['ALL_FILTER'])
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{category}_{subcategory}_{timestamp}.txt"
        
        # Ensure .txt extension
        if not output_filename.endswith('.txt'):
            output_filename += '.txt'
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Create text content matching reference implementation format
        text_content = "COMPLETE DATASET VIEW:\n"
        text_content += "=" * 50 + "\n\n"
        text_content += f"Total Rows: {len(subset)}\n"
        text_content += f"Category: {self.current_metadata.get(self.FIELD_NAMES['CATEGORY'], 'unknown')}\n"
        text_content += f"Subcategory: {self.current_metadata.get(self.FIELD_NAMES['SUBCATEGORY'], self.FIELD_NAMES['ALL_FILTER'])}\n"
        text_content += f"Source Dataset: {self.current_metadata.get('dataset_name', 'unknown')}\n"
        text_content += f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # Add each question in reference format
        for idx, row in enumerate(subset):
            question_text = self.display_manager.extract_question_text(row)
            ground_truth = self.display_manager.extract_ground_truth(row)
            
            text_content += f"--- Question {idx + 1} ---\n"
            text_content += f"question_id: {row.get(self.FIELD_NAMES['QUESTION_ID'], f'q_{idx}')}\n"
            text_content += f"category: {row.get(self.FIELD_NAMES['CATEGORY'], self.current_metadata.get(self.FIELD_NAMES['CATEGORY'], 'unknown'))}\n"
            text_content += f"ground_truth: {ground_truth}\n"
            text_content += f"turns: {question_text}\n"
            text_content += f"task: {row.get(self.FIELD_NAMES['TASK'], row.get(self.FIELD_NAMES['SUBCATEGORY'], 'unknown'))}\n"
            
            # Add other fields if available
            if 'livebench_release_date' in row:
                text_content += f"livebench_release_date: {row['livebench_release_date']}\n"
            if 'livebench_removal_date' in row:
                text_content += f"livebench_removal_date: {row['livebench_removal_date']}\n"
            if 'level' in row:
                text_content += f"level: {row['level']}\n"
            
            text_content += "\n"
        
        # Save to text file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text_content)
        
        logger.info(f"Successfully exported {len(subset)} questions to {output_path}")
        return output_path, len(subset)
    
    def get_exported_files(self) -> List[str]:
        """Get list of previously exported text files"""
        try:
            files = [f for f in os.listdir(self.output_dir) if f.endswith('.txt')]
            return sorted(files, reverse=True)  # Most recent first
        except:
            return []
