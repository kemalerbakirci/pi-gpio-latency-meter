#!/usr/bin/env python3
"""
Comprehensive unit tests for GPIO latency meter statistics and simulator.
"""
import unittest
import numpy as np
import tempfile
import csv
import os
import sys
import time
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from latency_meter import compute_percentiles, compute_full_stats
from sim_backend import setup_sim_lines, get_distribution_info, _LatencyModel


class TestPercentiles(unittest.TestCase):
    """Test percentile computation robustness."""
    
    def test_basic_percentiles(self):
        """Test percentiles with normal data."""
        dts = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        p50, p95, p99, mx = compute_percentiles(dts)
        
        self.assertAlmostEqual(p50, 55, delta=10)  # Median around middle
        self.assertGreaterEqual(p95, 90)
        self.assertGreaterEqual(p99, 95) 
        self.assertEqual(mx, 100)
    
    def test_empty_list(self):
        """Test percentiles with empty input."""
        p50, p95, p99, mx = compute_percentiles([])
        self.assertEqual(p50, 0.0)
        self.assertEqual(p95, 0.0)
        self.assertEqual(p99, 0.0)
        self.assertEqual(mx, 0)
    
    def test_single_value(self):
        """Test percentiles with single value."""
        dts = [42]
        p50, p95, p99, mx = compute_percentiles(dts)
        
        self.assertEqual(p50, 42.0)
        self.assertEqual(p95, 42.0)
        self.assertEqual(p99, 42.0)
        self.assertEqual(mx, 42)
    
    def test_with_nans_and_negatives(self):
        """Test percentiles filtering invalid values."""
        dts = [10, 20, float('nan'), -5, 30, None, 40]
        p50, p95, p99, mx = compute_percentiles(dts)
        
        # Should only consider [10, 20, 30, 40]
        self.assertAlmostEqual(p50, 25, delta=5)
        self.assertEqual(mx, 40)
    
    def test_outliers(self):
        """Test percentiles with extreme outliers."""
        # Most values around 100, with one huge outlier
        dts = [100] * 98 + [200, 10000]
        p50, p95, p99, mx = compute_percentiles(dts)
        
        self.assertAlmostEqual(p50, 100, delta=1)
        self.assertLess(p95, 1000)  # P95 shouldn't be affected by outlier
        self.assertGreater(p99, 100)  # P99 might catch the 200
        self.assertEqual(mx, 10000)


class TestFullStats(unittest.TestCase):
    """Test comprehensive statistics computation."""
    
    def test_full_stats_normal(self):
        """Test full statistics with normal data."""
        dts = list(range(1, 101))  # 1 to 100
        stats = compute_full_stats(dts)
        
        self.assertEqual(stats.total_samples, 100)
        self.assertEqual(stats.successful_samples, 100)
        self.assertEqual(stats.missed_samples, 0)
        self.assertAlmostEqual(stats.mean_ns, 50.5, delta=1)
        self.assertEqual(stats.min_ns, 1)
        self.assertEqual(stats.max_ns, 100)
    
    def test_full_stats_with_misses(self):
        """Test full statistics with missed samples."""
        dts = [10, 20, None, 30, None, 40]
        stats = compute_full_stats(dts)
        
        self.assertEqual(stats.total_samples, 6)
        self.assertEqual(stats.successful_samples, 4)
        self.assertEqual(stats.missed_samples, 2)
        self.assertAlmostEqual(stats.mean_ns, 25, delta=1)
    
    def test_full_stats_all_misses(self):
        """Test full statistics with all missed samples."""
        dts = [None, None, None]
        stats = compute_full_stats(dts)
        
        self.assertEqual(stats.total_samples, 3)
        self.assertEqual(stats.successful_samples, 0)
        self.assertEqual(stats.missed_samples, 3)
        self.assertEqual(stats.mean_ns, 0.0)


class TestSimulator(unittest.TestCase):
    """Test GPIO simulator functionality."""
    
    def test_simulator_setup(self):
        """Test basic simulator setup."""
        out_line, in_line = setup_sim_lines(mode="const", base_lat_us=100, jitter_us=0, seed=42)
        
        self.assertIsNotNone(out_line)
        self.assertIsNotNone(in_line)
        self.assertTrue(hasattr(out_line, 'set_value'))
        self.assertTrue(hasattr(in_line, 'event_wait'))
        self.assertTrue(hasattr(in_line, 'event_read'))
    
    def test_simulator_const_mode(self):
        """Test simulator with constant delay."""
        out_line, in_line = setup_sim_lines(mode="const", base_lat_us=500, jitter_us=0, seed=42)
        
        latencies_us = []
        
        for _ in range(10):
            start_time = time.perf_counter_ns()
            out_line.set_value(1)
            
            if in_line.event_wait(0.1):  # 100ms timeout
                in_line.event_read()
                end_time = time.perf_counter_ns()
                latency_us = (end_time - start_time) / 1000.0
                latencies_us.append(latency_us)
            
            out_line.set_value(0)
            time.sleep(0.001)  # Small delay between samples
        
        # Should have consistent latencies around 500µs (±50µs for timing overhead)
        self.assertGreater(len(latencies_us), 5)  # Most should succeed
        mean_latency = np.mean(latencies_us)
        self.assertGreater(mean_latency, 450)
        self.assertLess(mean_latency, 700)  # Adjusted for system overhead
    
    def test_latency_model_distributions(self):
        """Test different latency distribution modes."""
        base_ns = 100000  # 100µs
        jitter_ns = 20000  # 20µs
        
        for mode in ["const", "uniform", "normal", "lognormal", "heavy"]:
            with self.subTest(mode=mode):
                model = _LatencyModel(mode, base_ns, jitter_ns, seed=42)
                
                # Generate samples
                samples = [model.sample_ns() for _ in range(1000)]
                
                # All samples should be non-negative
                self.assertTrue(all(s >= 0 for s in samples))
                
                # Check mode-specific properties
                if mode == "const":
                    # All samples should be identical
                    self.assertTrue(all(s == base_ns for s in samples))
                else:
                    # Should have some variation
                    self.assertGreater(np.std(samples), 0)
    
    def test_distribution_info(self):
        """Test distribution information function."""
        info = get_distribution_info("lognormal", base_us=400, jitter_us=150)
        
        self.assertEqual(info['mode'], "lognormal")
        self.assertEqual(info['base_us'], 400)
        self.assertEqual(info['jitter_us'], 150)
        
        # Should have reasonable statistical measures
        self.assertGreater(info['actual_mean_us'], 0)
        self.assertGreater(info['actual_std_us'], 0)
        self.assertLess(info['actual_p50_us'], info['actual_p95_us'])
        self.assertLess(info['actual_p95_us'], info['actual_p99_us'])


class TestLatencyMeterIntegration(unittest.TestCase):
    """Integration tests for the full latency meter."""
    
    def test_csv_output_format(self):
        """Test CSV output format compliance."""
        # This test would require running the actual latency_meter
        # For now, we'll test CSV format validation
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["ts_send_ns", "ts_edge_ns", "dt_ns"])
            writer.writerow([1000000000, 1000500000, 500000])
            writer.writerow([2000000000, 2000300000, 300000])
            writer.writerow([3000000000, "", ""])  # Missed sample
            csv_path = f.name
        
        try:
            # Verify we can read it back
            dts = []
            with open(csv_path, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    dt_str = row.get("dt_ns", "").strip()
                    if dt_str:
                        dts.append(int(dt_str))
            
            self.assertEqual(len(dts), 2)  # Two successful samples
            self.assertIn(500000, dts)
            self.assertIn(300000, dts)
            
        finally:
            os.unlink(csv_path)


class TestSmokeTest(unittest.TestCase):
    """Smoke tests for overall functionality."""
    
    def test_simulator_smoke_test(self):
        """Run simulator for short duration and verify basic functionality."""
        
        # This simulates what the main script does
        out_line, in_line = setup_sim_lines(mode="lognormal", base_lat_us=200, jitter_us=50, seed=42)
        
        samples = []
        successful_count = 0
        
        # Simulate 20 pulses
        for i in range(20):
            # Send pulse
            start_time = time.perf_counter_ns()
            out_line.set_value(1)
            
            # Wait for edge
            if in_line.event_wait(0.05):  # 50ms timeout
                event = in_line.event_read()
                end_time = time.perf_counter_ns()
                dt_ns = end_time - start_time
                samples.append(dt_ns)
                successful_count += 1
            
            out_line.set_value(0)
            time.sleep(0.002)  # 2ms between pulses
        
        # Verify results
        self.assertGreater(successful_count, 15)  # Most should succeed
        self.assertGreater(len(samples), 15)
        
        # Compute stats
        stats = compute_full_stats(samples)
        self.assertGreater(stats.successful_samples, 0)
        self.assertGreater(stats.p50_ns, 100000)  # At least 100µs
        self.assertLess(stats.p99_ns, 2000000)    # Less than 2ms
        
        # Verify ordering
        self.assertLessEqual(stats.p50_ns, stats.p95_ns)
        self.assertLessEqual(stats.p95_ns, stats.p99_ns)
        self.assertLessEqual(stats.p99_ns, stats.max_ns)


if __name__ == "__main__":
    # Run all tests
    unittest.main(verbosity=2)
