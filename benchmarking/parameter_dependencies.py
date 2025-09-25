"""
Parameter Dependencies Analysis
Handles llama.cpp parameter dependencies and calculates valid combinations for ACO
"""

from typing import Dict, List, Any
import itertools
from .interfaces import ParameterConverter


class ParameterDependencyAnalyzer:
    """
    Analyzes parameter dependencies and calculates valid optimization combinations
    Based on llama.cpp server parameter interdependencies
    """

    def __init__(self):
        self.dependency_groups = {
            "penalties": {
                "controller": "repeat_penalty",
                "controller_conditions": [
                    ("samplers", "contains", "penalties"),
                    ("repeat_penalty", "not_equals", 1.0),
                ],
                "dependents": [
                    "frequency_penalty",
                    "presence_penalty",
                    "repeat_last_n",
                    "penalize_nl",
                ],
            },
            "dry": {
                "controller": "dry_multiplier",
                "controller_conditions": [
                    ("samplers", "contains", "dry"),
                    ("dry_multiplier", "greater_than", 0.0),
                ],
                "dependents": [
                    "dry_base",
                    "dry_allowed_length",
                    "dry_penalty_last_n",
                    "dry_sequence_breakers",
                ],
            },
            "mirostat": {
                "controller": "mirostat",
                "controller_conditions": [
                    ("samplers", "contains", "mirostat"),
                    ("mirostat", "in_values", [1, 2]),
                ],
                "dependents": ["mirostat_tau", "mirostat_eta"],
                "exclusions": ["top_k", "top_p", "typical_p"],
            },
            "xtc": {
                "controller": "xtc_probability",
                "controller_conditions": [
                    ("samplers", "contains", "xtc"),
                    ("xtc_probability", "greater_than", 0.0),
                ],
                "dependents": ["xtc_threshold"],
            },
            "dynatemp": {
                "controller": "dynatemp_range",
                "controller_conditions": [
                    ("samplers", "contains", "dynatemp"),
                    ("dynatemp_range", "greater_than", 0.0),
                ],
                "dependents": ["dynatemp_exponent"],
            },
        }

    def parse_samplers_array(self, samplers_value: str) -> List[str]:
        if not samplers_value or not samplers_value.strip():
            return [
                "penalties",
                "dry",
                "top_n_sigma",
                "top_k",
                "typ_p",
                "top_p",
                "min_p",
                "xtc",
                "temperature",
            ]
        s = samplers_value.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        samplers: List[str] = []
        for item in s.split(","):
            name = item.strip().strip('"\'')
            if not name:
                continue
            samplers.append("typical_p" if name == "typ_p" else name)
        return samplers

    def check_condition(
        self, param_name: str, condition_type: str, condition_value: Any, combination: Dict[str, Any]
    ) -> bool:
        val = combination.get(param_name)
        if condition_type == "contains":
            if param_name == "samplers":
                act = self.parse_samplers_array(val) if isinstance(val, str) else (val or [])
                return condition_value in act
            return False
        if condition_type == "not_equals":
            return val != condition_value
        if condition_type == "greater_than":
            try:
                return float(val) > float(condition_value)
            except (TypeError, ValueError):
                return False
        if condition_type == "in_values":
            return val in condition_value
        return False

    def is_dependency_group_active(self, group_name: str, combination: Dict[str, Any]) -> bool:
        group = self.dependency_groups[group_name]
        controller = group["controller"]
        if controller not in combination:
            return False
        for pname, ctype, cval in group["controller_conditions"]:
            if not self.check_condition(pname, ctype, cval, combination):
                return False
        return True

    def get_effective_parameters(self, combination: Dict[str, Any]) -> Dict[str, Any]:
        effective: Dict[str, Any] = dict(combination)
        for gname, ginfo in self.dependency_groups.items():
            if not self.is_dependency_group_active(gname, combination):
                for dep in ginfo["dependents"]:
                    effective.pop(dep, None)
            else:
                for ex in ginfo.get("exclusions", []):
                    effective.pop(ex, None)
        return effective

    def calculate_effective_combinations(self, extracted_arrays: Dict[str, Dict[str, Any]]) -> int:
        if not extracted_arrays:
            return 0
        names = list(extracted_arrays.keys())
        values = [extracted_arrays[n]["values"] for n in names]
        if not values:
            return 0
        seen = set()
        for combo_vals in itertools.product(*values):
            combo = {n: ParameterConverter.convert_parameter_value(n, v) for n, v in zip(names, combo_vals)}
            eff = self.get_effective_parameters(combo)
            seen.add(ParameterConverter.make_hashable_key(eff))
        return len(seen)

    def get_blacklisted_combinations(self, extracted_arrays: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not extracted_arrays:
            return []
        names = list(extracted_arrays.keys())
        values = [extracted_arrays[n]["values"] for n in names]
        if not values:
            return []
        blacklisted: List[Dict[str, Any]] = []
        for combo_vals in itertools.product(*values):
            combo = {n: ParameterConverter.convert_parameter_value(n, v) for n, v in zip(names, combo_vals)}
            should_blacklist = False
            reasons: List[str] = []
            for gname, ginfo in self.dependency_groups.items():
                active = self.is_dependency_group_active(gname, combo)
                for dep in ginfo["dependents"]:
                    if dep in combo and not active:
                        should_blacklist = True
                        reasons.append(f"{dep} requires {ginfo['controller']} to be active")
            if should_blacklist:
                combo["_blacklist_reason"] = reasons
                blacklisted.append(combo)
        return blacklisted

    def get_dependency_warnings(self, extracted_arrays: Dict[str, Dict[str, Any]]) -> List[str]:
        warnings: List[str] = []
        param_names = set(extracted_arrays.keys())
        penalties_dependents = {"frequency_penalty", "presence_penalty", "repeat_last_n", "penalize_nl"}
        if penalties_dependents.intersection(param_names):
            if "repeat_penalty" not in param_names and "samplers" not in param_names:
                warnings.append("WARNING: Penalty parameters defined but repeat_penalty and samplers not configured")
        dry_dependents = {"dry_base", "dry_allowed_length", "dry_penalty_last_n", "dry_sequence_breakers"}
        if dry_dependents.intersection(param_names):
            if "dry_multiplier" not in param_names and "samplers" not in param_names:
                warnings.append("WARNING: DRY parameters defined but dry_multiplier and samplers not configured")
        mirostat_dependents = {"mirostat_tau", "mirostat_eta"}
        if mirostat_dependents.intersection(param_names):
            if "mirostat" not in param_names:
                warnings.append("WARNING: Mirostat parameters defined but mirostat not configured")
        if "mirostat" in param_names:
            excluded_with_mirostat = {"top_k", "top_p", "typical_p"}
            if excluded_with_mirostat.intersection(param_names):
                warnings.append("WARNING: top_k, top_p, typical_p will be ignored when mirostat is active")
        return warnings
