#!/usr/bin/env bash
# Example: Run simulator backend with various distribution modes

set -euo pipefail
cd "$(dirname "$0")/.."

echo "🧪 Running GPIO latency simulator examples..."

# Create output directory
mkdir -p data/examples

# Test different simulator modes
echo "📊 Testing different latency distributions..."

# 1. Constant latency (deterministic)
echo "  1. Constant latency mode..."
python3 latency_meter.py --backend sim --sim-mode const \
    --sim-base-us 400 --sim-jitter-us 0 \
    --seconds 5 --csv data/examples/sim_const.csv

# 2. Normal distribution
echo "  2. Normal distribution mode..."
python3 latency_meter.py --backend sim --sim-mode normal \
    --sim-base-us 400 --sim-jitter-us 50 \
    --seconds 5 --csv data/examples/sim_normal.csv

# 3. Lognormal distribution (realistic)
echo "  3. Lognormal distribution mode..."
python3 latency_meter.py --backend sim --sim-mode lognormal \
    --sim-base-us 400 --sim-jitter-us 100 \
    --seconds 5 --csv data/examples/sim_lognormal.csv

# 4. Heavy-tail distribution (with spikes)
echo "  4. Heavy-tail distribution mode..."
python3 latency_meter.py --backend sim --sim-mode heavy \
    --sim-base-us 350 --sim-jitter-us 75 \
    --seconds 5 --csv data/examples/sim_heavy.csv

echo "✅ Simulator tests complete!"
echo "📁 Results saved in data/examples/"
echo "📊 Plot results with: python3 plot.py --csv data/examples/sim_lognormal.csv"
