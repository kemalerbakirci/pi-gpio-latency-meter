#!/usr/bin/env python3
"""
GPIO Loopback Latency Meter (Raspberry Pi) — Real (libgpiod) + Sim + pigpio backends.

Measures user-space observed latency from toggling an OUT pin HIGH
to receiving a rising-edge event on an IN pin. Reports P50/P95/P99,
max, and miss count. Optional CSV dump and real-time scheduling.

Author: MIT Licensed
"""
import argparse
import csv
import os
import signal
import sys
import threading
import time
import queue
from typing import Tuple, Any, Optional, List, Union
from dataclasses import dataclass

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy required. Install with: pip install numpy", file=sys.stderr)
    sys.exit(1)


def now_ns() -> int:
    """Monotonic high-resolution timestamp in ns."""
    return time.perf_counter_ns()


@dataclass
class LatencyResult:
    """Container for latency measurement results."""
    total_samples: int
    successful_samples: int
    missed_samples: int
    p50_ns: float
    p95_ns: float
    p99_ns: float
    max_ns: int
    min_ns: int
    mean_ns: float
    std_ns: float


def set_realtime_priority() -> bool:
    """Set SCHED_FIFO priority if available. Returns True if successful."""
    try:
        import os
        import ctypes
        
        # SCHED_FIFO = 1, priority range typically 1-99
        SCHED_FIFO = 1
        priority = 50
        
        # Try to set real-time scheduling
        result = os.sched_setscheduler(0, SCHED_FIFO, os.sched_param(priority))
        if result == 0:
            print(f"✓ Set SCHED_FIFO priority {priority}")
            return True
    except (ImportError, OSError, AttributeError) as e:
        print(f"⚠ Failed to set real-time priority: {e}")
    return False


# ------------------------- backends -------------------------

def setup_lines_gpiod(chipname: str, out_bcm: int, in_bcm: int) -> Tuple[Any, Any, Any]:
    """
    Real backend via libgpiod v1 Python bindings.
    Returns (chip, out_line, in_line).
    """
    try:
        import gpiod
    except ImportError as e:
        print("ERROR: gpiod not available. Install 'python3-gpiod' (apt) or 'gpiod' (pip).", file=sys.stderr)
        raise

    try:
        chip = gpiod.Chip(chipname)
        outl = chip.get_line(out_bcm)
        inl = chip.get_line(in_bcm)

        outl.request(consumer="lat-out", type=gpiod.LINE_REQ_DIR_OUT)
        inl.request(consumer="lat-in", type=gpiod.LINE_REQ_EV_RISING_EDGE)

        # Set initial state to LOW
        outl.set_value(0)
        
        print(f"✓ GPIO setup: OUT=BCM{out_bcm}, IN=BCM{in_bcm} on {chipname}")
        return chip, outl, inl
    except Exception as e:
        print(f"ERROR: GPIO setup failed: {e}", file=sys.stderr)
        print("Ensure proper permissions and wiring. See docs/pinout.md", file=sys.stderr)
        raise


def setup_lines_sim(mode: str, base_us: int, jitter_us: int, seed: Optional[int]) -> Tuple[Any, Any, Any]:
    """
    Simulator backend. Edges are scheduled after a sampled delay.
    Returns (dummy_chip, out_line_like, in_line_like).
    """
    from sim_backend import setup_sim_lines
    outl, inl = setup_sim_lines(mode=mode, base_lat_us=base_us, jitter_us=jitter_us, seed=seed)

    class _DummyChip:
        def close(self):
            pass

    print(f"✓ Simulator setup: mode={mode}, base={base_us}µs, jitter={jitter_us}µs, seed={seed}")
    return _DummyChip(), outl, inl


def setup_lines_pigpio(out_bcm: int, in_bcm: int) -> Tuple[Any, Any, Any]:
    """
    pigpio backend with DMA timestamps (if available).
    Returns (pi, out_line_wrapper, in_line_wrapper).
    """
    try:
        import pigpio
    except ImportError:
        print("ERROR: pigpio not available. Install with: pip install pigpio", file=sys.stderr)
        print("Also ensure pigpiod daemon is running: sudo systemctl start pigpiod", file=sys.stderr)
        raise

    try:
        pi = pigpio.pi()
        if not pi.connected:
            raise RuntimeError("Failed to connect to pigpiod daemon")

        # Configure pins
        pi.set_mode(out_bcm, pigpio.OUTPUT)
        pi.set_mode(in_bcm, pigpio.INPUT)
        pi.set_pull_up_down(in_bcm, pigpio.PUD_DOWN)
        pi.write(out_bcm, 0)

        class PigpioWrapper:
            def __init__(self, pi, pin, is_output=False):
                self.pi = pi
                self.pin = pin
                self.is_output = is_output
                self._last_tick = 0
                self._event_queue = queue.Queue(maxsize=1000)
                
                if not is_output:
                    # Set up edge detection
                    self._callback = pi.callback(pin, pigpio.RISING_EDGE, self._edge_callback)

            def _edge_callback(self, gpio, level, tick):
                """Called by pigpio on rising edge. tick is DMA timestamp."""
                try:
                    self._event_queue.put_nowait((tick, now_ns()))
                except queue.Full:
                    pass

            def set_value(self, value):
                if self.is_output:
                    self.pi.write(self.pin, value)

            def event_wait(self, timeout):
                try:
                    self._last_tick, self._last_user_ns = self._event_queue.get(timeout=timeout)
                    return True
                except queue.Empty:
                    return False

            def event_read(self):
                # Return a simple object with tick for DMA timestamp
                class Event:
                    def __init__(self, tick, user_ns):
                        self.tick = tick
                        self.user_ns = user_ns
                return Event(self._last_tick, self._last_user_ns)

        out_wrapper = PigpioWrapper(pi, out_bcm, is_output=True)
        in_wrapper = PigpioWrapper(pi, in_bcm, is_output=False)
        
        print(f"✓ pigpio setup: OUT=BCM{out_bcm}, IN=BCM{in_bcm} (DMA timestamps)")
        return pi, out_wrapper, in_wrapper
        
    except Exception as e:
        print(f"ERROR: pigpio setup failed: {e}", file=sys.stderr)
        raise


# ------------------------- statistics -------------------------

def compute_percentiles(dts_ns: List[int]) -> Tuple[float, float, float, int]:
    """Compute percentiles with robust handling of edge cases."""
    if not dts_ns:
        return 0.0, 0.0, 0.0, 0
    
    # Filter out invalid values
    valid_dts = [dt for dt in dts_ns if dt is not None and not np.isnan(dt) and dt >= 0]
    if not valid_dts:
        return 0.0, 0.0, 0.0, 0
    
    arr = np.array(valid_dts, dtype=np.int64)
    
    if len(arr) == 1:
        val = float(arr[0])
        return val, val, val, int(arr[0])
    
    p50 = float(np.percentile(arr, 50))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))
    mx = int(arr.max())
    return p50, p95, p99, mx


def compute_full_stats(dts_ns: List[int]) -> LatencyResult:
    """Compute comprehensive statistics for latency measurements."""
    total = len(dts_ns)
    valid_dts = [dt for dt in dts_ns if dt is not None and not np.isnan(dt) and dt >= 0]
    successful = len(valid_dts)
    missed = total - successful
    
    if not valid_dts:
        return LatencyResult(
            total_samples=total,
            successful_samples=0,
            missed_samples=missed,
            p50_ns=0.0, p95_ns=0.0, p99_ns=0.0,
            max_ns=0, min_ns=0, mean_ns=0.0, std_ns=0.0
        )
    
    arr = np.array(valid_dts, dtype=np.int64)
    
    return LatencyResult(
        total_samples=total,
        successful_samples=successful,
        missed_samples=missed,
        p50_ns=float(np.percentile(arr, 50)),
        p95_ns=float(np.percentile(arr, 95)),
        p99_ns=float(np.percentile(arr, 99)),
        max_ns=int(arr.max()),
        min_ns=int(arr.min()),
        mean_ns=float(arr.mean()),
        std_ns=float(arr.std())
    )



# ------------------------- main measurement loop -------------------------

def main():
    ap = argparse.ArgumentParser(description="GPIO Loopback Latency Meter (real, sim, or pigpio)")
    ap.add_argument("--backend", choices=["gpiod", "sim", "pigpio"], default="sim", 
                   help="Backend: gpiod (libgpiod), sim (simulator), pigpio (DMA timestamps)")
    ap.add_argument("--chip", default="gpiochip0", help="gpiod chip name (real backend)")
    ap.add_argument("--out", dest="out_bcm", type=int, default=18, help="BCM OUT line (default 18)")
    ap.add_argument("--in", dest="in_bcm", type=int, default=23, help="BCM IN line (default 23)")
    ap.add_argument("--hz", type=float, default=50.0, help="pulse frequency (Hz)")
    ap.add_argument("--seconds", type=float, default=10.0, help="test duration (0 = run indefinitely)")
    ap.add_argument("--pulse-us", type=int, default=1000, help="HIGH pulse width (microseconds)")
    ap.add_argument("--csv", default=None, help="optional CSV output path")
    ap.add_argument("--rt", action="store_true", help="attempt real-time scheduling (SCHED_FIFO)")
    ap.add_argument("--busy-wait-us", type=int, default=50, 
                   help="busy-wait threshold in microseconds (lower = more precise, higher CPU)")

    # simulator knobs
    ap.add_argument("--sim-mode", choices=["const", "uniform", "normal", "lognormal", "heavy"], 
                   default="lognormal", help="simulator delay distribution")
    ap.add_argument("--sim-base-us", type=int, default=400, help="base latency (µs) for rising edge")
    ap.add_argument("--sim-jitter-us", type=int, default=150, help="jitter scale (µs)")
    ap.add_argument("--sim-seed", type=int, default=42, help="random seed for reproducibility")

    args = ap.parse_args()

    # Validate arguments
    if args.hz <= 0:
        print("ERROR: --hz must be positive", file=sys.stderr)
        sys.exit(1)
    if args.seconds < 0:
        print("ERROR: --seconds must be non-negative", file=sys.stderr)
        sys.exit(1)

    # Optional real-time scheduling
    if args.rt:
        set_realtime_priority()

    # Backend setup
    try:
        if args.backend == "gpiod":
            chip, outl, inl = setup_lines_gpiod(args.chip, args.out_bcm, args.in_bcm)
        elif args.backend == "pigpio":
            chip, outl, inl = setup_lines_pigpio(args.out_bcm, args.in_bcm)
        else:  # sim
            chip, outl, inl = setup_lines_sim(args.sim_mode, args.sim_base_us, args.sim_jitter_us, args.sim_seed)
    except Exception as e:
        print(f"ERROR: Backend setup failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Timing parameters
    period_ns = int(1e9 / max(1e-6, args.hz))
    pulse_ns = int(max(1, args.pulse_us) * 1000)
    busy_wait_ns = args.busy_wait_us * 1000
    
    # Duration (0 = indefinite)
    run_indefinitely = args.seconds == 0
    t_end = time.time() + args.seconds if not run_indefinitely else float('inf')

    # Thread-safe queues with sequence numbers for better pairing
    sends_q: "queue.Queue[Tuple[int, int]]" = queue.Queue(maxsize=100000)  # (seq, ts_send)
    edges_q: "queue.Queue[Tuple[int, int]]" = queue.Queue(maxsize=100000)  # (seq, ts_edge)
    stop = threading.Event()

    # Sequence counter for pairing
    seq_counter = [0]  # mutable container for thread sharing

    def toggler():
        """Thread that generates pulses at specified frequency."""
        next_ts = now_ns()
        last_val = 0
        
        while not stop.is_set() and (run_indefinitely or time.time() < t_end):
            next_ts += period_ns
            
            # Sleep most of the way, then busy-wait for precision
            sleep_until = next_ts - busy_wait_ns
            current = now_ns()
            if current < sleep_until:
                time.sleep((sleep_until - current) / 1e9)
            
            # Busy-wait for final precision
            while now_ns() < next_ts and not stop.is_set():
                pass
            
            if stop.is_set():
                break
                
            ts_send = now_ns()
            seq = seq_counter[0]
            seq_counter[0] += 1
            
            try:
                sends_q.put_nowait((seq, ts_send))
            except queue.Full:
                print("⚠ Send queue full, dropping sample", file=sys.stderr)
                continue

            # Generate rising edge
            try:
                outl.set_value(1)
                last_val = 1
            except Exception as e:
                print(f"⚠ Output error: {e}", file=sys.stderr)
                continue
            
            # Keep high for pulse duration
            pulse_end = ts_send + pulse_ns
            sleep_until = pulse_end - busy_wait_ns
            current = now_ns()
            if current < sleep_until:
                time.sleep((sleep_until - current) / 1e9)
            
            while now_ns() < pulse_end and not stop.is_set():
                pass
            
            # Return to low
            try:
                outl.set_value(0)
                last_val = 0
            except Exception as e:
                print(f"⚠ Output error: {e}", file=sys.stderr)

    def listener():
        """Thread that waits for rising edges."""
        current_seq = 0
        
        while not stop.is_set() and (run_indefinitely or time.time() < t_end):
            try:
                if inl.event_wait(1.0):  # 1s timeout
                    event = inl.event_read()
                    ts_edge = now_ns()
                    
                    try:
                        edges_q.put_nowait((current_seq, ts_edge))
                        current_seq += 1
                    except queue.Full:
                        print("⚠ Edge queue full, dropping sample", file=sys.stderr)
            except Exception as e:
                if not stop.is_set():
                    print(f"⚠ Input error: {e}", file=sys.stderr)

    # Start threads
    tg = threading.Thread(target=toggler, name="toggler", daemon=True)
    lg = threading.Thread(target=listener, name="listener", daemon=True)
    
    print(f"🚀 Starting measurement: {args.hz}Hz, {args.seconds}s{'(indefinite)' if run_indefinitely else ''}")
    print("Press Ctrl+C to stop...")
    
    tg.start()
    lg.start()

    # Sample collection with improved pairing
    samples = []  # (ts_send, ts_edge, dt_ns) or (ts_send, None, None) for misses
    send_buffer = {}  # seq -> ts_send for pending sends
    edge_buffer = {}  # seq -> ts_edge for unmatched edges
    
    def handle_signal(*_):
        print("\n🛑 Stopping measurement...")
        stop.set()
    
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, handle_signal)

    try:
        while not stop.is_set() and (run_indefinitely or time.time() < t_end):
            # Process sends
            try:
                seq, ts_send = sends_q.get(timeout=0.1)
                send_buffer[seq] = ts_send
                
                # Check if we have a matching edge
                if seq in edge_buffer:
                    ts_edge = edge_buffer.pop(seq)
                    dt = ts_edge - ts_send
                    samples.append((ts_send, ts_edge, dt))
                    
            except queue.Empty:
                pass
            
            # Process edges
            try:
                seq, ts_edge = edges_q.get_nowait()
                
                if seq in send_buffer:
                    ts_send = send_buffer.pop(seq)
                    dt = ts_edge - ts_send
                    samples.append((ts_send, ts_edge, dt))
                else:
                    edge_buffer[seq] = ts_edge
                    
            except queue.Empty:
                pass
            
            # Clean up old unmatched items (prevent memory leak)
            if len(samples) % 1000 == 0:
                current_seq = seq_counter[0]
                old_threshold = current_seq - 10000
                send_buffer = {k: v for k, v in send_buffer.items() if k > old_threshold}
                edge_buffer = {k: v for k, v in edge_buffer.items() if k > old_threshold}
                
    except KeyboardInterrupt:
        handle_signal()

    # Final cleanup and processing
    stop.set()
    tg.join(timeout=2.0)
    lg.join(timeout=2.0)
    
    # Process any remaining pairs
    final_timeout = time.time() + 1.0
    while time.time() < final_timeout:
        processed_any = False
        
        try:
            seq, ts_send = sends_q.get_nowait()
            send_buffer[seq] = ts_send
            processed_any = True
        except queue.Empty:
            pass
        
        try:
            seq, ts_edge = edges_q.get_nowait()
            if seq in send_buffer:
                ts_send = send_buffer.pop(seq)
                dt = ts_edge - ts_send
                samples.append((ts_send, ts_edge, dt))
            processed_any = True
        except queue.Empty:
            pass
            
        if not processed_any:
            break
    
    # Add missed samples
    for seq, ts_send in send_buffer.items():
        samples.append((ts_send, None, None))

    # Cleanup backend
    try:
        if hasattr(chip, 'close'):
            chip.close()
    except Exception:
        pass

    # Analysis
    if not samples:
        print("⚠ No samples collected. Check wiring/backend setup.", file=sys.stderr)
        sys.exit(2)

    dts = [dt for (_, _, dt) in samples if dt is not None]
    stats = compute_full_stats(dts)
    
    # Results summary
    print(f"\n📊 Results Summary:")
    print(f"Total samples: {stats.total_samples}")
    print(f"Successful: {stats.successful_samples}")
    print(f"Missed: {stats.missed_samples} ({100*stats.missed_samples/max(1,stats.total_samples):.1f}%)")
    
    if stats.successful_samples > 0:
        print(f"Latency (µs): P50={stats.p50_ns/1000:.1f}  P95={stats.p95_ns/1000:.1f}  P99={stats.p99_ns/1000:.1f}")
        print(f"Min/Max (µs): {stats.min_ns/1000:.1f} / {stats.max_ns/1000:.1f}")
        print(f"Mean±σ (µs): {stats.mean_ns/1000:.1f}±{stats.std_ns/1000:.1f}")

    # CSV output
    if args.csv:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
            with open(args.csv, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts_send_ns", "ts_edge_ns", "dt_ns"])
                for s, e, dt in samples:
                    w.writerow([s, e if e is not None else "", dt if dt is not None else ""])
            print(f"💾 CSV written: {args.csv}")
        except Exception as e:
            print(f"⚠ CSV write failed: {e}", file=sys.stderr)

    return 0 if stats.successful_samples > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
