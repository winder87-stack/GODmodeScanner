
"""
Comprehensive test suite for Singularity Engine - Dockerized Code Synthesis
"""

import pytest
import asyncio
import json
import os
import tempfile
import shutil
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, '/a0/usr/projects/godmodescanner/projects/godmodescanner')

from agents.memory.singularity_engine import SingularityEngine

@pytest.fixture
def singularity_engine():
    temp_dir = tempfile.mkdtemp()
    os.environ['OLLAMA_ENDPOINT'] = 'http://localhost:11434/api/generate'
    engine = SingularityEngine()
    engine.storage_dir = temp_dir
    yield engine
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.mark.asyncio
async def test_ollama_connection_simulation(singularity_engine):
    engine = singularity_engine
    assert engine.ollama_endpoint is not None
    assert engine.model == "codellama:7b-code"
    assert engine.max_function_lines == 40
    print("PASS: Ollama configuration validated")

@pytest.mark.asyncio
async def test_code_validation(singularity_engine):
    valid_code = """def detect_test_abc123(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return 1.0
"""
    assert singularity_engine._validate_generated_code(valid_code) is True
    print("PASS: Valid code passes validation")

    dangerous_code = """def detect_test_xyz(df):
    import os
    os.system("rm -rf /")
    return 0.0
"""
    assert singularity_engine._validate_generated_code(dangerous_code) is False
    print("PASS: Dangerous code rejected")

    no_return = 'def detect_test(df):\n    pass'
    assert singularity_engine._validate_generated_code(no_return) is False
    print("PASS: Code without return rejected")

@pytest.mark.asyncio
async def test_function_name_extraction(singularity_engine):
    code1 = 'def detect_early_buyer_abc123(df):\n    return 1.0'
    name1 = singularity_engine._extract_function_name(code1)
    assert name1 == 'detect_early_buyer_abc123'
    print(f"PASS: Extracted name: {name1}")

    code2 = """def detect_king_maker_xyz789(df: pd.DataFrame) -> float:
    return 0.87
"""
    name2 = singularity_engine._extract_function_name(code2)
    assert name2 == 'detect_king_maker_xyz789'
    print(f"PASS: Extracted name with docstring: {name2}")

@pytest.mark.asyncio
async def test_hot_injection_into_agent(singularity_engine):
    function_data = {
        'function_name': 'detect_test_inject_123',
        'code': """def detect_test_inject_123(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return 0.95
"""
    }
    
    mock_agent = Mock()
    mock_agent.custom_detectors = {}
    
    result = await singularity_engine.inject_into_agent(function_data, mock_agent)
    
    assert result is True
    assert 'detect_test_inject_123' in mock_agent.custom_detectors
    
    test_df = pd.DataFrame({'timestamp': [datetime.now()]})
    func = mock_agent.custom_detectors['detect_test_inject_123']
    score = func(test_df)
    assert score == 0.95
    print("PASS: Function hot-injected and executable")

if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
