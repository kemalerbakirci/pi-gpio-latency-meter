# GPIO Pin Reference and Wiring Guide

## BCM vs Header Pin Mapping

The GPIO Latency Meter uses **BCM (Broadcom) pin numbering**. Here's the mapping to physical header pins:

| BCM | Header | Function | Direction | Notes |
|-----|--------|----------|-----------|-------|
| 18  | Pin 12 | PWM0     | OUT       | Default output pin |
| 23  | Pin 16 | -        | IN        | Default input pin |
| 12  | Pin 32 | PWM0     | OUT       | Alternative output |
| 24  | Pin 18 | -        | IN        | Alternative input |

## Raspberry Pi Header Layout

```
     3V3  (1) (2)  5V     
   GPIO2  (3) (4)  5V     
   GPIO3  (5) (6)  GND    
   GPIO4  (7) (8)  GPIO14 
     GND  (9) (10) GPIO15 
  GPIO17 (11) (12) GPIO18  ← Default OUT
  GPIO27 (13) (14) GND    
  GPIO22 (15) (16) GPIO23  ← Default IN
     3V3 (17) (18) GPIO24 
  GPIO10 (19) (20) GND    
   GPIO9 (21) (22) GPIO25 
  GPIO11 (23) (24) GPIO8  
     GND (25) (26) GPIO7  
   GPIO0 (27) (28) GPIO1  
   GPIO5 (29) (30) GND    
   GPIO6 (31) (32) GPIO12  ← Alternative OUT
  GPIO13 (33) (34) GND    
  GPIO19 (35) (36) GPIO16 
  GPIO26 (37) (38) GPIO20 
     GND (39) (40) GPIO21 
```

## Wiring Instructions

### Basic Loopback Connection

**Required components:**
- 1× Jumper wire (male-to-male)
- 1× 10kΩ resistor
- Breadboard (optional)

**Connections:**
```
OUT Pin 12 (BCM18) ───────────────── IN Pin 16 (BCM23)
                                         │
                                      10kΩ
                                         │
                                    GND Pin 14
```

### Alternative: Using Breadboard

```
Pi Pin 12 (BCM18) ──── Breadboard Row A ──── Pi Pin 16 (BCM23)
                                │
                            10kΩ Resistor
                                │
Pi Pin 14 (GND)   ──── Breadboard Ground Rail
```

## Electrical Characteristics

### GPIO Specifications (Raspberry Pi 4)

| Parameter | Min | Typical | Max | Unit |
|-----------|-----|---------|-----|------|
| Input High Voltage | 1.8 | - | 3.3 | V |
| Input Low Voltage | 0 | - | 0.8 | V |
| Output High Voltage | 3.0 | 3.3 | 3.3 | V |
| Output Low Voltage | 0 | 0 | 0.4 | V |
| Input Current | - | - | ±16 | mA |
| Rise/Fall Time | - | 5 | - | ns |

### Why Use a Pulldown Resistor?

Without a pulldown resistor, the input pin can **float** to an undefined voltage, causing:
- False edge detections
- Inconsistent measurements  
- EMI sensitivity

The 10kΩ pulldown ensures the input stays at 0V when the output is LOW.

## Safety Guidelines

### ⚠️ Important Warnings

1. **Never exceed 3.3V** on any GPIO pin
2. **Never connect 5V directly** to GPIO pins
3. **Always use current limiting** for LED connections
4. **Avoid short circuits** between power rails
5. **Check polarity** before connecting

### Current Limits

- **Per GPIO pin**: 16mA maximum
- **Total GPIO current**: 50mA maximum  
- **3.3V rail current**: 100mA maximum

### Protection Circuit (Optional)

For added protection, especially during development:

```
OUT ──── 330Ω ──── Signal ──── IN
                      │
                   10kΩ
                      │
                    GND
```

The 330Ω series resistor limits current to ~10mA.

## Troubleshooting Wiring Issues

### No Edge Detection

**Symptoms:**
- "No edges captured" error
- All measurements timeout

**Checks:**
1. Verify physical connections with multimeter
2. Check BCM pin numbers (not header numbers)
3. Confirm pulldown resistor placement
4. Test with known-good jumper wires

**Debugging commands:**
```bash
# Check GPIO state
gpioget gpiochip0 23

# Manual GPIO control
gpioset gpiochip0 18=1  # Set OUT high
gpioget gpiochip0 23    # Should read 1
gpioset gpiochip0 18=0  # Set OUT low  
gpioget gpiochip0 23    # Should read 0
```

### Inconsistent Measurements

**Symptoms:**
- High miss rate (>5%)
- Erratic latency values
- Occasional very high spikes

**Possible causes:**
1. **Loose connections** - Re-seat jumper wires
2. **Poor power supply** - Check `vcgencmd get_throttled`
3. **EMI interference** - Move away from USB devices
4. **Missing pulldown** - Add/check 10kΩ resistor

### Permission Errors

**Error:** `Permission denied` when accessing GPIO

**Solutions:**
```bash
# Method 1: Add user to gpio group
sudo usermod -a -G gpio $USER
newgrp gpio  # Or log out/in

# Method 2: Run with sudo
sudo python3 latency_meter.py

# Method 3: Adjust udev rules (persistent)
echo 'SUBSYSTEM=="gpio", GROUP="gpio", MODE="0664"' | sudo tee /etc/udev/rules.d/99-gpio.rules
```

## Alternative Pin Configurations

### High-Frequency Capable Pins

For measurements above 100Hz, prefer PWM-capable outputs:

| BCM | Header | PWM | Max Freq |
|-----|--------|-----|----------|
| 18  | Pin 12 | PWM0 | 100MHz |
| 12  | Pin 32 | PWM0 | 100MHz |
| 13  | Pin 33 | PWM1 | 100MHz |
| 19  | Pin 35 | PWM1 | 100MHz |

### Multiple Channel Setup

For simultaneous measurements:

```bash
# Channel 1: BCM18 → BCM23
python3 latency_meter.py --out 18 --in 23 --csv ch1.csv &

# Channel 2: BCM12 → BCM24  
python3 latency_meter.py --out 12 --in 24 --csv ch2.csv &
```

## PCB Design Considerations

For permanent installations or repeated testing:

### Recommended PCB Layout

```
[Pi Header Connector]
        │
    [Level Shifters] (if interfacing with 5V)
        │
    [Test Points]
        │
    [Loopback Traces]
        │
    [Pulldown Resistors]
```

### Trace Impedance

- **Single-ended**: 50Ω nominal
- **Differential**: 100Ω nominal  
- **Trace width**: 0.2mm minimum
- **Via size**: 0.2mm drill minimum

### Component Placement

- Place pulldown resistors close to input pins
- Minimize loop area for loopback connections
- Add test points for oscilloscope probing
- Include power supply bypass capacitors

## Oscilloscope Validation

### Probe Setup

```
Ch1 (Yellow) ──── OUT Pin (BCM18)
Ch2 (Blue)   ──── IN Pin (BCM23)
GND          ──── Any GND pin
```

### Measurement Settings

- **Timebase**: 50µs/div (for ~400µs latency)
- **Voltage**: 1V/div
- **Trigger**: Rising edge on Ch1
- **Coupling**: DC

### Expected Waveforms

```
Ch1 (OUT):  ____┌─────┐____
                │     │
Ch2 (IN):   ____│     │____
                └─────┘
                ↑
            ~400µs delay
```

The delay between Ch1 and Ch2 rising edges should match software measurements ±10µs.
