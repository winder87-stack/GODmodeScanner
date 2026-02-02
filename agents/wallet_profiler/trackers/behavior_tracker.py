"""Behavior tracker for monitoring wallet activity patterns."""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import statistics
import math


class BehaviorTracker:
    """Tracks and analyzes wallet behavior patterns over time."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the behavior tracker.

        Args:
            config: Configuration for behavior tracking
        """
        self.config = config or {
            'tracking_window_days': 30,
            'pattern_detection_threshold': 3,
            'anomaly_detection_enabled': True,
            'burst_detection_window_seconds': 60,
            'burst_std_threshold': 5.0,
            'min_historical_samples': 10
        }
        
        # Track transactions per wallet with timestamps
        self.transaction_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        
        # Rolling window counters for different time periods
        self.rolling_windows: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            '1h': 0,
            '24h': 0,
            '7d': 0
        })
        
        # Transaction type tracking (Buy/Sell)
        self.transaction_types: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # Token launch timing tracking
        self.token_launches: Dict[str, datetime] = {}  # token_address -> launch_time
        
        # Historical statistics for burst detection
        self.historical_rates: Dict[str, List[float]] = defaultdict(list)
        
        self.tracked_wallets = defaultdict(dict)
        self.behavior_history = defaultdict(list)

    def track_transaction(self, wallet_address: str, tx_data: Dict[str, Any]) -> None:
        """Track a new transaction for a wallet and update rolling windows.

        Args:
            wallet_address: Wallet address
            tx_data: Transaction data containing:
                - timestamp: datetime or ISO string
                - tx_type: 'buy' or 'sell'
                - amount: transaction amount
                - token_address: token being traded
                - token_launch_time: (optional) when token was launched
        """
        # Parse timestamp
        if isinstance(tx_data.get('timestamp'), str):
            timestamp = datetime.fromisoformat(tx_data['timestamp'].replace('Z', '+00:00'))
        elif isinstance(tx_data.get('timestamp'), datetime):
            timestamp = tx_data['timestamp']
        else:
            timestamp = datetime.now(timezone.utc)
        
        # Ensure timezone awareness
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        # Store transaction with full data
        tx_record = {
            'timestamp': timestamp,
            'tx_type': tx_data.get('tx_type', 'unknown').lower(),
            'amount': tx_data.get('amount', 0),
            'token_address': tx_data.get('token_address', ''),
            'token_launch_time': tx_data.get('token_launch_time')
        }
        
        self.transaction_history[wallet_address].append(tx_record)
        self.transaction_types[wallet_address].append(tx_record)
        
        # Track token launch time if provided
        if tx_record['token_launch_time'] and tx_record['token_address']:
            if tx_record['token_address'] not in self.token_launches:
                launch_time = tx_record['token_launch_time']
                if isinstance(launch_time, str):
                    launch_time = datetime.fromisoformat(launch_time.replace('Z', '+00:00'))
                self.token_launches[tx_record['token_address']] = launch_time
        
        # Update rolling window counts
        self._update_rolling_windows(wallet_address, timestamp)
        
        # Update historical rate statistics (transactions per minute)
        self._update_historical_rates(wallet_address, timestamp)

    def _update_rolling_windows(self, wallet_address: str, current_time: datetime) -> None:
        """Update rolling window transaction counts for 1h, 24h, and 7d.

        Args:
            wallet_address: Wallet address
            current_time: Current timestamp
        """
        history = self.transaction_history[wallet_address]
        
        # Define time windows
        windows = {
            '1h': timedelta(hours=1),
            '24h': timedelta(hours=24),
            '7d': timedelta(days=7)
        }
        
        # Count transactions within each window
        for window_name, window_delta in windows.items():
            cutoff_time = current_time - window_delta
            count = sum(1 for tx in history if tx['timestamp'] >= cutoff_time)
            self.rolling_windows[wallet_address][window_name] = count

    def _update_historical_rates(self, wallet_address: str, current_time: datetime) -> None:
        """Update historical transaction rate statistics.

        Args:
            wallet_address: Wallet address
            current_time: Current timestamp
        """
        history = self.transaction_history[wallet_address]
        
        # Calculate transactions per minute over the last hour (excluding last minute)
        one_hour_ago = current_time - timedelta(hours=1)
        one_minute_ago = current_time - timedelta(minutes=1)
        
        # Get transactions from 1 hour ago to 1 minute ago
        historical_txs = [tx for tx in history 
                         if one_hour_ago <= tx['timestamp'] < one_minute_ago]
        
        if len(historical_txs) >= self.config['min_historical_samples']:
            # Calculate rate (transactions per minute)
            time_span_minutes = (one_minute_ago - one_hour_ago).total_seconds() / 60
            rate = len(historical_txs) / time_span_minutes if time_span_minutes > 0 else 0
            
            # Store historical rate (keep last 100 samples)
            if len(self.historical_rates[wallet_address]) >= 100:
                self.historical_rates[wallet_address].pop(0)
            self.historical_rates[wallet_address].append(rate)

    def detect_burst_activity(self, wallet_address: str) -> bool:
        """Detect if transaction frequency exceeds 5 standard deviations of historical average.

        Args:
            wallet_address: Wallet address to check

        Returns:
            True if burst activity detected, False otherwise
        """
        history = self.transaction_history[wallet_address]
        historical_rates = self.historical_rates[wallet_address]
        
        # Need sufficient historical data
        if len(historical_rates) < self.config['min_historical_samples']:
            return False
        
        # Calculate current rate (transactions in last minute)
        current_time = datetime.now(timezone.utc)
        one_minute_ago = current_time - timedelta(
            seconds=self.config['burst_detection_window_seconds']
        )
        
        recent_txs = [tx for tx in history if tx['timestamp'] >= one_minute_ago]
        current_rate = len(recent_txs)  # Transactions per minute
        
        # Calculate historical statistics
        try:
            mean_rate = statistics.mean(historical_rates)
            
            # Use sample standard deviation if we have enough samples
            if len(historical_rates) >= 2:
                std_rate = statistics.stdev(historical_rates)
            else:
                return False
            
            # Avoid division by zero
            if std_rate == 0:
                # If std is 0, check if current rate is significantly higher than mean
                return current_rate > mean_rate * 2
            
            # Calculate z-score (number of standard deviations from mean)
            z_score = (current_rate - mean_rate) / std_rate
            
            # Detect burst if z-score exceeds threshold
            return z_score > self.config['burst_std_threshold']
            
        except statistics.StatisticsError:
            return False

    def calculate_aggressiveness(self, wallet_address: str, 
                                token_address: Optional[str] = None) -> float:
        """Calculate aggressiveness score based on buy/sell ratio and sniper behavior.

        Args:
            wallet_address: Wallet address to analyze
            token_address: Optional specific token to analyze

        Returns:
            Float between 0.0 and 1.0, where:
            - 0.0 = Not aggressive (balanced trading)
            - 1.0 = Highly aggressive (heavy buying, fast execution, sniper behavior)
        """
        tx_history = self.transaction_types[wallet_address]
        
        if not tx_history:
            return 0.0
        
        # Filter by token if specified
        if token_address:
            tx_history = [tx for tx in tx_history if tx['token_address'] == token_address]
        
        if not tx_history:
            return 0.0
        
        # Component 1: Buy/Sell Ratio (40% weight)
        buy_count = sum(1 for tx in tx_history if tx['tx_type'] == 'buy')
        sell_count = sum(1 for tx in tx_history if tx['tx_type'] == 'sell')
        total_count = buy_count + sell_count
        
        if total_count == 0:
            buy_sell_score = 0.0
        else:
            # Score increases with buy ratio
            buy_ratio = buy_count / total_count
            buy_sell_score = buy_ratio  # 0.0 (all sells) to 1.0 (all buys)
        
        # Component 2: Sniper Behavior - Speed after token launch (40% weight)
        sniper_scores = []
        for tx in tx_history:
            if tx['tx_type'] == 'buy' and tx['token_address'] in self.token_launches:
                launch_time = self.token_launches[tx['token_address']]
                time_after_launch = (tx['timestamp'] - launch_time).total_seconds()
                
                # Score based on how quickly they bought after launch
                if time_after_launch <= 5:  # Within 5 seconds
                    sniper_scores.append(1.0)
                elif time_after_launch <= 30:  # Within 30 seconds
                    sniper_scores.append(0.8)
                elif time_after_launch <= 60:  # Within 1 minute
                    sniper_scores.append(0.6)
                elif time_after_launch <= 300:  # Within 5 minutes
                    sniper_scores.append(0.3)
                else:
                    sniper_scores.append(0.0)
        
        sniper_score = statistics.mean(sniper_scores) if sniper_scores else 0.0
        
        # Component 3: Transaction Frequency (20% weight)
        # Higher frequency = more aggressive
        current_time = datetime.now(timezone.utc)
        recent_window = current_time - timedelta(hours=1)
        recent_txs = [tx for tx in tx_history if tx['timestamp'] >= recent_window]
        
        # Normalize frequency (cap at 20 transactions per hour = max aggressive)
        frequency_score = min(len(recent_txs) / 20.0, 1.0)
        
        # Weighted combination
        aggressiveness = (
            buy_sell_score * 0.4 +
            sniper_score * 0.4 +
            frequency_score * 0.2
        )
        
        # Ensure result is between 0.0 and 1.0
        return max(0.0, min(1.0, aggressiveness))

    def get_rolling_window_stats(self, wallet_address: str) -> Dict[str, int]:
        """Get current rolling window transaction counts.

        Args:
            wallet_address: Wallet address

        Returns:
            Dictionary with counts for 1h, 24h, and 7d windows
        """
        return self.rolling_windows[wallet_address].copy()

    def analyze_behavior_patterns(self, wallet_address: str) -> Dict[str, Any]:
        """Analyze behavior patterns for a wallet.

        Args:
            wallet_address: Wallet address to analyze

        Returns:
            Behavior pattern analysis
        """
        tx_history = self.transaction_history[wallet_address]
        
        if not tx_history:
            return {
                'trading_frequency': 0.0,
                'preferred_times': [],
                'average_trade_size': 0.0,
                'token_preferences': [],
                'detected_patterns': [],
                'anomalies': [],
                'avg_curve_position': self._calculate_avg_curve_position(wallet_address),
                'aggressiveness_score': 0.0,
                'burst_detected': False
            }
        
        # Calculate metrics
        buy_count = sum(1 for tx in tx_history if tx['tx_type'] == 'buy')
        sell_count = sum(1 for tx in tx_history if tx['tx_type'] == 'sell')
        
        patterns = {
            'trading_frequency': len(tx_history),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'buy_sell_ratio': buy_count / sell_count if sell_count > 0 else float('inf'),
            'rolling_windows': self.get_rolling_window_stats(wallet_address),
            'aggressiveness_score': self.calculate_aggressiveness(wallet_address),
            'burst_detected': self.detect_burst_activity(wallet_address),
            'avg_curve_position': self._calculate_avg_curve_position(wallet_address),
            'detected_patterns': [],
            'anomalies': []
        }
        
        # Detect patterns
        if patterns['aggressiveness_score'] > 0.7:
            patterns['detected_patterns'].append('high_aggressiveness')
        
        if patterns['burst_detected']:
            patterns['detected_patterns'].append('burst_activity')
            patterns['anomalies'].append('unusual_transaction_frequency')
        
        if patterns['buy_sell_ratio'] > 5:
            patterns['detected_patterns'].append('heavy_accumulation')
        
        return patterns

    def detect_behavior_change(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Detect significant behavior changes.

        Args:
            wallet_address: Wallet address

        Returns:
            Behavior change detection results if change detected
        """
        # Check for burst activity as a behavior change indicator
        if self.detect_burst_activity(wallet_address):
            return {
                'change_type': 'burst_activity',
                'severity': 'high',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': 'Transaction frequency exceeds 5 standard deviations'
            }
        
        return None

    def get_wallet_behavior_summary(self, wallet_address: str,
                                   days: int = 30) -> Dict[str, Any]:
        """Get behavior summary for a wallet.

        Args:
            wallet_address: Wallet address
            days: Number of days to summarize

        Returns:
            Behavior summary
        """
        patterns = self.analyze_behavior_patterns(wallet_address)
        
        # Determine activity level
        tx_count_24h = patterns.get('rolling_windows', {}).get('24h', 0)
        if tx_count_24h > 50:
            activity_level = 'very_high'
        elif tx_count_24h > 20:
            activity_level = 'high'
        elif tx_count_24h > 5:
            activity_level = 'moderate'
        elif tx_count_24h > 0:
            activity_level = 'low'
        else:
            activity_level = 'inactive'
        
        summary = {
            'wallet': wallet_address,
            'period_days': days,
            'activity_level': activity_level,
            'patterns': patterns.get('detected_patterns', []),
            'risk_indicators': patterns.get('anomalies', []),
            'aggressiveness_score': patterns.get('aggressiveness_score', 0.0),
            'burst_detected': patterns.get('burst_detected', False),
            'rolling_windows': patterns.get('rolling_windows', {})
        }
        
        return summary

    

    def _calculate_avg_curve_position(self, wallet_address: str) -> float:
        """Calculate average bonding curve entry position for a wallet.

        This estimates how early the wallet enters tokens by analyzing
        the timing of their first buy relative to token launch times.

        Returns:
            Average curve position as percentage (0-100)
            - 0-10%: Very early entry (strong sniper behavior)
            - 10-30%: Early entry (insider-like)
            - 30-70%: Normal entry
            - 70-100%: Late entry
        """
        tx_history = self.transaction_history.get(wallet_address, [])

        if not tx_history:
            return 50.0  # Default to middle position

        positions = []

        for tx in tx_history:
            if tx.get('tx_type') != 'buy':
                continue

            token_address = tx.get('token_address')
            if not token_address or token_address not in self.token_launches:
                continue

            # Calculate time since token launch
            launch_time = self.token_launches[token_address]
            tx_time = tx['timestamp']

            seconds_after_launch = (tx_time - launch_time).total_seconds()

            # Map seconds to curve position percentage
            # 0-60s = 0-10% (very early)
            # 60-300s = 10-30% (early)
            # 300-1800s = 30-70% (normal)
            # 1800+ = 70-100% (late)

            if seconds_after_launch < 0:
                # Pre-launch transaction (shouldn't happen but handle it)
                position = 0.0
            elif seconds_after_launch <= 60:
                # 0-60s: 0-10%
                position = (seconds_after_launch / 60.0) * 10.0
            elif seconds_after_launch <= 300:
                # 60-300s: 10-30%
                position = 10.0 + ((seconds_after_launch - 60.0) / 240.0) * 20.0
            elif seconds_after_launch <= 1800:
                # 300-1800s: 30-70%
                position = 30.0 + ((seconds_after_launch - 300.0) / 1500.0) * 40.0
            else:
                # 1800+ seconds: 70-100%
                position = min(100.0, 70.0 + ((seconds_after_launch - 1800.0) / 1800.0) * 30.0)

            positions.append(position)

        if not positions:
            return 50.0  # No valid data, return middle

        # Return average position
        return sum(positions) / len(positions)

    def analyze(self, wallet_address: str) -> Dict[str, Any]:
        """Async wrapper for analyze_behavior_patterns.

        This method provides async interface for the BehaviorTracker,
        matching the expected interface by WalletProfilerAgent.

        Args:
            wallet_address: Wallet address to analyze

        Returns:
            Behavior analysis dictionary
        """
        return self.analyze_behavior_patterns(wallet_address)

    def get_aggressiveness_score(self, wallet_address: str) -> float:
        """Get the aggressiveness score for a wallet.

        Args:
            wallet_address: Wallet address

        Returns:
            Aggressiveness score (0-1)
        """
        behavior = self.analyze_behavior_patterns(wallet_address)
        return behavior.get('aggressiveness_score', 0.5)

    def get_avg_curve_position(self, wallet_address: str) -> float:
        """Get the average bonding curve entry position.

        Args:
            wallet_address: Wallet address

        Returns:
            Average curve position percentage (0-100)
        """
        behavior = self.analyze_behavior_patterns(wallet_address)
        return behavior.get('avg_curve_position', 50.0)
