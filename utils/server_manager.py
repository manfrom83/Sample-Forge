"""
Multi-Instance Server Manager
Provides process ownership tracking to allow multiple app instances to run simultaneously
while ensuring each instance only manages its own server process.
"""
import subprocess
import time
import threading
from typing import Optional, Dict, Any
from utils.api_client import LLMClient
from utils.logger import logger


class AppServerManager:
    """
    Server manager that tracks process ownership for multi-instance support.
    
    Each app instance can run its own server without interfering with other instances.
    Implements clean server lifecycle management with proper cleanup.
    """
    
    def __init__(self):
        self.owned_server_process: Optional[subprocess.Popen] = None
        self.owned_server_config = None
        self.owned_server_url = None
        self.startup_timeout = 30  # seconds
        self.termination_timeout = 5  # seconds
        # Background reader to drain server stdout to avoid PIPE back-pressure hangs
        self._stdout_thread: Optional[threading.Thread] = None
    
    def is_my_server_running(self) -> bool:
        """
        Check if our owned server process is still running.
        
        Returns:
            bool: True if our server process is alive and responsive
        """
        if not self.owned_server_process:
            return False
        
        # Check if process is still alive
        if self.owned_server_process.poll() is not None:
            # Process has terminated
            self.owned_server_process = None
            self.owned_server_config = None
            self.owned_server_url = None
            return False
        
        # Process is alive - check if server is responsive via LLMClient
        if self.owned_server_url:
            try:
                client = LLMClient(self.owned_server_url, timeout=2, request_timeout=2)
                ok, _ = client.health_check()
                return ok
            except Exception:
                return False
        return False
    
    def start_server_for_aco(self, server_config, log_callback=None, force_clean: bool = True) -> bool:
        """
        Start server with ACO configuration, ensuring clean state.

        When force_clean is True, kills ALL llama servers (including those started by
        other tabs) to guarantee fresh start with exact ACO configuration. When False,
        only the server owned by this manager is stopped/restarted.
        
        Args:
            server_config: ServerConfig object with ACO settings
            log_callback: Optional function to receive status messages
            
        Returns:
            bool: True if server started successfully, False otherwise
        """
        def log(message: str):
            if log_callback:
                log_callback(message)
            else:
                logger.info(f"ServerManager: {message}")
        
        try:
            # Ensure our owned server is stopped first
            self.stop_owned_server(log_callback=log_callback)

            # Optionally terminate any other llama servers to ensure a clean state
            if force_clean:
                log("Terminating any existing llama servers to ensure clean state...")
                from utils.server_utils import kill_all_llama_servers
                kill_all_llama_servers()
            
            # Generate server command
            log("Generating server command with ACO configuration...")
            command = server_config.generate_server_command()
            try:
                log("Server command: " + " ".join([str(c) for c in command]))
            except Exception:
                pass
            if not command:
                log("ERROR: No server executable configured")
                return False
            
            # Start fresh server process
            log("Starting fresh server process for ACO optimization...")
            self.owned_server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )

            # Drain stdout in background to prevent the child from blocking if it writes a lot
            # This avoids startup hangs due to PIPE buffers filling up.
            try:
                def _drain_stdout(proc: subprocess.Popen):
                    try:
                        if proc.stdout is None:
                            return
                        for _line in proc.stdout:
                            # Intentionally discard or forward logs here if desired
                            # We keep it simple to avoid UI blocking.
                            pass
                    except Exception:
                        # Swallow any reader errors; process lifecycle will handle cleanup
                        pass
                self._stdout_thread = threading.Thread(target=_drain_stdout, args=(self.owned_server_process,), daemon=True)
                self._stdout_thread.start()
            except Exception:
                # If we fail to start the drain thread, continue; worst case we may hit buffer limits
                self._stdout_thread = None
            
            # Store server configuration and URL
            self.owned_server_config = server_config
            self.owned_server_url = server_config.get_server_url()
            try:
                log(f"Expected server URL: {self.owned_server_url}")
            except Exception:
                pass
            
            # Wait for server to become ready
            # Derive a dynamic startup timeout based on configured server timeouts for slow warmups
            log("Waiting for server to become ready...")
            dynamic_timeout = self.startup_timeout
            try:
                # Prefer request_timeout; fallback to --timeout if available
                tcfg = server_config.get_connection_timeouts()
                req_t = int(tcfg.get('request_timeout', 0) or 0)
                srv_t = int(server_config.values.get('--timeout', 0) or 0)
                # Be generous: at least the larger of configured values
                if req_t > 0 or srv_t > 0:
                    dynamic_timeout = max(self.startup_timeout, req_t, srv_t)
            except Exception:
                # Keep default on any error
                pass
            max_attempts = int(dynamic_timeout) * 2  # Check every 0.5 seconds
            attempt = 0
            
            while attempt < max_attempts:
                # Check if process crashed
                if self.owned_server_process.poll() is not None:
                    log("ERROR: Server process terminated during startup")
                    self.owned_server_process = None
                    return False
                
                # Check if server is responding
                try:
                    client = LLMClient(self.owned_server_url, timeout=2, request_timeout=2)
                    ok, _ = client.health_check()
                except Exception:
                    ok = False
                if ok:
                    log(f"ACO server ready at {self.owned_server_url} (pid={self.owned_server_process.pid})")
                    return True
                
                time.sleep(0.5)
                attempt += 1
            
            # Timeout - kill the failed process
            log(f"ERROR: Server failed to start after {dynamic_timeout} seconds")
            self.stop_owned_server(log_callback=log_callback)
            return False
            
        except Exception as e:
            log(f"ERROR: Failed to start ACO server: {str(e)}")
            self.stop_owned_server(log_callback=log_callback)
            return False
    
    def stop_owned_server(self, log_callback=None) -> None:
        """
        Stop our owned server process gracefully.
        
        Only affects the server process that this instance started.
        Other app instances' servers are left untouched.
        
        Args:
            log_callback: Optional function to receive status messages
        """
        def log(message: str):
            if log_callback:
                log_callback(message)
            else:
                logger.info(f"ServerManager: {message}")
        
        if not self.owned_server_process:
            return
        
        try:
            log("Stopping owned server process...")
            
            # Terminate gracefully first
            self.owned_server_process.terminate()
            
            try:
                # Wait for graceful shutdown
                self.owned_server_process.wait(timeout=self.termination_timeout)
                log("Server stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if not responsive
                log("Server not responding, forcing shutdown...")
                self.owned_server_process.kill()
                self.owned_server_process.wait()
                log("Server force-stopped")
                
        except Exception as e:
            log(f"Warning: Error stopping server: {str(e)}")
        finally:
            # Clean up references
            self.owned_server_process = None
            self.owned_server_config = None
            self.owned_server_url = None
            self._stdout_thread = None
    
    def get_server_status(self) -> Dict[str, Any]:
        """
        Get current server status information.
        
        Returns:
            dict: Server status including URL, PID, and health status
        """
        if not self.owned_server_process:
            return {
                'running': False,
                'url': None,
                'pid': None,
                'health': 'no_server'
            }
        
        return {
            'running': self.owned_server_process.poll() is None,
            'url': self.owned_server_url,
            'pid': self.owned_server_process.pid,
            'health': 'healthy' if self.is_my_server_running() else 'unhealthy'
        }
    
    def cleanup(self):
        """
        Cleanup method to call when app is shutting down.
        Ensures our server process is properly terminated.
        """
        self.stop_owned_server()


# Global instance for app-wide server management
app_server_manager = AppServerManager()


def cleanup_all_servers(log_callback=None) -> bool:
    """
    Centralized helper to terminate any running llama-server processes.

    Use this from UI and other modules instead of importing kill_all_llama_servers
    directly, so we keep process management concerns in one place.

    Returns:
        bool: True if cleanup likely succeeded, False otherwise
    """
    def log(message: str):
        if log_callback:
            log_callback(message)
        else:
            logger.info(f"ServerManager: {message}")

    try:
        from utils.server_utils import kill_all_llama_servers
        log("Cleaning up existing llama-server processes...")
        return kill_all_llama_servers()
    except Exception as e:
        log(f"Warning: cleanup failed: {e}")
        return False
