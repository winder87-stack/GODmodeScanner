"""
GodMode ML Models

Machine learning models for behavioral prediction and pattern classification.
Uses ONNX Runtime for inference and PyTorch for training.
"""

import os
import json
import asyncio
import structlog
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = structlog.get_logger(__name__)

# Try to import ML libraries
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available - training disabled")

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("ONNX Runtime not available - using fallback")


class GodmodeMLModels:
    """
    ML models for wallet behavior prediction
    
    Architecture:
    - Input: 768-dimensional feature vector
    - Hidden: 512 → 256 neurons
    - Output: 4 classes (HODL, SELL, BUY, SNIPER)
    """
    
    def __init__(self, redis_client=None, model_path: str = 'data/models/behavioral_dna.onnx'):
        self.redis = redis_client
        self.model_path = model_path
        self.onnx_session = None
        
        # Load ONNX model if available
        if ONNX_AVAILABLE and os.path.exists(model_path):
            try:
                self.onnx_session = ort.InferenceSession(
                    model_path,
                    providers=['CPUExecutionProvider']
                )
                logger.info(f"ONNX model loaded: {model_path}")
            except Exception as e:
                logger.error(f"Failed to load ONNX model: {e}")
        
        self.logger = logger.bind(model="godmode_ml")
    
    # ━━━━ TODO #1: EXTRACT FEATURES ━━━━
    def extract_features(self, wallet_data: Dict[str, Any]) -> np.ndarray:
        """
        Extract 768-dimensional feature vector from wallet data
        
        Feature Groups:
        - Trading metrics (100 dims)
        - Timing features (100 dims)
        - Network features (100 dims)
        - Behavioral patterns (100 dims)
        - Historical performance (100 dims)
        - Transaction patterns (100 dims)
        - Jito usage (68 dims)
        - Statistical (100 dims)
        """
        features = []
        
        # ━━━━ GROUP 1: TRADING METRICS (100 features) ━━━━
        win_rate = wallet_data.get('win_rate', 0.0)
        features.extend([
            win_rate,
            wallet_data.get('graduation_rate', 0.0),
            wallet_data.get('total_trades', 0) / 1000.0,
            wallet_data.get('successful_trades', 0) / 1000.0,
            wallet_data.get('failed_trades', 0) / 1000.0,
        ])
        
        total_volume = wallet_data.get('total_volume_sol', 0.0)
        features.extend([
            np.log1p(total_volume),
            wallet_data.get('avg_trade_size_sol', 0.0),
            wallet_data.get('max_trade_size_sol', 0.0),
            wallet_data.get('min_trade_size_sol', 0.0),
            wallet_data.get('volume_std', 0.0),
        ])
        
        features.extend([
            wallet_data.get('curve_entry', 0.5),
            wallet_data.get('avg_entry_price', 0.0),
            wallet_data.get('avg_exit_price', 0.0),
            wallet_data.get('avg_profit_percent', 0.0),
            wallet_data.get('max_profit_percent', 0.0),
            wallet_data.get('max_loss_percent', 0.0),
        ])
        
        features.extend([
            wallet_data.get('trades_per_day', 0.0),
            wallet_data.get('tokens_per_day', 0.0),
            wallet_data.get('active_days', 0) / 365.0,
            wallet_data.get('days_since_first_trade', 0) / 365.0,
            wallet_data.get('days_since_last_trade', 0) / 30.0,
        ])
        
        features.extend([0.0] * (100 - len(features)))
        
        # ━━━━ GROUP 2: TIMING FEATURES (100 features) ━━━━
        timing_features = [
            wallet_data.get('avg_entry_seconds', 60) / 300.0,
            wallet_data.get('min_entry_seconds', 60) / 300.0,
            wallet_data.get('entries_under_3s', 0) / max(1, wallet_data.get('total_trades', 1)),
            wallet_data.get('entries_under_10s', 0) / max(1, wallet_data.get('total_trades', 1)),
            wallet_data.get('entries_under_60s', 0) / max(1, wallet_data.get('total_trades', 1)),
        ]
        
        avg_hold = wallet_data.get('avg_hold_time_seconds', 3600)
        timing_features.extend([
            np.log1p(avg_hold) / 10.0,
            wallet_data.get('min_hold_time_seconds', 0) / 3600.0,
            wallet_data.get('max_hold_time_seconds', 0) / 86400.0,
            wallet_data.get('hold_time_std', 0) / 3600.0,
        ])
        
        timing_features.extend([
            wallet_data.get('trades_during_market_hours', 0) / max(1, wallet_data.get('total_trades', 1)),
            wallet_data.get('trades_during_off_hours', 0) / max(1, wallet_data.get('total_trades', 1)),
            wallet_data.get('avg_time_between_trades', 3600) / 86400.0,
        ])
        
        timing_features.extend([0.0] * (100 - len(timing_features)))
        features.extend(timing_features[:100])
        
        # ━━━━ GROUP 3: NETWORK FEATURES (100 features) ━━━━
        network_features = [
            wallet_data.get('network_degree', 0) / 100.0,
            wallet_data.get('pagerank_score', 0.0) * 1000.0,
            wallet_data.get('betweenness_centrality', 0.0) * 100.0,
            wallet_data.get('clustering_coefficient', 0.0),
            wallet_data.get('common_funding_sources', 0) / 10.0,
        ]
        
        network_features.extend([
            wallet_data.get('cluster_size', 0) / 100.0,
            wallet_data.get('cluster_density', 0.0),
            float(wallet_data.get('is_sybil_member', False)),
            wallet_data.get('sybil_confidence', 0.0),
        ])
        
        network_features.extend([
            wallet_data.get('unique_counterparties', 0) / 100.0,
            wallet_data.get('repeat_trades_ratio', 0.0),
            wallet_data.get('coordinated_trades', 0) / 10.0,
        ])
        
        network_features.extend([0.0] * (100 - len(network_features)))
        features.extend(network_features[:100])
        
        # ━━━━ GROUP 4: BEHAVIORAL PATTERNS (100 features) ━━━━
        behavioral_features = [
            float(wallet_data.get('is_king_maker', False)),
            float(wallet_data.get('is_sniper_bot', False)),
            float(wallet_data.get('is_wash_trader', False)),
            float(wallet_data.get('is_dev_insider', False)),
        ]
        
        behavioral_features.extend([
            wallet_data.get('risk_score', 0.0) / 100.0,
            wallet_data.get('confidence_interval_low', 0.0) / 100.0,
            wallet_data.get('confidence_interval_high', 1.0) / 100.0,
            wallet_data.get('risk_consistency', 0.0),
        ])
        
        behavioral_features.extend([
            wallet_data.get('scalp_trading_ratio', 0.0),
            wallet_data.get('swing_trading_ratio', 0.0),
            wallet_data.get('position_trading_ratio', 0.0),
            wallet_data.get('diversification_score', 0.0),
        ])
        
        behavioral_features.extend([0.0] * (100 - len(behavioral_features)))
        features.extend(behavioral_features[:100])
        
        # ━━━━ GROUP 5: HISTORICAL PERFORMANCE (100 features) ━━━━
        historical_features = [
            wallet_data.get('total_profit_sol', 0.0) / 1000.0,
            wallet_data.get('total_loss_sol', 0.0) / 1000.0,
            wallet_data.get('net_profit_sol', 0.0) / 1000.0,
            wallet_data.get('roi_percent', 0.0) / 100.0,
            wallet_data.get('sharpe_ratio', 0.0),
        ]
        
        historical_features.extend([
            wallet_data.get('tokens_graduated', 0) / 100.0,
            wallet_data.get('tokens_failed', 0) / 100.0,
            wallet_data.get('tokens_rugged', 0) / 10.0,
            wallet_data.get('avg_token_lifetime_days', 0.0) / 30.0,
        ])
        
        historical_features.extend([
            wallet_data.get('best_trade_profit_sol', 0.0) / 100.0,
            wallet_data.get('worst_trade_loss_sol', 0.0) / 100.0,
            wallet_data.get('winning_streak', 0) / 10.0,
            wallet_data.get('losing_streak', 0) / 10.0,
        ])
        
        historical_features.extend([0.0] * (100 - len(historical_features)))
        features.extend(historical_features[:100])
        
        # ━━━━ GROUP 6: TRANSACTION PATTERNS (100 features) ━━━━
        tx_features = [
            wallet_data.get('avg_gas_price', 0.0) / 1000.0,
            wallet_data.get('total_fees_paid_sol', 0.0) / 10.0,
            wallet_data.get('priority_fee_usage_ratio', 0.0),
        ]
        
        tx_features.extend([
            wallet_data.get('compute_units_avg', 0) / 200000.0,
            wallet_data.get('instructions_per_tx_avg', 0) / 10.0,
            wallet_data.get('failed_tx_ratio', 0.0),
        ])
        
        tx_features.extend([0.0] * (100 - len(tx_features)))
        features.extend(tx_features[:100])
        
        # ━━━━ GROUP 7: JITO USAGE (68 features) ━━━━
        jito_features = []
        jito_stats = wallet_data.get('jito_stats', {})
        jito_features.extend([
            jito_stats.get('total_bundles', 0) / 100.0,
            jito_stats.get('total_tips_sol', 0.0) / 10.0,
            jito_stats.get('avg_tip_sol', 0.0),
            jito_stats.get('max_tip_sol', 0.0),
            jito_stats.get('bundle_success_rate', 0.0),
            jito_stats.get('first_position_ratio', 0.0),
        ])
        
        jito_features.extend([0.0] * (68 - len(jito_features)))
        features.extend(jito_features[:68])
        
        # ━━━━ GROUP 8: STATISTICAL (100 features) ━━━━
        stat_features = [
            wallet_data.get('win_rate_7d', 0.0),
            wallet_data.get('win_rate_30d', 0.0),
            wallet_data.get('volume_7d', 0.0) / 100.0,
            wallet_data.get('volume_30d', 0.0) / 1000.0,
            wallet_data.get('trades_7d', 0) / 100.0,
            wallet_data.get('trades_30d', 0) / 1000.0,
        ]
        
        stat_features.extend([
            wallet_data.get('profit_volatility', 0.0),
            wallet_data.get('volume_volatility', 0.0),
            wallet_data.get('frequency_volatility', 0.0),
        ])
        
        stat_features.extend([
            wallet_data.get('win_rate_trend', 0.0),
            wallet_data.get('volume_trend', 0.0),
            wallet_data.get('frequency_trend', 0.0),
        ])
        
        stat_features.extend([0.0] * (100 - len(stat_features)))
        features.extend(stat_features[:100])
        
        # Convert to numpy array and normalize
        feature_vector = np.array(features[:768], dtype=np.float32)
        
        if len(feature_vector) < 768:
            feature_vector = np.pad(
                feature_vector,
                (0, 768 - len(feature_vector)),
                mode='constant'
            )
        
        feature_vector = np.clip(feature_vector, -10.0, 10.0)
        
        return feature_vector
    
    # ━━━━ TODO #2: PREDICT ━━━━
    async def predict(self, wallet_address: str) -> Dict[str, float]:
        """
        Predict wallet behavior using ONNX model
        
        Returns:
            Dictionary with probabilities for HODL, SELL, BUY, SNIPER
        """
        try:
            # Fetch wallet data
            wallet_data = await self._fetch_wallet_data(wallet_address)
            
            if not wallet_data:
                return {
                    'HODL': 0.25, 'SELL': 0.25, 'BUY': 0.25, 'SNIPER': 0.25,
                    'confidence': 0.0
                }
            
            # Extract features
            features = self.extract_features(wallet_data)
            features_batch = features.reshape(1, -1)
            
            # Run inference
            if self.onnx_session:
                input_name = self.onnx_session.get_inputs()[0].name
                output_name = self.onnx_session.get_outputs()[0].name
                
                result = self.onnx_session.run(
                    [output_name],
                    {input_name: features_batch}
                )[0][0]
            else:
                result = self._fallback_prediction(wallet_data)
            
            # Parse results
            predictions = {
                'HODL': float(result[0]) if len(result) > 0 else 0.25,
                'SELL': float(result[1]) if len(result) > 1 else 0.25,
                'BUY': float(result[2]) if len(result) > 2 else 0.25,
                'SNIPER': float(result[3]) if len(result) > 3 else 0.25,
            }
            
            # Calculate confidence
            entropy = -sum(p * np.log(p + 1e-10) for p in predictions.values())
            max_entropy = np.log(4)
            confidence = 1.0 - (entropy / max_entropy)
            
            predictions['confidence'] = float(confidence)
            
            # Store prediction
            if self.redis:
                await self.redis.hset(
                    f"prediction:{wallet_address}",
                    mapping={**predictions, 'timestamp': datetime.utcnow().isoformat()}
                )
            
            return predictions
            
        except Exception as e:
            logger.error(f"Prediction error: {e}", wallet=wallet_address)
            return {
                'HODL': 0.25, 'SELL': 0.25, 'BUY': 0.25, 'SNIPER': 0.25,
                'confidence': 0.0, 'error': str(e)
            }
    
    def _fallback_prediction(self, wallet_data: Dict) -> np.ndarray:
        """Simple heuristic-based prediction"""
        sniper_score = 0.0
        if wallet_data.get('avg_entry_seconds', 60) < 3:
            sniper_score = 0.8
        elif wallet_data.get('entries_under_10s', 0) > 5:
            sniper_score = 0.6
        
        win_rate = wallet_data.get('win_rate', 0.5)
        avg_hold = wallet_data.get('avg_hold_time_seconds', 3600)
        
        if win_rate > 0.7 and avg_hold > 3600:
            hodl_score, sell_score, buy_score = 0.6, 0.2, 0.2
        elif win_rate < 0.3:
            hodl_score, sell_score, buy_score = 0.1, 0.7, 0.2
        else:
            hodl_score, sell_score, buy_score = 0.4, 0.3, 0.3
        
        total = hodl_score + sell_score + buy_score + sniper_score
        return np.array([hodl_score / total, sell_score / total, buy_score / total, sniper_score / total])
    
    # ━━━━ TODO #3: TRAIN ━━━━
    async def train(self, training_data: List[Dict[str, Any]]):
        """
        Train PyTorch model on labeled data
        """
        if not TORCH_AVAILABLE:
            logger.error("PyTorch not available - cannot train")
            return
        
        try:
            import torch.nn as nn
            import torch.optim as optim
            from torch.utils.data import Dataset, DataLoader
            
            logger.info(f"Starting training with {len(training_data)} samples")
            
            # Extract features and labels
            X, y = [], []
            for sample in training_data:
                features = self.extract_features(sample['wallet_data'])
                X.append(features)
                label_map = {'HODL': 0, 'SELL': 1, 'BUY': 2, 'SNIPER': 3}
                y.append(label_map.get(sample['label'], 0))
            
            X = np.array(X, dtype=np.float32)
            y = np.array(y, dtype=np.int64)
            
            # Split train/validation
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]
            
            # PyTorch datasets
            class WalletDataset(Dataset):
                def __init__(self, features, labels):
                    import torch
                    self.features = torch.tensor(features, dtype=torch.float32)
                    self.labels = torch.tensor(labels, dtype=torch.long)
                def __len__(self):
                    return len(self.labels)
                def __getitem__(self, idx):
                    return self.features[idx], self.labels[idx]
            
            train_dataset = WalletDataset(X_train, y_train)
            val_dataset = WalletDataset(X_val, y_val)
            
            train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=32)
            
            # Model architecture
            class BehavioralDNAModel(nn.Module):
                def __init__(self):
                    import torch.nn as nn
                    super().__init__()
                    self.fc1 = nn.Linear(768, 512)
                    self.fc2 = nn.Linear(512, 256)
                    self.fc3 = nn.Linear(256, 4)
                    self.relu = nn.ReLU()
                    self.dropout = nn.Dropout(0.3)
                
                def forward(self, x):
                    x = self.relu(self.fc1(x))
                    x = self.dropout(x)
                    x = self.relu(self.fc2(x))
                    x = self.dropout(x)
                    return self.fc3(x)
            
            import torch
            model = BehavioralDNAModel()
            criterion = nn.CrossEntropyLoss()
            optimizer = optim.Adam(model.parameters(), lr=0.001)
            
            # Training loop
            best_val_acc = 0.0
            for epoch in range(50):
                model.train()
                train_correct = train_total = 0
                
                for features_batch, labels_batch in train_loader:
                    optimizer.zero_grad()
                    outputs = model(features_batch)
                    loss = criterion(outputs, labels_batch)
                    loss.backward()
                    optimizer.step()
                    
                    _, predicted = torch.max(outputs.data, 1)
                    train_total += labels_batch.size(0)
                    train_correct += (predicted == labels_batch).sum().item()
                
                train_acc = 100 * train_correct / train_total
                
                # Validate
                model.eval()
                val_correct = val_total = 0
                with torch.no_grad():
                    for features_batch, labels_batch in val_loader:
                        outputs = model(features_batch)
                        _, predicted = torch.max(outputs.data, 1)
                        val_total += labels_batch.size(0)
                        val_correct += (predicted == labels_batch).sum().item()
                
                val_acc = 100 * val_correct / val_total
                
                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    torch.save(model.state_dict(), 'data/models/behavioral_dna_best.pt')
                
                if epoch % 10 == 0:
                    logger.info(f"Epoch {epoch}: train_acc={train_acc:.2f}%, val_acc={val_acc:.2f}%")
            
            # Export to ONNX
            model.eval()
            dummy_input = torch.randn(1, 768)
            torch.onnx.export(model, dummy_input, 'data/models/behavioral_dna.onnx',
                             input_names=['input'], output_names=['output'],
                             dynamic_axes={'input': {0: 'batch_size'}, 'output': {0: 'batch_size'}})
            
            logger.info(f"Training complete: best_val_acc={best_val_acc:.2f}%")
            
        except Exception as e:
            logger.error(f"Training error: {e}")
            raise
    
    # ━━━━ TODO #4: ONLINE LEARN ━━━━
    async def online_learn(self, wallet_address: str, actual_behavior: str):
        """
        Online learning: update model with observed behavior
        """
        try:
            wallet_data = await self._fetch_wallet_data(wallet_address)
            
            if not wallet_data:
                logger.warning(f"No data for online learning: {wallet_address}")
                return
            
            experience = {
                'wallet_data': wallet_data,
                'label': actual_behavior,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            if self.redis:
                await self.redis.lpush('ml:experience_buffer', json.dumps(experience))
                await self.redis.ltrim('ml:experience_buffer', 0, 9999)
                
                buffer_size = await self.redis.llen('ml:experience_buffer')
                
                if buffer_size >= 1000 and buffer_size % 1000 == 0:
                    logger.info(f"Triggering retraining with {buffer_size} samples")
                    buffer_data = await self.redis.lrange('ml:experience_buffer', 0, -1)
                    training_data = [json.loads(sample) for sample in buffer_data]
                    asyncio.create_task(self.train(training_data))
            
        except Exception as e:
            logger.error(f"Online learning error: {e}")
    
    # ━━━━ TODO #5: CLASSIFY ━━━━
    def classify(self, features: np.ndarray) -> str:
        """
        Classify wallet into behavior category
        """
        try:
            features_batch = features.reshape(1, -1)
            
            if self.onnx_session:
                input_name = self.onnx_session.get_inputs()[0].name
                output_name = self.onnx_session.get_outputs()[0].name
                
                result = self.onnx_session.run([output_name],
                                              {input_name: features_batch.astype(np.float32)})[0][0]
                predicted_class = int(np.argmax(result))
            else:
                # Fallback
                if features[200] > 0.8:
                    predicted_class = 3
                elif features[400] > 0.7:
                    predicted_class = 1
                elif features[0] > 0.7:
                    predicted_class = 0
                else:
                    predicted_class = 2
            
            class_map = {0: 'HODL', 1: 'SELL', 2: 'BUY', 3: 'SNIPER'}
            return class_map[predicted_class]
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return 'HODL'
    
    # ━━━━ TODO #6: EXPLAIN ━━━━
    async def explain(self, wallet_address: str) -> Dict[str, Any]:
        """
        Explain model prediction using feature importance
        """
        try:
            prediction = await self.predict(wallet_address)
            wallet_data = await self._fetch_wallet_data(wallet_address)
            features = self.extract_features(wallet_data)
            
            # Feature importance (magnitude-based)
            feature_importances = np.abs(features)
            top_indices = np.argsort(feature_importances)[-10:][::-1]
            
            top_features = [{'index': int(idx), 'importance': float(feature_importances[idx])}
                           for idx in top_indices]
            
            predicted_class = max(prediction, key=lambda k: prediction[k] if k != 'confidence' else 0)
            confidence = prediction.get('confidence', 0.0)
            
            # Generate explanation
            explanation = f"High confidence prediction: {predicted_class}. "
            
            if predicted_class == 'SNIPER':
                explanation += f"Sniper bot characteristics: avg entry {wallet_data.get('avg_entry_seconds', 0):.1f}s."
            elif predicted_class == 'HODL':
                explanation += f"Holding behavior: win rate {wallet_data.get('win_rate', 0):.1%}."
            
            return {
                'wallet': wallet_address,
                'prediction': predicted_class,
                'confidence': confidence,
                'top_features': top_features,
                'explanation': explanation
            }
            
        except Exception as e:
            logger.error(f"Explanation error: {e}")
            return {'wallet': wallet_address, 'error': str(e)}
    
    # Helper methods
    async def _fetch_wallet_data(self, wallet_address: str) -> Dict[str, Any]:
        """Fetch wallet data from Redis"""
        try:
            if not self.redis:
                return {}
            
            cached = await self.redis.hgetall(f"wallet:{wallet_address}")
            
            if cached:
                return {
                    k.decode() if isinstance(k, bytes) else k:
                    json.loads(v) if isinstance(v, (str, bytes)) and v not in ('null', b'null') else v
                    for k, v in cached.items()
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Wallet data fetch error: {e}")
            return {}
