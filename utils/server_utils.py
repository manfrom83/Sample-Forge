import subprocess
import sys
import urllib.request
from .logger import logger


def is_server_running(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
            return response.getcode() == 200
    except:
        return False


def kill_all_llama_servers():
    success = False
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ['taskkill', '/F', '/IM', 'llama-server.exe'], 
                capture_output=True, 
                text=True
            )
            success = result.returncode in [0, 128]
            if result.returncode == 0:
                logger.info("Cleaned up llama-server processes")
        else:
            result = subprocess.run(
                ['pkill', 'llama-server'], 
                capture_output=True, 
                text=True
            )
            success = result.returncode in [0, 1]
            if result.returncode == 0:
                logger.info("Cleaned up llama-server processes")
        
        return success
            
    except Exception as e:
        logger.warn(f"Could not clean up llama-server processes: {e}")
        return False
