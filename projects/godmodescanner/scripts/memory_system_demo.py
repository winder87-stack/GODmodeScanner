#!/usr/bin/env python3
"""Demonstration and Performance Reporting for Enhanced Memory System."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [DEMO] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner/projects/godmodescanner'
sys.path.insert(0, project_root)

from agents.memory.enhanced_storage import EnhancedMemoryStorage
from agents.memory.consolidators.enhanced_consolidator import EnhancedMemoryConsolidator
from agents.memory.pattern_integration import MemoryPatternIntegration
from agents.memory.memory_models import Memory, MemoryType, MemoryImportance


async def create_sample_memories(storage: EnhancedMemoryStorage, count: int = 50):
    """Create sample memories for demonstration."""
    logger.info(f"Creating {count} sample memories...")

    pattern_types = [
        'daisy_chain_funding',
        'coordinated_buying',
        'wash_trading',
        'pump_and_dump',
        'sybil_network',
        'insider_trading'
    ]

    for i in range(count):
        # Create pattern memory
        pattern_type = pattern_types[i % len(pattern_types)]

        memory_content = {
            'pattern_type': pattern_type,
            'wallet_addresses': [f'wallet_{i}_{j}' for j in range(3)],
            'confidence': 0.5 + (i % 5) * 0.1,
            'occurrences': i % 10 + 1,
            'detected_at': (datetime.now() - timedelta(days=i % 30)).isoformat()
        }

        importance = MemoryImportance.CRITICAL if i % 4 == 0 else                     MemoryImportance.HIGH if i % 3 == 0 else                     MemoryImportance.MEDIUM

        memory = Memory.create(
            memory_type=MemoryType.PATTERN,
            content=memory_content,
            importance=importance,
            tags=['pattern_weight', pattern_type, 'demo']
        )
        memory.metadata.confidence = memory_content['confidence']

        await storage.store(memory)

    logger.info(f"✅ Created {count} sample memories")


async def generate_before_metrics(storage: EnhancedMemoryStorage) -> dict:
    """Generate metrics before consolidation."""
    logger.info("📊 Generating BEFORE metrics...")

    stats = storage.get_statistics()

    # Calculate pattern distribution
    pattern_memories = [m for m in storage.memories.values() if m.memory_type == MemoryType.PATTERN]

    avg_confidence = sum(m.metadata.confidence for m in pattern_memories) / len(pattern_memories) if pattern_memories else 0

    before_metrics = {
        'timestamp': datetime.now().isoformat(),
        'total_memories': stats['total_memories'],
        'pattern_memories': len(pattern_memories),
        'avg_confidence': avg_confidence,
        'tier_distribution': stats['by_tier'],
        'importance_distribution': stats['by_importance'],
        'memory_types': stats['by_type']
    }

    logger.info(f"✅ BEFORE: {before_metrics['total_memories']} memories, avg confidence: {avg_confidence:.2f}")
    return before_metrics


async def generate_after_metrics(storage: EnhancedMemoryStorage, consolidator: EnhancedMemoryConsolidator) -> dict:
    """Generate metrics after consolidation."""
    logger.info("📊 Generating AFTER metrics...")

    stats = storage.get_statistics()
    consolidation_metrics = consolidator.metrics.to_dict()

    # Calculate pattern distribution
    pattern_memories = [m for m in storage.memories.values() if m.memory_type == MemoryType.PATTERN]

    avg_confidence = sum(m.metadata.confidence for m in pattern_memories) / len(pattern_memories) if pattern_memories else 0

    after_metrics = {
        'timestamp': datetime.now().isoformat(),
        'total_memories': stats['total_memories'],
        'pattern_memories': len(pattern_memories),
        'avg_confidence': avg_confidence,
        'tier_distribution': stats['by_tier'],
        'importance_distribution': stats['by_importance'],
        'memory_types': stats['by_type'],
        'consolidation_metrics': consolidation_metrics
    }

    logger.info(f"✅ AFTER: {after_metrics['total_memories']} memories, avg confidence: {avg_confidence:.2f}")
    return after_metrics


async def generate_comparison_report(before: dict, after: dict) -> dict:
    """Generate comparison report."""
    logger.info("📊 Generating comparison report...")

    # Calculate improvements
    memory_reduction = before['total_memories'] - after['total_memories']
    memory_reduction_pct = (memory_reduction / before['total_memories'] * 100) if before['total_memories'] > 0 else 0

    confidence_improvement = after['avg_confidence'] - before['avg_confidence']
    confidence_improvement_pct = (confidence_improvement / before['avg_confidence'] * 100) if before['avg_confidence'] > 0 else 0

    comparison_report = {
        'timestamp': datetime.now().isoformat(),
        'before_metrics': before,
        'after_metrics': after,
        'improvements': {
            'memory_reduction': memory_reduction,
            'memory_reduction_percentage': f"{memory_reduction_pct:.2f}%",
            'confidence_improvement': confidence_improvement,
            'confidence_improvement_percentage': f"{confidence_improvement_pct:.2f}%",
            'patterns_merged': after['consolidation_metrics']['patterns_merged'],
            'false_positives_removed': after['consolidation_metrics']['false_positives_removed']
        },
        'performance_summary': {
            'consolidations_performed': after['consolidation_metrics']['consolidations_performed'],
            'avg_accuracy_improvement': after['consolidation_metrics']['avg_accuracy_improvement'],
            'memory_efficiency': f"{(after['consolidation_metrics']['patterns_merged'] / before['total_memories'] * 100):.2f}%" if before['total_memories'] > 0 else '0%'
        }
    }

    logger.info("✅ Comparison report generated")
    return comparison_report


async def main():
    """Main demonstration function."""
    logger.info("🚀 Starting Enhanced Memory System Demonstration...")
    logger.info("="*80)

    # Initialize components
    logger.info("
📦 Initializing memory components...")
    storage = EnhancedMemoryStorage(
        storage_path="/a0/usr/projects/godmodescanner/data/memory",
        embedding_model="all-MiniLM-L6-v2"
    )

    consolidator = EnhancedMemoryConsolidator(
        storage=storage,
        config={
            'consolidation_interval_hours': 24,
            'similarity_threshold': 0.85,
            'min_cluster_size': 2,
            'max_age_days': 30,
            'false_positive_threshold': 0.3,
            'pattern_weight_decay': 0.95,
            'auto_consolidation_enabled': True
        }
    )

    integration = MemoryPatternIntegration(
        storage=storage,
        consolidator=consolidator
    )

    # Create sample memories
    logger.info("
📝 Creating sample memories...")
    await create_sample_memories(storage, count=50)

    # Generate BEFORE metrics
    logger.info("
📊 Generating BEFORE metrics...")
    before_metrics = await generate_before_metrics(storage)

    # Run consolidation
    logger.info("
🔄 Running memory consolidation...")
    consolidation_report = await consolidator.consolidate()

    # Generate AFTER metrics
    logger.info("
📊 Generating AFTER metrics...")
    after_metrics = await generate_after_metrics(storage, consolidator)

    # Generate comparison report
    logger.info("
📊 Generating comparison report...")
    comparison_report = await generate_comparison_report(before_metrics, after_metrics)

    # Generate integration report
    logger.info("
📊 Generating integration report...")
    integration_report = await integration.generate_integration_report()

    # Save all reports
    reports_dir = Path("/a0/usr/projects/godmodescanner/data/memory/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Save comparison report
    with open(reports_dir / "comparison_report.json", 'w') as f:
        json.dump(comparison_report, f, indent=2)

    # Save consolidation report
    with open(reports_dir / "consolidation_report.json", 'w') as f:
        json.dump(consolidation_report, f, indent=2)

    # Save integration report
    with open(reports_dir / "integration_report.json", 'w') as f:
        json.dump(integration_report, f, indent=2)

    # Print summary
    logger.info("
" + "="*80)
    logger.info("📊 PERFORMANCE SUMMARY")
    logger.info("="*80)
    logger.info(f"
🎯 Memory Optimization:")
    logger.info(f"  • Memory Reduction: {comparison_report['improvements']['memory_reduction']} memories ({comparison_report['improvements']['memory_reduction_percentage']})")
    logger.info(f"  • Patterns Merged: {comparison_report['improvements']['patterns_merged']}")
    logger.info(f"  • False Positives Removed: {comparison_report['improvements']['false_positives_removed']}")

    logger.info(f"
📈 Detection Accuracy:")
    logger.info(f"  • Confidence Improvement: {comparison_report['improvements']['confidence_improvement']:.4f} ({comparison_report['improvements']['confidence_improvement_percentage']})")
    logger.info(f"  • Average Accuracy Improvement: {comparison_report['performance_summary']['avg_accuracy_improvement']}")

    logger.info(f"
⚡ Performance Metrics:")
    logger.info(f"  • Memory Efficiency: {comparison_report['performance_summary']['memory_efficiency']}")
    logger.info(f"  • Consolidations Performed: {comparison_report['performance_summary']['consolidations_performed']}")
    logger.info(f"  • Total Memories: {after_metrics['total_memories']}")
    logger.info(f"  • Pattern Memories: {after_metrics['pattern_memories']}")

    logger.info(f"
💾 Reports saved to: {reports_dir}")
    logger.info("  • comparison_report.json")
    logger.info("  • consolidation_report.json")
    logger.info("  • integration_report.json")

    logger.info("
✅ Demonstration complete!")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(main())
