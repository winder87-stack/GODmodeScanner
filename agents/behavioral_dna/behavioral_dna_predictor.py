"""Behavioral DNA Predictor - Real-time wallet behavior prediction engine.

This module provides ONNX-based inference for predicting a wallet's next action.
Target: <50ms prediction latency for sub-second market advantage.
"""

import asyncio
import time
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import structlog

logger = structlog.get_logger()

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("ONNX Runtime not available. Behavioral DNA prediction disabled.")


class BehavioralDNAPredictor:
    """
    Real-time inference engine for predicting wallet behavior.
    
    Uses a pre-trained ONNX model for sub-50ms predictions of:
    - Next action (BUY/SELL/HOLD)
    - Timing (seconds after token launch)
    - Amount (SOL)
    - Confidence (0-1)
    
    Performance targets:
    - Inference latency: <50ms
    - Throughput: 20+ predictions/second
    - Accuracy: >=75% on test set
    """
    
    # Action mappings
    ACTION_MAP = {'BUY': 0, 'SELL': 1, 'HOLD': 2}
    ACTION_MAP_INV = {0: 'BUY', 1: 'SELL', 2: 'HOLD'}
    
    # Model configuration
    SEQUENCE_LENGTH = 20  # Number of past actions to consider
    NUM_FEATURES = 4  # [action_id, timing, amount, market_cap]
    
    def __init__(self, model_path: str = "models/behavioral_dna_v1.onnx", 
                 num_threads: int = 0):
        """
        Initialize the predictor with a pre-trained ONNX model.
        
        Args:
            model_path: Path to ONNX model file
            num_threads: Number of threads for ONNX Runtime (0 = auto)
        """
        self.model_path = model_path
        self.session = None
        self.input_name = None
        self.output_name = None
        self._initialized = False
        
        if ONNX_AVAILABLE:
            self._load_model(num_threads)
    
    def _load_model(self, num_threads: int) -> None:
        """Load ONNX model with optimized settings."""
        try:
            # Configure ONNX Runtime for maximum performance
            sess_options = ort.SessionOptions()
            sess_options.inter_op_num_threads = num_threads  # 0 = use all available cores
            sess_options.intra_op_num_threads = num_threads
            sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            
            # Load the model
            self.session = ort.InferenceSession(self.model_path, sess_options=sess_options)
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            self._initialized = True
            
            logger.info(
                "BehavioralDNA model loaded successfully",
                model_path=self.model_path,
                input_name=self.input_name,
                output_name=self.output_name
            )
        except FileNotFoundError:
            logger.warning(
                "ONNX model file not found. Prediction disabled.",
                model_path=self.model_path
            )
            self.session = None
        except Exception as e:
            logger.error(
                "Failed to load ONNX model",
                model_path=self.model_path,
                error=str(e)
            )
            self.session = None
    
    def is_available(self) -> bool:
        """Check if the predictor is ready for inference."""
        return ONNX_AVAILABLE and self.session is not None
    
    async def predict_next_action(self, 
                                  wallet_address: str,
                                  db_pool,
                                  lookback: int = 20) -> Optional[Dict[str, Any]]:
        """
        Predict the next action for a given wallet.
        
        Args:
            wallet_address: Wallet address to predict for
            db_pool: Database connection pool
            lookback: Number of past actions to consider
        
        Returns:
            Prediction dictionary with:
            {
                'action': 'BUY',           # or 'SELL', 'HOLD'
                'timing': 15.3,           # Predicted seconds after token launch
                'amount': 2.5,            # Predicted amount in SOL
                'confidence': 0.85,        # Model confidence (0-1)
                'latency_ms': 42.3         # Actual inference latency
            }
            None if prediction unavailable (no model, insufficient data, or error)
        """
        if not self.is_available():
            logger.warning("BehavioralDNA model not available, skipping prediction")
            return None
        
        start_time = time.perf_counter()
        
        try:
            # 1. Fetch the wallet's recent action sequence
            sequence = await self._fetch_wallet_sequence(wallet_address, db_pool, lookback)
            if not sequence or len(sequence) < 5:
                logger.debug(
                    "Insufficient history for prediction",
                    wallet=wallet_address,
                    history_length=len(sequence) if sequence else 0,
                    minimum_required=5
                )
                return None
            
            # 2. Pre-process the sequence into model input format
            input_tensor = self._preprocess_sequence(sequence)
            
            # 3. Run inference (ONNX is synchronous, use thread pool)
            loop = asyncio.get_event_loop()
            outputs = await loop.run_in_executor(
                None,
                self.session.run,
                [self.output_name],
                {self.input_name: input_tensor}
            )
            
            prediction = outputs[0]  # Assuming single output
            
            # 4. Post-process output into human-readable format
            result = self._postprocess_prediction(prediction)
            
            # 5. Add latency information
            latency_ms = (time.perf_counter() - start_time) * 1000
            result['latency_ms'] = latency_ms
            
            logger.info(
                "BehavioralDNA prediction generated",
                wallet=wallet_address,
                action=result['action'],
                confidence=result['confidence'],
                latency_ms=latency_ms
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "BehavioralDNA prediction failed",
                wallet=wallet_address,
                error=str(e),
                exc_info=True
            )
            return None
    
    async def _fetch_wallet_sequence(self,
                                     wallet_address: str,
                                     db_pool,
                                     lookback: int = 20) -> Optional[List[Dict]]:
        """
        Fetch the last N actions for a wallet from the database.
        
        Args:
            wallet_address: Wallet address to fetch history for
            db_pool: Database connection pool
            lookback: Number of recent actions to fetch
        
        Returns:
            List of action dictionaries with fields:
            - action: 'BUY', 'SELL', or 'HOLD'
            - timestamp: datetime of the action
            - amount: amount in SOL
            - token_launch_time: datetime when token was launched
            - token_market_cap: market cap at time of action
        """
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        action,
                        timestamp,
                        amount,
                        token_launch_time,
                        token_market_cap
                    FROM behavior_history 
                    WHERE wallet_address = $1
                    ORDER BY timestamp DESC 
                    LIMIT $2
                """, wallet_address, lookback)
                
                # Convert to list of dicts
                sequence = [dict(row) for row in rows]
                
                # Reverse to have chronological order (oldest first)
                sequence.reverse()
                
                return sequence
                
        except Exception as e:
            logger.error(
                "Failed to fetch wallet sequence",
                wallet=wallet_address,
                error=str(e)
            )
            return None
    
    def _preprocess_sequence(self, sequence: List[Dict]) -> np.ndarray:
        """
        Convert a list of actions into a numerical tensor for the model.
        
        Features per action:
        - action_id: 0 (BUY), 1 (SELL), 2 (HOLD)
        - timing: Hours since token launch
        - amount: Normalized amount (SOL / 10)
        - market_cap: Normalized market cap (SOL / 100k)
        
        Args:
            sequence: List of action dictionaries
        
        Returns:
            numpy array of shape (1, SEQUENCE_LENGTH, NUM_FEATURES)
        """
        processed_sequence = []
        
        for action in sequence:
            # Action ID
            action_id = self.ACTION_MAP.get(action.get('action', 'HOLD'), 2)
            
            # Normalize timing (hours since launch)
            timestamp = action.get('timestamp', datetime.now())
            launch_time = action.get('token_launch_time', timestamp)
            timing_hours = (timestamp - launch_time).total_seconds() / 3600.0
            
            # Normalize amount (SOL / 10)
            amount = action.get('amount', 0) / 10.0
            
            # Normalize market cap (SOL / 100k)
            mcap = action.get('token_market_cap', 0) / 100000.0
            
            processed_sequence.append([action_id, timing_hours, amount, mcap])
        
        # Pad or truncate to fixed length
        if len(processed_sequence) < self.SEQUENCE_LENGTH:
            # Pad with zeros (no action)
            padding = [[0, 0, 0, 0]] * (self.SEQUENCE_LENGTH - len(processed_sequence))
            processed_sequence.extend(padding)
        else:
            # Truncate (keep most recent)
            processed_sequence = processed_sequence[-self.SEQUENCE_LENGTH:]
        
        # Return as numpy array with batch dimension
        return np.array([processed_sequence], dtype=np.float32)
    
    def _postprocess_prediction(self, raw_output: np.ndarray) -> Dict[str, Any]:
        """
        Convert raw model output into a clean prediction.
        
        Expected output format:
        - raw_output[0][0]: Action logits (3 values)
        - raw_output[0][1]: Timing prediction (hours)
        - raw_output[0][2]: Amount prediction (normalized)
        - raw_output[0][3]: Confidence score (0-1)
        
        Args:
            raw_output: Raw numpy array from ONNX model
        
        Returns:
            Dictionary with processed prediction
        """
        # Extract outputs
        action_logits = raw_output[0][0]
        timing_pred = raw_output[0][1]
        amount_pred = raw_output[0][2]
        confidence_pred = raw_output[0][3]
        
        # Get most likely action
        action_id = np.argmax(action_logits)
        action = self.ACTION_MAP_INV.get(action_id, 'HOLD')
        
        # Convert back to original units
        timing_seconds = float(timing_pred * 3600)  # Hours to seconds
        amount_sol = float(amount_pred * 10)  # Normalized to SOL
        confidence = float(np.clip(confidence_pred, 0, 1))  # Clip to valid range
        
        return {
            'action': action,
            'timing': timing_seconds,
            'amount': amount_sol,
            'confidence': confidence
        }
    
    async def predict_batch(self, 
                           wallet_addresses: List[str],
                           db_pool,
                           lookback: int = 20) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Predict next actions for multiple wallets in parallel.
        
        Args:
            wallet_addresses: List of wallet addresses to predict for
            db_pool: Database connection pool
            lookback: Number of past actions to consider
        
        Returns:
            Dictionary mapping wallet_address -> prediction or None
        """
        # Create prediction tasks
        tasks = [
            self.predict_next_action(addr, db_pool, lookback)
            for addr in wallet_addresses
        ]
        
        # Execute in parallel
        results = await asyncio.gather(*tasks)
        
        # Map back to wallet addresses
        return dict(zip(wallet_addresses, results))


# Convenience function for quick instantiation
_predictor_instance: Optional[BehavioralDNAPredictor] = None

def get_predictor(model_path: str = "models/behavioral_dna_v1.onnx") -> BehavioralDNAPredictor:
    """Get or create a singleton predictor instance."""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = BehavioralDNAPredictor(model_path)
    return _predictor_instance
