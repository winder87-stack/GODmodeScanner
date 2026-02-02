"""
ONNX Runtime Inference Engine with TensorRT Optimization

GPU-accelerated inference for Behavioral DNA and other ML models.
Achieves sub-50ms inference latency using TensorRT and CUDA.

Usage:
    engine = await get_onnx_engine()
    prediction = await engine.predict(features)
    
    # Batch inference
    predictions = await engine.batch_predict(features_list)
"""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
from pathlib import Path
import time

import numpy as np

# Setup logging
logger = logging.getLogger(__name__)

# Try to import ONNX Runtime
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    logger.warning("ONNX Runtime not installed, using NumPy fallback")
    ONNX_AVAILABLE = False
    ort = None


@dataclass
class InferenceMetrics:
    """Inference performance metrics"""
    total_inferences: int = 0
    total_batch_inferences: int = 0
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    throughput_per_sec: float = 0.0
    last_inference_time: float = 0.0
    
    def record(self, latency_ms: float):
        """Record a new inference latency"""
        self.total_inferences += 1
        self.last_inference_time = time.time()
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        alpha = 0.1
        self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms


@dataclass  
class PredictionResult:
    """Prediction result with metadata"""
    prediction: np.ndarray
    confidence: float
    latency_ms: float
    model_name: str
    timestamp: float


class ONNXInferenceEngine:
    """
    GPU-accelerated ONNX inference engine
    
    Features:
    - TensorRT execution provider (primary)
    - CUDA execution provider (fallback)  
    - CPU execution provider (last resort)
    - Pre-allocated tensors for zero-copy
    - Async batch processing
    - Automatic model warmup
    """
    
    def __init__(
        self,
        model_path: str,
        input_shape: Tuple[int, ...] = (768,),
        batch_size: int = 1,
        use_tensorrt: bool = True,
        use_cuda: bool = True,
        tensorrt_workspace_mb: int = 2048,
        tensorrt_fp16: bool = True
    ):
        self.model_path = model_path
        self.input_shape = input_shape
        self.batch_size = batch_size
        self.use_tensorrt = use_tensorrt
        self.use_cuda = use_cuda
        
        self.session = None
        self.input_name = None
        self.output_name = None
        self.input_dtype = np.float32
        
        # Pre-allocated tensors
        self.input_buffer = None
        self.batch_buffer = None
        
        # Metrics
        self.metrics = InferenceMetrics()
        self.latency_history = []
        self.max_history_size = 1000
        
        # Initialize session
        if ONNX_AVAILABLE:
            self._initialize_session(
                tensorrt_workspace_mb=tensorrt_workspace_mb,
                tensorrt_fp16=tensorrt_fp16
            )
        else:
            logger.warning("Running in fallback mode (NumPy only)")
        
        logger.info(f"ONNXInferenceEngine initialized: {model_path}")
    
    def _initialize_session(self, tensorrt_workspace_mb, tensorrt_fp16):
        """Create optimized ONNX Runtime session"""
        
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
        sess_options.inter_op_num_threads = 4
        sess_options.intra_op_num_threads = 4
        sess_options.enable_mem_pattern = True
        
        # Execution providers (priority order)
        providers = []
        provider_options = []
        
        # TensorRT (fastest)
        if self.use_tensorrt:
            providers.append('TensorrtExecutionProvider')
            trt_cache_path = os.path.join(os.path.dirname(self.model_path), 'trt_cache')
            os.makedirs(trt_cache_path, exist_ok=True)
            provider_options.append({
                'trt_max_workspace_size': tensorrt_workspace_mb * 1024 * 1024,
                'trt_fp16_enable': tensorrt_fp16,
                'trt_engine_cache_enable': True,
                'trt_engine_cache_path': trt_cache_path,
            })
        
        # CUDA (second fastest)
        if self.use_cuda:
            providers.append('CUDAExecutionProvider')
            provider_options.append({
                'device_id': 0,
                'arena_extend_strategy': 'kNextPowerOfTwo',
            })
        
        # CPU (fallback)
        providers.append('CPUExecutionProvider')
        provider_options.append({})
        
        try:
            self.session = ort.InferenceSession(
                self.model_path,
                sess_options=sess_options,
                providers=providers,
                provider_options=provider_options
            )
            
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            
            active_providers = self.session.get_providers()
            logger.info(f"ONNX session created with providers: {active_providers}")
            
            self._allocate_buffers()
            self._warmup()
            
        except Exception as e:
            logger.error(f"Failed to create ONNX session: {e}")
            raise
    
    def _allocate_buffers(self):
        """Pre-allocate input buffers for zero-copy inference"""
        self.input_buffer = np.zeros((1,) + self.input_shape, dtype=self.input_dtype)
        self.batch_buffer = np.zeros((self.batch_size,) + self.input_shape, dtype=self.input_dtype)
    
    def _warmup(self, num_runs=10):
        """Warmup the model for consistent performance"""
        if self.session is None:
            return
        
        logger.info(f"Warming up model with {num_runs} runs...")
        dummy_input = np.random.randn(1, *self.input_shape).astype(self.input_dtype)
        
        for _ in range(num_runs):
            try:
                self.session.run(None, {self.input_name: dummy_input})
            except Exception as e:
                logger.warning(f"Warmup run failed: {e}")
        
        logger.info("Warmup complete")
    
    async def predict(self, features, return_confidence=True):
        """Run single inference"""
        start_time = time.time()
        
        # Convert to numpy if needed
        if isinstance(features, list):
            features = np.array(features, dtype=self.input_dtype)
        
        # Ensure correct shape
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        # Run inference
        if self.session is not None and ONNX_AVAILABLE:
            prediction = await self._run_onnx_inference(features)
        else:
            prediction = await self._run_fallback_inference(features)
        
        latency_ms = (time.time() - start_time) * 1000
        self.metrics.record(latency_ms)
        self._update_latency_history(latency_ms)
        
        confidence = self._calculate_confidence(prediction) if return_confidence else 0.0
        
        return PredictionResult(
            prediction=prediction,
            confidence=confidence,
            latency_ms=latency_ms,
            model_name=os.path.basename(self.model_path),
            timestamp=time.time()
        )
    
    async def _run_onnx_inference(self, features):
        """Run ONNX inference in executor"""
        loop = asyncio.get_event_loop()
        
        if features.shape[0] == 1 and self.input_buffer is not None:
            np.copyto(self.input_buffer, features)
            input_data = self.input_buffer
        else:
            input_data = features
        
        outputs = await loop.run_in_executor(
            None,
            self.session.run,
            None,
            {self.input_name: input_data}
        )
        
        return outputs[0]
    
    async def _run_fallback_inference(self, features):
        """Fallback inference using simple heuristics"""
        prediction = np.tanh(features[0][:4])
        return prediction.reshape(1, -1)
    
    async def batch_predict(self, features_list, max_batch_size=None):
        """Run batch inference for efficiency"""
        if max_batch_size is None:
            max_batch_size = self.batch_size
        
        results = []
        for i in range(0, len(features_list), max_batch_size):
            batch = features_list[i:i + max_batch_size]
            batch_results = await self._process_batch(batch)
            results.extend(batch_results)
        
        self.metrics.total_batch_inferences += 1
        return results
    
    async def _process_batch(self, batch):
        """Process a single batch"""
        start_time = time.time()
        batch_size = len(batch)
        
        if self.batch_buffer is not None and batch_size <= self.batch_size:
            for i, features in enumerate(batch):
                if isinstance(features, list):
                    features = np.array(features, dtype=self.input_dtype)
                np.copyto(self.batch_buffer[i], features)
            input_data = self.batch_buffer[:batch_size]
        else:
            input_data = np.stack([
                np.array(f, dtype=self.input_dtype) if isinstance(f, list) else f
                for f in batch
            ])
        
        if self.session is not None and ONNX_AVAILABLE:
            loop = asyncio.get_event_loop()
            outputs = await loop.run_in_executor(
                None, self.session.run, None, {self.input_name: input_data}
            )
            predictions = outputs[0]
        else:
            predictions = np.array([
                await self._run_fallback_inference(input_data[i:i+1])
                for i in range(batch_size)
            ])
        
        total_latency_ms = (time.time() - start_time) * 1000
        per_sample_latency_ms = total_latency_ms / batch_size
        
        results = []
        for pred in predictions:
            self.metrics.record(per_sample_latency_ms)
            results.append(PredictionResult(
                prediction=pred,
                confidence=self._calculate_confidence(pred),
                latency_ms=per_sample_latency_ms,
                model_name=os.path.basename(self.model_path),
                timestamp=time.time()
            ))
        
        return results
    
    def _calculate_confidence(self, prediction):
        """Calculate confidence score from prediction"""
        if len(prediction.shape) > 0:
            exp_preds = np.exp(prediction - np.max(prediction))
            probs = exp_preds / np.sum(exp_preds)
            return float(np.max(probs))
        return 0.5
    
    def _update_latency_history(self, latency_ms):
        """Update latency history for percentile calculations"""
        self.latency_history.append(latency_ms)
        if len(self.latency_history) > self.max_history_size:
            self.latency_history.pop(0)
        
        if len(self.latency_history) >= 100:
            sorted_history = sorted(self.latency_history)
            p95_idx = int(len(sorted_history) * 0.95)
            p99_idx = int(len(sorted_history) * 0.99)
            self.metrics.p95_latency_ms = sorted_history[min(p95_idx, len(sorted_history)-1)]
            self.metrics.p99_latency_ms = sorted_history[min(p99_idx, len(sorted_history)-1)]
    
    def get_metrics(self):
        """Get current performance metrics"""
        if self.metrics.latency_history:
            avg_latency_sec = self.metrics.avg_latency_ms / 1000
            throughput = 1.0 / avg_latency_sec if avg_latency_sec > 0 else 0
        else:
            throughput = 0
        
        return {
            'total_inferences': self.metrics.total_inferences,
            'avg_latency_ms': self.metrics.avg_latency_ms,
            'min_latency_ms': self.metrics.min_latency_ms if self.metrics.min_latency_ms != float('inf') else 0,
            'max_latency_ms': self.metrics.max_latency_ms,
            'p95_latency_ms': self.metrics.p95_latency_ms,
            'p99_latency_ms': self.metrics.p99_latency_ms,
            'throughput_per_sec': throughput,
            'model_name': os.path.basename(self.model_path),
            'providers': self.session.get_providers() if self.session else ['NumPy (fallback)'],
        }


# Singleton registry
_model_registry = {}


async def get_onnx_engine(model_name='behavioral_dna', models_dir='models', **kwargs):
    """Get or create ONNX inference engine singleton"""
    global _model_registry
    
    if model_name not in _model_registry:
        model_path = os.path.join(models_dir, f"{model_name}.onnx")
        if not os.path.exists(model_path):
            # Create dummy model for testing
            logger.warning(f"Model not found: {model_path}, using dummy")
            os.makedirs(models_dir, exist_ok=True)
            _create_dummy_model(model_path)
        
        _model_registry[model_name] = ONNXInferenceEngine(model_path, **kwargs)
    
    return _model_registry[model_name]


def _create_dummy_model(model_path):
    """Create a dummy ONNX model for testing"""
    try:
        import torch
        import torch.nn as nn
        
        class DummyModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = nn.Linear(768, 4)
            
            def forward(self, x):
                return torch.sigmoid(self.fc(x))
        
        model = DummyModel()
        dummy_input = torch.randn(1, 768)
        torch.onnx.export(model, dummy_input, model_path, opset_version=17)
        logger.info(f"Created dummy model: {model_path}")
        
    except ImportError:
        logger.error("Cannot create dummy model: PyTorch not installed")


def reset_engine(model_name=None):
    """Reset inference engine(s)"""
    global _model_registry
    if model_name:
        if model_name in _model_registry:
            del _model_registry[model_name]
    else:
        _model_registry.clear()
