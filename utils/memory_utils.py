"""
GPU Memory Management Utilities and Monitoring Tools
Comprehensive tools for monitoring, debugging, and managing GPU memory in the optimization system
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from contextlib import contextmanager
import json

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Snapshot of GPU memory state at a point in time"""
    timestamp: datetime
    gpu_used_mb: float
    gpu_total_mb: float
    gpu_usage_percent: float
    pinned_used_mb: float = 0.0
    pinned_total_mb: float = 0.0
    context: str = ""  # What operation was happening
    solver_id: Optional[int] = None


@dataclass
class MemoryLeak:
    """Detected memory leak information"""
    start_snapshot: MemorySnapshot
    end_snapshot: MemorySnapshot
    leaked_mb: float
    context: str
    severity: str  # 'low', 'medium', 'high', 'critical'


class MemoryMonitor:
    """
    Comprehensive GPU memory monitoring system
    """

    def __init__(self, monitoring_interval: float = 5.0, history_size: int = 1000):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size
        self.snapshots: List[MemorySnapshot] = []
        self.detected_leaks: List[MemoryLeak] = []
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Statistics
        self.stats = {
            'peak_usage_mb': 0.0,
            'average_usage_mb': 0.0,
            'total_snapshots': 0,
            'leak_count': 0,
            'last_cleanup_time': None
        }

        # Thresholds
        self.leak_threshold_mb = 50.0  # Consider 50MB+ as potential leak
        self.warning_threshold = 0.8   # Warn at 80% usage
        self.critical_threshold = 0.95 # Critical at 95% usage

    def start_monitoring(self):
        """Start continuous memory monitoring"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("GPU memory monitoring started")

    def stop_monitoring(self):
        """Stop memory monitoring"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        logger.info("GPU memory monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                snapshot = self.take_snapshot("periodic_monitor")
                self._check_for_issues(snapshot)
                time.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Memory monitoring error: {e}")
                time.sleep(self.monitoring_interval)

    def take_snapshot(self, context: str = "", solver_id: Optional[int] = None) -> MemorySnapshot:
        """Take a snapshot of current GPU memory state with version compatibility"""
        try:
            # Use the compatible memory info function
            try:
                from core.solver import get_gpu_memory_info
                memory_info = get_gpu_memory_info()
            except ImportError:
                # Fallback if solver module not available
                memory_info = self._get_memory_info_fallback()

            snapshot = MemorySnapshot(
                timestamp=datetime.now(),
                gpu_used_mb=memory_info['gpu_used_mb'],
                gpu_total_mb=memory_info['gpu_total_mb'],
                gpu_usage_percent=memory_info['gpu_usage_percent'],
                pinned_used_mb=memory_info.get('pinned_used_mb', 0.0),
                pinned_total_mb=memory_info.get('pinned_total_mb', 0.0),
                context=context,
                solver_id=solver_id
            )

            with self.lock:
                self.snapshots.append(snapshot)

                # Maintain history size
                if len(self.snapshots) > self.history_size:
                    self.snapshots = self.snapshots[-self.history_size:]

                # Update statistics
                self._update_stats(snapshot)

            return snapshot

        except Exception as e:
            logger.error(f"Failed to take memory snapshot: {e}")
            # Return dummy snapshot on error
            return MemorySnapshot(
                timestamp=datetime.now(),
                gpu_used_mb=0.0,
                gpu_total_mb=0.0,
                gpu_usage_percent=0.0,
                context=f"error: {e}"
            )

    def _get_memory_info_fallback(self) -> Dict[str, float]:
        """Fallback memory info function with version compatibility"""
        try:
            import cupy as cp
            mempool = cp.get_default_memory_pool()

            gpu_used_bytes = mempool.used_bytes()
            gpu_total_bytes = mempool.total_bytes()

            result = {
                'gpu_used_mb': gpu_used_bytes / 1024**2,
                'gpu_total_mb': gpu_total_bytes / 1024**2,
                'gpu_usage_percent': (gpu_used_bytes / max(1, gpu_total_bytes)) * 100
            }

            # Try to get pinned memory with compatibility
            try:
                pinned_mempool = cp.get_default_pinned_memory_pool()
                if hasattr(pinned_mempool, 'used_bytes'):
                    result['pinned_used_mb'] = pinned_mempool.used_bytes() / 1024**2
                elif hasattr(pinned_mempool, 'n_bytes_used'):
                    result['pinned_used_mb'] = pinned_mempool.n_bytes_used() / 1024**2
                else:
                    result['pinned_used_mb'] = 0.0

                if hasattr(pinned_mempool, 'total_bytes'):
                    result['pinned_total_mb'] = pinned_mempool.total_bytes() / 1024**2
                elif hasattr(pinned_mempool, 'n_bytes_total'):
                    result['pinned_total_mb'] = pinned_mempool.n_bytes_total() / 1024**2
                else:
                    result['pinned_total_mb'] = 0.0
            except Exception:
                result['pinned_used_mb'] = 0.0
                result['pinned_total_mb'] = 0.0

            return result

        except Exception as e:
            logger.debug(f"Fallback memory info failed: {e}")
            return {
                'gpu_used_mb': 0.0,
                'gpu_total_mb': 0.0,
                'pinned_used_mb': 0.0,
                'pinned_total_mb': 0.0,
                'gpu_usage_percent': 0.0
            }

    def _update_stats(self, snapshot: MemorySnapshot):
        """Update monitoring statistics"""
        self.stats['total_snapshots'] += 1

        # Update peak usage
        if snapshot.gpu_used_mb > self.stats['peak_usage_mb']:
            self.stats['peak_usage_mb'] = snapshot.gpu_used_mb

        # Update average usage (simple moving average)
        count = self.stats['total_snapshots']
        current_avg = self.stats['average_usage_mb']
        self.stats['average_usage_mb'] = ((current_avg * (count - 1)) + snapshot.gpu_used_mb) / count

    def _check_for_issues(self, snapshot: MemorySnapshot):
        """Check for memory issues and alert if needed"""
        usage_percent = snapshot.gpu_usage_percent / 100.0

        # Check usage thresholds
        if usage_percent >= self.critical_threshold:
            logger.critical(f"CRITICAL GPU memory usage: {snapshot.gpu_usage_percent:.1f}% ({snapshot.gpu_used_mb:.1f}MB)")
        elif usage_percent >= self.warning_threshold:
            logger.warning(f"High GPU memory usage: {snapshot.gpu_usage_percent:.1f}% ({snapshot.gpu_used_mb:.1f}MB)")

        # Check for potential leaks
        self._detect_memory_leaks()

    def _detect_memory_leaks(self):
        """Detect potential memory leaks by analyzing recent snapshots"""
        if len(self.snapshots) < 10:  # Need some history
            return

        recent_snapshots = self.snapshots[-10:]

        # Look for sustained memory growth
        start_usage = recent_snapshots[0].gpu_used_mb
        end_usage = recent_snapshots[-1].gpu_used_mb
        growth = end_usage - start_usage

        if growth > self.leak_threshold_mb:
            # Potential leak detected
            leak = MemoryLeak(
                start_snapshot=recent_snapshots[0],
                end_snapshot=recent_snapshots[-1],
                leaked_mb=growth,
                context=f"Sustained growth over {len(recent_snapshots)} snapshots",
                severity=self._classify_leak_severity(growth)
            )

            with self.lock:
                self.detected_leaks.append(leak)
                self.stats['leak_count'] += 1

            logger.warning(f"Potential memory leak detected: {growth:.1f}MB growth ({leak.severity} severity)")

    def _classify_leak_severity(self, leaked_mb: float) -> str:
        """Classify leak severity based on amount leaked"""
        if leaked_mb > 500:
            return "critical"
        elif leaked_mb > 200:
            return "high"
        elif leaked_mb > 100:
            return "medium"
        else:
            return "low"

    @contextmanager
    def operation_context(self, operation_name: str, solver_id: Optional[int] = None):
        """Context manager to monitor memory during an operation"""
        before = self.take_snapshot(f"{operation_name}_start", solver_id)

        try:
            yield before
        finally:
            after = self.take_snapshot(f"{operation_name}_end", solver_id)

            # Check for memory retention
            memory_diff = after.gpu_used_mb - before.gpu_used_mb
            if memory_diff > 10.0:  # 10MB threshold
                logger.info(f"Operation '{operation_name}' retained {memory_diff:.1f}MB")

    def get_memory_report(self) -> Dict[str, Any]:
        """Generate comprehensive memory report"""
        with self.lock:
            if not self.snapshots:
                return {"error": "No memory snapshots available"}

            latest = self.snapshots[-1]

            # Calculate trends
            if len(self.snapshots) >= 2:
                prev = self.snapshots[-2]
                trend_mb = latest.gpu_used_mb - prev.gpu_used_mb
                trend_direction = "increasing" if trend_mb > 1 else "decreasing" if trend_mb < -1 else "stable"
            else:
                trend_mb = 0.0
                trend_direction = "unknown"

            return {
                "current_status": {
                    "timestamp": latest.timestamp.isoformat(),
                    "gpu_used_mb": latest.gpu_used_mb,
                    "gpu_total_mb": latest.gpu_total_mb,
                    "gpu_usage_percent": latest.gpu_usage_percent,
                    "trend_mb": trend_mb,
                    "trend_direction": trend_direction
                },
                "statistics": self.stats.copy(),
                "detected_leaks": len(self.detected_leaks),
                "recent_leaks": [
                    {
                        "leaked_mb": leak.leaked_mb,
                        "severity": leak.severity,
                        "context": leak.context,
                        "timestamp": leak.end_snapshot.timestamp.isoformat()
                    }
                    for leak in self.detected_leaks[-5:]  # Last 5 leaks
                ],
                "memory_efficiency": {
                    "snapshots_taken": len(self.snapshots),
                    "monitoring_duration_minutes":
                        (latest.timestamp - self.snapshots[0].timestamp).total_seconds() / 60
                        if len(self.snapshots) > 1 else 0
                }
            }

    def export_snapshots(self, filename: Optional[str] = None) -> str:
        """Export memory snapshots to JSON file"""
        if filename is None:
            filename = f"memory_snapshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with self.lock:
            data = {
                "export_timestamp": datetime.now().isoformat(),
                "snapshots": [
                    {
                        "timestamp": s.timestamp.isoformat(),
                        "gpu_used_mb": s.gpu_used_mb,
                        "gpu_total_mb": s.gpu_total_mb,
                        "gpu_usage_percent": s.gpu_usage_percent,
                        "context": s.context,
                        "solver_id": s.solver_id
                    }
                    for s in self.snapshots
                ],
                "statistics": self.stats,
                "detected_leaks": [
                    {
                        "leaked_mb": leak.leaked_mb,
                        "severity": leak.severity,
                        "context": leak.context,
                        "start_time": leak.start_snapshot.timestamp.isoformat(),
                        "end_time": leak.end_snapshot.timestamp.isoformat()
                    }
                    for leak in self.detected_leaks
                ]
            }

        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Memory snapshots exported to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Failed to export snapshots: {e}")
            return ""


class MemoryProfiler:
    """
    Profile memory usage of specific operations
    """

    def __init__(self):
        self.profiles: Dict[str, List[Dict[str, Any]]] = {}

    @contextmanager
    def profile_operation(self, operation_name: str, **metadata):
        """Profile memory usage of an operation"""
        try:
            from core.solver import get_gpu_memory_info

            start_time = time.time()
            start_memory = get_gpu_memory_info()

            yield

            end_time = time.time()
            end_memory = get_gpu_memory_info()

            profile = {
                "operation": operation_name,
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": end_time - start_time,
                "start_memory_mb": start_memory['gpu_used_mb'],
                "end_memory_mb": end_memory['gpu_used_mb'],
                "memory_delta_mb": end_memory['gpu_used_mb'] - start_memory['gpu_used_mb'],
                "peak_usage_percent": max(start_memory['gpu_usage_percent'], end_memory['gpu_usage_percent']),
                "metadata": metadata
            }

            if operation_name not in self.profiles:
                self.profiles[operation_name] = []
            self.profiles[operation_name].append(profile)

            logger.debug(f"Profiled {operation_name}: {profile['memory_delta_mb']:+.1f}MB in {profile['duration_seconds']:.3f}s")

        except Exception as e:
            logger.error(f"Memory profiling failed for {operation_name}: {e}")

    def get_profile_summary(self, operation_name: str) -> Dict[str, Any]:
        """Get summary statistics for a profiled operation"""
        if operation_name not in self.profiles:
            return {"error": f"No profiles found for {operation_name}"}

        profiles = self.profiles[operation_name]
        if not profiles:
            return {"error": f"No profiles data for {operation_name}"}

        memory_deltas = [p['memory_delta_mb'] for p in profiles]
        durations = [p['duration_seconds'] for p in profiles]

        return {
            "operation": operation_name,
            "execution_count": len(profiles),
            "memory_stats": {
                "average_delta_mb": sum(memory_deltas) / len(memory_deltas),
                "max_delta_mb": max(memory_deltas),
                "min_delta_mb": min(memory_deltas),
                "total_allocated_mb": sum(max(0, d) for d in memory_deltas),
                "total_freed_mb": sum(abs(min(0, d)) for d in memory_deltas)
            },
            "performance_stats": {
                "average_duration_seconds": sum(durations) / len(durations),
                "max_duration_seconds": max(durations),
                "min_duration_seconds": min(durations)
            },
            "recent_executions": profiles[-5:]  # Last 5 executions
        }


# Global instances
_memory_monitor: Optional[MemoryMonitor] = None
_memory_profiler: Optional[MemoryProfiler] = None


def get_memory_monitor() -> MemoryMonitor:
    """Get the global memory monitor instance"""
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
        _memory_monitor.start_monitoring()
    return _memory_monitor


def get_memory_profiler() -> MemoryProfiler:
    """Get the global memory profiler instance"""
    global _memory_profiler
    if _memory_profiler is None:
        _memory_profiler = MemoryProfiler()
    return _memory_profiler


# Decorator for automatic memory profiling
def profile_memory(operation_name: str = None, **metadata):
    """Decorator to automatically profile memory usage of a function"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            name = operation_name or f"{func.__module__}.{func.__name__}"
            profiler = get_memory_profiler()

            with profiler.profile_operation(name, **metadata):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# Context manager for manual memory profiling
@contextmanager
def profile_memory_usage(operation_name: str, **metadata):
    """Context manager for profiling memory usage"""
    profiler = get_memory_profiler()
    with profiler.profile_operation(operation_name, **metadata):
        yield


# Memory diagnostic utilities
def diagnose_memory_issues() -> Dict[str, Any]:
    """Comprehensive memory diagnostics"""
    try:
        from core.solver import get_gpu_memory_info

        current_memory = get_gpu_memory_info()
        monitor = get_memory_monitor()
        profiler = get_memory_profiler()

        # Get recent memory report
        memory_report = monitor.get_memory_report()

        # Check for common issues
        issues = []

        # High memory usage
        if current_memory['gpu_usage_percent'] > 80:
            issues.append({
                "type": "high_memory_usage",
                "severity": "warning" if current_memory['gpu_usage_percent'] < 95 else "critical",
                "description": f"GPU memory usage is {current_memory['gpu_usage_percent']:.1f}%",
                "recommendation": "Consider reducing concurrent solver instances or problem sizes"
            })

        # Memory leaks
        if monitor.detected_leaks:
            recent_leaks = [leak for leak in monitor.detected_leaks
                          if (datetime.now() - leak.end_snapshot.timestamp).total_seconds() < 3600]
            if recent_leaks:
                issues.append({
                    "type": "memory_leaks",
                    "severity": "warning",
                    "description": f"{len(recent_leaks)} potential memory leaks detected in the last hour",
                    "recommendation": "Check solver operations for incomplete cleanup"
                })

        return {
            "timestamp": datetime.now().isoformat(),
            "current_memory": current_memory,
            "memory_monitor_report": memory_report,
            "detected_issues": issues,
            "recommendations": [
                "Enable aggressive memory cleanup if not already enabled",
                "Monitor memory usage during peak load periods",
                "Consider implementing circuit breakers for high memory usage",
                "Profile individual operations to identify memory-intensive components"
            ]
        }

    except Exception as e:
        return {
            "error": f"Memory diagnostics failed: {e}",
            "timestamp": datetime.now().isoformat()
        }


def force_memory_cleanup():
    """Force comprehensive memory cleanup with version compatibility"""
    try:
        import gc
        import cupy as cp

        # Python garbage collection
        gc.collect()

        # GPU memory cleanup
        mempool = cp.get_default_memory_pool()

        before_gpu = mempool.used_bytes() / 1024**2

        # Handle pinned memory with compatibility
        before_pinned = 0
        pinned_mempool = None
        try:
            pinned_mempool = cp.get_default_pinned_memory_pool()
            if hasattr(pinned_mempool, 'used_bytes'):
                before_pinned = pinned_mempool.used_bytes() / 1024**2
            elif hasattr(pinned_mempool, 'n_bytes_used'):
                before_pinned = pinned_mempool.n_bytes_used() / 1024**2
        except Exception as e:
            logger.debug(f"Could not get pinned memory before cleanup: {e}")

        # Cleanup GPU memory
        mempool.free_all_blocks()

        # Cleanup pinned memory with compatibility
        if pinned_mempool:
            try:
                if hasattr(pinned_mempool, 'free_all_blocks'):
                    pinned_mempool.free_all_blocks()
                elif hasattr(pinned_mempool, 'free_all_pinned'):
                    pinned_mempool.free_all_pinned()
            except Exception as e:
                logger.debug(f"Pinned memory cleanup issue: {e}")

        after_gpu = mempool.used_bytes() / 1024**2

        # Get pinned memory after cleanup
        after_pinned = 0
        if pinned_mempool:
            try:
                if hasattr(pinned_mempool, 'used_bytes'):
                    after_pinned = pinned_mempool.used_bytes() / 1024**2
                elif hasattr(pinned_mempool, 'n_bytes_used'):
                    after_pinned = pinned_mempool.n_bytes_used() / 1024**2
            except Exception as e:
                logger.debug(f"Could not get pinned memory after cleanup: {e}")

        freed_gpu = before_gpu - after_gpu
        freed_pinned = before_pinned - after_pinned

        logger.info(f"Forced cleanup freed {freed_gpu:.1f}MB GPU, {freed_pinned:.1f}MB pinned memory")

        return {
            "freed_gpu_mb": freed_gpu,
            "freed_pinned_mb": freed_pinned,
            "current_gpu_mb": after_gpu,
            "current_pinned_mb": after_pinned
        }

    except Exception as e:
        logger.error(f"Force cleanup failed: {e}")
        return {"error": str(e)}


# Example usage functions
def example_memory_monitoring():
    """Example of how to use memory monitoring"""

    # Get monitor
    monitor = get_memory_monitor()

    # Take manual snapshots
    snapshot1 = monitor.take_snapshot("before_operation")

    # Use operation context
    with monitor.operation_context("optimization_solve", solver_id=1):
        # Your optimization code here
        time.sleep(1)  # Simulate work

    # Get memory report
    report = monitor.get_memory_report()
    print(f"Current GPU usage: {report['current_status']['gpu_usage_percent']:.1f}%")
    print(f"Detected leaks: {report['detected_leaks']}")

    # Export snapshots
    filename = monitor.export_snapshots()
    print(f"Snapshots exported to: {filename}")


def example_memory_profiling():
    """Example of how to use memory profiling"""

    # Using decorator
    @profile_memory("test_operation", problem_size=100)
    def test_function():
        # Simulate memory allocation
        import numpy as np
        data = np.random.random((1000, 1000))
        return data.sum()

    # Using context manager
    with profile_memory_usage("manual_operation", solver_id=2):
        # Your code here
        pass

    # Get profile summary
    profiler = get_memory_profiler()
    summary = profiler.get_profile_summary("test_operation")
    print(f"Average memory delta: {summary['memory_stats']['average_delta_mb']:.1f}MB")


if __name__ == "__main__":
    # Run diagnostics
    print("Running memory diagnostics...")
    diagnostics = diagnose_memory_issues()

    if "error" in diagnostics:
        print(f"Diagnostics failed: {diagnostics['error']}")
    else:
        print(f"Current GPU usage: {diagnostics['current_memory']['gpu_usage_percent']:.1f}%")
        print(f"Issues detected: {len(diagnostics['detected_issues'])}")

        for issue in diagnostics['detected_issues']:
            print(f"- {issue['type']}: {issue['description']}")

    # Example usage
    print("\nRunning examples...")
    example_memory_monitoring()
    example_memory_profiling()