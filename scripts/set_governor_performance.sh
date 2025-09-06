#!/bin/bash
# Set CPU governor to performance mode for stable timing

set -euo pipefail

echo "🚀 Setting CPU governor to performance mode..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)" 
   exit 1
fi

# Check if cpufreq is available
if [[ ! -d /sys/devices/system/cpu/cpu0/cpufreq ]]; then
    echo "❌ CPU frequency scaling not available on this system"
    exit 1
fi

# Get current governor
CURRENT=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)
echo "📊 Current governor: $CURRENT"

# Set performance governor for all CPUs
CPU_COUNT=$(nproc)
echo "🔧 Setting performance governor for $CPU_COUNT CPUs..."

for ((i=0; i<$CPU_COUNT; i++)); do
    GOVERNOR_FILE="/sys/devices/system/cpu/cpu$i/cpufreq/scaling_governor"
    if [[ -f $GOVERNOR_FILE ]]; then
        echo "performance" > $GOVERNOR_FILE
        echo "✅ CPU$i: $(cat $GOVERNOR_FILE)"
    else
        echo "⚠️  CPU$i: governor file not found"
    fi
done

echo "✅ Performance governor enabled!"
