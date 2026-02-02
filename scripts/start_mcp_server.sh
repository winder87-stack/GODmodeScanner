#!/bin/bash
# MCP Server Startup Script

set -e

echo "🚀 Starting GODMODESCANNER MCP Server"
echo "====================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set defaults
export MCP_PORT=${MCP_PORT:-8000}
export REDIS_URL=${REDIS_URL:-redis://localhost:6379}
export LOG_LEVEL=${LOG_LEVEL:-info}

# Check Redis connection
echo "
📡 Checking Redis connection..."
if redis-cli -u $REDIS_URL ping > /dev/null 2>&1; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running. Starting Redis..."
    redis-server --daemonize yes
    sleep 2
fi

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "
📦 Installing MCP dependencies..."
    pip install fastapi uvicorn httpx redis psutil langgraph
fi

# Start MCP server
echo "
🚀 Starting MCP Server on port $MCP_PORT..."
cd /a0/usr/projects/godmodescanner/mcp_servers
python mcp_server.py &
MCP_PID=$!

echo "✅ MCP Server started (PID: $MCP_PID)"
echo "
📊 Server Info:"
echo "   • URL: http://localhost:$MCP_PORT"
echo "   • Health: http://localhost:$MCP_PORT/health"
echo "   • Docs: http://localhost:$MCP_PORT/docs"
echo "   • WebSocket: ws://localhost:$MCP_PORT/ws/events"

# Wait for server to be ready
echo "
⏳ Waiting for server to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:$MCP_PORT/health > /dev/null 2>&1; then
        echo "✅ MCP Server is ready!"
        break
    fi
    sleep 1
done

echo "
" + "="*80
echo "🎉 MCP SERVER RUNNING"
echo "="*80
echo "
Press Ctrl+C to stop"

# Handle shutdown
trap "echo '
🛑 Stopping MCP Server...'; kill $MCP_PID; exit 0" INT TERM

# Keep script running
wait $MCP_PID
