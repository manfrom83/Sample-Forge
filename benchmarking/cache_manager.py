"""
Cache Manager Module
Handles local caching of LiveBench dataset metadata for fast startup
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from managers.path_manager import app_paths
from utils.logger import logger


class CacheManager:
    """Manages local caching of dataset metadata for performance"""
    
    def __init__(self, cache_dir: str = None):
        # Use centralized cache directory from path manager
        if cache_dir is None:
            cache_dir = app_paths.cache
        
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "livebench_metadata.json")
        
        # Memory cache to avoid multiple disk reads
        self._memory_cache = None
        self._cache_loaded = False
        
        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)
    
    def load_cache(self) -> Optional[Dict[str, Any]]:
        """Load cached dataset metadata (with memory caching)"""
        # Return cached data if already loaded
        if self._cache_loaded:
            return self._memory_cache
            
        try:
            if not os.path.exists(self.cache_file):
                self._cache_loaded = True
                self._memory_cache = None
                return None
            
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Validate cache structure
            required_keys = ['metadata', 'categories']
            if not all(key in cache_data for key in required_keys):
                logger.warn("Cache file corrupted - missing required keys")
                self._cache_loaded = True
                self._memory_cache = None
                return None
            
            logger.info(f"Loaded cache with {len(cache_data['categories'])} categories")
            
            # Cache in memory for subsequent calls
            self._memory_cache = cache_data
            self._cache_loaded = True
            return cache_data
            
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self._cache_loaded = True
            self._memory_cache = None
            return None
    
    def save_cache(self, cache_data: Dict[str, Any]) -> bool:
        """Save dataset metadata to cache"""
        try:
            # Add metadata
            cache_data['metadata'] = {
                'last_updated': datetime.now().isoformat(),
                'cache_version': '1.0',
                'total_categories': len(cache_data.get('categories', {}))
            }
            
            # Save to file
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Cache saved with {cache_data['metadata']['total_categories']} categories")
            
            # Update memory cache with new data
            self._memory_cache = cache_data
            self._cache_loaded = True
            return True
            
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False
    
    def is_cache_valid(self, max_age_days: int = 7) -> bool:
        """Check if cache exists and is not too old"""
        cache_data = self.load_cache()
        if not cache_data:
            return False
        
        try:
            last_updated = datetime.fromisoformat(cache_data['metadata']['last_updated'])
            age = datetime.now() - last_updated
            
            is_valid = age <= timedelta(days=max_age_days)
            if not is_valid:
                logger.warn(f"Cache is {age.days} days old, exceeds {max_age_days} day limit")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error checking cache validity: {e}")
            return False
    
    def get_categories_from_cache(self) -> List[str]:
        """Get list of available categories from cache"""
        cache_data = self.load_cache()
        if not cache_data:
            return []
        
        return list(cache_data.get('categories', {}).keys())
    
    def get_subcategories_from_cache(self, category: str) -> List[str]:
        """Get subcategories for a specific category from cache"""
        cache_data = self.load_cache()
        if not cache_data:
            return []
        
        category_data = cache_data.get('categories', {}).get(category, {})
        return category_data.get('subcategories', [])
    
    def get_category_info_from_cache(self, category: str) -> Dict[str, Any]:
        """Get complete information for a category from cache"""
        cache_data = self.load_cache()
        if not cache_data:
            return {}
        
        return cache_data.get('categories', {}).get(category, {})
    
    def clear_cache(self) -> bool:
        """Remove cache file and clear memory cache"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                logger.info("Cache cleared")
            
            # Clear memory cache
            self._memory_cache = None
            self._cache_loaded = False
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache"""
        cache_data = self.load_cache()
        if not cache_data:
            return {'exists': False}
        
        try:
            metadata = cache_data.get('metadata', {})
            categories = cache_data.get('categories', {})
            
            total_subcategories = sum(
                len(cat_data.get('subcategories', [])) 
                for cat_data in categories.values()
            )
            
            total_questions = sum(
                cat_data.get('total_questions', 0)
                for cat_data in categories.values()
            )
            
            return {
                'exists': True,
                'last_updated': metadata.get('last_updated'),
                'total_categories': len(categories),
                'total_subcategories': total_subcategories,
                'total_questions': total_questions,
                'cache_file_size': os.path.getsize(self.cache_file) if os.path.exists(self.cache_file) else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'exists': False, 'error': str(e)}