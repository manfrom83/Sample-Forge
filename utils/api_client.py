import json
import requests
import time
from typing import Dict, Any, Optional, Tuple
from .logger import logger


class LLMClient:
    
    def __init__(self, base_url: str = None, timeout: int = None, request_timeout: int = None):
        self.configure(base_url, timeout, request_timeout)
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def configure(self, base_url: str = None, timeout: int = None, request_timeout: int = None):
        self.base_url = base_url.rstrip('/') if base_url else None
        self.timeout = timeout
        self.request_timeout = request_timeout
    
    def health_check(self) -> Tuple[bool, str]:
        if not self.base_url:
            return False, "No server URL configured"
        if self.timeout is None or self.timeout <= 0:
            return False, "No valid timeout configured"
            
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                return True, "Server is healthy"
            else:
                return False, f"Server returned status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to server - is it running?"
        except requests.exceptions.Timeout:
            return False, "Server health check timed out"
        except Exception as e:
            return False, f"Health check failed: {str(e)}"
    
    
    def get_slots_info_raw(self) -> Optional[str]:
        if not self.base_url or self.timeout is None or self.timeout <= 0:
            return None
            
        try:
            response = self.session.get(f"{self.base_url}/slots", timeout=self.timeout * 2)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            logger.warn(f"Error getting slots information: {e}")
            return None
    
    def chat_completion(self, messages: list, parameters: Dict[str, Any] = None, timeout: int = None) -> Tuple[bool, Dict[str, Any]]:
        if not self.base_url:
            return False, {"error": "No server URL configured"}
        
        timeout = timeout or self.request_timeout
        if timeout is None or timeout <= 0:
            return False, {"error": "No valid request timeout configured"}
            
        try:
            payload = {"messages": messages}
            if parameters:
                payload.update(parameters)
            
            start_time = time.time()
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=timeout
            )
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                result['response_time'] = response_time
                result['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
                result['_raw_server_response'] = response.text
                return True, result
            else:
                return False, {"error": f"HTTP {response.status_code}: {response.text}", "response_time": response_time}
                
        except requests.exceptions.Timeout:
            return False, {"error": f"Request timed out after {timeout} seconds"}
        except requests.exceptions.ConnectionError:
            return False, {"error": "Cannot connect to server - is it running?"}
        except Exception as e:
            return False, {"error": str(e)}
    
    def simple_chat(self, user_message: str, parameters: Dict[str, Any] = None) -> Tuple[bool, str, Dict[str, Any]]:
        messages = [{"role": "user", "content": user_message}]
        success, result = self.chat_completion(messages, parameters)
        
        if success:
            try:
                response_text = result['choices'][0]['message']['content']
                return True, response_text, result
            except (KeyError, IndexError) as e:
                return False, f"Unexpected response format: {e}", result
        else:
            error_msg = result.get('error', 'Unknown error')
            return False, error_msg, result
    
    def text_completion(self, prompt: str, parameters: Dict[str, Any] = None, timeout: int = None) -> Tuple[bool, Dict[str, Any]]:
        if not self.base_url:
            return False, {"error": "No server URL configured"}
        
        timeout = timeout or self.request_timeout
        if timeout is None or timeout <= 0:
            return False, {"error": "No valid request timeout configured"}
            
        try:
            payload = {"prompt": prompt}
            if parameters:
                payload.update(parameters)
            
            start_time = time.time()
            response = self.session.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=timeout
            )
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                result = response.json()
                result['response_time'] = response_time
                result['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
                result['_raw_server_response'] = response.text
                return True, result
            else:
                return False, {"error": f"HTTP {response.status_code}: {response.text}", "response_time": response_time}
                
        except requests.exceptions.Timeout:
            return False, {"error": f"Request timed out after {timeout} seconds"}
        except requests.exceptions.ConnectionError:
            return False, {"error": "Cannot connect to server - is it running?"}
        except Exception as e:
            return False, {"error": str(e)}

    def unified_completion(self, endpoint_type: str, content, parameters: Dict[str, Any] = None, timeout: int = None) -> Tuple[bool, Dict[str, Any]]:
        """Unified method that calls either chat_completion or text_completion based on endpoint_type"""
        if endpoint_type == "completions":
            return self.text_completion(content, parameters, timeout)
        else:  # "chat_completions"
            return self.chat_completion(content, parameters, timeout)

    def close(self):
        if hasattr(self, 'session') and self.session:
            self.session.close()
            self.session = None
