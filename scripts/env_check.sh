#!/bin/bash
# Environment check script for GPIO Latency Meter

set -euo pipefail

echo "🔍 GPIO Latency Meter Environment Check"
echo "========================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track overall status
ERRORS=0
WARNINGS=0

error() {
    echo -e "${RED}❌ ERROR: $1${NC}"
    ((ERRORS++))
}

warning() {
    echo -e "${YELLOW}⚠️  WARNING: $1${NC}"
    ((WARNINGS++))
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

info() {
    echo -e "ℹ️  $1"
}

# Check Python version
echo
echo "📋 Python Environment"
echo "--------------------"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -ge 8 ]]; then
        success "Python $PYTHON_VERSION (compatible)"
    else
        error "Python $PYTHON_VERSION (requires Python 3.8+)"
    fi
else
    error "Python 3 not found"
fi

# Check required Python packages
echo
echo "📦 Python Dependencies" 
echo "---------------------"
for pkg in numpy matplotlib; do
    if python3 -c "import $pkg" 2>/dev/null; then
        VERSION=$(python3 -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "unknown")
        success "$pkg ($VERSION)"
    else
        error "$pkg not installed (pip install $pkg)"
    fi
done

# Check optional GPIO packages
echo
echo "🔌 GPIO Libraries"
echo "----------------"
if python3 -c "import gpiod" 2>/dev/null; then
    success "gpiod (for real GPIO backend)"
else
    warning "gpiod not installed (apt install python3-gpiod OR pip install gpiod)"
fi

if python3 -c "import pigpio" 2>/dev/null; then
    success "pigpio (for DMA timestamp backend)"
else
    warning "pigpio not installed (pip install pigpio)"
fi

# Check GPIO permissions
echo
echo "🔐 GPIO Permissions"
echo "------------------"
if [[ -c /dev/gpiochip0 ]]; then
    if [[ -r /dev/gpiochip0 && -w /dev/gpiochip0 ]]; then
        success "GPIO device accessible"
    else
        warning "GPIO device exists but not accessible (try: sudo usermod -a -G gpio $USER)"
    fi
else
    warning "GPIO device /dev/gpiochip0 not found (not on Raspberry Pi?)"
fi

# Check if user is in gpio group
if groups | grep -q gpio; then
    success "User in gpio group"
else
    warning "User not in gpio group (run: sudo usermod -a -G gpio $USER)"
fi

# Summary
echo
echo "📊 Summary"
echo "=========="
if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    success "Environment check passed! Ready to run GPIO latency measurements."
elif [[ $ERRORS -eq 0 ]]; then
    echo -e "${YELLOW}⚠️  Environment check completed with $WARNINGS warning(s).${NC}"
    echo "The tool should work, but consider addressing warnings for optimal performance."
else
    echo -e "${RED}❌ Environment check failed with $ERRORS error(s) and $WARNINGS warning(s).${NC}"
    echo "Please fix the errors before running the tool."
    exit 1
fi
