# GPIO Loopback Latency Meter

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI version](https://img.shields.io/pypi/v/pi-gpio-latency-meter.svg)](https://pypi.org/project/pi-gpio-latency-meter/)
[![Downloads](https://img.shields.io/pypi/dm/pi-gpio-latency-meter.svg)](https://pypi.org/project/pi-gpio-latency-meter/)



A professional-grade tool for measuring GPIO latency on Raspberry Pi systems. Supports both **real GPIO hardware** (via libgpiod/pigpio) and a **software simulator** for development and CI.

## 🎯 Features

- **Multiple backends**: libgpiod (standard), pigpio (DMA timestamps), simulator
- **Real-time scheduling**: Optional SCHED_FIFO for reduced jitter
- **Comprehensive statistics**: P50/P95/P99, min/max, mean±σ, miss rate
- **Data export**: CSV output with timestamp data
- **Visualization**: Histogram plotting with percentile markers
- **No-hardware testing**: Full simulator with realistic latency distributions
- **Production ready**: Proper error handling, logging, and CI integration

## 🚀 Quick Start

### Simulator (No Hardware Required)

```bash
# Install dependencies
pip install -r requirements.txt

# Run 5-second test with lognormal latency distribution
python3 latency_meter.py --backend sim --seconds 5 --csv data/sim_results.csv

# Plot results
python3 plot.py --csv data/sim_results.csv --output plots/sim_histogram.png
```

### Real Hardware Setup

1. **Wire the loopback connection**:
   ```
   GPIO 18 (OUT) ──────┐
                       │ (short jumper wire)
   GPIO 23 (IN)  ──────┘
   
   GND pin       ──────┐
                       │ (10kΩ pulldown resistor)
   GPIO 23 (IN)  ──────┘
   ```

2. **Run measurement**:
   ```bash
   # Basic test
   python3 latency_meter.py --backend gpiod --seconds 10
   
   # With real-time priority and CSV output
   sudo python3 latency_meter.py --backend gpiod --rt --csv data/real_results.csv
   ```

3. **Alternative pigpio backend** (DMA timestamps):
   ```bash
   # Start pigpio daemon
   sudo systemctl start pigpiod
   
   # Run with pigpio backend
   python3 latency_meter.py --backend pigpio --seconds 10
   ```

## 📊 Sample Output

```
🚀 Starting measurement: 50Hz, 10s
✓ GPIO setup: OUT=BCM18, IN=BCM23 on gpiochip0
Press Ctrl+C to stop...

📊 Results Summary:
Total samples: 500
Successful: 498
Missed: 2 (0.4%)
Latency (µs): P50=387.2  P95=456.8  P99=502.1
Min/Max (µs): 298.4 / 651.2
Mean±σ (µs): 392.7±31.4
💾 CSV written: data/real_results.csv
```

## 🔧 Installation

### Using pip (recommended)

```bash
pip install -e .
pi-latency-meter --backend sim --seconds 5
```

### Manual setup

```bash
git clone https://github.com/kemalerbakirci/pi-gpio-latency-meter.git
cd pi-gpio-latency-meter
pip install -r requirements.txt
```

### Raspberry Pi OS dependencies

```bash
# libgpiod (standard GPIO access)
sudo apt install python3-gpiod

# pigpio (alternative with DMA timestamps)
sudo apt install pigpio python3-pigpio
sudo systemctl enable pigpiod
```

## 📚 Usage

### Command Line Options

```bash
python3 latency_meter.py [OPTIONS]

GPIO Backend Options:
  --backend {gpiod,sim,pigpio}   Backend selection (default: sim)
  --chip CHIPNAME               GPIO chip name (default: gpiochip0)
  --out BCM_PIN                 Output pin BCM number (default: 18)
  --in BCM_PIN                  Input pin BCM number (default: 23)

Measurement Options:
  --hz FREQUENCY                Pulse frequency in Hz (default: 50)
  --seconds DURATION            Test duration, 0=infinite (default: 10)
  --pulse-us MICROSECONDS       Pulse width in µs (default: 1000)
  --csv PATH                    CSV output file path

Performance Options:
  --rt                          Enable real-time scheduling (requires sudo)
  --busy-wait-us THRESHOLD      Busy-wait threshold in µs (default: 50)

Simulator Options:
  --sim-mode {const,uniform,normal,lognormal,heavy}
  --sim-base-us MICROSECONDS    Base latency (default: 400)
  --sim-jitter-us MICROSECONDS  Jitter scale (default: 150)
  --sim-seed SEED               Random seed (default: 42)
```

### Performance Tuning

For best measurement accuracy on real hardware:

```bash
# Set CPU governor to performance
sudo bash scripts/set_governor_performance.sh

# Run with real-time priority
sudo python3 latency_meter.py --backend gpiod --rt --busy-wait-us 10

# Pin to specific CPU core
sudo taskset -c 3 python3 latency_meter.py --backend gpiod

# Reduce system load
sudo systemctl stop cron
sudo systemctl stop rsyslog
```

## 🔬 Methodology

### What We Measure

The tool measures **user-space observed latency**:

1. **T0**: Application calls `outl.set_value(1)` 
2. **T1**: GPIO hardware generates rising edge
3. **T2**: Kernel GPIO interrupt fires  
4. **T3**: Application receives edge via `inl.event_wait()`

**Measured latency = T3 - T0**

This includes:
- GPIO driver latency
- Kernel interrupt + scheduling latency  
- System call overhead
- User-space scheduling delays

### Limitations

- **User-space measurement**: Includes OS scheduling jitter
- **Single-threaded**: No multi-core GPIO concurrency testing
- **Loopback only**: Doesn't measure external device response times
- **Pi-specific**: Optimized for Raspberry Pi GPIO characteristics

### Comparison with pigpio

The pigpio backend provides **DMA timestamps** that exclude some user-space delays:

```bash
# Compare backends
python3 latency_meter.py --backend gpiod --csv results_gpiod.csv
python3 latency_meter.py --backend pigpio --csv results_pigpio.csv
```

Typically: `pigpio_latency < gpiod_latency` due to hardware timestamping.

## 🧪 Testing

```bash
# Run unit tests
python3 -m pytest tests/ -v

# Run specific test categories
python3 -m pytest tests/test_stats.py::TestPercentiles -v

# Smoke test with simulator
python3 tests/test_stats.py TestSmokeTest.test_simulator_smoke_test

# Quick integration test
make test
```

## 🛠️ Development

### Using the Makefile

```bash
make run-sim        # Quick simulator test
make run-real       # Real GPIO test (requires hardware)
make test          # Run unit tests
make lint          # Code formatting check
make plot          # Plot latest results
```

### Pre-commit Setup

```bash
pip install pre-commit
pre-commit install
```

## 📋 Wiring Reference

### Standard Loopback (BCM 18 → 23)

```
Pi Header Layout (top view):
  
   3V3  (1) (2)  5V
 GPIO2  (3) (4)  5V  
 GPIO3  (5) (6)  GND
 GPIO4  (7) (8)  GPIO14
   GND  (9) (10) GPIO15
GPIO17 (11) (12) GPIO18  ← OUT pin
GPIO27 (13) (14) GND
GPIO22 (15) (16) GPIO23  ← IN pin
   3V3 (17) (18) GPIO24
```

**Connections**:
- **Signal**: Pin 12 (GPIO18) → Pin 16 (GPIO23) 
- **Pulldown**: Pin 16 (GPIO23) → 10kΩ resistor → Pin 14 (GND)

### Alternative Pin Mappings

| Purpose | BCM | Header | Notes |
|---------|-----|--------|-------|
| OUT     | 18  | Pin 12 | Default, PWM capable |
| OUT Alt | 12  | Pin 32 | Alternative output |
| IN      | 23  | Pin 16 | Default input |
| IN Alt  | 24  | Pin 18 | Alternative input |

⚠️ **Safety**: Always use current-limiting resistors. Avoid connecting 3.3V directly to GPIO pins.

## ❓ FAQ

### Q: Why do I get "Permission denied" errors?

**A**: GPIO access requires appropriate permissions:
```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER
# Log out and back in, or:
sudo python3 latency_meter.py --backend gpiod
```

### Q: BCM vs BOARD pin numbering?

**A**: This tool uses **BCM numbering** (chip pin numbers). Header physical pins are different:
- BCM 18 = Header Pin 12
- BCM 23 = Header Pin 16

### Q: Should I use a pulldown resistor?

**A**: **Yes, highly recommended**. Without it, the input pin may float and cause false triggers:
```
GPIO23 ───── 10kΩ ───── GND
```

### Q: What causes high latency spikes?

**A**: Common causes:
- **Thermal throttling**: Check `vcgencmd get_throttled`
- **Undervoltage**: Use quality 5V/3A power supply
- **System load**: Stop unnecessary services
- **USB interference**: Avoid USB3 devices during testing
- **WiFi activity**: Use ethernet for critical measurements

### Q: How do I compare with other tools?

**A**: Cross-validate with:
```bash
# GPIO interrupt latency (kernel module approach)
sudo modprobe gpio-latency-test

# Oscilloscope measurement (gold standard)
# Connect scope probes to OUT and IN pins

# pigpio direct measurement
pigs m 18 w w 18 1 mils 1 w 18 0
```

## 📈 Performance Expectations

### Typical Results (Raspberry Pi 4B)

| Condition | P50 | P95 | P99 | Notes |
|-----------|-----|-----|-----|-------|
| Default | 350µs | 420µs | 480µs | Standard setup |
| Real-time | 320µs | 380µs | 430µs | With `--rt` flag |
| Pigpio | 280µs | 340µs | 390µs | DMA timestamps |
| Heavy load | 450µs | 850µs | 1200µs | With stress-ng |

### Optimization Checklist

- [ ] Use performance CPU governor
- [ ] Enable real-time scheduling (`--rt`)
- [ ] Reduce busy-wait threshold (`--busy-wait-us 10`)
- [ ] Pin to isolated CPU core
- [ ] Disable unnecessary services
- [ ] Use wired ethernet (not WiFi)
- [ ] Ensure adequate power supply
- [ ] Check thermal throttling status

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make changes and add tests
4. Run the test suite: `make test`
5. Check code formatting: `make lint`
6. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🔗 Related Projects

- [gpiozero](https://gpiozero.readthedocs.io/) - Simple GPIO interface
- [rt-tests](https://github.com/linux-test-project/ltp) - Real-time testing tools
