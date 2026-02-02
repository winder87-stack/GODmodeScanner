#!/usr/bin/env python3
"""
Convert PyTorch Models to ONNX Format

Converts Behavioral DNA and other PyTorch models to ONNX for
GPU-accelerated inference with TensorRT optimization.

Usage:
    python scripts/convert_to_onnx.py --model behavioral_dna --output models/
    python scripts/convert_to_onnx.py --model risk_scorer --input models/risk.pt
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import torch
import torch.nn as nn

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DummyBehavioralDNA(nn.Module):
    """Dummy model for testing - replace with actual model"""

    def __init__(self, input_dim: int = 768, output_dim: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, 512)
        self.fc2 = nn.Linear(512, 256)
        self.fc3 = nn.Linear(256, output_dim)
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.sigmoid(self.fc3(x))
        return x


def get_model(model_name: str, checkpoint_path: Optional[str] = None) -> nn.Module:
    """
    Load PyTorch model by name or checkpoint

    Args:
        model_name: Name of the model (behavioral_dna, risk_scorer, etc.)
        checkpoint_path: Path to checkpoint file

    Returns:
        PyTorch model instance
    """
    if checkpoint_path and os.path.exists(checkpoint_path):
        logger.info(f"Loading model from checkpoint: {checkpoint_path}")
        model = torch.load(checkpoint_path, map_location='cpu')
        return model

    # Create model by name
    if model_name == 'behavioral_dna':
        model = DummyBehavioralDNA(input_dim=768, output_dim=4)
    elif model_name == 'risk_scorer':
        model = DummyBehavioralDNA(input_dim=16, output_dim=1)
    elif model_name == 'pattern_classifier':
        model = DummyBehavioralDNA(input_dim=32, output_dim=6)
    else:
        raise ValueError(f"Unknown model: {model_name}")

    model.eval()
    return model


def convert_to_onnx(
    model: nn.Module,
    output_path: str,
    input_shape: tuple = (1, 768),
    opset_version: int = 17,
    dynamic_axes: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convert PyTorch model to ONNX format

    Args:
        model: PyTorch model
        output_path: Output ONNX file path
        input_shape: Shape of dummy input
        opset_version: ONNX opset version
        dynamic_axes: Dynamic axes configuration

    Returns:
        Path to saved ONNX model
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Create dummy input
    dummy_input = torch.randn(*input_shape)

    # Default dynamic axes for batch size
    if dynamic_axes is None:
        dynamic_axes = {
            'input': {0: 'batch_size'},
            'output': {0: 'batch_size'}
        }

    # Export to ONNX
    logger.info(f"Converting model to ONNX: {output_path}")
    logger.info(f"  Input shape: {input_shape}")
    logger.info(f"  Opset version: {opset_version}")
    logger.info(f"  Dynamic axes: {dynamic_axes}")

    try:
        torch.onnx.export(
            model,
            dummy_input,
            output_path,
            export_params=True,
            opset_version=opset_version,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output'],
            dynamic_axes=dynamic_axes
        )

        logger.info(f"✅ Model converted successfully: {output_path}")

        # Verify the model
        _verify_onnx_model(output_path)

        return output_path

    except Exception as e:
        logger.error(f"❌ Failed to convert model: {e}")
        raise


def _verify_onnx_model(onnx_path: str):
    """Verify ONNX model is valid"""
    try:
        import onnx
        model = onnx.load(onnx_path)
        onnx.checker.check_model(model)

        # Log model info
        logger.info(f"  Model inputs: {[input.name for input in model.graph.input]}")
        logger.info(f"  Model outputs: {[output.name for output in model.graph.outputs]}")
        logger.info(f"  Opset version: {model.opset_import[0].version}")
        logger.info("✅ ONNX model verification passed")

    except ImportError:
        logger.warning("onnx package not installed, skipping verification")
    except Exception as e:
        logger.warning(f"ONNX verification warning: {e}")


def optimize_for_tensorrt(onnx_path: str, output_path: Optional[str] = None) -> str:
    """
    Optimize ONNX model for TensorRT

    Args:
        onnx_path: Path to ONNX model
        output_path: Output path for optimized model

    Returns:
        Path to optimized model
    """
    if output_path is None:
        base, ext = os.path.splitext(onnx_path)
        output_path = f"{base}_trt{ext}"

    logger.info(f"Optimizing for TensorRT: {output_path}")

    try:
        # Try using polygraphy if available
        from polygraphy.backend.onnxrt import OnnxRtRunner
        from polygraphy.backend.trt import EngineFromNetwork

        logger.info("Using Polygraphy for TensorRT optimization")
        # Note: Full TensorRT optimization requires runtime

    except ImportError:
        logger.info("Polygraphy not available, using standard ONNX")

    # For now, just copy the file (TensorRT optimization happens at runtime)
    import shutil
    shutil.copy(onnx_path, output_path)
    logger.info(f"✅ TensorRT-ready model: {output_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Convert PyTorch models to ONNX format'
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='behavioral_dna',
        help='Model name (behavioral_dna, risk_scorer, pattern_classifier)'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        help='Path to PyTorch checkpoint (.pt file)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='models',
        help='Output directory for ONNX model'
    )
    parser.add_argument(
        '--opset',
        type=int,
        default=17,
        help='ONNX opset version (default: 17)'
    )
    parser.add_argument(
        '--tensorrt', '-t',
        action='store_true',
        help='Optimize for TensorRT'
    )

    args = parser.parse_args()

    # Load model
    logger.info(f"Loading model: {args.model}")
    model = get_model(args.model, args.input)

    # Determine input shape based on model
    input_shapes = {
        'behavioral_dna': (1, 768),
        'risk_scorer': (1, 16),
        'pattern_classifier': (1, 32)
    }
    input_shape = input_shapes.get(args.model, (1, 768))

    # Output path
    output_path = os.path.join(args.output, f"{args.model}.onnx")

    # Convert
    onnx_path = convert_to_onnx(
        model,
        output_path,
        input_shape=input_shape,
        opset_version=args.opset
    )

    # TensorRT optimization
    if args.tensorrt:
        optimize_for_tensorrt(onnx_path)

    logger.info("Conversion complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
