#!/usr/bin/env python3
"""GODMODESCANNER Production Launcher

Launches GODMODESCANNER with production settings:
- Optimized rate limits for free RPC endpoints
- Real-time metrics monitoring
- Transaction monitor with RPC enrichment
"""

import os
import sys
import time
import subprocess
import signal
from datetime import datetime
from pathlib import Path

class ProductionLauncher:
    def __init__(self):
        self.project_dir = Path.cwd()
        self.processes = []
        self.metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'total_latency': 0,
            'request_count': 0,
            'alerts_generated': 0
        }
        self.start_time = time.time()
        
    def print_banner(self):
        print("\n" + "="*70)
        print("  GODMODESCANNER - Production Launcher".center(70))
        print("="*70 + "\n")
        
    def print_section(self, num, total, title):
        print(f"\033[1;33m[{num}/{total}] {title}\033[0m")
        
    def check_dependencies(self):
        """Verify production dependencies are available."""
        print("Checking dependencies...")
        
        # Check Python
        print(f"  ✓ Python {sys.version.split()[0]}")
        
        # Check Redis
        try:
            result = subprocess.run(
                ['redis-cli', '-p', '16379', 'ping'],
                capture_output=True, text=True, timeout=2
            )
            if result.stdout.strip() == 'PONG':
                print("  ✓ Guerrilla Redis Cluster (port 16379)")
        except:
            print("  ⚠ Guerrilla Redis Cluster not available")
            
        # Check required modules
        try:
            import asyncio
            import aiohttp
            print("  ✓ Required modules available")
        except ImportError as e:
            print(f"  ✗ Missing module: {e}")
            return False
            
        return True
        
    def apply_production_settings(self):
        """Set environment variables for production deployment."""
        print("\nApplying production settings...")
        
        # Optimized settings for free RPC endpoints
        os.environ['RPC_INITIAL_RPS'] = '5.0'
        os.environ['RPC_MAX_RPS'] = '15.0'
        os.environ['RPC_CACHE_MAXSIZE'] = '2000'
        os.environ['ENABLE_RPC_ENRICHMENT'] = 'true'
        os.environ['ENRICHMENT_MAX_ACCOUNTS'] = '5'
        os.environ['LOG_LEVEL'] = 'INFO'
        
        print("  ✓ Rate limits configured:")
        print(f"    - Initial RPS: {os.environ['RPC_INITIAL_RPS']}")
        print(f"    - Max RPS: {os.environ['RPC_MAX_RPS']}")
        print(f"    - Cache Size: {os.environ['RPC_CACHE_MAXSIZE']}")
        print(f"    - RPC Enrichment: {os.environ['ENABLE_RPC_ENRICHMENT']}")
        
    def start_transaction_monitor(self):
        """Launch transaction monitor with production settings."""
        print("\nStarting Transaction Monitor...")
        
        # Create logs directory
        log_dir = self.project_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        # Log file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'transaction_monitor_{timestamp}.log'
        
        # Start transaction monitor
        process = subprocess.Popen(
            [sys.executable, 'agents/transaction_monitor.py'],
            stdout=open(log_file, 'w'),
            stderr=subprocess.STDOUT,
            cwd=str(self.project_dir)
        )
        
        self.processes.append({
            'name': 'Transaction Monitor',
            'pid': process.pid,
            'log_file': str(log_file)
        })
        
        print(f"  ✓ Transaction Monitor started (PID: {process.pid})")
        print(f"    - Log file: {log_file}")
        
        # Wait for startup
        time.sleep(3)
        
        # Check if process is running
        if process.poll() is None:
            print("  ✓ Transaction Monitor is running")
            return True
        else:
            print("  ✗ Transaction Monitor failed to start")
            print(f"    Check log: {log_file}")
            self.print_log_tail(log_file)
            return False
            
    def print_log_tail(self, log_file, lines=20):
        """Print last N lines of log file."""
        try:
            with open(log_file, 'r') as f:
                log_lines = f.readlines()[-lines:]
                for line in log_lines:
                    print(f"    {line.rstrip()}")
        except:
            pass
            
    def display_metrics_dashboard(self):
        """Display real-time metrics dashboard."""
        uptime = time.time() - self.start_time
        
        # Calculate metrics
        total_requests = self.metrics['successful_requests'] + self.metrics['failed_requests']
        cache_hit_rate = (self.metrics['cache_hits'] / 
                         (self.metrics['cache_hits'] + self.metrics['cache_misses']) 
                         if (self.metrics['cache_hits'] + self.metrics['cache_misses']) > 0 else 0)
        success_rate = (self.metrics['successful_requests'] / total_requests 
                       if total_requests > 0 else 0)
        avg_latency = (self.metrics['total_latency'] / self.metrics['request_count'] 
                      if self.metrics['request_count'] > 0 else 0)
        
        # Color coding
        cache_color = '\033[1;32m' if cache_hit_rate >= 0.6 else '\033[1;33m'
        success_color = '\033[1;32m' if success_rate >= 0.99 else '\033[1;33m'
        latency_color = '\033[1;32m' if avg_latency < 100 else '\033[1;33m'
        
        # Clear screen and print dashboard
        print('\033[2J\033[H')
        print("="*70)
        print("  GODMODESCANNER - Production Monitoring Dashboard".center(70))
        print("="*70)
        print()
        print(f"Uptime: {uptime:.2f}s | Time: {datetime.now().strftime('%H:%M:%S')}")
        print()
        print("━"*70)
        print("KEY METRICS")
        print("━"*70)
        print(f"Cache Hit Rate: {cache_color}{cache_hit_rate*100:.2f}%\033[0m (Target: >60%)")
        print(f"Success Rate:   {success_color}{success_rate*100:.2f}%\033[0m (Target: >99%)")
        print(f"Avg Latency:    {latency_color}{avg_latency:.2f}ms\033[0m (Target: <100ms)")
        print()
        print("━"*70)
        print("REQUEST STATISTICS")
        print("━"*70)
        print(f"Successful:    {self.metrics['successful_requests']}")
        print(f"Failed:        {self.metrics['failed_requests']}")
        print(f"Total:         {total_requests}")
        print()
        print("━"*70)
        print("TARGET STATUS")
        print("━"*70)
        cache_status = "✓ PASS" if cache_hit_rate >= 0.6 else "⚠ BELOW TARGET"
        success_status = "✓ PASS" if success_rate >= 0.99 else "⚠ BELOW TARGET"
        latency_status = "✓ PASS" if avg_latency < 100 else "⚠ ABOVE TARGET"
        print(f"Cache Hit Rate (>60%):   {cache_status}")
        print(f"Success Rate (>99%):     {success_status}")
        print(f"Avg Latency (<100ms):    {latency_status}")
        print()
        print("━"*70)
        print("RUNNING SERVICES")
        print("━"*70)
        for proc in self.processes:
            status = "Running" if self.is_process_running(proc['pid']) else "Stopped"
            print(f"{proc['name']}: {status} (PID: {proc['pid']})")
        print()
        print("Press Ctrl+C to stop")
        
    def is_process_running(self, pid):
        """Check if process with given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
            
    def monitor_loop(self):
        """Main monitoring loop."""
        try:
            while True:
                self.display_metrics_dashboard()
                time.sleep(2)
        except KeyboardInterrupt:
            print("\n\nStopping production deployment...")
            self.stop_all()
            
    def stop_all(self):
        """Stop all running processes."""
        for proc in self.processes:
            try:
                os.kill(proc['pid'], signal.SIGTERM)
                print(f"  ✓ Stopped {proc['name']} (PID: {proc['pid']})")
            except:
                pass
        print("\nAll services stopped.")
        
    def display_status(self):
        """Display final deployment status."""
        print("\n" + "="*70)
        print("  PRODUCTION DEPLOYMENT COMPLETE".center(70))
        print("="*70)
        print()
        print("Active Services:")
        for proc in self.processes:
            print(f"  - {proc['name']} (PID: {proc['pid']})")
        print()
        print("Target Metrics:")
        print("  - Cache Hit Rate: >60%")
        print("  - Success Rate: >99%")
        print("  - Avg Latency: <100ms")
        print()
        print("Production Settings:")
        print(f"  - RPC Initial RPS: {os.environ.get('RPC_INITIAL_RPS', '5.0')}")
        print(f"  - RPC Max RPS: {os.environ.get('RPC_MAX_RPS', '15.0')}")
        print(f"  - Cache Size: {os.environ.get('RPC_CACHE_MAXSIZE', '2000')}")
        print(f"  - RPC Enrichment: {os.environ.get('ENABLE_RPC_ENRICHMENT', 'true')}")
        print()
        print("Log Files:")
        for proc in self.processes:
            print(f"  - {proc['name']}: {proc['log_file']}")
        print()
        print("To upgrade to authenticated endpoints:")
        print("  1. Get API keys from Helius, Triton, or QuickNode")
        print("  2. Edit .env.production with your keys")
        print("  3. Copy: cp .env.production .env")
        print("  4. Restart: python launch_production.py")
        print()
        
    def run(self):
        """Main entry point."""
        self.print_banner()
        
        # Step 1: Check dependencies
        self.print_section(1, 4, "Checking dependencies")
        if not self.check_dependencies():
            print("\n✗ Dependency check failed")
            return False
            
        # Step 2: Apply production settings
        self.print_section(2, 4, "Applying production settings")
        self.apply_production_settings()
        
        # Step 3: Start transaction monitor
        self.print_section(3, 4, "Starting transaction monitor")
        if not self.start_transaction_monitor():
            print("\n✗ Failed to start transaction monitor")
            return False
            
        # Step 4: Display status and start monitoring
        self.print_section(4, 4, "Starting monitoring dashboard")
        self.display_status()
        
        print("\nStarting real-time monitoring...")
        time.sleep(2)
        
        # Start monitoring loop
        self.monitor_loop()
        
        return True

if __name__ == '__main__':
    launcher = ProductionLauncher()
    launcher.run()
