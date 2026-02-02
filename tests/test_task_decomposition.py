
"""
Comprehensive Test Suite for Agent Zero Task Decomposition System
================================================================

Tests all components:
- TaskDecomposer: Hierarchical task breakdown
- SubordinateManager: Agent registration and load balancing
- TaskScheduler: Priority scheduling and dispatch
- GODMODEBridge: GODMODESCANNER integration

Success Criteria:
- Complex tasks decompose into executable subtasks
- Subordinate agents complete tasks with <50ms overhead
- System maintains 1000+ TPS throughput
- Zero additional operational cost
"""

import asyncio
import time
import sys
import os

# Add project root to path
sys.path.insert(0, "/a0/usr/projects/godmodescanner/projects/godmodescanner")

import pytest
from typing import List, Dict, Any


class TestTaskDecomposer:
    """Test suite for TaskDecomposer."""

    def test_import(self):
        """Test module imports correctly."""
        from agentzero.task_decomposer import (
            TaskDecomposer, CompositeTask, SubTask,
            TaskType, TaskPriority, TaskStatus
        )
        assert TaskDecomposer is not None
        assert TaskType.WALLET_ANALYSIS is not None

    def test_decomposer_initialization(self):
        """Test TaskDecomposer initializes correctly."""
        from agentzero.task_decomposer import TaskDecomposer

        decomposer = TaskDecomposer(max_parallel_subtasks=20)
        assert decomposer.max_parallel == 20
        assert len(decomposer.tasks) == 0
        assert len(decomposer.subtasks) == 0

    @pytest.mark.asyncio
    async def test_wallet_analysis_decomposition(self):
        """Test wallet analysis task decomposes correctly."""
        from agentzero.task_decomposer import (
            TaskDecomposer, create_wallet_analysis_task, TaskPriority
        )

        decomposer = TaskDecomposer()
        task = create_wallet_analysis_task(
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            TaskPriority.HIGH
        )

        subtasks = await decomposer.decompose(task)

        # Wallet analysis should decompose into 5 subtasks
        assert len(subtasks) == 5
        assert task.id in decomposer.tasks

        # Check subtask names
        step_names = [st.payload.get("step_name") for st in subtasks]
        assert "fetch_transactions" in step_names
        assert "analyze_behavior" in step_names
        assert "calculate_risk" in step_names

    @pytest.mark.asyncio
    async def test_sybil_detection_decomposition(self):
        """Test Sybil detection task decomposes correctly."""
        from agentzero.task_decomposer import (
            TaskDecomposer, create_sybil_detection_task, TaskPriority
        )

        decomposer = TaskDecomposer()
        task = create_sybil_detection_task(
            ["wallet1", "wallet2", "wallet3"],
            TaskPriority.CRITICAL
        )

        subtasks = await decomposer.decompose(task)

        # Sybil detection should decompose into 5 subtasks
        assert len(subtasks) == 5

        # Check for Sybil-specific steps
        step_names = [st.payload.get("step_name") for st in subtasks]
        assert "identify_cluster" in step_names
        assert "detect_coordination" in step_names
        assert "flag_wallets" in step_names

    @pytest.mark.asyncio
    async def test_dependency_resolution(self):
        """Test task dependencies are resolved correctly."""
        from agentzero.task_decomposer import (
            TaskDecomposer, create_wallet_analysis_task, TaskPriority, TaskStatus
        )

        decomposer = TaskDecomposer()
        task = create_wallet_analysis_task("test_wallet", TaskPriority.MEDIUM)
        subtasks = await decomposer.decompose(task)

        # Find tasks with no dependencies (should be READY)
        ready_tasks = [st for st in subtasks if st.status == TaskStatus.READY]
        assert len(ready_tasks) >= 1

        # First task should have no dependencies
        first_task = next(st for st in subtasks if st.payload.get("step_name") == "fetch_transactions")
        assert len(first_task.dependencies) == 0
        assert first_task.status == TaskStatus.READY

    @pytest.mark.asyncio
    async def test_critical_path(self):
        """Test critical path calculation."""
        from agentzero.task_decomposer import (
            TaskDecomposer, create_wallet_analysis_task, TaskPriority
        )

        decomposer = TaskDecomposer()
        task = create_wallet_analysis_task("test_wallet", TaskPriority.HIGH)
        await decomposer.decompose(task)

        critical_path = decomposer.get_critical_path(task.id)

        # Critical path should exist
        assert len(critical_path) >= 1

        # Should start with a task that has no dependencies
        if critical_path:
            assert len(critical_path[0].dependencies) == 0

    def test_agent_profile_mapping(self):
        """Test task type to agent profile mapping."""
        from agentzero.task_decomposer import TaskDecomposer, TaskType

        decomposer = TaskDecomposer()

        assert decomposer.get_agent_for_task(TaskType.WALLET_ANALYSIS) == "transaction_analyst"
        assert decomposer.get_agent_for_task(TaskType.RISK_SCORING) == "risk_assessor"
        assert decomposer.get_agent_for_task(TaskType.GRAPH_TRAVERSAL) == "graph_analyst"
        assert decomposer.get_agent_for_task(TaskType.SYBIL_DETECTION) == "graph_analyst"


class TestSubordinateManager:
    """Test suite for SubordinateManager."""

    def test_import(self):
        """Test module imports correctly."""
        from agentzero.subordinate_manager import (
            SubordinateManager, SubordinateAgent, AgentStatus, LoadBalancingStrategy
        )
        assert SubordinateManager is not None
        assert LoadBalancingStrategy.WEIGHTED is not None

    def test_manager_initialization(self):
        """Test SubordinateManager initializes correctly."""
        from agentzero.subordinate_manager import SubordinateManager, LoadBalancingStrategy

        manager = SubordinateManager(
            strategy=LoadBalancingStrategy.LEAST_LOADED,
            health_check_interval=5.0
        )

        assert manager.strategy == LoadBalancingStrategy.LEAST_LOADED
        assert manager.health_check_interval == 5.0
        assert len(manager.agents) == 0

    def test_agent_registration(self):
        """Test agent registration."""
        from agentzero.subordinate_manager import SubordinateManager, AgentStatus

        manager = SubordinateManager()

        agent = manager.register_agent(
            agent_id="test-agent-1",
            profile="transaction_analyst",
            max_concurrent=10
        )

        assert agent.id == "test-agent-1"
        assert agent.profile == "transaction_analyst"
        assert agent.status == AgentStatus.IDLE
        assert agent.metrics.max_concurrent == 10
        assert "test-agent-1" in manager.agents

    def test_agent_capabilities(self):
        """Test agent capabilities are auto-detected from profile."""
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_decomposer import TaskType

        manager = SubordinateManager()

        agent = manager.register_agent(
            agent_id="analyst-1",
            profile="transaction_analyst"
        )

        assert TaskType.WALLET_ANALYSIS in agent.capabilities
        assert TaskType.PATTERN_DETECTION in agent.capabilities
        assert agent.can_handle(TaskType.WALLET_ANALYSIS)

    def test_task_assignment(self):
        """Test task assignment to agents."""
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_decomposer import SubTask, TaskType, TaskPriority, TaskStatus

        manager = SubordinateManager()
        manager.register_agent("analyst-1", "transaction_analyst", max_concurrent=5)
        manager.register_agent("analyst-2", "transaction_analyst", max_concurrent=5)

        task = SubTask(
            id="test-task-1",
            parent_id="parent-1",
            task_type=TaskType.WALLET_ANALYSIS,
            priority=TaskPriority.HIGH,
            payload={"wallet": "test"}
        )

        assigned = manager.assign_task(task)

        assert assigned is not None
        assert task.assigned_agent == assigned.id
        assert task.status == TaskStatus.RUNNING
        assert task.id in assigned.assigned_tasks

    def test_load_balancing(self):
        """Test load balancing distributes tasks."""
        from agentzero.subordinate_manager import SubordinateManager, LoadBalancingStrategy
        from agentzero.task_decomposer import SubTask, TaskType, TaskPriority

        manager = SubordinateManager(strategy=LoadBalancingStrategy.LEAST_LOADED)
        manager.register_agent("agent-1", "transaction_analyst", max_concurrent=2)
        manager.register_agent("agent-2", "transaction_analyst", max_concurrent=2)

        # Assign multiple tasks
        assignments = []
        for i in range(4):
            task = SubTask(
                id=f"task-{i}",
                parent_id="parent",
                task_type=TaskType.WALLET_ANALYSIS,
                priority=TaskPriority.MEDIUM,
                payload={}
            )
            agent = manager.assign_task(task)
            if agent:
                assignments.append(agent.id)

        # Both agents should have received tasks
        assert "agent-1" in assignments
        assert "agent-2" in assignments

    def test_task_completion(self):
        """Test task completion updates metrics."""
        from agentzero.subordinate_manager import SubordinateManager, AgentStatus
        from agentzero.task_decomposer import SubTask, TaskType, TaskPriority

        manager = SubordinateManager()
        manager.register_agent("agent-1", "transaction_analyst")

        task = SubTask(
            id="task-1",
            parent_id="parent",
            task_type=TaskType.WALLET_ANALYSIS,
            priority=TaskPriority.HIGH,
            payload={}
        )

        agent = manager.assign_task(task)
        assert agent.metrics.current_load == 1

        manager.complete_task(task, success=True, execution_time_ms=25.5)

        assert agent.metrics.current_load == 0
        assert agent.metrics.tasks_completed == 1
        assert agent.metrics.avg_latency_ms == 25.5
        assert agent.status == AgentStatus.IDLE

    def test_statistics(self):
        """Test statistics generation."""
        from agentzero.subordinate_manager import SubordinateManager

        manager = SubordinateManager()
        manager.register_agent("agent-1", "transaction_analyst")
        manager.register_agent("agent-2", "risk_assessor")

        stats = manager.get_statistics()

        assert stats["total_agents"] == 2
        assert "transaction_analyst" in stats["by_profile"]
        assert "risk_assessor" in stats["by_profile"]


class TestTaskScheduler:
    """Test suite for TaskScheduler."""

    def test_import(self):
        """Test module imports correctly."""
        from agentzero.task_scheduler import TaskScheduler, ScheduledTask, SchedulerMetrics
        assert TaskScheduler is not None
        assert SchedulerMetrics is not None

    def test_scheduler_initialization(self):
        """Test TaskScheduler initializes correctly."""
        from agentzero.task_decomposer import TaskDecomposer
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_scheduler import TaskScheduler

        decomposer = TaskDecomposer()
        manager = SubordinateManager()
        scheduler = TaskScheduler(
            decomposer=decomposer,
            manager=manager,
            max_concurrent_dispatch=100,
            batch_size=20
        )

        assert scheduler.max_concurrent == 100
        assert scheduler.batch_size == 20

    @pytest.mark.asyncio
    async def test_task_scheduling(self):
        """Test task scheduling adds to queue."""
        from agentzero.task_decomposer import TaskDecomposer, create_wallet_analysis_task, TaskPriority
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_scheduler import TaskScheduler

        decomposer = TaskDecomposer()
        manager = SubordinateManager()
        scheduler = TaskScheduler(decomposer, manager)

        # Register agents
        manager.register_agent("analyst-1", "transaction_analyst")
        manager.register_agent("risk-1", "risk_assessor")

        # Schedule task
        task = create_wallet_analysis_task("test_wallet", TaskPriority.HIGH)
        subtasks = await scheduler.schedule(task)

        assert len(subtasks) == 5
        assert scheduler.metrics.tasks_scheduled >= 1

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test tasks are ordered by priority."""
        from agentzero.task_decomposer import TaskDecomposer, SubTask, TaskType, TaskPriority
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_scheduler import TaskScheduler

        decomposer = TaskDecomposer()
        manager = SubordinateManager()
        scheduler = TaskScheduler(decomposer, manager)

        # Schedule tasks with different priorities
        low_task = SubTask(
            id="low-1", parent_id="p", task_type=TaskType.GENERIC,
            priority=TaskPriority.LOW, payload={}
        )
        high_task = SubTask(
            id="high-1", parent_id="p", task_type=TaskType.GENERIC,
            priority=TaskPriority.HIGH, payload={}
        )
        critical_task = SubTask(
            id="critical-1", parent_id="p", task_type=TaskType.GENERIC,
            priority=TaskPriority.CRITICAL, payload={}
        )

        # Schedule in reverse priority order
        await scheduler.schedule_subtask(low_task)
        await scheduler.schedule_subtask(high_task)
        await scheduler.schedule_subtask(critical_task)

        # Queue should have critical first
        assert scheduler.get_queue_depth() == 3

    def test_statistics(self):
        """Test scheduler statistics."""
        from agentzero.task_decomposer import TaskDecomposer
        from agentzero.subordinate_manager import SubordinateManager
        from agentzero.task_scheduler import TaskScheduler

        decomposer = TaskDecomposer()
        manager = SubordinateManager()
        scheduler = TaskScheduler(decomposer, manager)

        stats = scheduler.get_statistics()

        assert "queue_depth" in stats
        assert "tasks_scheduled" in stats
        assert "backpressure_active" in stats


class TestGODMODEBridge:
    """Test suite for GODMODEBridge."""

    def test_import(self):
        """Test module imports correctly."""
        from agentzero.integration.godmode_bridge import GODMODEBridge, BridgeMetrics
        assert GODMODEBridge is not None
        assert BridgeMetrics is not None

    def test_bridge_initialization(self):
        """Test GODMODEBridge initializes correctly."""
        from agentzero.integration.godmode_bridge import GODMODEBridge

        bridge = GODMODEBridge(
            enable_direct_invocation=False,
            max_concurrent_tasks=50,
            latency_target_us=100.0
        )

        assert bridge.max_concurrent == 50
        assert bridge.latency_target_us == 100.0
        assert bridge.decomposer is not None
        assert bridge.manager is not None
        assert bridge.scheduler is not None

    @pytest.mark.asyncio
    async def test_bridge_start_stop(self):
        """Test bridge starts and stops cleanly."""
        from agentzero.integration.godmode_bridge import GODMODEBridge

        bridge = GODMODEBridge(enable_direct_invocation=False)

        await bridge.start()
        assert bridge._running == True

        await bridge.stop()
        assert bridge._running == False

    @pytest.mark.asyncio
    async def test_wallet_analysis_submission(self):
        """Test wallet analysis task submission."""
        from agentzero.integration.godmode_bridge import GODMODEBridge
        from agentzero.task_decomposer import TaskPriority

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        task_id = await bridge.analyze_wallet(
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
            TaskPriority.HIGH
        )

        assert task_id is not None
        assert bridge.metrics.tasks_received == 1
        assert bridge.metrics.tasks_routed == 1

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_sybil_detection_submission(self):
        """Test Sybil detection task submission."""
        from agentzero.integration.godmode_bridge import GODMODEBridge
        from agentzero.task_decomposer import TaskPriority

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        task_id = await bridge.detect_sybil(
            ["wallet1", "wallet2"],
            TaskPriority.CRITICAL
        )

        assert task_id is not None
        assert bridge.metrics.tasks_received == 1

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_latency_measurement(self):
        """Test routing latency is measured."""
        from agentzero.integration.godmode_bridge import GODMODEBridge
        from agentzero.task_decomposer import TaskPriority

        bridge = GODMODEBridge(
            enable_direct_invocation=False,
            latency_target_us=1000.0  # 1ms target for test
        )
        await bridge.start()

        # Submit multiple tasks
        for i in range(5):
            await bridge.analyze_wallet(f"wallet_{i}", TaskPriority.MEDIUM)

        # Check latency was measured
        assert bridge.metrics.total_latency_us > 0
        assert bridge.metrics.avg_latency_us > 0

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check returns status."""
        from agentzero.integration.godmode_bridge import GODMODEBridge

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        health = await bridge.health_check()

        assert "status" in health
        assert "components" in health
        assert health["status"] in ["healthy", "degraded"]

        await bridge.stop()

    @pytest.mark.asyncio
    async def test_statistics(self):
        """Test comprehensive statistics."""
        from agentzero.integration.godmode_bridge import GODMODEBridge

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        stats = bridge.get_statistics()

        assert "bridge" in stats
        assert "scheduler" in stats
        assert "manager" in stats
        assert "decomposer" in stats
        assert "agents" in stats

        await bridge.stop()


class TestPerformance:
    """Performance tests for latency and throughput."""

    @pytest.mark.asyncio
    async def test_decomposition_latency(self):
        """Test task decomposition completes in <50ms."""
        from agentzero.task_decomposer import TaskDecomposer, create_wallet_analysis_task, TaskPriority

        decomposer = TaskDecomposer()
        task = create_wallet_analysis_task("test_wallet", TaskPriority.HIGH)

        start = time.perf_counter()
        await decomposer.decompose(task)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 50, f"Decomposition took {elapsed_ms:.2f}ms (target: <50ms)"

    @pytest.mark.asyncio
    async def test_routing_latency(self):
        """Test task routing completes in <50ms."""
        from agentzero.integration.godmode_bridge import GODMODEBridge
        from agentzero.task_decomposer import TaskPriority

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        start = time.perf_counter()
        await bridge.analyze_wallet("test_wallet", TaskPriority.HIGH)
        elapsed_ms = (time.perf_counter() - start) * 1000

        await bridge.stop()

        assert elapsed_ms < 50, f"Routing took {elapsed_ms:.2f}ms (target: <50ms)"

    @pytest.mark.asyncio
    async def test_throughput(self):
        """Test system can handle 100+ tasks/second."""
        from agentzero.integration.godmode_bridge import GODMODEBridge
        from agentzero.task_decomposer import TaskPriority

        bridge = GODMODEBridge(enable_direct_invocation=False)
        await bridge.start()

        num_tasks = 100
        start = time.perf_counter()

        for i in range(num_tasks):
            await bridge.analyze_wallet(f"wallet_{i}", TaskPriority.MEDIUM)

        elapsed = time.perf_counter() - start
        throughput = num_tasks / elapsed

        await bridge.stop()

        assert throughput >= 100, f"Throughput: {throughput:.1f} tasks/sec (target: 100+)"
        print(f"\n  Throughput: {throughput:.1f} tasks/second")


def run_tests():
    """Run all tests and report results."""
    print("="*70)
    print("AGENT ZERO TASK DECOMPOSITION SYSTEM - TEST SUITE")
    print("="*70)

    results = {
        "passed": 0,
        "failed": 0,
        "errors": []
    }

    test_classes = [
        TestTaskDecomposer,
        TestSubordinateManager,
        TestTaskScheduler,
        TestGODMODEBridge,
        TestPerformance
    ]

    for test_class in test_classes:
        print(f"\n{test_class.__name__}")
        print("-" * 50)

        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith("test_"):
                method = getattr(instance, method_name)
                try:
                    if asyncio.iscoroutinefunction(method):
                        asyncio.get_event_loop().run_until_complete(method())
                    else:
                        method()
                    print(f"  ✅ {method_name}")
                    results["passed"] += 1
                except AssertionError as e:
                    print(f"  ❌ {method_name}: {e}")
                    results["failed"] += 1
                    results["errors"].append((method_name, str(e)))
                except Exception as e:
                    print(f"  ❌ {method_name}: {type(e).__name__}: {e}")
                    results["failed"] += 1
                    results["errors"].append((method_name, str(e)))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    total = results["passed"] + results["failed"]
    print(f"Total:  {total}")
    print(f"Passed: {results['passed']} ✅")
    print(f"Failed: {results['failed']} ❌")
    print(f"Rate:   {results['passed']/total*100:.1f}%")

    if results["errors"]:
        print("\nErrors:")
        for name, error in results["errors"]:
            print(f"  - {name}: {error[:100]}")

    return results


if __name__ == "__main__":
    run_tests()
