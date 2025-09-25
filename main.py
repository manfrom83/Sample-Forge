import sys
from managers.api_config_manager import ParameterConfig
from utils.api_client import LLMClient
from utils.logger import logger
from ui.main_window import ParameterUI
from benchmarking.cache_manager import CacheManager


def main():
    logger.info("Starting application...")
    
    try:
        config = ParameterConfig()
        api_client = LLMClient()
        cache_manager = CacheManager()
        ui = ParameterUI(config, api_client, cache_manager)
        root = ui.create_main_window()
        
        # Start GUI
        ui.run()
        
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        logger.error("=" * 60)
        logger.error("FULL ERROR DETAILS (copy this to share with your coding agent):")
        logger.error("=" * 60)
        import traceback
        logger.error(traceback.format_exc())
        logger.error("=" * 60)
        
        # Keep window open so user can copy error
        input("\nPress Enter to close...")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
