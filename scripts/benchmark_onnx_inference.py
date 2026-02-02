#!/usr/bin/env python3
"""
Benchmark ONNX Runtime Inference Performance

Validates sub-50ms inference latency target using TensorRT/CUDA optimization.

Usage:
    python scripts/benchmark_onnx_inference.py
    python scripts/benchmark_onnx_inference.py --model behavioral_dna --iterations 1000
"""

import sys
import os
import asyncio
import time
import argparse
import json
from datetime import datetime
from typing import List, Dict, Any

import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.ml.onnx_inference_engine import ONNXInferenceEngine, get_onnx_engine, ONNX_AVAILABLE


async def benchmark_single_inference(
    engine: ONNXInferenceEngine,
    num_iterations: int = 100
) -> Dict[str, Any]:
    """Benchmark single inference latency"""
    
    latencies = []
    
    print(f"Running {num_iterations} single inferences...")
    
    for i in range(num_iterations):
        # Generate random features
        features = np.random.randn(768).astype(np.float32)
        
        # Run inference
        result = await engine.predict(features)
        latencies.append(result.latency_ms)
        
        if (i + 1) % 20 == 0:
            print(f"  Completed {i + 1}/{num_iterations}")
    
    # Calculate statistics
    latencies = np.array(latencies)
    
    return {
        'avg_latency_ms': float(np.mean(latencies)),
        'min_latency_ms': float(np.min(latencies)),
        'max_latency_ms': float(np.max(latencies)),
        'p50_latency_ms': float(np.percentile(latencies, 50)),
        'p95_latency_ms': float(np.percentile(latencies, 95)),
        'p99_latency_ms': float(np.percentile(latencies, 99)),
        'std_latency_ms': float(np.std(latencies)),
        'total_iterations': num_iterations,
        'throughput_per_sec': 1000.0 / float(np.mean(latencies))
    }


async def benchmark_batch_inference(
    engine: ONNXInferenceEngine,
    batch_sizes: List[int] = [4, 8, 16, 32],
    iterations_per_batch: int = 10
) -> Dict[int, Dict[str, Any]]:
    """Benchmark batch inference performance"""
    
    results = {}
    
    print("\nBatch inference benchmarks:")
    
    for batch_size in batch_sizes:
        latencies = []
        
        for _ in range(iterations_per_batch):
            # Generate batch
            features_list = [
                np.random.randn(768).astype(np.float32)
                for _ in range(batch_size)
            ]
            
            # Run batch inference
            start = time.time()
            results_batch = await engine.batch_predict(features_list)
            latency_ms = (time.time() - start) * 1000
            
            latencies.append(latency_ms)
        
        latencies = np.array(latencies)
        
        results[batch_size] = {
            'avg_latency_ms': float(np.mean(latencies)),
            'avg_per_sample_ms': float(np.mean(latencies)) / batch_size,
            'throughput_per_sec': (batch_size * 1000.0) / float(np.mean(latencies))
        }
        
        print(f"  Batch {batch_size:2d}: {results[batch_size]['avg_latency_ms']:.2f}ms "
              f"({results[batch_size]['avg_per_sample_ms']:.2f}ms/sample, "
              f"{results[batch_size]['throughput_per_sec']:.0f} samples/sec)")
    
    return results


async def run_benchmark(
    model_name: str = 'behavioral_dna',
    num_iterations: int = 100,
    output_file: str = None
) -> Dict[str, Any]:
    """Run complete benchmark suite"""
    
    print("=" * 70)
    print("ONNX Runtime Inference Benchmark")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Model: {model_name}")
    print(f"  ONNX Available: {ONNX_AVAILABLE}")
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Initialize engine
    print("Initializing inference engine...")
    engine = await get_onnx_engine(model_name)
    
    # Get initial metrics
    initial_metrics = engine.get_metrics()
    print(f"  Active providers: {initial_metrics['providers']}")
    print()
    
    # Single inference benchmark
    single_results = await benchmark_single_inference(engine, num_iterations)
    
    # Batch inference benchmark
    batch_results = await benchmark_batch_inference(engine)
    
    # Final metrics
    final_metrics = engine.get_metrics()
    
    # Print results
    print("\n" + "=" * 70)
    print("SINGLE INFERENCE RESULTS")
    print("=" * 70)
    print(f"  Average latency:  {single_results['avg_latency_ms']:.2f}ms")
    print(f"  Min latency:      {single_results['min_latency_ms']:.2f}ms")
    print(f"  Max latency:      {single_results['max_latency_ms']:.2f}ms")
    print(f"  P50 latency:      {single_results['p50_latency_ms']:.2f}ms")
    print(f"  P95 latency:      {single_results['p95_latency_ms']:.2f}ms")
    print(f"  P99 latency:      {single_results['p99_latency_ms']:.2f}ms")
    print(f"  Std deviation:    {single_results['std_latency_ms']:.2f}ms")
    print(f"  Throughput:       {single_results['throughput_per_sec']:.0f} inf/sec")
    print()
    
    # Success criteria
    print("=" * 70)
    print("SUCCESS CRITERIA")
    print("=" * 70)
    
    target_latency = 50.0  # ms
    target_throughput = 1000.0  # per second
    
    criteria = [
        (f"P95 latency < {target_latency}ms", 
         single_results['p95_latency_ms'] < target_latency),
        (f"P99 latency < {target_latency * 2}ms", 
         single_results['p99_latency_ms'] < target_latency * 2),
        (f"Throughput > {target_throughput} inf/sec", 
         single_results['throughput_per_sec'] > target_throughput),
        ("ONNX Runtime available", ONNX_AVAILABLE),
    ]
    
    passed = 0
    for criterion, result in criteria:
        status = "PASS" if result else "FAIL"
        icon = "[OK]" if result else "[X]"
        print(f"  {icon} {criterion}: {status}")
        if result:
            passed += 1
    
    print(f"\nResult: {passed}/{len(criteria)} criteria passed")
    
    if not ONNX_AVAILABLE:
        print("\n" + "=" * 70)
        print("WARNING: Running in fallback mode (NumPy)")
        print("Install onnxruntime-gpu for TensorRT/CUDA acceleration:")
        print("  pip install onnxruntime-gpu")
        print("=" * 70)
    
    # Compile results
    full_results = {
        'timestamp': datetime.now().isoformat(),
        'model_name': model_name,
        'onnx_available': ONNX_AVAILABLE,
        'providers': final_metrics['providers'],
        'single_inference': single_results,
        'batch_inference': {str(k): v for k, v in batch_results.items()},
        'criteria_passed': passed,
        'criteria_total': len(criteria)
    }
    
    # Save results
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(full_results, f, indent=2)
        print(f"\nResults saved to: {output_file}")
    
    return full_results


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark ONNX Runtime inference performance'
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='behavioral_dna',
        help='Model name to benchmark'
    )
    parser.add_argument(
        '--iterations', '-i',
        type=int,
        default=100,
        help='Number of inference iterations'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/onnx_benchmark_results.json',
        help='Output file for results'
    )
    
    args = parser.parse_args()
    
    asyncio.run(run_benchmark(
        model_name=args.model,
        num_iterations=args.iterations,
        output_file=args.output
    ))


if __name__ == "__main__":
    main()
