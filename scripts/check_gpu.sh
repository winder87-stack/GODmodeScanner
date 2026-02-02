#!/bin/bash
# ============================================
# GODMODESCANNER GPU Availability Checker
# ============================================
# Verifies NVIDIA GPU and CUDA environment
# for GPU-accelerated graph analysis
#
# Usage: ./scripts/check_gpu.sh
# ============================================

set -e

echo "========================================="
echo "GODMODESCANNER GPU Environment Check"
echo "========================================="
echo ""

# Colors for output
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
NC='[0m' # No Color

pass_count=0
fail_count=0

check_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((pass_count++))
}

check_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((fail_count++))
}

check_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# ============================================
# 1. Check NVIDIA Driver
# ============================================
echo "[1/6] Checking NVIDIA Driver..."
if command -v nvidia-smi &> /dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    if [ -n "$DRIVER_VERSION" ]; then
        check_pass "NVIDIA Driver $DRIVER_VERSION installed"
    else
        check_fail "NVIDIA driver installed but not responding"
    fi
else
    check_fail "nvidia-smi not found - NVIDIA driver not installed"
fi

# ============================================
# 2. Check GPU Hardware
# ============================================
echo ""
echo "[2/6] Checking GPU Hardware..."
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    if [ -n "$GPU_NAME" ]; then
        check_pass "GPU: $GPU_NAME ($GPU_MEMORY)"
    else
        check_fail "No GPU detected"
    fi
else
    check_fail "Cannot query GPU hardware"
fi

# ============================================
# 3. Check CUDA Version
# ============================================
echo ""
echo "[3/6] Checking CUDA..."
if command -v nvcc &> /dev/null; then
    CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $5}' | cut -d',' -f1)
    check_pass "CUDA $CUDA_VERSION installed"
else
    # Try alternative check
    if [ -f /usr/local/cuda/version.txt ]; then
        CUDA_VERSION=$(cat /usr/local/cuda/version.txt)
        check_pass "CUDA found: $CUDA_VERSION"
    elif nvidia-smi &> /dev/null; then
        CUDA_VERSION=$(nvidia-smi | grep "CUDA Version" | awk '{print $9}')
        if [ -n "$CUDA_VERSION" ]; then
            check_pass "CUDA $CUDA_VERSION (driver-reported)"
        else
            check_warn "CUDA toolkit not found, but driver supports CUDA"
        fi
    else
        check_fail "CUDA not installed"
    fi
fi

# ============================================
# 4. Check Docker GPU Support
# ============================================
echo ""
echo "[4/6] Checking Docker GPU Support..."
if command -v docker &> /dev/null; then
    # Check for nvidia-container-toolkit
    if docker info 2>/dev/null | grep -q "nvidia"; then
        check_pass "Docker NVIDIA runtime available"
    elif [ -f /etc/docker/daemon.json ] && grep -q "nvidia" /etc/docker/daemon.json 2>/dev/null; then
        check_pass "NVIDIA Container Toolkit configured"
    else
        check_warn "NVIDIA Container Toolkit may not be configured"
        echo "       Install with: apt-get install nvidia-container-toolkit"
    fi
else
    check_warn "Docker not installed (required for containerized deployment)"
fi

# ============================================
# 5. Check Python GPU Libraries
# ============================================
echo ""
echo "[5/6] Checking Python GPU Libraries..."

# Check cuGraph
python3 -c "import cugraph; print(f'cuGraph {cugraph.__version__}')" 2>/dev/null && check_pass "cuGraph installed" || check_warn "cuGraph not installed (GPU graph analysis unavailable)"

# Check cuDF
python3 -c "import cudf; print(f'cuDF {cudf.__version__}')" 2>/dev/null && check_pass "cuDF installed" || check_warn "cuDF not installed"

# Check CuPy
python3 -c "import cupy; print(f'CuPy {cupy.__version__}')" 2>/dev/null && check_pass "CuPy installed" || check_warn "CuPy not installed"

# Check PyTorch CUDA
python3 -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" 2>/dev/null && check_pass "PyTorch with CUDA" || check_warn "PyTorch CUDA not available"

# ============================================
# 6. GPU Memory Test
# ============================================
echo ""
echo "[6/6] Running GPU Memory Test..."
python3 << 'EOF' 2>/dev/null
try:
    import cupy as cp
    # Allocate 1GB test array
    test_size = 1024 * 1024 * 256  # 1GB of float32
    arr = cp.zeros(test_size, dtype=cp.float32)
    del arr
    cp.get_default_memory_pool().free_all_blocks()
    print("GPU memory allocation: OK")
except ImportError:
    print("CuPy not available - skipping memory test")
except Exception as e:
    print(f"GPU memory test failed: {e}")
EOF

if [ $? -eq 0 ]; then
    check_pass "GPU memory allocation test"
else
    check_warn "GPU memory test skipped or failed"
fi

# ============================================
# Summary
# ============================================
echo ""
echo "========================================="
echo "GPU Check Summary"
echo "========================================="
echo -e "Passed: ${GREEN}$pass_count${NC}"
echo -e "Failed: ${RED}$fail_count${NC}"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ GPU environment ready for GODMODESCANNER${NC}"
    echo ""
    echo "To deploy with GPU acceleration:"
    echo "  docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d"
    exit 0
else
    echo -e "${YELLOW}⚠ GPU environment has issues${NC}"
    echo ""
    echo "GODMODESCANNER will use CPU fallback for graph analysis."
    echo "For GPU acceleration, resolve the failed checks above."
    echo ""
    echo "Quick fixes:"
    echo "  1. Install NVIDIA driver: apt-get install nvidia-driver-535"
    echo "  2. Install CUDA toolkit: apt-get install cuda-toolkit-12-1"
    echo "  3. Install container toolkit: apt-get install nvidia-container-toolkit"
    echo "  4. Install RAPIDS: pip install cugraph-cu12 cudf-cu12 cupy-cuda12x"
    exit 1
fi
