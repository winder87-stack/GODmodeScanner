"""HOSTILE TAKEOVER PROTOCOL - Comprehensive Test Suite

Tests for all takeover components:
- OverlordAgent
- BattleMonitorAgent
- DatabaseReaperAgent
- SirenController
- MirageFeatures
"""

import asyncio
import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Import components
import sys
sys.path.insert(0, '/a0/usr/projects/godmodescanner/projects/godmodescanner')

from agents.overlord.overlord_agent import OverlordAgent, TakeoverStatus
from agents.overlord.battle_monitor_agent import BattleMonitorAgent, BenchmarkResult, BattleStats
from agents.overlord.database_reaper_agent import DatabaseReaperAgent, ReaperStats
from agents.overlord.siren_controller import SirenController, SirenStatus
from agents.overlord.mirage_features import (
    MirageFeatures, CabalViewer, PredictiveAPI, InstantReplay,
    CabalNode, CabalCluster, PredictionResult, ReplayFrame
)


# ============================================================================
# OVERLORD AGENT TESTS
# ============================================================================

class TestOverlordAgent:
    """Tests for the master orchestrator."""
    
    def test_initialization(self):
        """Test OverlordAgent initializes with correct defaults."""
        agent = OverlordAgent()
        assert agent.battle_mode == True
        assert agent.auto_enable_threshold == 3.0
        assert agent.siren_stability_minutes == 10
        assert agent.reaper_enabled == True
        assert agent.reaper_batch_size == 100
    
    def test_initialization_with_custom_values(self):
        """Test OverlordAgent with custom configuration."""
        agent = OverlordAgent(
            battle_mode=False,
            auto_enable_threshold=5.0,
            siren_stability_minutes=20,
            reaper_enabled=False,
            reaper_batch_size=50,
        )
        assert agent.battle_mode == False
        assert agent.auto_enable_threshold == 5.0
        assert agent.siren_stability_minutes == 20
        assert agent.reaper_enabled == False
        assert agent.reaper_batch_size == 50
    
    def test_status_initialization(self):
        """Test TakeoverStatus initializes correctly."""
        status = TakeoverStatus()
        assert status.phase == "INFILTRATION"
        assert status.ghost_protocol_enabled == False
        assert status.legacy_system_active == True
        assert status.battle_score == 0.0
    
    def test_status_to_dict(self):
        """Test TakeoverStatus serialization."""
        status = TakeoverStatus(
            phase="DOMINANCE",
            battle_score=3.5,
            profiles_migrated=100,
        )
        d = status.to_dict()
        assert d["phase"] == "DOMINANCE"
        assert d["battle_score"] == 3.5
        assert d["profiles_migrated"] == 100
    
    def test_get_status(self):
        """Test getting current status."""
        agent = OverlordAgent()
        status = agent.get_status()
        assert "phase" in status
        assert "ghost_protocol_enabled" in status
        assert "uptime_seconds" in status


# ============================================================================
# BATTLE MONITOR TESTS
# ============================================================================

class TestBattleMonitorAgent:
    """Tests for the performance war engine."""
    
    def test_initialization(self):
        """Test BattleMonitorAgent initializes correctly."""
        monitor = BattleMonitorAgent(history_size=1000)
        assert monitor.history_size == 1000
        assert len(monitor._history) == 0
    
    def test_benchmark_result(self):
        """Test BenchmarkResult calculations."""
        result = BenchmarkResult(
            operation="test_op",
            ghost_latency_ms=10.0,
            legacy_latency_ms=50.0,
            ghost_success=True,
            legacy_success=True,
        )
        assert result.advantage_ratio == 5.0
        assert result.ghost_wins == True
    
    def test_benchmark_result_ghost_faster(self):
        """Test Ghost Protocol wins when faster."""
        result = BenchmarkResult(
            operation="test",
            ghost_latency_ms=5.0,
            legacy_latency_ms=100.0,
            ghost_success=True,
            legacy_success=True,
        )
        assert result.ghost_wins == True
        assert result.advantage_ratio == 20.0
    
    def test_benchmark_result_legacy_faster(self):
        """Test Legacy wins when faster (rare)."""
        result = BenchmarkResult(
            operation="test",
            ghost_latency_ms=100.0,
            legacy_latency_ms=50.0,
            ghost_success=True,
            legacy_success=True,
        )
        assert result.ghost_wins == False
    
    def test_record_result(self):
        """Test recording benchmark results."""
        monitor = BattleMonitorAgent()
        result = BenchmarkResult(
            operation="test",
            ghost_latency_ms=10.0,
            legacy_latency_ms=50.0,
            ghost_success=True,
            legacy_success=True,
        )
        monitor._record_result(result)
        assert len(monitor._history) == 1
    
    def test_get_stats(self):
        """Test getting battle statistics."""
        monitor = BattleMonitorAgent()
        stats = monitor.get_stats()
        assert "total_battles" in stats
        assert "ghost_wins" in stats
        assert "advantage_ratio" in stats
    
    def test_get_leaderboard(self):
        """Test getting public leaderboard."""
        monitor = BattleMonitorAgent()
        leaderboard = monitor.get_leaderboard()
        assert "title" in leaderboard
        assert "dominance_level" in leaderboard
        assert "verdict" in leaderboard


# ============================================================================
# DATABASE REAPER TESTS
# ============================================================================

class TestDatabaseReaperAgent:
    """Tests for the legacy system death march."""
    
    def test_initialization(self):
        """Test DatabaseReaperAgent initializes correctly."""
        reaper = DatabaseReaperAgent(batch_size=50)
        assert reaper.batch_size == 50
        assert reaper.verify_before_delete == True
    
    def test_reaper_stats(self):
        """Test ReaperStats initialization."""
        stats = ReaperStats()
        assert stats.profiles_migrated == 0
        assert stats.profiles_remaining == 0
        assert stats.accelerated == False
    
    def test_reaper_stats_progress(self):
        """Test progress calculation."""
        stats = ReaperStats(
            profiles_migrated=75,
            profiles_remaining=25,
        )
        d = stats.to_dict()
        assert d["progress_percent"] == 75.0
    
    def test_get_stats(self):
        """Test getting reaper statistics."""
        reaper = DatabaseReaperAgent()
        stats = reaper.get_stats()
        assert "profiles_migrated" in stats
        assert "profiles_remaining" in stats
        assert "progress_percent" in stats
    
    def test_death_march_status(self):
        """Test death march status messages."""
        reaper = DatabaseReaperAgent()
        status = reaper.get_death_march_status()
        assert "status" in status
        assert "message" in status
        assert "progress_percent" in status


# ============================================================================
# SIREN CONTROLLER TESTS
# ============================================================================

class TestSirenController:
    """Tests for the autonomous takeover controller."""
    
    def test_initialization(self):
        """Test SirenController initializes correctly."""
        siren = SirenController(threshold=3.0, stability_minutes=10)
        assert siren.threshold == 3.0
        assert siren.stability_minutes == 10
    
    def test_siren_status(self):
        """Test SirenStatus initialization."""
        status = SirenStatus()
        assert status.armed == True
        assert status.triggered == False
    
    def test_arm_disarm(self):
        """Test arming and disarming."""
        siren = SirenController()
        siren.disarm()
        assert siren._status.armed == False
        siren.arm()
        assert siren._status.armed == True
    
    def test_get_status(self):
        """Test getting siren status."""
        siren = SirenController()
        status = siren.get_status()
        assert "armed" in status
        assert "triggered" in status
        assert "threshold" in status
    
    def test_get_countdown(self):
        """Test getting countdown information."""
        siren = SirenController()
        countdown = siren.get_countdown()
        assert "status" in countdown
        assert "message" in countdown


# ============================================================================
# MIRAGE FEATURES TESTS
# ============================================================================

class TestMirageFeatures:
    """Tests for the advanced features."""
    
    def test_cabal_node(self):
        """Test CabalNode creation."""
        node = CabalNode(
            wallet_address="test_wallet",
            risk_score=0.85,
            is_king_maker=True,
            total_trades=100,
            win_rate=0.75,
        )
        d = node.to_dict()
        assert d["wallet_address"] == "test_wallet"
        assert d["risk_score"] == 0.85
        assert d["is_king_maker"] == True
    
    def test_cabal_cluster(self):
        """Test CabalCluster creation."""
        nodes = [
            CabalNode("w1", 0.8, True, 50, 0.7),
            CabalNode("w2", 0.7, False, 30, 0.6),
        ]
        cluster = CabalCluster(
            cluster_id="test_cluster",
            nodes=nodes,
            total_volume_sol=1000.0,
            coordination_score=0.9,
            detected_at=datetime.now(timezone.utc),
        )
        d = cluster.to_dict()
        assert d["cluster_id"] == "test_cluster"
        assert d["node_count"] == 2
        assert d["coordination_score"] == 0.9
    
    def test_prediction_result(self):
        """Test PredictionResult creation."""
        result = PredictionResult(
            wallet_address="test_wallet",
            predicted_action="BUY",
            confidence=0.85,
            time_horizon_minutes=5,
        )
        d = result.to_dict()
        assert d["predicted_action"] == "BUY"
        assert d["confidence"] == 0.85
    
    def test_replay_frame(self):
        """Test ReplayFrame creation."""
        frame = ReplayFrame(
            timestamp=datetime.now(timezone.utc),
            wallet_address="test_wallet",
            action="BUY",
            token_address="test_token",
            amount_sol=1.5,
            price_at_time=0.00001,
            risk_score_at_time=0.75,
        )
        d = frame.to_dict()
        assert d["action"] == "BUY"
        assert d["amount_sol"] == 1.5
    
    def test_cabal_viewer_initialization(self):
        """Test CabalViewer initialization."""
        viewer = CabalViewer()
        assert len(viewer._clusters) == 0
    
    def test_predictive_api_initialization(self):
        """Test PredictiveAPI initialization."""
        api = PredictiveAPI()
        assert api._model is None
    
    def test_instant_replay_initialization(self):
        """Test InstantReplay initialization."""
        replay = InstantReplay(max_history_hours=24)
        assert replay.max_history_hours == 24
        assert len(replay._frame_buffer) == 0
    
    def test_mirage_features_initialization(self):
        """Test MirageFeatures initialization."""
        features = MirageFeatures()
        assert features.cabal_viewer is not None
        assert features.predictive_api is not None
        assert features.instant_replay is not None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests for the complete takeover system."""
    
    @pytest.mark.asyncio
    async def test_overlord_lazy_loading(self):
        """Test that sub-agents are lazy loaded."""
        agent = OverlordAgent()
        monitor = agent.battle_monitor
        assert monitor is not None
        assert agent._battle_monitor is not None
    
    @pytest.mark.asyncio
    async def test_battle_monitor_register_operation(self):
        """Test registering battle operations."""
        monitor = BattleMonitorAgent()
        
        async def ghost_handler(x):
            return x * 2
        
        async def legacy_handler(x):
            await asyncio.sleep(0.01)
            return x * 2
        
        monitor.register_operation("multiply", ghost_handler, legacy_handler)
        assert "multiply" in monitor._ghost_handlers
        assert "multiply" in monitor._legacy_handlers
    
    @pytest.mark.asyncio
    async def test_instant_replay_record_and_retrieve(self):
        """Test recording and retrieving replay frames."""
        replay = InstantReplay()
        
        frame = ReplayFrame(
            timestamp=datetime.now(timezone.utc),
            wallet_address="test_wallet",
            action="BUY",
            token_address="test_token",
            amount_sol=1.5,
            price_at_time=0.00001,
            risk_score_at_time=0.75,
        )
        
        await replay.record_frame(frame)
        assert len(replay._frame_buffer) == 1
        
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc) + timedelta(hours=1)
        frames = replay.get_frames(start, end)
        assert len(frames) == 1
    
    def test_instant_replay_state_reconstruction(self):
        """Test wallet state reconstruction."""
        replay = InstantReplay()
        
        now = datetime.now(timezone.utc)
        replay._frame_buffer.append(ReplayFrame(
            timestamp=now - timedelta(minutes=10),
            wallet_address="wallet1",
            action="BUY",
            token_address="token1",
            amount_sol=2.0,
            price_at_time=0.00001,
            risk_score_at_time=0.5,
        ))
        replay._frame_buffer.append(ReplayFrame(
            timestamp=now - timedelta(minutes=5),
            wallet_address="wallet1",
            action="SELL",
            token_address="token1",
            amount_sol=1.0,
            price_at_time=0.00002,
            risk_score_at_time=0.6,
        ))
        
        state = replay.get_state_at(now, "wallet1")
        assert state["state"] == "RECONSTRUCTED"
        assert state["frame_count"] == 2
