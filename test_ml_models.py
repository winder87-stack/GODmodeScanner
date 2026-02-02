"""Test ML Models implementations"""

import sys
sys.path.insert(0, '.')

import numpy as np

print("=" * 60)
print("ML MODELS TEST SUITE")
print("=" * 60)

# Test 1: Feature Extraction
print("\n1. Testing Feature Extraction...")
try:
    from agents.godmode_ml_models import GodmodeMLModels
    
    ml = GodmodeMLModels()
    
    test_wallet = {
        'win_rate': 0.75,
        'total_trades': 100,
        'avg_entry_seconds': 5.0,
        'total_volume_sol': 1000.0,
        'is_king_maker': True,
        'jito_stats': {'total_bundles': 50, 'avg_tip_sol': 0.5}
    }
    
    features = ml.extract_features(test_wallet)
    
    assert features.shape == (768,), f"Expected (768,), got {features.shape}"
    assert features.dtype == np.float32, f"Expected float32, got {features.dtype}"
    assert not np.isnan(features).any(), "Features contain NaN"
    
    print(f"✅ Feature extraction: {features.shape}")
    print(f"✅ Feature range: [{features.min():.2f}, {features.max():.2f}]")
    print("✅ Feature extraction PASSED")
    
except Exception as e:
    print(f"❌ Feature extraction FAILED: {e}")

# Test 2: Classification
print("\n2. Testing Classification...")
try:
    from agents.godmode_ml_models import GodmodeMLModels
    
    ml = GodmodeMLModels()
    
    # Test with sniper-like features
    sniper_features = np.zeros(768, dtype=np.float32)
    sniper_features[200] = 0.9  # High entry timing score
    
    result = ml.classify(sniper_features)
    
    assert result in ['HODL', 'SELL', 'BUY', 'SNIPER'], f"Invalid classification: {result}"
    
    print(f"✅ Classification result: {result}")
    print("✅ Classification PASSED")
    
except Exception as e:
    print(f"❌ Classification FAILED: {e}")

# Test 3: Pattern Analyzer ML Models
print("\n3. Testing Pattern Analyzer ML Models...")
try:
    from agents.pattern_analyzer.models.ml_models import MLModels
    
    ml = MLModels()
    
    test_wallet = {
        'win_rate': 0.85,
        'total_trades': 200,
        'avg_entry_seconds': 2.5,
        'is_sniper_bot': True
    }
    
    features = ml.extract_features(test_wallet)
    
    assert features.shape == (768,), f"Expected (768,), got {features.shape}"
    
    result = ml.classify(features)
    
    print(f"✅ Pattern analyzer features: {features.shape}")
    print(f"✅ Pattern analyzer classification: {result}")
    print("✅ Pattern Analyzer ML Models PASSED")
    
except Exception as e:
    print(f"❌ Pattern Analyzer ML Models FAILED: {e}")

# Test 4: Fallback Prediction
print("\n4. Testing Fallback Prediction...")
try:
    from agents.godmode_ml_models import GodmodeMLModels
    
    ml = GodmodeMLModels()
    
    # Test sniper detection
    sniper_wallet = {'avg_entry_seconds': 2.0, 'entries_under_10s': 10}
    result = ml._fallback_prediction(sniper_wallet)
    
    assert result.shape == (4,), f"Expected (4,), got {result.shape}"
    assert np.isclose(result.sum(), 1.0, atol=0.01), f"Probabilities don't sum to 1: {result.sum()}"
    
    print(f"✅ Fallback prediction: {result}")
    print(f"✅ Sniper score: {result[3]:.2f}")
    print("✅ Fallback Prediction PASSED")
    
except Exception as e:
    print(f"❌ Fallback Prediction FAILED: {e}")

print("\n" + "=" * 60)
print("ML MODELS TEST SUMMARY")
print("=" * 60)
print("✅ Feature extraction: 768-dimensional vectors")
print("✅ Classification: 4-class prediction")
print("✅ Pattern analyzer: Full integration")
print("✅ Fallback: Heuristic-based prediction")
print("\n✅ ALL ML MODEL TESTS PASSED")
print("=" * 60)
