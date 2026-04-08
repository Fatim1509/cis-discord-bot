#!/bin/bash
# CIS Discord Bot Startup Script

# Enable wake lock if in Termux
if command -v termux-wake-lock >/dev/null 2>&1; then
    echo "🔋 Enabling wake lock..."
    termux-wake-lock
fi

# Change to script directory
cd "$(dirname "$0")"

# Create logs directory
mkdir -p logs data

# Create config from example if it doesn't exist
if [ ! -f config.json ]; then
    echo "⚙️ Creating config.json from example..."
    cp config.json.example config.json
    echo "❗ Please edit config.json with your tokens before running again"
    exit 1
fi

# Check Python installation
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# Start bot
echo "🚀 Starting CIS Discord Bot..."
echo "   Logs: logs/bot.log"
echo "   Config: config.json"
echo "   Press Ctrl+C to stop"

# Run with logging
nohup python3 bot.py > logs/bot.log 2>&1 &
BOT_PID=$!

echo $BOT_PID > bot.pid
echo "✅ Bot started with PID: $BOT_PID"

# Function to stop bot
stop_bot() {
    echo "🛑 Stopping CIS Bot..."
    if [ -f bot.pid ]; then
        PID=$(cat bot.pid)
        kill $PID 2>/dev/null
        rm bot.pid
        echo "✅ Bot stopped"
    else
        echo "❌ Bot PID file not found"
    fi
    
    # Disable wake lock if in Termux
    if command -v termux-wake-unlock >/dev/null 2>&1; then
        echo "🔓 Disabling wake lock..."
        termux-wake-unlock
    fi
}

# Handle script termination
trap stop_bot EXIT

# Keep script running
echo "📝 Bot is running. Press Ctrl+C to stop."
echo "📊 Check logs: tail -f logs/bot.log"

# Wait for termination
wait $BOT_PID