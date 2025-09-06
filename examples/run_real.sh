#!/usr/bin/env bash
# Example: Run real GPIO backend with proper setup and validation

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🔌 Running real GPIO latency measurement..."

# Environment check
echo "🔍 Checking environment..."
bash scripts/env_check.sh || {
    echo "❌ Environment check failed. Please fix issues before continuing."
    exit 1
}

# Create output directory
mkdir -p data/examples

# Wiring reminder
echo
echo "📋 WIRING CHECKLIST:"
echo "  ✓ GPIO 18 (Pin 12) connected to GPIO 23 (Pin 16)"
echo "  ✓ 10kΩ resistor from GPIO 23 to GND"
echo "  ✓ No other devices using these GPIO pins"
echo
read -p "Press Enter when wiring is confirmed, or Ctrl+C to abort..."

# Optional: Set performance governor for better timing
if [[ $EUID -eq 0 ]]; then
    echo "🚀 Setting performance governor..."
    bash scripts/set_governor_performance.sh
else
    echo "💡 For best results, run with sudo to enable performance governor"
fi

# Run basic test
echo "🎯 Running basic GPIO test (10 seconds)..."
python3 latency_meter.py --backend gpiod \
    --out 18 --in 23 \
    --hz 50 --seconds 10 \
    --csv data/examples/real_basic.csv

# Run with real-time scheduling (if sudo)
if [[ $EUID -eq 0 ]]; then
    echo "⚡ Running with real-time scheduling..."
    python3 latency_meter.py --backend gpiod \
        --out 18 --in 23 \
        --hz 50 --seconds 10 --rt \
        --csv data/examples/real_rt.csv
fi

# Test different frequencies
echo "📈 Testing different frequencies..."
for freq in 10 25 50 100; do
    echo "  Testing ${freq}Hz..."
    python3 latency_meter.py --backend gpiod \
        --out 18 --in 23 \
        --hz $freq --seconds 5 \
        --csv "data/examples/real_${freq}hz.csv"
done

echo "✅ Real GPIO tests complete!"
echo "📁 Results saved in data/examples/"
echo "📊 Compare with simulator: python3 plot.py --csv data/examples/real_basic.csv"

# Optional: Test pigpio backend if available
if python3 -c "import pigpio" 2>/dev/null && systemctl is-active --quiet pigpiod 2>/dev/null; then
    echo "🐷 Testing pigpio backend..."
    python3 latency_meter.py --backend pigpio \
        --out 18 --in 23 \
        --hz 50 --seconds 10 \
        --csv data/examples/pigpio_test.csv
    echo "📊 Compare backends: diff between gpiod and pigpio results"
fi
