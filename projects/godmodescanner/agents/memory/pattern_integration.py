"""Integration module connecting enhanced memory system with pattern learning."""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import json
from pathlib import Path

from agents.memory.enhanced_storage import EnhancedMemoryStorage
from agents.memory.consolidators.enhanced_consolidator import EnhancedMemoryConsolidator
from agents.memory.memory_models import Memory, MemoryType, MemoryImportance, MemoryQuery

logger = logging.getLogger(__name__)


class MemoryPatternIntegration:
    """Integrates enhanced memory system with pattern learning and adaptation."""

    def __init__(self, storage: EnhancedMemoryStorage, consolidator: EnhancedMemoryConsolidator):
        """Initialize the integration layer.

        Args:
            storage: Enhanced memory storage
            consolidator: Enhanced memory consolidator
        """
        self.storage = storage
        self.consolidator = consolidator
        self.pattern_weights_path = Path("/a0/usr/projects/godmodescanner/config/detection_rules.json")
        self.integration_log_path = Path("/a0/usr/projects/godmodescanner/data/memory/integration_log.json")

    async def feed_patterns_to_memory(self, pattern_weights: Dict[str, Any]):
        """Feed pattern learning results to memory system.

        Args:
            pattern_weights: Dictionary of pattern weights from pattern_learning_adaptation.py
        """
        logger.info("📥 Feeding pattern weights to memory system...")

        for pattern_name, weight_data in pattern_weights.items():
            # Create pattern memory
            memory_content = {
                'pattern_name': pattern_name,
                'current_weight': weight_data.get('current_weight', 1.0),
                'base_weight': weight_data.get('base_weight', 1.0),
                'adjustment_factor': weight_data.get('adjustment_factor', 1.0),
                'rug_correlation': weight_data.get('rug_correlation', 0.0),
                'dump_correlation': weight_data.get('dump_correlation', 0.0),
                'performance_history': weight_data.get('performance_history', []),
                'last_updated': datetime.now().isoformat()
            }

            # Determine importance based on correlation
            avg_correlation = (weight_data.get('rug_correlation', 0.0) + 
                             weight_data.get('dump_correlation', 0.0)) / 2

            if avg_correlation > 0.8:
                importance = MemoryImportance.CRITICAL
            elif avg_correlation > 0.6:
                importance = MemoryImportance.HIGH
            elif avg_correlation > 0.4:
                importance = MemoryImportance.MEDIUM
            else:
                importance = MemoryImportance.LOW

            # Create memory
            memory = Memory.create(
                memory_type=MemoryType.PATTERN,
                content=memory_content,
                importance=importance,
                tags=['pattern_weight', pattern_name, 'adaptive_learning']
            )
            memory.metadata.confidence = avg_correlation
            memory.metadata.source = 'pattern_learning_adaptation'

            # Store in memory system
            await self.storage.store(memory)

        logger.info(f"✅ Stored {len(pattern_weights)} pattern weights in memory")

    async def retrieve_consolidated_patterns(self) -> Dict[str, Any]:
        """Retrieve consolidated pattern memories for pattern learning.

        Returns:
            Dictionary of consolidated pattern data
        """
        logger.info("📤 Retrieving consolidated patterns from memory...")

        # Query pattern memories
        query = MemoryQuery(
            memory_types=[MemoryType.PATTERN],
            tags=['pattern_weight', 'adaptive_learning'],
            min_importance=MemoryImportance.LOW,
            limit=100
        )

        memories = await self.storage.query(query)

        # Convert to pattern weights format
        pattern_weights = {}
        for memory in memories:
            pattern_name = memory.content.get('pattern_name')
            if pattern_name:
                pattern_weights[pattern_name] = {
                    'current_weight': memory.content.get('current_weight', 1.0),
                    'base_weight': memory.content.get('base_weight', 1.0),
                    'adjustment_factor': memory.content.get('adjustment_factor', 1.0),
                    'rug_correlation': memory.content.get('rug_correlation', 0.0),
                    'dump_correlation': memory.content.get('dump_correlation', 0.0),
                    'confidence': memory.metadata.confidence,
                    'importance': memory.metadata.importance.name,
                    'access_count': memory.metadata.access_count,
                    'last_accessed': memory.metadata.last_accessed.isoformat()
                }

        logger.info(f"✅ Retrieved {len(pattern_weights)} consolidated patterns")
        return pattern_weights

    async def update_pattern_accuracy(self, pattern_name: str, was_correct: bool, 
                                     detection_details: Optional[Dict[str, Any]] = None):
        """Update pattern accuracy based on detection results.

        Args:
            pattern_name: Name of the pattern
            was_correct: Whether the detection was correct
            detection_details: Optional details about the detection
        """
        logger.info(f"📊 Updating accuracy for pattern: {pattern_name}")

        # Find pattern memory
        query = MemoryQuery(
            memory_types=[MemoryType.PATTERN],
            tags=['pattern_weight', pattern_name],
            limit=1
        )

        memories = await self.storage.query(query)
        if not memories:
            logger.warning(f"Pattern memory not found: {pattern_name}")
            return

        memory = memories[0]

        # Update confidence
        if was_correct:
            memory.metadata.confidence = min(1.0, memory.metadata.confidence * 1.1)
            adjustment = 1.1
        else:
            memory.metadata.confidence = max(0.0, memory.metadata.confidence * 0.9)
            adjustment = 0.9

        # Update weight
        current_weight = memory.content.get('current_weight', 1.0)
        memory.content['current_weight'] = current_weight * adjustment
        memory.content['adjustment_factor'] = memory.content.get('adjustment_factor', 1.0) * adjustment

        # Add to performance history
        if 'performance_history' not in memory.content:
            memory.content['performance_history'] = []
        memory.content['performance_history'].append({
            'timestamp': datetime.now().isoformat(),
            'was_correct': was_correct,
            'confidence': memory.metadata.confidence,
            'details': detection_details
        })

        # Update importance
        if memory.metadata.confidence > 0.8:
            memory.metadata.importance = MemoryImportance.CRITICAL
        elif memory.metadata.confidence > 0.6:
            memory.metadata.importance = MemoryImportance.HIGH
        elif memory.metadata.confidence > 0.4:
            memory.metadata.importance = MemoryImportance.MEDIUM
        else:
            memory.metadata.importance = MemoryImportance.LOW

        # Update consolidator metrics
        await self.consolidator.update_pattern_accuracy(memory.memory_id, was_correct)

        logger.info(f"✅ Updated pattern {pattern_name}: confidence={memory.metadata.confidence:.2f}")

    async def sync_with_detection_rules(self):
        """Synchronize memory patterns with detection_rules.json."""
        logger.info("🔄 Synchronizing with detection_rules.json...")

        # Load current detection rules
        if self.pattern_weights_path.exists():
            with open(self.pattern_weights_path, 'r') as f:
                detection_rules = json.load(f)
        else:
            detection_rules = {'patterns': {}}

        # Get consolidated patterns from memory
        consolidated_patterns = await self.retrieve_consolidated_patterns()

        # Update detection rules with consolidated patterns
        for pattern_name, pattern_data in consolidated_patterns.items():
            if pattern_name not in detection_rules['patterns']:
                detection_rules['patterns'][pattern_name] = {}

            detection_rules['patterns'][pattern_name].update({
                'weight': pattern_data['current_weight'],
                'confidence': pattern_data['confidence'],
                'importance': pattern_data['importance'],
                'last_updated': datetime.now().isoformat(),
                'source': 'memory_consolidation'
            })

        # Save updated detection rules
        self.pattern_weights_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pattern_weights_path, 'w') as f:
            json.dump(detection_rules, f, indent=2)

        logger.info(f"✅ Synchronized {len(consolidated_patterns)} patterns with detection_rules.json")

    async def generate_integration_report(self) -> Dict[str, Any]:
        """Generate integration performance report.

        Returns:
            Integration report
        """
        logger.info("📊 Generating integration report...")

        # Get storage statistics
        storage_stats = self.storage.get_statistics()

        # Get consolidation metrics
        consolidation_metrics = self.consolidator.metrics.to_dict()

        # Get pattern memories
        pattern_query = MemoryQuery(
            memory_types=[MemoryType.PATTERN],
            tags=['pattern_weight'],
            limit=1000
        )
        pattern_memories = await self.storage.query(pattern_query)

        # Calculate pattern statistics
        pattern_stats = {
            'total_patterns': len(pattern_memories),
            'high_confidence_patterns': sum(1 for m in pattern_memories if m.metadata.confidence > 0.7),
            'critical_patterns': sum(1 for m in pattern_memories if m.metadata.importance == MemoryImportance.CRITICAL),
            'avg_confidence': sum(m.metadata.confidence for m in pattern_memories) / len(pattern_memories) if pattern_memories else 0.0,
            'avg_access_count': sum(m.metadata.access_count for m in pattern_memories) / len(pattern_memories) if pattern_memories else 0.0
        }

        report = {
            'timestamp': datetime.now().isoformat(),
            'storage_statistics': storage_stats,
            'consolidation_metrics': consolidation_metrics,
            'pattern_statistics': pattern_stats,
            'integration_status': 'operational'
        }

        # Save report
        self.integration_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.integration_log_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info("✅ Integration report generated")
        return report

    async def run_integration_cycle(self):
        """Run a complete integration cycle."""
        logger.info("🔄 Starting integration cycle...")

        try:
            # Step 1: Sync with detection rules
            await self.sync_with_detection_rules()

            # Step 2: Run consolidation if needed
            if await self.consolidator.should_consolidate():
                consolidation_report = await self.consolidator.consolidate()
                logger.info(f"Consolidation complete: {consolidation_report['patterns_merged']} patterns merged")

            # Step 3: Generate integration report
            report = await self.generate_integration_report()

            logger.info("✅ Integration cycle complete")
            return report

        except Exception as e:
            logger.error(f"❌ Error in integration cycle: {e}")
            raise

    async def auto_integration_loop(self):
        """Run automatic integration loop."""
        while True:
            try:
                await self.run_integration_cycle()
                # Sleep for 6 hours
                await asyncio.sleep(21600)
            except Exception as e:
                logger.error(f"❌ Error in auto-integration loop: {e}")
                await asyncio.sleep(3600)
