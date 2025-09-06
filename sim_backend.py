#!/usr/bin/env python3
"""
Enhanced GPIO simulator for the latency meter.

Provides a realistic simulation of GPIO latency with multiple distribution modes
and configurable parameters. Mirrors the interface used by latency_meter.py:
- OUT line exposes set_value(v)
- IN line exposes event_wait(timeout) and event_read()

A rising edge is scheduled after a sampled delay drawn from a configurable
distribution (const/uniform/normal/lognormal/heavy).
"""
import time
import threading
import queue
import random
import math
import numpy as np
from dataclasses import dataclass
from typing import Optional


def now_ns() -> int:
    """Monotonic high-resolution timestamp in ns."""
    return time.perf_counter_ns()


@dataclass
class _SimEvent:
    """Simulated GPIO event with timestamp."""
    sec: int
    nsec: int


class _LatencyModel:
    """Models GPIO latency with various probability distributions."""
    
    def __init__(self, mode: str, base_ns: int, jitter_ns: int, seed: Optional[int] = None):
        self.mode = mode.lower()
        self.base = max(0, int(base_ns))
        self.jitter = max(0, int(jitter_ns))
        self.rng = random.Random(seed)
        
        # Pre-calculate parameters for efficiency
        if self.mode == "lognormal":
            self._setup_lognormal()
        elif self.mode == "heavy":
            self._setup_heavy_tail()
    
    def _setup_lognormal(self):
        """Setup lognormal distribution parameters."""
        if self.base <= 0:
            self.base = 1000  # 1µs default
        
        # Target: median ≈ base, controlled spread via jitter
        target_median = self.base
        target_std = max(self.jitter, self.base * 0.1)  # At least 10% CV
        
        # Solve for µ and σ parameters
        self.ln_median = math.log(target_median)
        self.ln_sigma = math.sqrt(math.log(1 + (target_std / target_median) ** 2))
        self.ln_mu = self.ln_median - 0.5 * self.ln_sigma ** 2
    
    def _setup_heavy_tail(self):
        """Setup heavy-tail distribution (mix of normal + occasional spikes)."""
        self.heavy_prob = 0.05  # 5% chance of spike
        self.heavy_multiplier = 10  # Spikes are 10x normal
    
    def sample_ns(self) -> int:
        """Sample a latency value in nanoseconds."""
        if self.mode == "const":
            return self.base
            
        elif self.mode == "uniform":
            if self.jitter == 0:
                return self.base
            return self.base + self.rng.randint(0, self.jitter)
            
        elif self.mode == "normal":
            if self.jitter == 0:
                return self.base
            # Use jitter as 3-sigma range (99.7% within base ± jitter)
            sigma = self.jitter / 3
            value = self.rng.gauss(self.base, sigma)
            return max(0, int(value))
            
        elif self.mode == "lognormal":
            value = math.exp(self.rng.gauss(self.ln_mu, self.ln_sigma))
            return max(0, int(value))
            
        elif self.mode == "heavy":
            # Heavy-tail: mostly normal, occasional large spikes
            if self.rng.random() < self.heavy_prob:
                # Spike: much larger delay
                base_val = self.base * self.heavy_multiplier
                jitter_val = self.jitter * self.heavy_multiplier
                if jitter_val > 0:
                    value = self.rng.gauss(base_val, jitter_val / 3)
                else:
                    value = base_val
            else:
                # Normal case
                if self.jitter > 0:
                    value = self.rng.gauss(self.base, self.jitter / 3)
                else:
                    value = self.base
            return max(0, int(value))
            
        else:
            # Default to constant
            return self.base


class _EdgeScheduler:
    """Thread-safe edge event scheduler using priority queue."""
    
    def __init__(self):
        self._q = queue.PriorityQueue()
        self._cv = threading.Condition()
        self._shutdown = False
    
    def schedule_edge_at(self, ts_ns: int):
        """Schedule a rising edge at the specified timestamp."""
        with self._cv:
            if not self._shutdown:
                self._q.put(ts_ns)
                self._cv.notify_all()
    
    def event_wait(self, timeout: Optional[float]) -> bool:
        """
        Wait for the next scheduled edge.
        Returns True if an edge is ready, False on timeout.
        """
        if timeout is None:
            timeout = 1e9  # Very large timeout
        
        deadline = time.time() + timeout
        
        while not self._shutdown:
            with self._cv:
                if self._q.empty():
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return False
                    self._cv.wait(timeout=min(remaining, 1.0))
                    continue
                
                # Check if the earliest event is ready
                try:
                    ts_ns = self._q.queue[0]  # Peek at earliest
                    now = now_ns()
                    
                    if ts_ns <= now:
                        return True
                    
                    # Sleep until the event is ready or timeout
                    sleep_time = min((ts_ns - now) / 1e9, deadline - time.time())
                    if sleep_time <= 0:
                        return False
                        
                except (IndexError, AttributeError):
                    # Queue became empty while we were looking
                    continue
            
            # Sleep outside the lock
            if sleep_time > 0:
                time.sleep(min(sleep_time, 0.01))  # Max 10ms sleep chunks
        
        return False
    
    def event_read(self) -> _SimEvent:
        """Read the next available event (call after event_wait returns True)."""
        try:
            ts_ns = self._q.get_nowait()
            sec = ts_ns // 1_000_000_000
            nsec = ts_ns % 1_000_000_000
            return _SimEvent(sec=int(sec), nsec=int(nsec))
        except queue.Empty:
            # Should not happen if event_wait returned True
            current = now_ns()
            sec = current // 1_000_000_000
            nsec = current % 1_000_000_000
            return _SimEvent(sec=int(sec), nsec=int(nsec))
    
    def shutdown(self):
        """Shutdown the scheduler and wake up waiting threads."""
        with self._cv:
            self._shutdown = True
            self._cv.notify_all()


class SimOutLine:
    """Simulated GPIO output line."""
    
    def __init__(self, scheduler: _EdgeScheduler, model: _LatencyModel):
        self._scheduler = scheduler
        self._model = model
        self._last_value = 0
        self._lock = threading.Lock()
    
    def set_value(self, value: int):
        """Set output value. Triggers edge simulation on 0->1 transition."""
        value = 1 if value else 0
        
        with self._lock:
            # Schedule an IN rising-edge when we see a 0->1 transition
            if self._last_value == 0 and value == 1:
                delay_ns = self._model.sample_ns()
                edge_time = now_ns() + delay_ns
                self._scheduler.schedule_edge_at(edge_time)
            
            self._last_value = value


class SimInLine:
    """Simulated GPIO input line."""
    
    def __init__(self, scheduler: _EdgeScheduler):
        self._scheduler = scheduler
    
    def event_wait(self, timeout: float) -> bool:
        """Wait for a rising edge event."""
        return self._scheduler.event_wait(timeout)
    
    def event_read(self) -> _SimEvent:
        """Read the most recent edge event."""
        return self._scheduler.event_read()


def setup_sim_lines(mode: str = "lognormal", base_lat_us: int = 400, jitter_us: int = 150, 
                   seed: Optional[int] = 42) -> tuple[SimOutLine, SimInLine]:
    """
    Setup simulated GPIO lines.
    
    Args:
        mode: Distribution mode ('const', 'uniform', 'normal', 'lognormal', 'heavy')
        base_lat_us: Base latency in microseconds
        jitter_us: Jitter/spread parameter in microseconds
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (out_line, in_line) objects
    """
    # Convert to nanoseconds
    base_ns = base_lat_us * 1000
    jitter_ns = jitter_us * 1000
    
    # Create shared components
    scheduler = _EdgeScheduler()
    model = _LatencyModel(mode, base_ns, jitter_ns, seed)
    
    # Create line objects
    out_line = SimOutLine(scheduler, model)
    in_line = SimInLine(scheduler)
    
    return out_line, in_line


def get_distribution_info(mode: str, base_us: int, jitter_us: int) -> dict:
    """Get statistical information about the configured distribution."""
    base_ns = base_us * 1000
    jitter_ns = jitter_us * 1000
    model = _LatencyModel(mode, base_ns, jitter_ns, seed=42)
    
    # Generate samples for analysis
    samples = [model.sample_ns() for _ in range(10000)]
    samples_us = np.array(samples) / 1000.0
    
    return {
        'mode': mode,
        'base_us': base_us,
        'jitter_us': jitter_us,
        'actual_mean_us': float(np.mean(samples_us)),
        'actual_std_us': float(np.std(samples_us)),
        'actual_p50_us': float(np.percentile(samples_us, 50)),
        'actual_p95_us': float(np.percentile(samples_us, 95)),
        'actual_p99_us': float(np.percentile(samples_us, 99)),
        'actual_max_us': float(np.max(samples_us)),
        'actual_min_us': float(np.min(samples_us)),
    }


if __name__ == "__main__":
    # Demo/test the simulator
    import argparse
    
    ap = argparse.ArgumentParser(description="Test GPIO simulator")
    ap.add_argument("--mode", choices=["const", "uniform", "normal", "lognormal", "heavy"], 
                   default="lognormal")
    ap.add_argument("--base-us", type=int, default=400)
    ap.add_argument("--jitter-us", type=int, default=150)
    ap.add_argument("--samples", type=int, default=1000)
    args = ap.parse_args()
    
    print(f"Testing simulator: {args.mode} mode, base={args.base_us}µs, jitter={args.jitter_us}µs")
    
    out_line, in_line = setup_sim_lines(args.mode, args.base_us, args.jitter_us, seed=42)
    
    latencies = []
    
    for i in range(args.samples):
        # Trigger rising edge
        t_start = now_ns()
        out_line.set_value(1)
        
        # Wait for response
        if in_line.event_wait(0.1):  # 100ms timeout
            event = in_line.event_read()
            t_end = now_ns()
            latency_us = (t_end - t_start) / 1000.0
            latencies.append(latency_us)
        else:
            print(f"Timeout on sample {i}")
        
        out_line.set_value(0)
        time.sleep(0.001)  # Small delay between samples
    
    if latencies:
        latencies = np.array(latencies)

