"""
Benchmark UI helpers to centralize run calls and reduce duplication.
"""

from typing import List, Callable, Optional


def run_benchmark_enhanced_common(
    executor,
    *,
    dataset_path: str,
    config_data: dict,
    selected_questions: List[int],
    run_name: str,
    system_prompt: str,
    server_config_path: Optional[str],
    api_config_path: Optional[str],
    progress_callback: Optional[Callable[[str], None]] = None,
    detailed_progress_callback: Optional[Callable[[int, int, str], None]] = None,
    system_prompt_override_enabled: bool = False,
    system_prompt_override_text: str = "",
    system_prefix: str = "",
    system_suffix: str = "",
    user_prefix: str = "",
    user_suffix: str = "",
    endpoint_type: str = "chat_completions",
):
    """Thin wrapper around executor.run_benchmark_enhanced to keep call sites consistent."""
    return executor.run_benchmark_enhanced(
        dataset_path=dataset_path,
        config_data=config_data,
        selected_questions=selected_questions,
        run_name=run_name,
        system_prompt=system_prompt,
        server_config_path=server_config_path,
        api_config_path=api_config_path,
        progress_callback=progress_callback,
        detailed_progress_callback=detailed_progress_callback,
        system_prompt_override_enabled=system_prompt_override_enabled,
        system_prompt_override_text=system_prompt_override_text,
        system_prefix=system_prefix,
        system_suffix=system_suffix,
        user_prefix=user_prefix,
        user_suffix=user_suffix,
        endpoint_type=endpoint_type,
    )

