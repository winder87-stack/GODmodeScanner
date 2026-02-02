
"""
Singularity Engine - Dockerized Autonomous Code Generation
"""

import asyncio
import hashlib
import json
import os
import re
import structlog
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiohttp

logger = structlog.get_logger()

class SingularityEngine:
    def __init__(self):
        self.ollama_endpoint = os.getenv('OLLAMA_ENDPOINT', 'http://ollama:11434/api/generate')
        self.model = "codellama:7b-code"
        self.function_registry = {}
        self.storage_dir = "/data/singularity"
        os.makedirs(self.storage_dir, exist_ok=True)
        self.max_function_lines = 40
        self.max_synthesis_time = 30
        
        logger.info("SingularityEngine initialized", ollama_endpoint=self.ollama_endpoint)
        
    async def synthesize_detector_from_pattern(self, pattern: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate Python detection code from a behavioral pattern."""
        start_time = asyncio.get_event_loop().time()
        pattern_hash = hashlib.sha256(json.dumps(pattern, sort_keys=True).encode()).hexdigest()[:8]
        
        if pattern_hash in self.function_registry:
            logger.info("Pattern already synthesized", pattern_hash=pattern_hash)
            return self.function_registry[pattern_hash]
            
        prompt = self._build_synthesis_prompt(pattern, pattern_hash)
        
        try:
            code = await self._generate_code_via_ollama(prompt)
            
            if not code:
                logger.warning("Code synthesis returned empty result")
                return None
            
            if not self._validate_generated_code(code):
                logger.warning("Generated code failed validation")
                return None
            
            function_name = self._extract_function_name(code)
            
            result = {
                'function_name': function_name,
                'code': code,
                'pattern_hash': pattern_hash,
                'pattern': pattern,
                'created_at': datetime.utcnow().isoformat(),
                'performance': {'calls': 0, 'tp': 0, 'fp': 0, 'fitness': 0.0}
            }
            
            self.function_registry[pattern_hash] = result
            self._persist_function(pattern_hash, result)
            
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info("New detection function synthesized", pattern_hash=pattern_hash, function_name=function_name)
            
            return result
            
        except Exception as e:
            logger.error("Code synthesis failed", error=str(e), exc_info=True)
            return None
    
    async def _generate_code_via_ollama(self, prompt: str) -> Optional[str]:
        """Call Ollama Docker service for code generation."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 600
                    }
                }
                
                timeout = aiohttp.ClientTimeout(total=self.max_synthesis_time)
                
                async with session.post(self.ollama_endpoint, json=payload, timeout=timeout) as resp:
                    if resp.status != 200:
                        logger.error("Ollama API error", status=resp.status)
                        return None
                        
                    result = await resp.json()
                    raw_response = result.get("response", "")
                    code = self._extract_code_block(raw_response)
                    return code
                    
        except asyncio.TimeoutError:
            logger.error("Ollama code generation timeout")
            return None
        except Exception as e:
            logger.error("Ollama API call failed", error=str(e))
            return None
    
    def _build_synthesis_prompt(self, pattern: Dict, pattern_hash: str) -> str:
        """Build the LLM prompt for code generation."""
        characteristics = json.dumps(pattern.get('characteristics', {}), indent=2)
        
        lines = [
            "You are an expert Python developer writing a financial pattern detection function.",
            "",
            "PATTERN TO DETECT:",
            f"Type: {pattern['type']}",
            f"Confidence: {pattern.get('confidence', 0.0)}",
            f"Sample Size: {pattern.get('sample_size', 0)}",
            "Characteristics:",
            characteristics,
            "",
            "TASK: Write a single Python function that detects this exact pattern.",
            "",
            "STRICT REQUIREMENTS:",
            f"1. Function signature: def detect_{pattern['type']}_{pattern_hash}(df: pd.DataFrame) -> float:",
            "2. Input: pandas DataFrame with columns: [wallet_address, timestamp, amount_sol, token_address, price_usd, hold_time]",
            "3. Output: confidence score (0.0 to 1.0)",
            "4. Use only: pandas, numpy (no external libraries)",
            "5. Handle edge cases: empty df, missing columns, NaN values",
            "6. Add docstring explaining the pattern",
            "7. Include inline comments for each calculation",
            "8. NO print statements, NO external API calls",
            "9. Maximum 40 lines of code",
            "10. Return 0.0 if pattern not detected",
            "",
            "Output ONLY the Python code starting with 'def detect_' and ending with the return statement."
        ]
        
        return "
".join(lines)
    
    def _extract_code_block(self, llm_response: str) -> Optional[str]:
        """Extract Python code from LLM response."""
        if "```python" in llm_response:
            start = llm_response.find("```python") + 9
            end = llm_response.find("```", start)
            code = llm_response[start:end].strip()
        elif "```" in llm_response:
            start = llm_response.find("```") + 3
            end = llm_response.find("```", start)
            code = llm_response[start:end].strip()
        else:
            code = llm_response.strip()
        
        if code.startswith("def detect_"):
            return code
        
        lines = code.split('
')
        for i, line in enumerate(lines):
            if line.strip().startswith("def detect_"):
                return '
'.join(lines[i:])
        
        return None
    
    def _validate_generated_code(self, code: str) -> bool:
        """Basic validation of generated code."""
        if not code or len(code) < 50:
            return False
        
        if not code.strip().startswith("def detect_"):
            return False
        
        if "return" not in code:
            return False
        
        if "(df" not in code and "(df:" not in code:
            return False
        
        lines = [l for l in code.split('
') if l.strip() and not l.strip().startswith('#')]
        if len(lines) > self.max_function_lines:
            logger.warning("Generated code exceeds maximum lines")
            return False
        
        forbidden = ['import os', 'import sys', 'exec(', 'eval(', '__import__', 'open(']
        for keyword in forbidden:
            if keyword in code:
                logger.warning("Rejected code containing forbidden keyword")
                return False
        
        return True
    
    def _extract_function_name(self, code: str) -> str:
        """Extract function name from code."""
        match = re.search(r'def (detect_\w+)\(', code)
        if match:
            return match.group(1)
        return "unknown_function"
    
    def _persist_function(self, pattern_hash: str, function_data: Dict):
        """Save function to disk (Docker volume)."""
        filepath = os.path.join(self.storage_dir, f"{pattern_hash}.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(function_data, f, indent=2)
            logger.debug("Function persisted to disk", filepath=filepath)
        except Exception as e:
            logger.error("Failed to persist function", error=str(e))
    
    async def load_persisted_functions(self):
        """Load all previously generated functions from disk on startup."""
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.storage_dir, filename)
                    with open(filepath, 'r') as f:
                        function_data = json.load(f)
                        pattern_hash = function_data['pattern_hash']
                        self.function_registry[pattern_hash] = function_data
            
            logger.info("Loaded persisted functions", count=len(self.function_registry))
        except Exception as e:
            logger.error("Failed to load persisted functions", error=str(e))
    
    async def inject_into_agent(self, function_data: Dict, agent_instance) -> bool:
        """Hot-inject the new function into a running agent."""
        code = function_data['code']
        function_name = function_data['function_name']
        
        try:
            import pandas as pd
            import numpy as np
            
            namespace = {
                'pd': pd,
                'np': np,
                '__builtins__': {
                    'len': len, 'min': min, 'max': max, 'sum': sum,
                    'abs': abs, 'round': round, 'float': float,
                    'int': int, 'str': str
                }
            }
            
            exec(code, namespace)
            
            new_function = namespace.get(function_name)
            
            if not new_function or not callable(new_function):
                logger.error("Generated code did not create a callable function")
                return False
            
            if not hasattr(agent_instance, 'custom_detectors'):
                agent_instance.custom_detectors = {}
            
            agent_instance.custom_detectors[function_name] = new_function
            
            logger.info("Function hot-injected into agent", function=function_name)
            return True
            
        except Exception as e:
            logger.error("Function injection failed", error=str(e))
            return False
