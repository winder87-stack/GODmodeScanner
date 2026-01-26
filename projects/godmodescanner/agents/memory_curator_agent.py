#!/usr/bin/env python3
"""Memory Curator Agent - Manages memory consolidation and optimization for GODMODESCANNER."""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [MEMORY_CURATOR] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner/projects/godmodescanner'
sys.path.insert(0, project_root)

from agents.memory.enhanced_storage import EnhancedMemoryStorage
from agents.memory.consolidators.enhanced_consolidator import EnhancedMemoryConsolidator
from agents.memory.pattern_integration import MemoryPatternIntegration


class MemoryCuratorAgent:
    """Subordinate agent responsible for memory management and optimization."""

    def __init__(self):
        """Initialize the Memory Curator agent."""
        logger.info("🧠 Initializing Memory Curator Agent...")

        # Initialize memory components
        self.storage = EnhancedMemoryStorage(
            storage_path="/a0/usr/projects/godmodescanner/data/memory",
            embedding_model="all-MiniLM-L6-v2"
        )

        self.consolidator = EnhancedMemoryConsolidator(
            storage=self.storage,
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

        self.integration = MemoryPatternIntegration(
            storage=self.storage,
            consolidator=self.consolidator
        )

        self.status_file = Path("/a0/usr/projects/godmodescanner/data/memory/curator_status.json")
        logger.info("✅ Memory Curator Agent initialized")

    async def run_health_check(self) -> dict:
        """Run memory system health check.

        Returns:
            Health check report
        """
        logger.info("🏥 Running memory health check...")

        # Get storage statistics
        storage_stats = self.storage.get_statistics()

        # Get consolidation metrics
        consolidation_metrics = self.consolidator.metrics.to_dict()

        # Check memory tiers
        tier_health = {
            'recent': len(self.storage.tier_to_ids.get('recent', [])),
            'medium': len(self.storage.tier_to_ids.get('medium', [])),
            'historical': len(self.storage.tier_to_ids.get('historical', []))
        }

        # Calculate health score
        total_memories = storage_stats['total_memories']
        health_score = 100.0

        # Deduct points for issues
        if total_memories > 10000:
            health_score -= 20  # Too many memories
        if consolidation_metrics['consolidations_performed'] == 0:
            health_score -= 10  # Never consolidated
        if consolidation_metrics.get('avg_accuracy_improvement', 0) < 0:
            health_score -= 15  # Declining accuracy

        health_report = {
            'timestamp': datetime.now().isoformat(),
            'health_score': max(0, health_score),
            'status': 'healthy' if health_score > 70 else 'degraded' if health_score > 40 else 'critical',
            'storage_stats': storage_stats,
            'consolidation_metrics': consolidation_metrics,
            'tier_distribution': tier_health,
            'recommendations': []
        }

        # Add recommendations
        if total_memories > 10000:
            health_report['recommendations'].append('Consider increasing consolidation frequency')
        if tier_health['historical'] > tier_health['recent'] * 2:
            health_report['recommendations'].append('Historical tier is growing - consider pruning')
        if consolidation_metrics.get('false_positives_removed', 0) > 100:
            health_report['recommendations'].append('High false positive rate - review pattern detection')

        logger.info(f"✅ Health check complete: {health_report['status']} (score: {health_score:.1f})")
        return health_report

    async def run_consolidation_cycle(self) -> dict:
        """Run a complete consolidation cycle.

        Returns:
            Consolidation report
        """
        logger.info("🔄 Starting consolidation cycle...")

        try:
            # Run consolidation
            consolidation_report = await self.consolidator.consolidate()

            # Run integration cycle
            integration_report = await self.integration.run_integration_cycle()

            # Combine reports
            combined_report = {
                'timestamp': datetime.now().isoformat(),
                'consolidation': consolidation_report,
                'integration': integration_report,
                'status': 'success'
            }

            logger.info("✅ Consolidation cycle complete")
            return combined_report

        except Exception as e:
            logger.error(f"❌ Error in consolidation cycle: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'error': str(e)
            }

    async def generate_performance_report(self) -> dict:
        """Generate comprehensive performance report.

        Returns:
            Performance report
        """
        logger.info("📊 Generating performance report...")

        # Get health check
        health_report = await self.run_health_check()

        # Get integration report
        integration_report = await self.integration.generate_integration_report()

        # Calculate performance metrics
        storage_stats = self.storage.get_statistics()
        consolidation_metrics = self.consolidator.metrics.to_dict()

        # Calculate memory efficiency
        total_memories = storage_stats['total_memories']
        patterns_merged = consolidation_metrics['patterns_merged']
        memory_efficiency = (patterns_merged / total_memories * 100) if total_memories > 0 else 0

        # Calculate detection accuracy improvement
        accuracy_improvements = consolidation_metrics.get('accuracy_improvements', [])
        avg_accuracy_improvement = sum(accuracy_improvements) / len(accuracy_improvements) if accuracy_improvements else 0

        performance_report = {
            'timestamp': datetime.now().isoformat(),
            'system_health': health_report,
            'integration_status': integration_report,
            'performance_metrics': {
                'total_memories': total_memories,
                'memory_efficiency': f"{memory_efficiency:.2f}%",
                'consolidations_performed': consolidation_metrics['consolidations_performed'],
                'patterns_merged': patterns_merged,
                'false_positives_removed': consolidation_metrics['false_positives_removed'],
                'avg_accuracy_improvement': f"{avg_accuracy_improvement:.2%}",
                'embedding_dimension': storage_stats['embedding_dimension']
            },
            'tier_distribution': {
                'recent': storage_stats['by_tier'].get('recent', 0),
                'medium': storage_stats['by_tier'].get('medium', 0),
                'historical': storage_stats['by_tier'].get('historical', 0)
            },
            'memory_types': storage_stats['by_type'],
            'importance_distribution': storage_stats['by_importance']
        }

        # Save report
        report_path = Path("/a0/usr/projects/godmodescanner/data/memory/performance_report.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(performance_report, f, indent=2)

        logger.info("✅ Performance report generated")
        return performance_report

    async def run_maintenance(self):
        """Run routine maintenance tasks."""
        logger.info("🔧 Running maintenance tasks...")

        # Reorganize tiers
        await self.storage.reorganize_tiers()

        # Prune old memories
        await self.storage.prune_old_memories(max_age_days=30)

        # Sync with detection rules
        await self.integration.sync_with_detection_rules()

        logger.info("✅ Maintenance complete")

    async def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("👁️  Starting monitoring loop...")

        while True:
            try:
                # Update status
                status = {
                    'timestamp': datetime.now().isoformat(),
                    'status': 'running',
                    'last_health_check': None,
                    'last_consolidation': None
                }

                # Run health check every hour
                health_report = await self.run_health_check()
                status['last_health_check'] = health_report['timestamp']

                # Run consolidation if needed
                if await self.consolidator.should_consolidate():
                    consolidation_report = await self.run_consolidation_cycle()
                    status['last_consolidation'] = consolidation_report['timestamp']

                # Run maintenance every 6 hours
                if datetime.now().hour % 6 == 0:
                    await self.run_maintenance()

                # Save status
                self.status_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.status_file, 'w') as f:
                    json.dump(status, f, indent=2)

                # Sleep for 1 hour
                await asyncio.sleep(3600)

            except Exception as e:
                logger.error(f"❌ Error in monitoring loop: {e}")
                await asyncio.sleep(3600)

    async def run(self):
        """Run the Memory Curator agent."""
        logger.info("🚀 Starting Memory Curator Agent...")

        try:
            # Generate initial performance report
            initial_report = await self.generate_performance_report()
            logger.info(f"📊 Initial performance report generated")

            # Start monitoring loop
            await self.monitor_loop()

        except KeyboardInterrupt:
            logger.info("⏹️  Memory Curator Agent stopped by user")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            raise


if __name__ == "__main__":
    # Create and run the Memory Curator agent
    agent = MemoryCuratorAgent()
    asyncio.run(agent.run())
