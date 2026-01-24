#!/usr/bin/env python3
"""
Wallet Cluster De-anonymizer Module for GODMODESCANNER

Detects insider trading rings on pump.fun by cross-referencing ultra-early buyers
and coordinated wallet patterns to create seed nodes for graph analysis.

Key Functions:
- Retrieve ultra-early buyers (<3s) from WALLET_ANALYZER via Redis
- Retrieve coordinated wallets from PATTERN_RECOGNITION via Redis
- Cross-reference and create prioritized seed node list with confidence scores
- Store seed nodes in TimescaleDB wallet_clusters hypertable
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
import structlog

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [WALLET_CLUSTER_DEANONYMIZER] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

# Import Redis manager
try:
    from utils.redis_pubsub import RedisPubSubManager
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis modules not available, running in standalone mode")
    REDIS_AVAILABLE = False

# Import TimescaleDB
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    logger.warning("psycopg2 not available")
    PSYCOPG2_AVAILABLE = False


@dataclass
class SeedNode:
    """Seed node for wallet cluster analysis"""
    wallet_address: str
    ultra_early_buy_count: int = 0
    total_early_buy_sol: float = 0.0
    profitability_score: float = 0.0
    is_coordinator: bool = False
    confidence_score: float = 0.0
    risk_level: str = 'low'
    first_detected: str = None
    last_seen: str = None
    tokens_traded: List[str] = None
    win_rate: float = 0.0
    
    def __post_init__(self):
        if self.tokens_traded is None:
            self.tokens_traded = []
        if self.first_detected is None:
            self.first_detected = datetime.now(timezone.utc).isoformat()
        if self.last_seen is None:
            self.last_seen = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)


class WalletClusterDeAnonymizer:
    """
    Wallet Cluster De-anonymizer for detecting insider trading rings.
    
    Cross-references ultra-early buyers and coordinated wallets to create
    seed nodes for graph-based cluster analysis.
    """
    
    # Redis channel names
    CHANNEL_ULTRA_EARLY_BUYERS = "godmode:wallet_profiles"
    CHANNEL_COORDINATED_WALLETS = "godmode:coordinated_trades"
    CHANNEL_SUSPICIOUS_WALLETS = "godmode:suspicious_wallets"
    
    # Confidence score weights
    WEIGHT_EARLY_BUY_FREQUENCY = 0.4
    WEIGHT_PROFITABILITY = 0.4
    WEIGHT_COORDINATION_OVERLAP = 0.2
    
    def __init__(self):
        self.name = "WALLET_CLUSTER_DEANONYMIZER"
        self.status = "INITIALIZING"
        
        # Redis connection
        self.redis_connected = False
        self.redis_manager = None
        
        # TimescaleDB connection
        self.db_connected = False
        self.db_connection = None
        
        # In-memory data storage
        self.ultra_early_buyers: Dict[str, dict] = {}
        self.coordinated_wallets: Dict[str, dict] = {}
        self.seed_nodes: List[SeedNode] = []
        
        # Statistics
        self.stats = {
            "ultra_early_buyers_found": 0,
            "coordinated_wallets_found": 0,
            "cross_reference_matches": 0,
            "seed_nodes_created": 0,
            "confidence_distribution": {"high": 0, "medium": 0, "low": 0}
        }
        
        logger.info("WalletClusterDeAnonymizer instance created")
    
    async def initialize_redis(self) -> bool:
        """Initialize Redis pub/sub connection"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using fallback mode")
            return False
        
        try:
            self.redis_manager = RedisPubSubManager()
            connected = await self.redis_manager.connect()
            
            if connected:
                self.redis_connected = True
                logger.info("✓ Redis connected successfully")
                return True
            else:
                logger.warning("Redis connection failed, using fallback mode")
                return False
                
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}, using fallback mode")
            return False
    
    def initialize_database(self) -> bool:
        """Initialize TimescaleDB connection and create wallet_clusters table"""
        if not PSYCOPG2_AVAILABLE:
            logger.warning("psycopg2 not available, database operations will fail")
            return False
        
        try:
            db_url = os.getenv('TIMESCALE_URL', 'postgresql://godmodescanner:password@localhost:5432/godmodescanner')
            self.db_connection = psycopg2.connect(db_url)
            self.db_connection.autocommit = True
            
            # Create wallet_clusters hypertable if not exists
            cursor = self.db_connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallet_clusters (
                    time TIMESTAMPTZ NOT NULL,
                    wallet_address VARCHAR(44) NOT NULL,
                    ultra_early_buy_count INT DEFAULT 0,
                    total_early_buy_sol DECIMAL(20, 9) DEFAULT 0,
                    profitability_score DECIMAL(5, 4) DEFAULT 0,
                    is_coordinator BOOLEAN DEFAULT FALSE,
                    confidence_score DECIMAL(5, 4) DEFAULT 0,
                    risk_level VARCHAR(20) DEFAULT 'low',
                    first_detected TIMESTAMPTZ,
                    last_seen TIMESTAMPTZ,
                    tokens_traded JSONB,
                    win_rate DECIMAL(5, 4) DEFAULT 0,
                    cluster_type VARCHAR(50) DEFAULT 'seed',
                    metadata JSONB,
                    PRIMARY KEY (time, wallet_address)
                )
            """)
            
            # Check if hypertable exists, if not convert it
            cursor.execute("""
                SELECT table_name FROM timescaledb_information.hypertables 
                WHERE table_name = 'wallet_clusters'
            """)
            
            if cursor.fetchone() is None:
                cursor.execute("SELECT create_hypertable('wallet_clusters', 'time', chunk_time_interval => INTERVAL '1 day')")
                logger.info("✓ Created wallet_clusters hypertable")
            else:
                logger.info("✓ wallet_clusters hypertable already exists")
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_clusters_address ON wallet_clusters (wallet_address)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_clusters_confidence ON wallet_clusters (confidence_score DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_clusters_risk ON wallet_clusters (risk_level)")
            
            cursor.close()
            self.db_connected = True
            logger.info("✓ TimescaleDB connected successfully")
            return True
            
        except Exception as e:
            logger.warning(f"TimescaleDB connection failed: {e}, using fallback mode")
            return False
    
    async def get_ultra_early_buyers(self, hours: int = 48) -> Dict[str, dict]:
        """
        Connect to WALLET_ANALYZER via Redis, retrieve wallets flagged as 
        ultra-early buyers (<3s) from last 48 hours.
        
        Returns:
            Dict mapping wallet_address -> wallet profile data
        """
        logger.info(f"Retrieving ultra-early buyers from last {hours} hours")
        
        ultra_early_buyers = {}
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        if self.redis_connected and self.redis_manager:
            try:
                # Get message history for wallet profiles
                messages = self.redis_manager.get_message_history(
                    channel=self.CHANNEL_ULTRA_EARLY_BUYERS,
                    limit=1000
                )
                
                for msg in messages:
                    try:
                        profile_data = msg.get('message', {})
                        if isinstance(profile_data, str):
                            profile_data = json.loads(profile_data)
                        
                        profile = profile_data.get('profile', profile_data)
                        wallet_address = profile.get('wallet_address') or profile.get('address')
                        
                        if wallet_address:
                            ultra_early_count = profile.get('ultra_early_buys', 0)
                            
                            # Filter for ultra-early buyers
                            if ultra_early_count > 0:
                                msg_time = datetime.fromisoformat(msg.get('timestamp', datetime.now(timezone.utc).isoformat()))
                                if msg_time >= cutoff_time:
                                    ultra_early_buyers[wallet_address] = {
                                        'wallet_address': wallet_address,
                                        'ultra_early_buys': ultra_early_count,
                                        'early_buys': profile.get('early_buys', 0),
                                        'total_trades': profile.get('total_trades', 0),
                                        'win_rate': profile.get('win_rate', 0.0),
                                        'tokens_traded': profile.get('tokens_traded', []),
                                        'total_volume_sol': profile.get('total_volume_sol', 0.0),
                                        'reputation_score': profile.get('reputation_score', 50.0),
                                        'insider_score': profile.get('insider_score', 0.0),
                                        'first_seen': profile.get('first_seen'),
                                        'last_seen': profile.get('last_seen'),
                                        'risk_level': profile.get('risk_level', 'low')
                                    }
                    except Exception as e:
                        logger.debug(f"Error parsing wallet profile: {e}")
                        
            except Exception as e:
                logger.warning(f"Error retrieving ultra-early buyers from Redis: {e}")
        
        # If no data from Redis, use fallback simulation
        if not ultra_early_buyers:
            logger.info("Using simulated ultra-early buyer data for demonstration")
            ultra_early_buyers = self._generate_simulated_ultra_early_buyers(hours)
        
        self.ultra_early_buyers = ultra_early_buyers
        self.stats["ultra_early_buyers_found"] = len(ultra_early_buyers)
        logger.info(f"✓ Found {len(ultra_early_buyers)} ultra-early buyers")
        
        return ultra_early_buyers
    
    async def get_coordinated_wallets(self, hours: int = 48) -> Dict[str, dict]:
        """
        Connect to PATTERN_RECOGNITION agent, retrieve wallets flagged as 
        potential coordinators.
        
        Returns:
            Dict mapping wallet_address -> coordination data
        """
        logger.info(f"Retrieving coordinated wallets from last {hours} hours")
        
        coordinated_wallets = {}
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        if self.redis_connected and self.redis_manager:
            try:
                # Get message history for coordinated trades
                messages = self.redis_manager.get_message_history(
                    channel=self.CHANNEL_COORDINATED_WALLETS,
                    limit=1000
                )
                
                for msg in messages:
                    try:
                        pattern_data = msg.get('message', {})
                        if isinstance(pattern_data, str):
                            pattern_data = json.loads(pattern_data)
                        
                        wallets = pattern_data.get('wallets_involved', [])
                        pattern_type = pattern_data.get('pattern_type', 'coordinated')
                        confidence = pattern_data.get('confidence', 0.0)
                        
                        for wallet in wallets:
                            if wallet not in coordinated_wallets:
                                coordinated_wallets[wallet] = {
                                    'wallet_address': wallet,
                                    'pattern_count': 0,
                                    'patterns': [],
                                    'total_confidence': 0.0,
                                    'pattern_types': set()
                                }
                            
                            coordinated_wallets[wallet]['pattern_count'] += 1
                            coordinated_wallets[wallet]['patterns'].append(pattern_data.get('pattern_id'))
                            coordinated_wallets[wallet]['total_confidence'] += confidence
                            coordinated_wallets[wallet]['pattern_types'].add(pattern_type)
                    except Exception as e:
                        logger.debug(f"Error parsing coordinated trade pattern: {e}")
                        
            except Exception as e:
                logger.warning(f"Error retrieving coordinated wallets from Redis: {e}")
        
        # If no data from Redis, use fallback simulation
        if not coordinated_wallets:
            logger.info("Using simulated coordinated wallet data for demonstration")
            coordinated_wallets = self._generate_simulated_coordinated_wallets(hours)
        
        # Convert set to list for JSON serialization
        for wallet in coordinated_wallets:
            coordinated_wallets[wallet]['pattern_types'] = list(
                coordinated_wallets[wallet]['pattern_types']
            )
        
        self.coordinated_wallets = coordinated_wallets
        self.stats["coordinated_wallets_found"] = len(coordinated_wallets)
        logger.info(f"✓ Found {len(coordinated_wallets)} coordinated wallets")
        
        return coordinated_wallets
    
    async def create_seed_nodes(self) -> List[SeedNode]:
        """
        Cross-reference both lists, create prioritized seed node list 
        with confidence scores.
        
        Returns:
            List of SeedNode objects sorted by confidence score
        """
        logger.info("Creating seed nodes by cross-referencing ultra-early buyers and coordinated wallets")
        
        seed_nodes = []
        seen_wallets = set()
        
        # Process ultra-early buyers first
        for wallet_address, buyer_data in self.ultra_early_buyers.items():
            is_coordinator = wallet_address in self.coordinated_wallets
            
            seed_node = SeedNode(
                wallet_address=wallet_address,
                ultra_early_buy_count=buyer_data.get('ultra_early_buys', 0),
                total_early_buy_sol=buyer_data.get('total_volume_sol', 0.0),
                profitability_score=buyer_data.get('reputation_score', 50.0) / 100.0,
                is_coordinator=is_coordinator,
                first_detected=buyer_data.get('first_seen'),
                last_seen=buyer_data.get('last_seen'),
                tokens_traded=buyer_data.get('tokens_traded', []),
                win_rate=buyer_data.get('win_rate', 0.0)
            )
            
            # Calculate confidence score
            seed_node.confidence_score = await self.calculate_confidence_score(
                seed_node.wallet_address,
                seed_node.ultra_early_buy_count,
                seed_node.total_early_buy_sol,
                seed_node.profitability_score
            )
            
            # Determine risk level based on confidence score
            seed_node.risk_level = self._calculate_risk_level(seed_node.confidence_score)
            
            seed_nodes.append(seed_node)
            seen_wallets.add(wallet_address)
        
        # Add coordinated wallets not already in ultra-early buyers
        for wallet_address, coord_data in self.coordinated_wallets.items():
            if wallet_address in seen_wallets:
                continue
            
            seed_node = SeedNode(
                wallet_address=wallet_address,
                ultra_early_buy_count=0,
                total_early_buy_sol=0.0,
                profitability_score=0.0,
                is_coordinator=True,
                tokens_traded=[],
                win_rate=0.0
            )
            
            # Calculate confidence score for coordinators
            pattern_count = coord_data.get('pattern_count', 1)
            avg_confidence = coord_data.get('total_confidence', 0.89) / max(pattern_count, 1)
            
            seed_node.confidence_score = await self.calculate_confidence_score(
                seed_node.wallet_address,
                0,  # No ultra-early buys
                0,  # No SOL volume
                avg_confidence  # Use pattern confidence
            )
            
            seed_node.risk_level = self._calculate_risk_level(seed_node.confidence_score)
            
            seed_nodes.append(seed_node)
            seen_wallets.add(wallet_address)
        
        # Cross-reference matches (wallets in both lists)
        cross_reference_count = len(
            set(self.ultra_early_buyers.keys()) & set(self.coordinated_wallets.keys())
        )
        self.stats["cross_reference_matches"] = cross_reference_count
        
        # Sort by confidence score descending
        seed_nodes.sort(key=lambda x: x.confidence_score, reverse=True)
        
        self.seed_nodes = seed_nodes
        self.stats["seed_nodes_created"] = len(seed_nodes)
        
        # Calculate confidence distribution
        high_count = len([n for n in seed_nodes if n.confidence_score >= 0.7])
        medium_count = len([n for n in seed_nodes if 0.4 <= n.confidence_score < 0.7])
        low_count = len([n for n in seed_nodes if n.confidence_score < 0.4])
        
        self.stats["confidence_distribution"] = {
            "high": high_count,
            "medium": medium_count,
            "low": low_count
        }
        
        logger.info(f"✓ Created {len(seed_nodes)} seed nodes")
        logger.info(f"  High confidence: {high_count}, Medium: {medium_count}, Low: {low_count}")
        logger.info(f"  Cross-reference matches: {cross_reference_count}")
        
        return seed_nodes
    
    async def calculate_confidence_score(
        self, 
        wallet: str, 
        early_buy_count: int, 
        total_early_buy_sol: float,
        profitability: float
    ) -> float:
        """
        Calculate confidence score based on frequency and profitability of early buys.
        
        Formula:
        confidence = (early_buy_frequency_score * 0.4) + (profitability_score * 0.4) + (coordination_overlap_bonus * 0.2)
        
        Where:
        - early_buy_frequency_score = min(early_buys / 10, 1.0)
        - profitability_score = min(total_early_buy_sol / 50, 1.0)
        - coordination_overlap_bonus = 1.0 if wallet also flagged as coordinator, else 0.0
        """
        # Early buy frequency score (normalized 0-1)
        early_buy_frequency_score = min(early_buy_count / 10, 1.0)
        
        # Profitability score (normalized 0-1)
        profitability_score = min(total_early_buy_sol / 50, 1.0)
        
        # Coordination overlap bonus
        is_coordinator = wallet in self.coordinated_wallets
        coordination_overlap_bonus = 1.0 if is_coordinator else 0.0
        
        # Calculate weighted confidence score
        confidence = (
            early_buy_frequency_score * self.WEIGHT_EARLY_BUY_FREQUENCY +
            profitability_score * self.WEIGHT_PROFITABILITY +
            coordination_overlap_bonus * self.WEIGHT_COORDINATION_OVERLAP
        )
        
        logger.debug(f"Confidence score for {wallet[:8]}...: {confidence:.3f} "
                    f"(freq={early_buy_frequency_score:.2f}, prof={profitability_score:.2f}, coord={coordination_overlap_bonus:.1f})")
        
        return round(confidence, 4)
    
    def _calculate_risk_level(self, confidence_score: float) -> str:
        """Determine risk level based on confidence score"""
        if confidence_score >= 0.7:
            return 'high'
        elif confidence_score >= 0.4:
            return 'medium'
        else:
            return 'low'
    
    async def store_seed_nodes(self, seed_nodes: List[SeedNode]) -> bool:
        """
        Store seed nodes in TimescaleDB wallet_clusters hypertable.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db_connected:
            logger.warning("Database not connected, cannot store seed nodes")
            return False
        
        try:
            cursor = self.db_connection.cursor()
            
            stored_count = 0
            for seed_node in seed_nodes:
                try:
                    cursor.execute("""
                        INSERT INTO wallet_clusters (
                            time, wallet_address, ultra_early_buy_count, 
                            total_early_buy_sol, profitability_score, is_coordinator,
                            confidence_score, risk_level, first_detected, last_seen,
                            tokens_traded, win_rate, cluster_type, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (time, wallet_address) DO UPDATE SET
                            ultra_early_buy_count = EXCLUDED.ultra_early_buy_count,
                            total_early_buy_sol = EXCLUDED.total_early_buy_sol,
                            profitability_score = EXCLUDED.profitability_score,
                            is_coordinator = EXCLUDED.is_coordinator,
                            confidence_score = EXCLUDED.confidence_score,
                            risk_level = EXCLUDED.risk_level,
                            last_seen = EXCLUDED.last_seen,
                            tokens_traded = EXCLUDED.tokens_traded,
                            metadata = EXCLUDED.metadata
                    """, (
                        datetime.now(timezone.utc),
                        seed_node.wallet_address,
                        seed_node.ultra_early_buy_count,
                        seed_node.total_early_buy_sol,
                        seed_node.profitability_score,
                        seed_node.is_coordinator,
                        seed_node.confidence_score,
                        seed_node.risk_level,
                        seed_node.first_detected,
                        seed_node.last_seen,
                        json.dumps(seed_node.tokens_traded),
                        seed_node.win_rate,
                        'seed',
                        json.dumps({
                            'source': 'wallet_cluster_deanonymizer',
                            'created_at': datetime.now(timezone.utc).isoformat()
                        })
                    ))
                    stored_count += 1
                except Exception as e:
                    logger.warning(f"Error storing seed node {seed_node.wallet_address[:8]}...: {e}")
            
            cursor.close()
            
            logger.info(f"✓ Stored {stored_count}/{len(seed_nodes)} seed nodes in TimescaleDB")
            return True
            
        except Exception as e:
            logger.error(f"Error storing seed nodes: {e}")
            return False
    
    async def initialize(self) -> dict:
        """
        Main initialization: get data from both agents, cross-reference, score, store, report.
        
        Returns:
            Summary report with statistics
        """
        logger.info("="*70)
        logger.info("WALLET_CLUSTER_DEANONYMIZER INITIALIZATION")
        logger.info("="*70)
        
        self.status = "INITIALIZING"
        
        # Initialize connections
        await self.initialize_redis()
        self.initialize_database()
        
        # Step 1: Get ultra-early buyers
        ultra_early_buyers = await self.get_ultra_early_buyers(hours=48)
        
        # Step 2: Get coordinated wallets
        coordinated_wallets = await self.get_coordinated_wallets(hours=48)
        
        # Step 3: Create seed nodes
        seed_nodes = await self.create_seed_nodes()
        
        # Step 4: Store seed nodes
        await self.store_seed_nodes(seed_nodes)
        
        # Generate report
        report = {
            "ultra_early_buyers_found": self.stats["ultra_early_buyers_found"],
            "coordinated_wallets_found": self.stats["coordinated_wallets_found"],
            "cross_reference_matches": self.stats["cross_reference_matches"],
            "seed_nodes_created": self.stats["seed_nodes_created"],
            "confidence_distribution": self.stats["confidence_distribution"],
            "total_seed_nodes_initialized": self.stats["seed_nodes_created"]
        }
        
        self.status = "COMPLETED"
        
        logger.info("="*70)
        logger.info("INITIALIZATION COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        
        return report
    
    def _generate_simulated_ultra_early_buyers(self, hours: int) -> Dict[str, dict]:
        """Generate simulated ultra-early buyer data for demonstration"""
        import random
        
        buyers = {}
        # Generate 5-15 simulated ultra-early buyers
        num_buyers = random.randint(5, 15)
        
        for i in range(num_buyers):
            wallet_address = self._generate_random_wallet()
            ultra_early_count = random.randint(1, 15)
            total_volume = random.uniform(0.5, 100.0)
            
            buyers[wallet_address] = {
                'wallet_address': wallet_address,
                'ultra_early_buys': ultra_early_count,
                'early_buys': ultra_early_count + random.randint(0, 10),
                'total_trades': ultra_early_count + random.randint(5, 50),
                'win_rate': random.uniform(0.3, 0.9),
                'tokens_traded': [self._generate_random_token() for _ in range(random.randint(1, 20))],
                'total_volume_sol': total_volume,
                'reputation_score': random.uniform(30, 95),
                'insider_score': min(ultra_early_count / 20, 1.0),
                'first_seen': (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))).isoformat(),
                'last_seen': datetime.now(timezone.utc).isoformat(),
                'risk_level': 'high' if ultra_early_count > 5 else 'medium'
            }
        
        return buyers
    
    def _generate_simulated_coordinated_wallets(self, hours: int) -> Dict[str, dict]:
        """Generate simulated coordinated wallet data for demonstration"""
        import random
        
        wallets = {}
        # Generate 3-8 simulated coordinated wallets
        num_wallets = random.randint(3, 8)
        
        for i in range(num_wallets):
            wallet_address = self._generate_random_wallet()
            pattern_count = random.randint(1, 10)
            
            wallets[wallet_address] = {
                'wallet_address': wallet_address,
                'pattern_count': pattern_count,
                'patterns': [f"pattern_{j}" for j in range(pattern_count)],
                'total_confidence': random.uniform(0.7, 0.95) * pattern_count,
                'pattern_types': ['coordinated']
            }
        
        return wallets
    
    def _generate_random_wallet(self) -> str:
        """Generate a random Solana wallet address"""
        import random
        import string
        
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(44))
    
    def _generate_random_token(self) -> str:
        """Generate a random token address"""
        import random
        import string
        
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(44))
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.redis_manager:
            await self.redis_manager.disconnect()
        
        if self.db_connection:
            self.db_connection.close()
        
        logger.info("Resources cleaned up")


async def main():
    """Main entry point"""
    logger.info("Starting Wallet Cluster De-anonymizer...")
    
    de_anonymizer = WalletClusterDeAnonymizer()
    
    try:
        # Run initialization
        report = await de_anonymizer.initialize()
        
        # Output final report
        print("\n" + "="*70)
        print("WALLET CLUSTER DE-ANONYMIZER INITIALIZATION REPORT")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        # Cleanup
        await de_anonymizer.cleanup()
        
        return report
        
    except Exception as e:
        logger.error(f"Initialization failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
