#!/bin/bash
# Initialize Ollama with CodeLlama model after container starts

set -e

echo "========================================"
echo "SINGULARITY ENGINE: OLLAMA INITIALIZATION"
echo "========================================"

echo "Waiting for Ollama service to be ready..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker exec godmode_ollama curl -f http://localhost:11434/api/tags 2>/dev/null >/dev/null; then
        echo "✓ Ollama service is ready"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts: Waiting..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo "✗ Ollama service failed to start"
    exit 1
fi

echo ""
echo "Pulling CodeLlama 7B Code model (1.3GB)..."
echo "This may take several minutes on first run..."

docker exec godmode_ollama ollama pull codellama:7b-code

echo ""
echo "✓ Ollama initialized with CodeLlama model"
echo "Model available: codellama:7b-code"
echo ""
echo "SINGULARITY ENGINE READY FOR CODE SYNTHESIS"
echo "========================================"
