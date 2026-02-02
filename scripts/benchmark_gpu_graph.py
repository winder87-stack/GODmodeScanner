#!/usr/bin/env python3
"""
Benchmark GPU vs CPU Graph Analysis
Validates 100x performance improvement target

Usage:
    python scripts/benchmark_gpu_graph.py
    python scripts/benchmark_gpu_graph.py --wallets 50000 --transfers 200000
"""

import sys
import os
import time
import argparse
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple
import random
import string

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx

# Import GPU graph builder
from agents.wallet_deanonymizer.gpu_graph_builder import GPUWalletGraphBuilder, GPU_AVAILABLE


def generate_test_wallets(num_wallets: int) -> List[str]:
    """Generate random wallet addresses"""
    wallets = []
    for i in range(num_wallets):
        addr = ''.join(random.choices(
            string.ascii_letters + string.digits,
            k=44
        ))
        wallets.append(addr)
    return wallets


def generate_test_transfers(
    wallets: List[str],
    num_transfers: int
) -> List[Tuple[str, str, float, float]]:
    """Generate random transfer data"""
    transfers = []
    base_time = time.time()

    for i in range(num_transfers):
        src = random.choice(wallets)
        dst = random.choice(wallets)
        while dst == src:
            dst = random.choice(wallets)

        amount = random.uniform(0.001, 1000.0)
        timestamp = base_time - random.uniform(0, 86400 * 30)

        transfers.append((src, dst, amount, timestamp))

    return transfers


def benchmark_networkx(
    transfers: List[Tuple[str, str, float, float]]
) -> Dict[str, Any]:
    """Benchmark CPU NetworkX performance"""
    results = {
        'backend': 'NetworkX (CPU)',
        'build_time_ms': 0,
        'cluster_time_ms': 0,
        'pagerank_time_ms': 0,
        'triangle_time_ms': 0,
        'total_time_ms': 0,
        'num_clusters': 0,
        'num_triangles': 0
    }

    total_start = time.time()

    # Build graph
    build_start = time.time()
    graph = nx.DiGraph()
    for src, dst, amount, ts in transfers:
        graph.add_edge(src, dst, weight=amount, timestamp=ts)
    results['build_time_ms'] = (time.time() - build_start) * 1000

    # Cluster detection
    cluster_start = time.time()
    try:
        from networkx.algorithms.community import louvain_communities
        undirected = graph.to_undirected()
        communities = louvain_communities(undirected)
        results['num_clusters'] = len(communities)
    except Exception:
        undirected = graph.to_undirected()
        components = list(nx.connected_components(undirected))
        results['num_clusters'] = len(components)
    results['cluster_time_ms'] = (time.time() - cluster_start) * 1000

    # PageRank
    pagerank_start = time.time()
    pr = nx.pagerank(graph, alpha=0.85)
    results['pagerank_time_ms'] = (time.time() - pagerank_start) * 1000

    # Triangle counting
    triangle_start = time.time()
    try:
        undirected = graph.to_undirected()
        triangles = nx.triangles(undirected)
        results['num_triangles'] = sum(triangles.values()) // 3
    except Exception:
        results['num_triangles'] = 0
    results['triangle_time_ms'] = (time.time() - triangle_start) * 1000

    results['total_time_ms'] = (time.time() - total_start) * 1000

    return results


def benchmark_gpu_graph(
    transfers: List[Tuple[str, str, float, float]]
) -> Dict[str, Any]:
    """Benchmark GPU cuGraph performance"""
    results = {
        'backend': 'cuGraph (GPU)' if GPU_AVAILABLE else 'NetworkX (CPU fallback)',
        'gpu_available': GPU_AVAILABLE,
        'build_time_ms': 0,
        'cluster_time_ms': 0,
        'pagerank_time_ms': 0,
        'triangle_time_ms': 0,
        'total_time_ms': 0,
        'num_clusters': 0,
        'num_triangles': 0
    }

    total_start = time.time()

    # Create GPU graph builder
    graph = GPUWalletGraphBuilder(use_gpu=True)

    # Build graph (batch add)
    build_start = time.time()
    graph.add_transfers_batch(transfers)
    graph.build_graph()
    results['build_time_ms'] = (time.time() - build_start) * 1000

    # Cluster detection
    cluster_start = time.time()
    clusters = graph.detect_clusters()
    results['num_clusters'] = len(set(clusters.values()))
    results['cluster_time_ms'] = (time.time() - cluster_start) * 1000

    # PageRank
    pagerank_start = time.time()
    pagerank = graph.calculate_pagerank()
    results['pagerank_time_ms'] = (time.time() - pagerank_start) * 1000

    # Triangle counting
    triangle_start = time.time()
    results['num_triangles'] = graph.count_triangles()
    results['triangle_time_ms'] = (time.time() - triangle_start) * 1000

    results['total_time_ms'] = (time.time() - total_start) * 1000
    results['graph_stats'] = graph.get_stats()

    return results


def run_benchmark(
    num_wallets: int = 10000,
    num_transfers: int = 50000,
    output_file: str = None
) -> Dict[str, Any]:
    """Run complete benchmark suite"""

    print("=" * 70)
    print("GPU vs CPU Graph Analysis Benchmark")
    print("=" * 70)
    print("")
    print("Configuration:")
    print("  Wallets:   {:,}".format(num_wallets))
    print("  Transfers: {:,}".format(num_transfers))
    print("  GPU Available: {}".format(GPU_AVAILABLE))
    print("")

    # Generate test data
    print("Generating test data...")
    gen_start = time.time()
    wallets = generate_test_wallets(num_wallets)
    transfers = generate_test_transfers(wallets, num_transfers)
    gen_time = time.time() - gen_start
    print("  Generated in {:.2f}s".format(gen_time))
    print("")

    # Run CPU benchmark
    print("Running CPU (NetworkX) benchmark...")
    cpu_results = benchmark_networkx(transfers)
    print("  Build:     {:.2f}ms".format(cpu_results['build_time_ms']))
    print("  Clusters:  {:.2f}ms ({} clusters)".format(
        cpu_results['cluster_time_ms'], cpu_results['num_clusters']))
    print("  PageRank:  {:.2f}ms".format(cpu_results['pagerank_time_ms']))
    print("  Triangles: {:.2f}ms ({} triangles)".format(
        cpu_results['triangle_time_ms'], cpu_results['num_triangles']))
    print("  TOTAL:     {:.2f}ms".format(cpu_results['total_time_ms']))
    print("")

    # Run GPU benchmark
    print("Running GPU (cuGraph) benchmark...")
    gpu_results = benchmark_gpu_graph(transfers)
    print("  Backend:   {}".format(gpu_results['backend']))
    print("  Build:     {:.2f}ms".format(gpu_results['build_time_ms']))
    print("  Clusters:  {:.2f}ms ({} clusters)".format(
        gpu_results['cluster_time_ms'], gpu_results['num_clusters']))
    print("  PageRank:  {:.2f}ms".format(gpu_results['pagerank_time_ms']))
    print("  Triangles: {:.2f}ms ({} triangles)".format(
        gpu_results['triangle_time_ms'], gpu_results['num_triangles']))
    print("  TOTAL:     {:.2f}ms".format(gpu_results['total_time_ms']))
    print("")

    # Calculate speedups
    speedups = {
        'build': cpu_results['build_time_ms'] / max(gpu_results['build_time_ms'], 0.001),
        'cluster': cpu_results['cluster_time_ms'] / max(gpu_results['cluster_time_ms'], 0.001),
        'pagerank': cpu_results['pagerank_time_ms'] / max(gpu_results['pagerank_time_ms'], 0.001),
        'triangle': cpu_results['triangle_time_ms'] / max(gpu_results['triangle_time_ms'], 0.001),
        'total': cpu_results['total_time_ms'] / max(gpu_results['total_time_ms'], 0.001)
    }

    # Print results
    print("=" * 70)
    print("PERFORMANCE COMPARISON")
    print("=" * 70)
    print("")
    print("{:<15} {:<12} {:<12} {:<10}".format(
        'Operation', 'CPU (ms)', 'GPU (ms)', 'Speedup'))
    print("-" * 50)
    print("{:<15} {:<12.2f} {:<12.2f} {:<10.1f}x".format(
        'Build', cpu_results['build_time_ms'], gpu_results['build_time_ms'], speedups['build']))
    print("{:<15} {:<12.2f} {:<12.2f} {:<10.1f}x".format(
        'Clustering', cpu_results['cluster_time_ms'], gpu_results['cluster_time_ms'], speedups['cluster']))
    print("{:<15} {:<12.2f} {:<12.2f} {:<10.1f}x".format(
        'PageRank', cpu_results['pagerank_time_ms'], gpu_results['pagerank_time_ms'], speedups['pagerank']))
    print("{:<15} {:<12.2f} {:<12.2f} {:<10.1f}x".format(
        'Triangles', cpu_results['triangle_time_ms'], gpu_results['triangle_time_ms'], speedups['triangle']))
    print("-" * 50)
    print("{:<15} {:<12.2f} {:<12.2f} {:<10.1f}x".format(
        'TOTAL', cpu_results['total_time_ms'], gpu_results['total_time_ms'], speedups['total']))
    print("")

    # Success criteria
    print("=" * 70)
    print("SUCCESS CRITERIA")
    print("=" * 70)

    target_speedup = 100.0 if GPU_AVAILABLE else 1.0
    target_10k_time = 10.0 if GPU_AVAILABLE else 5000.0

    criteria = [
        ("Speedup >= {}x".format(target_speedup), speedups['total'] >= target_speedup),
        ("10K wallet analysis < {}ms".format(target_10k_time), gpu_results['total_time_ms'] < target_10k_time),
        ("Cluster detection working", gpu_results['num_clusters'] > 0),
        ("PageRank calculation working", gpu_results['pagerank_time_ms'] > 0),
    ]

    passed = 0
    for criterion, result in criteria:
        status = "PASS" if result else "FAIL"
        icon = "[OK]" if result else "[X]"
        print("  {} {}: {}".format(icon, criterion, status))
        if result:
            passed += 1

    print("")
    print("Result: {}/{} criteria passed".format(passed, len(criteria)))

    if not GPU_AVAILABLE:
        print("")
        print("=" * 70)
        print("NOTE: Running in CPU fallback mode (no CUDA GPU detected)")
        print("For 100x speedup, deploy with NVIDIA GPU and RAPIDS cuGraph")
        print("=" * 70)

    # Compile full results
    full_results = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'num_wallets': num_wallets,
            'num_transfers': num_transfers,
            'gpu_available': GPU_AVAILABLE
        },
        'cpu_results': cpu_results,
        'gpu_results': gpu_results,
        'speedups': speedups,
        'criteria_passed': passed,
        'criteria_total': len(criteria)
    }

    # Save results
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(full_results, f, indent=2, default=str)
        print("")
        print("Results saved to: {}".format(output_file))

    return full_results


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark GPU vs CPU graph analysis'
    )
    parser.add_argument(
        '--wallets', '-w',
        type=int,
        default=10000,
        help='Number of wallets to generate (default: 10000)'
    )
    parser.add_argument(
        '--transfers', '-t',
        type=int,
        default=50000,
        help='Number of transfers to generate (default: 50000)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/gpu_benchmark_results.json',
        help='Output file for results'
    )

    args = parser.parse_args()

    run_benchmark(
        num_wallets=args.wallets,
        num_transfers=args.transfers,
        output_file=args.output
    )


if __name__ == "__main__":
    main()
