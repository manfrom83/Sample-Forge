"""
Algorithm factory for creating optimization algorithm instances.

This factory provides a centralized way to create algorithm instances,
making it easy to add new algorithms without modifying the core runner.
"""

from typing import Dict, Type, List, Any
from utils.logger import logger
from ..interfaces import OptimizationAlgorithm, OptimizationConfig, OptimizationDatabase, ValidationError


class AlgorithmFactory:
    """Factory for creating optimization algorithm instances"""
    
    # Registry of available algorithms
    _algorithms: Dict[str, Type[OptimizationAlgorithm]] = {}
    
    @classmethod
    def register_algorithm(cls, name: str, algorithm_class: Type[OptimizationAlgorithm]) -> None:
        """Register a new algorithm class"""
        cls._algorithms[name] = algorithm_class
    
    @classmethod
    def create(cls, algorithm_name: str, config: OptimizationConfig, database: OptimizationDatabase) -> OptimizationAlgorithm:
        """
        Create an algorithm instance
        
        Args:
            algorithm_name: Name of the algorithm to create
            config: Optimization configuration
            database: Database instance for persistence
            
        Returns:
            Configured algorithm instance
            
        Raises:
            ValidationError: If algorithm name is not recognized
        """
        if algorithm_name not in cls._algorithms:
            available = ", ".join(cls._algorithms.keys())
            raise ValidationError(f"Unknown algorithm '{algorithm_name}'. Available algorithms: {available}")
        
        algorithm_class = cls._algorithms[algorithm_name]
        algorithm = algorithm_class()
        algorithm.initialize(config, database)
        
        return algorithm
    
    @classmethod
    def get_available_algorithms(cls) -> List[str]:
        """Get list of available algorithm names"""
        return list(cls._algorithms.keys())
    
    @classmethod
    def get_algorithm_info(cls, algorithm_name: str) -> Dict[str, str]:
        """Get information about a specific algorithm"""
        if algorithm_name not in cls._algorithms:
            return {"error": f"Algorithm '{algorithm_name}' not found"}
        
        algorithm_class = cls._algorithms[algorithm_name]
        
        return {
            "name": algorithm_name,
            "class": algorithm_class.__name__,
            "description": algorithm_class.__doc__ or "No description available",
            "module": algorithm_class.__module__
        }


# Import and register algorithms when this module is loaded
def _register_built_in_algorithms():
    """Register all built-in algorithms"""
    try:
        from .hierarchical_ts import HierarchicalTSBalanced
        AlgorithmFactory.register_algorithm("Hierarchical TS (Balanced)", HierarchicalTSBalanced)
    except ImportError as e:
        logger.warning(f"Could not import Hierarchical TS (Balanced): {e}")
    try:
        from .thompson_sampling import ThompsonSamplingAlgorithm
        AlgorithmFactory.register_algorithm("Thompson Sampling Bandit", ThompsonSamplingAlgorithm)
    except ImportError as e:
        logger.warning(f"Could not import Thompson Sampling algorithm: {e}")
    
    try:
        from .smart_continuous import SmartContinuousAlgorithm  
        AlgorithmFactory.register_algorithm("Smart Continuous Search", SmartContinuousAlgorithm)
    except ImportError as e:
        logger.warning(f"Could not import Smart Continuous Search algorithm: {e}")
    
    try:
        from .grid_search import GridSearchAlgorithm
        AlgorithmFactory.register_algorithm("Grid Search", GridSearchAlgorithm)
    except ImportError as e:
        logger.warning(f"Could not import Grid Search algorithm: {e}")


# Register algorithms on module import
_register_built_in_algorithms()


def get_algorithm_registry_status() -> Dict[str, Any]:
    """Get status of algorithm registration for debugging"""
    return {
        "registered_algorithms": list(AlgorithmFactory._algorithms.keys()),
        "algorithm_count": len(AlgorithmFactory._algorithms),
        "available_algorithms": AlgorithmFactory.get_available_algorithms()
    }
