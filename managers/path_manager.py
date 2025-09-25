"""
Centralized path management for portable, cross-platform file access
Auto-detects project root and provides consistent path resolution
"""

from pathlib import Path
from typing import Optional
import os


class AppPaths:
    """Centralized, portable path resolution for the entire application"""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize path manager with automatic project root detection
        
        Args:
            project_root: Optional override for project root (mainly for testing)
        """
        if project_root is None:
            project_root = self._find_project_root()
        
        self.root = Path(project_root)
        
        # Core directories
        self.config = self.root / "config"
        self.managers = self.root / "managers"
        self.ui = self.root / "ui"
        self.benchmarking = self.root / "benchmarking"
        self.data = self.root / "data"
        self.utils = self.root / "utils"
        
        # Data subdirectories
        self.saved_configs = self.data / "saved_configs"
        self.server_configs = self.data / "server_configs"
        self.benchmark_runs = self.data / "benchmarks" / "runs"
        self.aco_runs = self.data / "aco_runs"
        self.exported_datasets = self.data / "exported_datasets"
        self.benchmark_runner_state = self.data / "benchmark_runner"
        self.cache = self.data / "cache"
        
        # Config files (new structure)
        self.openai_api_schema = self.config / "openai_api_schema.json"
        self.llama_server_cli_flags = self.config / "llama_server_cli_flags.json"
        self.ui_configuration = self.config / "ui_configuration.json"
    
    def _find_project_root(self) -> Path:
        """
        Auto-detect project root by looking for main.py
        Works from any subdirectory within the project
        """
        current = Path(__file__).parent
        
        # Walk up the directory tree looking for main.py
        while current != current.parent:  # Not at filesystem root
            if (current / "main.py").exists():
                return current
            current = current.parent
        
        # If we can't find main.py, raise an error with helpful info
        raise RuntimeError(
            f"Could not find project root (main.py not found). "
            f"Started search from: {Path(__file__).parent}"
        )
    
    def ensure_directories_exist(self):
        """Create all necessary directories if they don't exist"""
        directories = [
            self.config,
            self.managers,
            self.ui,
            self.benchmarking,
            self.data,
            self.utils,
            self.saved_configs,
            self.server_configs,
            self.benchmark_runs,
            self.aco_runs,
            self.exported_datasets,
            self.benchmark_runner_state,
            self.cache
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    
    def __str__(self) -> str:
        """String representation for debugging"""
        return f"AppPaths(root={self.root})"


# Global instance for use throughout the application
app_paths = AppPaths()

# Ensure directories exist when module is imported
app_paths.ensure_directories_exist()