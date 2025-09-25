"""
Dataset Loader Module
Handles loading complete LiveBench dataset and building cache
"""

import json
from typing import Dict, List, Tuple, Any, Optional, Callable
from .cache_manager import CacheManager
from utils.logger import logger


class CompleteDatasetLoader:
    """Loads complete LiveBench dataset and builds cache"""
    
    def __init__(self, cache_manager: CacheManager, progress_callback: Callable = None):
        self.cache_manager = cache_manager
        self.progress_callback = progress_callback
        
        # Will be set when HuggingFace is loaded
        self.load_dataset = None
        self._huggingface_loaded = False
    
    def _ensure_huggingface_loaded(self):
        """Lazy load HuggingFace dependencies"""
        if not self._huggingface_loaded:
            try:
                from datasets import load_dataset
                self.load_dataset = load_dataset
                
                import huggingface_hub
                self._huggingface_loaded = True
                
            except ImportError as e:
                raise ImportError(f"Missing required dependency: {e}")
    
    def _update_progress(self, message: str, percent: int = None):
        """Update progress callback if provided"""
        if self.progress_callback:
            self.progress_callback(message, percent)
        else:
            logger.info(f"Progress: {message}" + (f" ({percent}%)" if percent else ""))
    
    def discover_categories(self) -> List[str]:
        """Discover the core LiveBench categories for this app.

        Behavior:
        - Restricts discovery to the six canonical categories the UI expects.
        - Verifies each by probing the Hugging Face dataset split.
        - Excludes auxiliary repos like "liveswebench" or "model_*".
        """
        self._ensure_huggingface_loaded()

        # Canonical LiveBench categories supported by the app
        core_categories = [
            'reasoning', 'math', 'coding', 'data_analysis',
            'language', 'instruction_following'
        ]

        verified: List[str] = []
        for category in core_categories:
            try:
                dataset_name = f"livebench/{category}"
                # Probe availability quickly via streaming iterator
                _ = self.load_dataset(dataset_name, split='test', streaming=True)
                verified.append(category)
                logger.info(f"Verified core category: {category}")
            except Exception as e:
                logger.warn(f"Core category unavailable: {category} -> {e}")

        # If none verified (e.g., transient network), fall back to the known list
        if not verified:
            logger.warn("No core categories verified; falling back to default list")
            verified = core_categories

        logger.info(f"Final categories: {verified}")
        return verified
    
    def load_category_metadata(self, category: str) -> Dict[str, Any]:
        """Load metadata for a single category without loading all questions"""
        self._ensure_huggingface_loaded()
        
        try:
            dataset_name = f"livebench/{category}"
            
            # Load the dataset
            ds = self.load_dataset(dataset_name, split='test')
            
            # Extract all questions to get subcategories and count
            questions_list = []
            for item in ds:
                questions_list.append(dict(item))
            
            # Extract unique subcategories
            subcategories = set()
            subcategory_fields = ['subcategory', 'task', 'task_type', 'category_detail']
            
            for question in questions_list:
                for field in subcategory_fields:
                    if field in question and question[field]:
                        subcategories.add(question[field])
            
            return {
                'dataset_name': dataset_name,
                'subcategories': sorted(list(subcategories)),
                'total_questions': len(questions_list),
                'sample_fields': list(questions_list[0].keys()) if questions_list else []
            }
            
        except Exception as e:
            logger.error(f"Error loading metadata for {category}: {e}")
            return {
                'dataset_name': f"livebench/{category}",
                'subcategories': [],
                'total_questions': 0,
                'error': str(e)
            }
    
    def load_complete_dataset_metadata(self) -> Dict[str, Any]:
        """Load metadata for ALL LiveBench categories"""
        self._update_progress("Discovering available categories...")
        
        # Discover categories dynamically
        categories = self.discover_categories()
        
        if not categories:
            raise Exception("No LiveBench categories found")
        
        self._update_progress(f"Found {len(categories)} categories")
        
        # Load metadata for each category
        complete_cache = {'categories': {}}
        
        for i, category in enumerate(categories):
            percent = int((i / len(categories)) * 100)
            self._update_progress(f"Loading {category} metadata...", percent)
            
            category_metadata = self.load_category_metadata(category)
            complete_cache['categories'][category] = category_metadata
            
            # Log progress
            subcats = len(category_metadata.get('subcategories', []))
            questions = category_metadata.get('total_questions', 0)
            logger.info(f"  {category}: {subcats} subcategories, {questions} questions")
        
        self._update_progress("Building cache...", 100)
        
        # Save to cache
        if self.cache_manager.save_cache(complete_cache):
            self._update_progress("Cache saved successfully!")
        else:
            self._update_progress("Warning: Failed to save cache")
        
        return complete_cache
    
    def get_categories(self) -> List[str]:
        """Get categories from cache, or return empty list if no cache"""
        return self.cache_manager.get_categories_from_cache()
    
    def get_subcategories(self, category: str) -> List[str]:
        """Get subcategories from cache, or return empty list if no cache"""
        return self.cache_manager.get_subcategories_from_cache(category)
    
    def has_valid_cache(self) -> bool:
        """Check if we have a valid cache"""
        return self.cache_manager.is_cache_valid()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache"""
        return self.cache_manager.get_cache_stats()
    
    def refresh_cache(self) -> bool:
        """Force refresh of the cache by loading from HuggingFace"""
        try:
            self.load_complete_dataset_metadata()
            return True
        except Exception as e:
            logger.error(f"Error refreshing cache: {e}")
            return False
