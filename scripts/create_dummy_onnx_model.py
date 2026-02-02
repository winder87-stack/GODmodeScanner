#!/usr/bin/env python3
"""
Create Dummy ONNX Model for Behavioral DNA Testing.

This script generates a simple PyTorch model and exports it to ONNX format
for immediate testing of the Behavioral DNA prediction pipeline.

The dummy model outputs correctly formatted predictions:
- Action logits (3 values: BUY, SELL, HOLD)
- Timing (hours since token launch)
- Amount (normalized SOL)
- Confidence (0-1)

Note: This is NOT a trained model. It outputs random but validly formatted data
for testing the integration pipeline.
"""

import torch
import torch.nn as nn
import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)


class DummyBehavioralModel(nn.Module):
    """
    Simple dummy model for testing Behavioral DNA integration.
    
    Architecture:
    - Input: (batch_size, sequence_length=20, num_features=4)
    - Flatten: (batch_size, 20*4 = 80)
    - Linear: 80 -> 4 outputs
    - Activation: Sigmoid for all outputs
    
    Outputs:
    - [0]: Action logits (will be expanded to 3 values)
    - [1]: Timing (hours since launch)
    - [2]: Amount (normalized SOL)
    - [3]: Confidence (0-1)
    """
    
    def __init__(self, sequence_length: int = 20, num_features: int = 4):
        super().__init__()
        self.sequence_length = sequence_length
        self.num_features = num_features
        
        # Simple linear layer: flattened input -> 4 outputs
        input_dim = sequence_length * num_features
        self.linear = nn.Linear(input_dim, 4)
        
        # Initialize weights for reasonable output ranges
        with torch.no_grad():
            self.linear.weight.fill_(0.1)
            self.linear.bias.fill_(0.5)
    
    def forward(self, x):
        """
        Forward pass.
        
        Args:
            x: Input tensor of shape (batch_size, sequence_length, num_features)
        
        Returns:
            Output tensor with 4 values per sample
        """
        # Flatten: (batch, seq, feat) -> (batch, seq*feat)
        x_flat = x.view(x.size(0), -1)
        
        # Linear transformation
        out = self.linear(x_flat)
        
        # Apply sigmoid to keep values in [0, 1]
        out = torch.sigmoid(out)
        
        # Reshape output to match expected format:
        # - Index 0: Action logits (3 values) - use sigmoid[0] to generate
        # - Index 1: Timing (hours) - scale sigmoid[1] to 0-24 hours
        # - Index 2: Amount (SOL) - scale sigmoid[2] to 0-10 SOL
        # - Index 3: Confidence (0-1)
        
        batch_size = x.size(0)
        
        # Create structured output: (batch, 4)
        # where output[:, 0] will be used to generate action logits
        return out


def create_dummy_model(output_path: str = "models/behavioral_dna_v1.onnx"):
    """
    Create and export dummy ONNX model.
    
    Args:
        output_path: Path to save ONNX model
    """
    print("\n=== Creating Dummy Behavioral DNA ONNX Model ===")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Create model
    print(f"Initializing dummy model...")
    model = DummyBehavioralModel(sequence_length=20, num_features=4)
    model.eval()  # Set to evaluation mode
    
    # Create dummy input
    print(f"Creating dummy input tensor (1, 20, 4)...")
    dummy_input = torch.randn(1, 20, 4)  # Batch=1, Seq=20, Feat=4
    
    # Export to ONNX
    print(f"Exporting model to ONNX: {output_path}")
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        input_names=['sequence'],
        output_names=['prediction'],
        dynamic_axes={
            'sequence': {0: 'batch_size'},
            'prediction': {0: 'batch_size'}
        },
        verbose=False
    )
    
    print(f"✓ Model exported successfully to {output_path}")
    
    # Verify the model
    print("\n=== Verifying ONNX Model ===")
    
    try:
        import onnxruntime as ort
        
        # Load and check the model
        session = ort.InferenceSession(output_path)
        
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        
        print(f"Input name: {input_name}")
        print(f"Input shape: {session.get_inputs()[0].shape}")
        print(f"Output name: {output_name}")
        print(f"Output shape: {session.get_outputs()[0].shape}")
        
        # Test inference
        print("\n=== Test Inference ===")
        outputs = session.run([output_name], {input_name: dummy_input.numpy()})
        
        print(f"Output shape: {outputs[0].shape}")
        print(f"Output values: {outputs[0]}")
        
        # Simulate post-processing
        print("\n=== Simulated Post-Processing ===")
        raw_output = outputs[0]
        
        # Extract components (as predictor would do)
        action_logits = raw_output[0]  # Use to determine action
        timing_pred = raw_output[1] * 24  # Scale to hours
        amount_pred = raw_output[2] * 10  # Scale to SOL
        confidence_pred = raw_output[3]  # Already in [0, 1]
        
        # Determine action (simulate argmax on 3 logits)
        # For dummy model, we'll use the single value to pick
        action_values = [action_logits * 0.5, action_logits * 1.0, action_logits * 0.3]
        action_id = action_values.index(max(action_values))
        action_map = {0: 'BUY', 1: 'SELL', 2: 'HOLD'}
        
        print(f"Predicted Action: {action_map[action_id]}")
        print(f"Timing: {timing_pred * 3600:.1f} seconds after launch")
        print(f"Amount: {amount_pred:.2f} SOL")
        print(f"Confidence: {confidence_pred:.2%}")
        
        print("\n✓ Dummy model created and verified successfully!")
        print("\nNote: This is a TEST model. It outputs random but validly formatted data.")
        print("For production, you must train a real model on historical wallet behavior.")
        
        return True
        
    except ImportError:
        print("\n⚠ ONNX Runtime not installed. Skipping verification.")
        print("Model was created but not verified.")
        print("Install with: pip install onnxruntime")
        return False
    except Exception as e:
        print(f"\n✗ Verification failed: {e}")
        return False


if __name__ == "__main__":
    # Parse command line args
    if len(sys.argv) > 1:
        output_path = sys.argv[1]
    else:
        output_path = os.path.join(project_root, "models", "behavioral_dna_v1.onnx")
    
    # Create model
    success = create_dummy_model(output_path)
    
    sys.exit(0 if success else 1)
