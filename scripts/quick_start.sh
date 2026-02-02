#!/bin/bash
# GODMODESCANNER Quick Start Script
# One-command deployment and startup

set -e  # Exit on error

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                                                                 ║"
echo "║            🔥 GODMODESCANNER QUICK START 🔥                    ║"
echo "║                                                                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Run deployment
echo "🚀 Running deployment..."
python3 scripts/deploy.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "🔥 Starting GODMODESCANNER..."
    echo ""
    python3 example_detector.py
else
    echo ""
    echo "❌ Deployment failed. Please check errors above."
    exit 1
fi
