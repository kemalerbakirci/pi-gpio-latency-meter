#!/usr/bin/env python3
"""
Enhanced histogram/summary plotting from CSV produced by latency_meter.py.
Supports PNG output, log-scale, and percentile markers.
"""
import argparse
import csv
import os
import sys
from typing import List, Optional

import numpy as np
import matplotlib.pyplot as plt


def load_latency_data(csv_path: str) -> List[float]:
    """Load latency data from CSV file."""
    dts_us = []
    
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dt_str = row.get("dt_ns", "").strip()
                if dt_str and dt_str != "":
                    try:
                        dt_ns = int(dt_str)
                        if dt_ns > 0:  # Only positive latencies
                            dts_us.append(dt_ns / 1000.0)  # Convert to µs
                    except ValueError:
                        continue  # Skip invalid entries
                        
    except FileNotFoundError:
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to read CSV: {e}", file=sys.stderr)
        sys.exit(1)
    
    return dts_us


def plot_latency_histogram(dts_us: List[float], bins: int = 50, log_scale: bool = False, 
                          output_path: Optional[str] = None, title: str = "GPIO Loopback Latency"):
    """Create and display/save latency histogram with percentile markers."""
    
    if not dts_us:
        print("No valid latency data to plot.", file=sys.stderr)
        return
    
    arr = np.array(dts_us)
    
    # Calculate statistics
    stats = {
        'mean': np.mean(arr),
        'std': np.std(arr),
        'p50': np.percentile(arr, 50),
        'p95': np.percentile(arr, 95),
        'p99': np.percentile(arr, 99),
        'p999': np.percentile(arr, 99.9),
        'min': np.min(arr),
        'max': np.max(arr),
        'count': len(arr)
    }
    
    # Print summary
    print(f"Latency Statistics from {stats['count']} samples:")
    print(f"  Mean±σ:  {stats['mean']:.1f}±{stats['std']:.1f} µs")
    print(f"  P50:     {stats['p50']:.1f} µs")
    print(f"  P95:     {stats['p95']:.1f} µs")
    print(f"  P99:     {stats['p99']:.1f} µs")
    print(f"  P99.9:   {stats['p999']:.1f} µs")
    print(f"  Range:   {stats['min']:.1f} - {stats['max']:.1f} µs")
    
    # Create figure
    plt.figure(figsize=(12, 8))
    
    # Main histogram
    counts, bin_edges, patches = plt.hist(arr, bins=bins, alpha=0.7, color='skyblue', 
                                         edgecolor='black', linewidth=0.5)
    
    # Add percentile lines
    percentiles = [
        (stats['p50'], 'P50', 'green', '--'),
        (stats['p95'], 'P95', 'orange', '--'),
        (stats['p99'], 'P99', 'red', '--'),
        (stats['p999'], 'P99.9', 'darkred', ':')
    ]
    
    y_max = max(counts) * 1.1
    for value, label, color, style in percentiles:
        plt.axvline(value, color=color, linestyle=style, linewidth=2, alpha=0.8)
        plt.text(value, y_max * 0.9, f'{label}\n{value:.1f}µs', 
                rotation=0, ha='center', va='bottom', color=color, fontweight='bold')
    
    # Formatting
    plt.xlabel("Latency (µs)", fontsize=12)
    plt.ylabel("Count", fontsize=12)
    plt.title(f"{title}\n{stats['count']} samples, Mean: {stats['mean']:.1f}µs, P99: {stats['p99']:.1f}µs", 
              fontsize=14)
    plt.grid(True, alpha=0.3)
    
    # Optional log scale
    if log_scale:
        plt.yscale('log')
        plt.ylabel("Count (log scale)", fontsize=12)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save or show
    if output_path:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            plt.savefig(output_path, dpi=300, bbox_inches='tight')
            print(f"💾 Plot saved: {output_path}")
        except Exception as e:
            print(f"⚠ Failed to save plot: {e}", file=sys.stderr)
    else:
        plt.show()
    
    plt.close()


def plot_time_series(csv_path: str, output_path: Optional[str] = None):
    """Plot latency over time to show temporal patterns."""
    
    timestamps = []
    latencies_us = []
    
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_str = row.get("ts_send_ns", "").strip()
                dt_str = row.get("dt_ns", "").strip()
                
                if ts_str and dt_str and dt_str != "":
                    try:
                        ts_ns = int(ts_str)
                        dt_ns = int(dt_str)
                        if dt_ns > 0:
                            timestamps.append(ts_ns)
                            latencies_us.append(dt_ns / 1000.0)
                    except ValueError:
                        continue
                        
    except Exception as e:
        print(f"⚠ Failed to load time series data: {e}", file=sys.stderr)
        return
    
    if not timestamps:
        print("No valid time series data found.", file=sys.stderr)
        return
    
    # Convert to relative time in seconds
    start_time = timestamps[0]
    rel_times = [(ts - start_time) / 1e9 for ts in timestamps]
    
    # Create plot
    plt.figure(figsize=(14, 6))
    plt.scatter(rel_times, latencies_us, alpha=0.6, s=1)
    
    # Add running percentiles
    if len(latencies_us) > 100:
        window_size = len(latencies_us) // 50  # 50 points
        running_p95 = []
        running_times = []
        
        for i in range(window_size, len(latencies_us), window_size):
            window = latencies_us[i-window_size:i]
            running_p95.append(np.percentile(window, 95))
            running_times.append(rel_times[i])
        
        plt.plot(running_times, running_p95, 'r-', linewidth=2, alpha=0.8, label='Running P95')
        plt.legend()
    
    plt.xlabel("Time (seconds)")
    plt.ylabel("Latency (µs)")
    plt.title("Latency Over Time")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    if output_path:
        base, ext = os.path.splitext(output_path)
        ts_path = f"{base}_timeseries{ext}"
        try:
            plt.savefig(ts_path, dpi=300, bbox_inches='tight')
            print(f"💾 Time series plot saved: {ts_path}")
        except Exception as e:
            print(f"⚠ Failed to save time series plot: {e}", file=sys.stderr)
    else:
        plt.show()
    
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="Plot GPIO latency histogram and statistics from CSV")
    ap.add_argument("--csv", required=True, help="CSV path (from latency_meter.py)")
    ap.add_argument("--bins", type=int, default=50, help="Number of histogram bins")
    ap.add_argument("--log", action="store_true", help="Use log scale for y-axis")
    ap.add_argument("--output", "-o", help="Save plot as PNG (default: show interactive)")
    ap.add_argument("--title", default="GPIO Loopback Latency", help="Plot title")
    ap.add_argument("--time-series", action="store_true", help="Also plot latency over time")
    
    args = ap.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.csv):
        print(f"ERROR: CSV file not found: {args.csv}", file=sys.stderr)
        sys.exit(1)
    
    # Load data
    dts_us = load_latency_data(args.csv)
    
    if not dts_us:
        print("ERROR: No valid latency data found in CSV", file=sys.stderr)
        sys.exit(1)
    
    # Create histogram
    plot_latency_histogram(
        dts_us=dts_us,
        bins=args.bins,
        log_scale=args.log,
        output_path=args.output,
        title=args.title
    )
    
    # Optional time series plot
    if args.time_series:
        plot_time_series(args.csv, args.output)


if __name__ == "__main__":
    main()
