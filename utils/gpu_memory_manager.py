"""
CUDA Memory Pool Management for Zero-Copy Transfers
Integrates with: GPU graph operations, FAISS GPU indexes
Purpose: Eliminate CPU<->GPU memory transfer overhead

Fallback: Uses NumPy when CUDA is not available
"""

import os
import logging
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)

# Try to import CUDA libraries
GPU_AVAILABLE = False
try:
    import cupy as cp
    import cudf
    GPU_AVAILABLE = True
    logger.info("CUDA libraries loaded successfully")
except ImportError:
    logger.warning("CUDA libraries not available, using CPU fallback")
    cp = None
    cudf = None


@dataclass
class GPUMetrics:
    """GPU memory and performance metrics"""
    total_allocated_bytes: int = 0
    peak_usage_bytes: int = 0
    allocation_count: int = 0
    deallocation_count: int = 0
    used_mb: float = 0.0
    total_mb: float = 0.0
    utilization_pct: float = 0.0
    device_name: str = "CPU (fallback)"
    gpu_available: bool = False


class GPUMemoryManager:
    """
    Manages GPU memory pools for:
    - Graph data structures
    - FAISS indexes
    - Tensor operations

    Automatically falls back to CPU/NumPy when GPU is not available.
    """

    def __init__(self, max_memory_gb: float = 8.0):
        self.max_memory_gb = max_memory_gb
        self.max_bytes = int(max_memory_gb * 1024**3)
        self.gpu_available = GPU_AVAILABLE

        # Pre-allocated buffers
        self.graph_buffer: Optional[Union[np.ndarray, Any]] = None
        self.embedding_buffer: Optional[Union[np.ndarray, Any]] = None

        # Statistics
        self.metrics = GPUMetrics()

        if self.gpu_available:
            self._init_gpu()
        else:
            self._init_cpu_fallback()

    def _init_gpu(self):
        """Initialize GPU memory pools"""
        try:
            # Get default memory pool
            self.pool = cp.get_default_memory_pool()
            self.pinned_pool = cp.get_default_pinned_memory_pool()

            # Set memory limit
            self.pool.set_limit(size=self.max_bytes)

            # Get device info
            device = cp.cuda.Device()
            self.metrics.device_name = device.name if hasattr(device, 'name') else f"GPU {device.id}"
            self.metrics.gpu_available = True

            logger.info(
                f"GPU Memory Manager initialized: {self.metrics.device_name}, "
                f"max {self.max_memory_gb}GB"
            )
        except Exception as e:
            logger.error(f"GPU initialization failed: {e}, falling back to CPU")
            self.gpu_available = False
            self._init_cpu_fallback()

    def _init_cpu_fallback(self):
        """Initialize CPU fallback mode"""
        self.pool = None
        self.pinned_pool = None
        self.metrics.device_name = "CPU (NumPy fallback)"
        self.metrics.gpu_available = False

        logger.info(
            f"GPU Memory Manager initialized in CPU fallback mode, "
            f"max {self.max_memory_gb}GB"
        )

    def preallocate_graph_buffer(self, max_edges: int = 1_000_000):
        """Pre-allocate buffer for graph edge data"""
        # 3 columns (src, dst, weight) x max_edges x 8 bytes (float64)
        buffer_size = 3 * max_edges

        if self.gpu_available:
            self.graph_buffer = cp.empty(buffer_size, dtype=cp.float64)
        else:
            self.graph_buffer = np.empty(buffer_size, dtype=np.float64)

        size_mb = buffer_size * 8 / 1024**2
        logger.info(
            f"Pre-allocated graph buffer: max_edges={max_edges:,}, "
            f"size={size_mb:.1f}MB, device={'GPU' if self.gpu_available else 'CPU'}"
        )

    def preallocate_embedding_buffer(self, max_vectors: int = 10_000_000, dims: int = 768):
        """Pre-allocate buffer for embeddings"""
        buffer_size = max_vectors * dims

        if self.gpu_available:
            self.embedding_buffer = cp.empty(buffer_size, dtype=cp.float32)
        else:
            self.embedding_buffer = np.empty(buffer_size, dtype=np.float32)

        size_mb = buffer_size * 4 / 1024**2  # float32 = 4 bytes
        logger.info(
            f"Pre-allocated embedding buffer: max_vectors={max_vectors:,}, "
            f"dims={dims}, size={size_mb:.1f}MB"
        )

    def allocate_array(self, shape: tuple, dtype=np.float64) -> Union[np.ndarray, Any]:
        """Allocate array on GPU or CPU"""
        if self.gpu_available:
            arr = cp.zeros(shape, dtype=dtype)
        else:
            arr = np.zeros(shape, dtype=dtype)

        self.metrics.allocation_count += 1
        size_bytes = np.prod(shape) * np.dtype(dtype).itemsize
        self.metrics.total_allocated_bytes += size_bytes

        return arr

    def to_gpu(self, array: np.ndarray) -> Union[np.ndarray, Any]:
        """Transfer NumPy array to GPU (or return as-is if no GPU)"""
        if self.gpu_available:
            return cp.asarray(array)
        return array

    def to_cpu(self, array: Union[np.ndarray, Any]) -> np.ndarray:
        """Transfer GPU array to CPU (or return as-is if already NumPy)"""
        if self.gpu_available and hasattr(array, 'get'):
            return array.get()
        return np.asarray(array)

    def create_dataframe(self, data: Dict[str, Any]) -> Any:
        """Create DataFrame on GPU or CPU"""
        if self.gpu_available:
            import cudf
            return cudf.DataFrame(data)
        else:
            import pandas as pd
            return pd.DataFrame(data)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get current memory statistics"""
        if self.gpu_available and self.pool is not None:
            used_bytes = self.pool.used_bytes()
            total_bytes = self.pool.total_bytes()

            self.metrics.used_mb = used_bytes / 1024**2
            self.metrics.total_mb = total_bytes / 1024**2
            self.metrics.peak_usage_bytes = max(
                self.metrics.peak_usage_bytes,
                used_bytes
            )
            self.metrics.utilization_pct = (used_bytes / self.max_bytes) * 100
        else:
            # CPU fallback - estimate from allocated arrays
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            self.metrics.used_mb = mem_info.rss / 1024**2
            self.metrics.total_mb = psutil.virtual_memory().total / 1024**2
            self.metrics.utilization_pct = psutil.virtual_memory().percent

        return {
            'used_mb': self.metrics.used_mb,
            'total_mb': self.metrics.total_mb,
            'peak_mb': self.metrics.peak_usage_bytes / 1024**2,
            'utilization_pct': self.metrics.utilization_pct,
            'device_name': self.metrics.device_name,
            'gpu_available': self.metrics.gpu_available,
            'allocation_count': self.metrics.allocation_count,
            'deallocation_count': self.metrics.deallocation_count,
            'total_allocated_bytes': self.metrics.total_allocated_bytes
        }

    def clear_memory(self):
        """Clear all GPU memory"""
        if self.gpu_available and self.pool is not None:
            self.pool.free_all_blocks()
            if self.pinned_pool:
                self.pinned_pool.free_all_blocks()
            logger.info("GPU memory cleared")
        else:
            # Force garbage collection for CPU
            import gc
            gc.collect()
            logger.info("CPU memory garbage collected")

        self.metrics.deallocation_count += 1

    def synchronize(self):
        """Synchronize GPU operations"""
        if self.gpu_available:
            cp.cuda.Stream.null.synchronize()


# Singleton instance
_gpu_memory_manager: Optional[GPUMemoryManager] = None


def get_gpu_memory_manager(max_memory_gb: float = 8.0) -> GPUMemoryManager:
    """Get or create GPU memory manager singleton"""
    global _gpu_memory_manager
    if _gpu_memory_manager is None:
        _gpu_memory_manager = GPUMemoryManager(max_memory_gb=max_memory_gb)
    return _gpu_memory_manager


def is_gpu_available() -> bool:
    """Check if GPU is available"""
    return GPU_AVAILABLE
