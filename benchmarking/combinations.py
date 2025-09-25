"""
Combinations Helper
Shared utilities for generating parameter combinations for ACO algorithms.
"""

from typing import Dict, List, Any
import itertools

from .interfaces import ParameterArrayInfo, ParameterConverter


def generate_all_combinations(parameter_arrays: Dict[str, ParameterArrayInfo]) -> List[Dict[str, Any]]:
    """
    Generate all possible parameter combinations using cartesian product,
    converting string values to appropriate Python types via ParameterConverter.

    Args:
        parameter_arrays: Mapping of parameter name to ParameterArrayInfo

    Returns:
        List of parameter dictionaries representing all combinations
    """
    if not parameter_arrays:
        return []

    param_names = list(parameter_arrays.keys())
    param_value_lists = [parameter_arrays[name].values for name in param_names]

    if not param_value_lists:
        return []

    combinations: List[Dict[str, Any]] = []
    for combination_values in itertools.product(*param_value_lists):
        combination: Dict[str, Any] = {}
        for param_name, value in zip(param_names, combination_values):
            combination[param_name] = ParameterConverter.convert_parameter_value(param_name, value)
        combinations.append(combination)

    return combinations

