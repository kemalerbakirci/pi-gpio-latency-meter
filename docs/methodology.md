# Measurement Methodology and Metrics

## Overview

The GPIO Latency Meter measures **user-space observed latency** from GPIO output assertion to input detection. This document describes the exact measurement methodology, statistical metrics, and interpretation guidelines.

## Measurement Definition

### Latency Timeline

```
T0: Application calls outl.set_value(1)
│
├─ GPIO driver processes request
├─ Hardware generates rising edge  
├─ Signal propagates through loopback wire
├─ Input hardware detects edge
├─ Kernel GPIO interrupt fires
├─ Interrupt handler queues event
├─ Scheduler wakes application thread
│
T1: Application receives event via inl.event_wait()

Measured Latency = T1 - T0
```

### What's Included

The measurement captures **total system latency** including:

1. **GPIO driver latency** (~10-50µs)
   - System call overhead
   - Driver processing time
   - Hardware register access

2. **Signal propagation** (~1-5ns)
   - Wire/trace delays (negligible for short connections)
   - GPIO pad delays

3. **Input detection latency** (~50-200µs)  
   - Edge detection hardware
   - Interrupt generation
   - Interrupt controller processing

4. **Kernel processing** (~100-300µs)
   - Interrupt handler execution
   - Event queuing
   - Process scheduling

5. **User-space delays** (~50-200µs)
   - System call return overhead
   - Thread scheduling
   - Application processing

### What's Excluded

- **Application computation time** (measured timestamp is taken immediately)
- **Cross-device communication** (this is a loopback test)
- **Multi-GPIO synchronization** (single pin pair measurement)

## Statistical Metrics

### Percentiles (Primary Metrics)

We report percentiles rather than standard mean/standard deviation because GPIO latency distributions are typically **right-skewed** with occasional high outliers.

| Metric | Definition | Significance |
|--------|------------|--------------|
| **P50 (Median)** | 50% of samples below this value | Typical performance |
| **P95** | 95% of samples below this value | Good performance boundary |  
| **P99** | 99% of samples below this value | Acceptable worst-case |
| **P99.9** | 99.9% of samples below this value | Extreme outlier threshold |

### Example Interpretation

```
P50=350µs  P95=420µs  P99=480µs  P99.9=850µs

Meaning:
- Typical latency: ~350µs
- 95% of operations complete within 420µs  
- 99% of operations complete within 480µs
- Rare spikes can reach 850µs
```

### Additional Metrics

| Metric | Formula | Purpose |
|--------|---------|---------|
| **Min/Max** | `min(samples)`, `max(samples)` | Range bounds |
| **Mean±σ** | `μ ± σ` | Central tendency (if normally distributed) |
| **Miss Rate** | `misses / total_attempts` | System reliability |

### Miss Rate Analysis

**Miss Definition**: An output pulse that doesn't generate a corresponding input edge within the timeout period.

**Typical causes:**
- System overload (CPU/memory pressure)
- Thermal throttling
- Power supply issues  
- Hardware malfunctions

**Acceptable thresholds:**
- **< 0.1%**: Excellent
- **0.1% - 1%**: Good  
- **1% - 5%**: Marginal
- **> 5%**: Poor (investigate system issues)

## Measurement Accuracy

### Timing Resolution

The tool uses `time.perf_counter_ns()` which provides:
- **Resolution**: 1ns theoretical
- **Accuracy**: ~100ns practical (depends on system timer)
- **Stability**: Monotonic, unaffected by clock adjustments

### Sources of Measurement Error

1. **Timer granularity** (±100ns)
2. **CPU frequency scaling** (±10µs)
3. **Thread scheduling jitter** (±50µs)
4. **Cache effects** (±1µs)
5. **System call overhead variation** (±5µs)

**Total measurement uncertainty**: ±50µs typical

### Reducing Measurement Error

```bash
# Enable real-time scheduling
sudo python3 latency_meter.py --rt

# Set CPU governor to performance  
sudo bash scripts/set_governor_performance.sh

# Reduce busy-wait threshold for better timing
python3 latency_meter.py --busy-wait-us 10

# Pin to specific CPU core
sudo taskset -c 3 python3 latency_meter.py
```

## Comparison with Other Tools

### vs. Oscilloscope Measurement

**Oscilloscope** measures purely electrical timing:
- **Scope latency**: Hardware propagation only (~1-10µs)
- **Software latency**: Full system stack (300-500µs)

**Relationship**: `Software_Latency ≈ Scope_Latency + System_Overhead`

### vs. pigpio Backend

**pigpio** provides DMA-based timestamps:
- **pigpio latency**: Excludes final user-space delays
- **gpiod latency**: Full user-space measurement

**Typical difference**: 50-100µs (pigpio faster)

### vs. Kernel GPIO Latency Tools

**Kernel modules** can measure interrupt latency directly:
- **Kernel latency**: ISR execution time only
- **User-space latency**: Includes scheduling delays

## Latency Distribution Characteristics

### Typical Raspberry Pi 4 Distribution

```
Distribution: Right-skewed (lognormal-like)
Bulk: 300-450µs (normal operation)  
Tail: 500-2000µs (occasional delays)
Outliers: >2000µs (rare system events)
```

### Common Distribution Patterns

1. **Normal Operation**
   ```
   P50: 350µs, P95: 420µs, P99: 480µs
   Shape: Tight distribution, few outliers
   ```

2. **Moderate Load**
   ```  
   P50: 380µs, P95: 500µs, P99: 750µs
   Shape: Wider distribution, more tail
   ```

3. **Heavy Load**
   ```
   P50: 450µs, P95: 850µs, P99: 1500µs  
   Shape: Very wide, long tail
   ```

4. **Thermal Throttling**
   ```
   P50: 500µs, P95: 1200µs, P99: 3000µs
   Shape: Bimodal (normal + throttled states)
   ```

## Environmental Factors

### CPU Governor Impact

| Governor | P50 | P95 | P99 | Notes |
|----------|-----|-----|-----|-------|
| `powersave` | 420µs | 650µs | 1200µs | High frequency scaling |
| `ondemand` | 380µs | 500µs | 800µs | Moderate scaling |
| `performance` | 350µs | 420µs | 480µs | No scaling |

### System Load Impact

| Load | P50 | P95 | P99 | Miss Rate |
|------|-----|-----|-----|-----------|
| Idle | 350µs | 420µs | 480µs | <0.1% |
| Light | 370µs | 450µs | 550µs | ~0.2% |
| Heavy | 450µs | 750µs | 1200µs | ~2% |
| Stress | 600µs | 1500µs | 3000µs | ~10% |

### Temperature Effects

```bash
# Check throttling status
vcgencmd get_throttled
# 0x0 = no throttling
# Non-zero = various throttling conditions active

# Monitor temperature
watch -n 1 vcgencmd measure_temp
```

**Thermal throttling onset**: ~80°C
**Performance degradation**: 2-3x latency increase when throttled

## Validation and Calibration

### Cross-Reference Measurements

1. **Oscilloscope validation**:
   ```bash
   # Run measurement while scoping GPIO pins
   python3 latency_meter.py --backend gpiod --hz 10 --seconds 60
   ```

2. **pigpio comparison**:
   ```bash
   python3 latency_meter.py --backend gpiod --csv gpiod_results.csv
   python3 latency_meter.py --backend pigpio --csv pigpio_results.csv
   # pigpio should show 50-100µs lower latency
   ```

3. **Real-time vs standard**:
   ```bash
   python3 latency_meter.py --csv standard.csv
   sudo python3 latency_meter.py --rt --csv realtime.csv
   # RT should show tighter distribution
   ```

### Expected Validation Results

| Test | Expected Outcome |
|------|------------------|
| Oscilloscope | Software = Scope + 300-500µs |
| pigpio vs gpiod | pigpio 50-100µs faster |
| RT vs standard | RT has lower P95/P99 |
| High frequency | Higher frequency = higher latency |

## Limitations and Caveats

### Measurement Limitations

1. **Single-threaded**: No concurrent GPIO testing
2. **User-space only**: Cannot measure kernel-internal latencies  
3. **Loopback only**: Doesn't test external device response
4. **Pi-specific**: Optimized for Raspberry Pi GPIO characteristics

### Statistical Limitations

1. **Sample size dependency**: Need >1000 samples for stable percentiles
2. **Temporal variation**: Results vary with system state
3. **Non-stationary**: Distribution may change during long tests

### Hardware Limitations

1. **GPIO speed**: Limited by Pi GPIO hardware (~100MHz max)
2. **Wire length**: Long wires add propagation delay
3. **Electrical loading**: Multiple connections affect timing

## Best Practices

### For Accurate Measurements

1. **Sufficient sample size**: Use ≥1000 samples (10+ seconds at 50Hz)
2. **Controlled environment**: Minimize system load during testing  
3. **Multiple runs**: Average results across several test runs
4. **Document conditions**: Record temperature, load, configuration

### For Comparative Analysis  

1. **Consistent setup**: Same pins, wiring, settings
2. **Baseline measurement**: Establish idle system baseline
3. **Statistical significance**: Use proper statistical tests for comparisons
4. **Environmental control**: Account for temperature, load variations

### For Production Monitoring

1. **Continuous monitoring**: Regular automated tests
2. **Alert thresholds**: Set alarms for P99 > acceptable limit  
3. **Trend analysis**: Monitor changes over time
4. **Correlation analysis**: Link latency to system metrics

## Troubleshooting Anomalous Results

### Very High Latency (>2ms)

**Possible causes:**
- Thermal throttling
- Memory pressure / swapping
- USB interference
- Background processes

**Investigation:**
```bash
vcgencmd get_throttled  # Check throttling
free -h                 # Check memory usage  
lsusb                   # Check USB devices
top                     # Check CPU usage
```

### High Miss Rate (>5%)

**Possible causes:**
- Wiring issues
- Power supply problems
- Severe system overload

**Investigation:**
```bash
# Test wiring
gpioget gpiochip0 23; gpioset gpiochip0 18=1; gpioget gpiochip0 23

# Check power
vcgencmd measure_volts core
vcgencmd measure_volts sdram_c

# Check system load
vmstat 1 10
```

### Inconsistent Results

**Possible causes:**
- Variable system load
- Frequency scaling
- Temperature variation

**Solutions:**
- Use `--rt` flag for real-time scheduling
- Set performance governor
- Ensure adequate cooling
- Run longer tests for stable statistics
