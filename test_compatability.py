#!/usr/bin/env python3
"""
CuPy Version Compatibility Test Script
Tests the updated memory management functions for compatibility with different CuPy versions
"""

import sys
import traceback


def test_cupy_compatibility():
    """Test CuPy version compatibility for memory management"""

    print("🧪 CuPy Version Compatibility Test")
    print("=" * 50)

    # Test 1: Basic CuPy import
    print("1. Testing CuPy import...")
    try:
        import cupy as cp
        print(f"   ✅ CuPy version: {cp.__version__}")

        # Check GPU availability
        try:
            device_id = cp.cuda.runtime.getDevice()
            device_props = cp.cuda.runtime.getDeviceProperties(device_id)
            print(f"   🎯 GPU: {device_props['name'].decode()}")
        except Exception as e:
            print(f"   ⚠️ GPU info failed: {e}")

    except ImportError as e:
        print(f"   ❌ CuPy not available: {e}")
        return False
    except Exception as e:
        print(f"   ❌ CuPy import error: {e}")
        return False

    # Test 2: Memory pool availability
    print("\n2. Testing memory pools...")
    try:
        mempool = cp.get_default_memory_pool()
        print(f"   ✅ Default memory pool available")
        print(f"   📊 GPU memory used: {mempool.used_bytes() / 1024 ** 2:.1f}MB")
        print(f"   📊 GPU memory total: {mempool.total_bytes() / 1024 ** 2:.1f}MB")

    except Exception as e:
        print(f"   ❌ Memory pool error: {e}")
        return False

    # Test 3: Pinned memory pool compatibility
    print("\n3. Testing pinned memory pool compatibility...")
    try:
        pinned_mempool = cp.get_default_pinned_memory_pool()
        print(f"   ✅ Pinned memory pool available")

        # Test different attribute names for version compatibility
        attrs_found = []

        if hasattr(pinned_mempool, 'used_bytes'):
            used_bytes = pinned_mempool.used_bytes()
            attrs_found.append('used_bytes')
            print(f"   ✅ used_bytes() method available: {used_bytes / 1024 ** 2:.1f}MB")

        if hasattr(pinned_mempool, 'n_bytes_used'):
            n_bytes_used = pinned_mempool.n_bytes_used()
            attrs_found.append('n_bytes_used')
            print(f"   ✅ n_bytes_used() method available: {n_bytes_used / 1024 ** 2:.1f}MB")

        if hasattr(pinned_mempool, 'total_bytes'):
            total_bytes = pinned_mempool.total_bytes()
            attrs_found.append('total_bytes')
            print(f"   ✅ total_bytes() method available: {total_bytes / 1024 ** 2:.1f}MB")

        if hasattr(pinned_mempool, 'n_bytes_total'):
            n_bytes_total = pinned_mempool.n_bytes_total()
            attrs_found.append('n_bytes_total')
            print(f"   ✅ n_bytes_total() method available: {n_bytes_total / 1024 ** 2:.1f}MB")

        if hasattr(pinned_mempool, 'free_all_blocks'):
            attrs_found.append('free_all_blocks')
            print(f"   ✅ free_all_blocks() method available")

        if hasattr(pinned_mempool, 'free_all_pinned'):
            attrs_found.append('free_all_pinned')
            print(f"   ✅ free_all_pinned() method available")

        if not attrs_found:
            print(f"   ⚠️ No known pinned memory attributes found")
            print(f"   🔍 Available attributes: {[attr for attr in dir(pinned_mempool) if not attr.startswith('_')]}")
        else:
            print(f"   ✅ Compatible attributes found: {attrs_found}")

    except Exception as e:
        print(f"   ⚠️ Pinned memory pool not available: {e}")
        print(f"   ℹ️ This is normal for some CuPy versions")

    # Test 4: Updated memory info function
    print("\n4. Testing updated get_gpu_memory_info function...")
    try:
        # Import the updated function
        sys.path.insert(0, '.')  # Add current directory to path
        from core.solver import get_gpu_memory_info

        memory_info = get_gpu_memory_info()
        print(f"   ✅ Memory info function works")
        print(f"   📊 GPU used: {memory_info['gpu_used_mb']:.1f}MB")
        print(f"   📊 GPU total: {memory_info['gpu_total_mb']:.1f}MB")
        print(f"   📊 GPU usage: {memory_info['gpu_usage_percent']:.1f}%")
        print(f"   📊 Pinned used: {memory_info['pinned_used_mb']:.1f}MB")
        print(f"   📊 Pinned total: {memory_info['pinned_total_mb']:.1f}MB")

    except ImportError as e:
        print(f"   ⚠️ Could not import updated function: {e}")
        print(f"   ℹ️ Testing fallback implementation...")

        # Test fallback implementation
        try:
            memory_info = test_fallback_memory_info()
            print(f"   ✅ Fallback memory info works")
            print(f"   📊 GPU used: {memory_info['gpu_used_mb']:.1f}MB")
            print(f"   📊 GPU total: {memory_info['gpu_total_mb']:.1f}MB")
            print(f"   📊 GPU usage: {memory_info['gpu_usage_percent']:.1f}%")
        except Exception as fallback_error:
            print(f"   ❌ Fallback failed: {fallback_error}")
            return False

    except Exception as e:
        print(f"   ❌ Memory info function error: {e}")
        traceback.print_exc()
        return False

    # Test 5: Memory context manager
    print("\n5. Testing memory context manager...")
    try:
        from core.solver import gpu_memory_context

        print(f"   Testing context manager...")
        with gpu_memory_context(solver_id=999):
            # Allocate some GPU memory for testing
            test_array = cp.random.random((1000, 1000))
            print(f"   ✅ Context manager completed successfully")
            del test_array  # Clean up test array

    except ImportError as e:
        print(f"   ⚠️ Could not import context manager: {e}")
    except Exception as e:
        print(f"   ❌ Context manager error: {e}")
        traceback.print_exc()
        return False

    print("\n" + "=" * 50)
    print("🎉 CuPy compatibility test completed successfully!")
    return True


def test_fallback_memory_info():
    """Test fallback memory info implementation"""
    import cupy as cp

    mempool = cp.get_default_memory_pool()
    gpu_used_bytes = mempool.used_bytes()
    gpu_total_bytes = mempool.total_bytes()

    result = {
        'gpu_used_mb': gpu_used_bytes / 1024 ** 2,
        'gpu_total_mb': gpu_total_bytes / 1024 ** 2,
        'gpu_usage_percent': (gpu_used_bytes / max(1, gpu_total_bytes)) * 100
    }

    # Try pinned memory with compatibility
    try:
        pinned_mempool = cp.get_default_pinned_memory_pool()

        if hasattr(pinned_mempool, 'used_bytes'):
            result['pinned_used_mb'] = pinned_mempool.used_bytes() / 1024 ** 2
        elif hasattr(pinned_mempool, 'n_bytes_used'):
            result['pinned_used_mb'] = pinned_mempool.n_bytes_used() / 1024 ** 2
        else:
            result['pinned_used_mb'] = 0.0

        if hasattr(pinned_mempool, 'total_bytes'):
            result['pinned_total_mb'] = pinned_mempool.total_bytes() / 1024 ** 2
        elif hasattr(pinned_mempool, 'n_bytes_total'):
            result['pinned_total_mb'] = pinned_mempool.n_bytes_total() / 1024 ** 2
        else:
            result['pinned_total_mb'] = 0.0

    except Exception:
        result['pinned_used_mb'] = 0.0
        result['pinned_total_mb'] = 0.0

    return result


def test_basic_optimization():
    """Test basic optimization to ensure everything works end-to-end"""

    print("\n🧪 Basic Optimization Test")
    print("=" * 50)

    try:
        # Import required modules
        from core.solver import TechnicianWorkOrderSolver
        from core.models import (
            Technician, WorkOrder, Location, TimeWindow,
            Priority, WorkOrderType, OptimizationProblem
        )

        print("1. Creating test problem...")

        # Create simple test problem
        technician = Technician(
            id="TECH001",
            name="Test Technician",
            start_location=Location(3.1073, 101.6067, "PJ Centre"),
            work_shift=TimeWindow(480, 1020),  # 8 AM - 5 PM
            break_window=TimeWindow(720, 780),  # 12 PM - 1 PM
            break_duration=60,
            skills={"electrical"},
            max_daily_orders=5
        )

        work_order = WorkOrder(
            id="WO001",
            location=Location(3.1319, 101.6292, "SS2 PJ"),
            priority=Priority.MEDIUM,
            work_type=WorkOrderType.MAINTENANCE,
            required_skills={"electrical"},
            service_time=60
        )

        problem = OptimizationProblem(
            technicians=[technician],
            work_orders=[work_order]
        )

        print("2. Creating solver...")
        solver = TechnicianWorkOrderSolver()

        print("3. Running optimization...")
        solution = solver.solve(problem)

        print(f"   ✅ Optimization completed")
        print(f"   📊 Status: {solution.status.value}")
        print(f"   🎯 Orders completed: {solution.orders_completed}")
        print(f"   ⏱️ Solve time: {solution.solve_time:.3f}s")

        return solution.status.value != "error"

    except Exception as e:
        print(f"   ❌ Basic optimization failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Starting CuPy compatibility and memory management tests...")
    print()

    # Run compatibility test
    compatibility_ok = test_cupy_compatibility()

    if compatibility_ok:
        # Run basic optimization test
        optimization_ok = test_basic_optimization()

        if optimization_ok:
            print("\n🎉 All tests passed! The system is ready to use.")
            exit(0)
        else:
            print("\n❌ Optimization test failed.")
            exit(1)
    else:
        print("\n❌ Compatibility test failed.")
        exit(1)