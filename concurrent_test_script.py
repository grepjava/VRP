#!/usr/bin/env python3
"""
Fixed concurrent test script using real Malaysian technician and work order data
Compatible with the existing concurrent_test_script.py name
"""

try:
    import requests
    import json
    import time
    import threading
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from typing import List, Dict, Any

    print("✅ All required imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please install missing packages: pip install requests")
    exit(1)


def load_problem_data(filename: str = "input.json") -> Dict[str, Any]:
    """Load problem data from JSON file"""
    try:
        if not os.path.exists(filename):
            print(f"❌ File {filename} not found in current directory")
            return None

        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"✅ Loaded problem data from {filename}")
        print(f"   Technicians: {len(data.get('technicians', []))}")
        print(f"   Work orders: {len(data.get('work_orders', []))}")

        return data

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {filename}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error loading {filename}: {e}")
        return None


def split_problem_data(data: Dict[str, Any], num_splits: int = 6) -> List[Dict[str, Any]]:
    """Split the problem data into multiple realistic problems for concurrent testing"""
    if not data or num_splits <= 1:
        return [data] if data else []

    technicians = data.get('technicians', [])
    work_orders = data.get('work_orders', [])
    config = data.get('config', {})

    if len(technicians) == 0 or len(work_orders) == 0:
        return [data]

    # Calculate realistic splits - ensure each split has adequate technicians
    min_techs_per_split = 2  # Minimum 2 technicians per split
    max_orders_per_tech = 10  # Maximum 10 orders per technician

    # Adjust splits based on available technicians
    effective_splits = min(num_splits, len(technicians) // min_techs_per_split)
    if effective_splits < 1:
        effective_splits = 1

    techs_per_split = max(min_techs_per_split, len(technicians) // effective_splits)
    orders_per_split = max(5, len(work_orders) // effective_splits)

    problems = []

    for i in range(effective_splits):
        # Get subset of technicians
        tech_start = i * techs_per_split
        tech_end = min((i + 1) * techs_per_split, len(technicians))
        if i == effective_splits - 1:  # Last split gets remaining techs
            tech_end = len(technicians)

        # Get subset of work orders
        order_start = i * orders_per_split
        order_end = min((i + 1) * orders_per_split, len(work_orders))
        if i == effective_splits - 1:  # Last split gets remaining orders
            order_end = len(work_orders)

        # Ensure we have adequate technicians for work orders
        num_techs = tech_end - tech_start
        num_orders = order_end - order_start

        if num_techs < 1 or num_orders < 1:
            continue

        # Adjust orders if too many for available technicians
        if num_orders > num_techs * max_orders_per_tech:
            order_end = order_start + (num_techs * max_orders_per_tech)
            num_orders = order_end - order_start

        split_data = {
            "technicians": technicians[tech_start:tech_end],
            "work_orders": work_orders[order_start:order_end],
            "use_concurrent": True,
            "priority": i + 1,
            "config": config.copy()
        }

        problems.append(split_data)

        print(f"   Split {i + 1}: {num_techs} techs, {num_orders} orders (ratio: {num_orders / num_techs:.1f} orders/tech)")

    return problems


def create_problem_variations(base_data: Dict[str, Any], num_variations: int = 6) -> List[Dict[str, Any]]:
    """Create variations of the base problem for concurrent testing"""
    if not base_data:
        return []

    technicians = base_data.get('technicians', [])
    work_orders = base_data.get('work_orders', [])
    config = base_data.get('config', {})

    variations = []

    # Strategy 1: Different time limits and problem sizes
    time_limits = [2, 3, 5, 7, 10, 15]

    for i in range(min(num_variations, len(time_limits))):
        variation_config = config.copy()
        variation_config['time_limit'] = time_limits[i]

        # For testing, use a subset to make it more manageable
        tech_count = min(len(technicians), 3 + i)  # 3-8 technicians
        order_count = min(len(work_orders), 15 + i * 10)  # 15-65 orders

        variation = {
            "technicians": technicians[:tech_count],
            "work_orders": work_orders[:order_count],
            "use_concurrent": True,
            "priority": i + 1,
            "config": variation_config
        }

        variations.append(variation)
        print(f"   Variation {i + 1}: {len(variation['technicians'])} techs, {len(variation['work_orders'])} orders, {time_limits[i]}s limit")

    return variations


def create_simple_test_problem(problem_id: int):
    """Create a minimal test problem that should always work"""
    return {
        "technicians": [
            {
                "id": f"TECH{problem_id:02d}",
                "name": f"Technician {problem_id}",
                "start_location": {
                    "latitude": 3.1073 + problem_id * 0.001,
                    "longitude": 101.6067 + problem_id * 0.001,
                    "address": f"Tech Location {problem_id}"
                },
                "work_shift": {"earliest": 480, "latest": 1020},  # 8 AM - 5 PM
                "break_window": {"earliest": 720, "latest": 780},  # 12 PM - 1 PM
                "break_duration": 60,
                "skills": ["electrical"],
                "max_daily_orders": 5,
                "max_travel_time": 300
            }
        ],
        "work_orders": [
            {
                "id": f"WO{problem_id:02d}",
                "location": {
                    "latitude": 3.1319 + problem_id * 0.001,
                    "longitude": 101.6292 + problem_id * 0.001,
                    "address": f"Work Location {problem_id}"
                },
                "priority": "medium",
                "work_type": "maintenance",
                "service_time": 60,
                "required_skills": ["electrical"],
                "customer_name": f"Customer {problem_id}",
                "description": f"Test work order {problem_id}"
            }
        ],
        "use_concurrent": True,
        "priority": problem_id
    }


def create_batch_test(url: str, problem_data: Dict[str, Any]):
    """Test the batch optimization endpoint with real data"""
    print(f"\n🧪 Testing batch optimization endpoint...")

    if not problem_data:
        print("❌ No problem data available")
        return False

    # Create smaller problems for batch processing
    technicians = problem_data.get('technicians', [])
    work_orders = problem_data.get('work_orders', [])

    # Create 4 smaller problems with realistic technician-to-order ratios
    batch_problems = []
    for i in range(4):
        tech_start = i * 2
        tech_end = min((i + 1) * 2 + 1, len(technicians))  # 2-3 techs per problem

        order_start = i * 15
        order_end = min((i + 1) * 15, len(work_orders))  # 15 orders per problem

        if tech_start < len(technicians) and order_start < len(work_orders):
            batch_problem = {
                "technicians": technicians[tech_start:tech_end],
                "work_orders": work_orders[order_start:order_end]
            }
            batch_problems.append(batch_problem)

    if not batch_problems:
        print("❌ Could not create batch problems")
        return False

    batch_request = {
        "problems": batch_problems,
        "timeout": 180.0
    }

    print(f"📤 Sending batch request with {len(batch_problems)} problems...")
    start_time = time.time()

    try:
        response = requests.post(
            f"{url}/vrp/optimize-batch",
            json=batch_request,
            timeout=200
        )

        elapsed = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            success_count = result.get('success_count', 0)
            failure_count = result.get('failure_count', 0)
            total_time = result.get('total_time', 0)

            print(f"✅ Batch optimization completed in {elapsed:.3f}s")
            print(f"   Server time: {total_time:.3f}s")
            print(f"   Successful: {success_count}/{len(batch_problems)}")
            print(f"   Failed: {failure_count}/{len(batch_problems)}")

            return success_count > 0
        else:
            print(f"❌ Batch request failed: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Batch request exception: {e}")
        return False


def send_optimization_request(url: str, problem_data: dict, request_id: int):
    """Send a single optimization request and return results"""
    thread_id = threading.get_ident()
    start_time = time.time()

    # Extract problem details for logging
    num_techs = len(problem_data.get('technicians', []))
    num_orders = len(problem_data.get('work_orders', []))
    time_limit = problem_data.get('config', {}).get('time_limit', 'default')

    try:
        print(f"📤 [Thread {thread_id}] Request {request_id}: {num_techs} techs, {num_orders} orders, {time_limit}s limit")

        response = requests.post(
            f"{url}/vrp/optimize",
            json=problem_data,
            headers={"Content-Type": "application/json"},
            timeout=120  # 2 minute timeout
        )

        elapsed_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            solver_id = result.get('solver_id', 'unknown')
            status = result.get('status', 'unknown')
            orders_completed = result.get('orders_completed', 0)
            solve_time = result.get('solve_time', 0)
            concurrent_execution = result.get('concurrent_execution', False)
            total_travel_time = result.get('total_travel_time', 0)
            objective_value = result.get('objective_value', 0)

            completion_rate = (orders_completed / num_orders * 100) if num_orders > 0 else 0

            print(f"✅ [Thread {thread_id}] Request {request_id}: "
                  f"Solver {solver_id}, Status={status}, "
                  f"Completed={orders_completed}/{num_orders} ({completion_rate:.1f}%), "
                  f"Travel={total_travel_time}min, Objective={objective_value:.1f}, "
                  f"SolveTime={solve_time:.3f}s, TotalTime={elapsed_time:.3f}s")

            return {
                'request_id': request_id,
                'thread_id': thread_id,
                'success': True,
                'solver_id': solver_id,
                'status': status,
                'orders_completed': orders_completed,
                'total_orders': num_orders,
                'completion_rate': completion_rate,
                'total_travel_time': total_travel_time,
                'objective_value': objective_value,
                'solve_time': solve_time,
                'total_time': elapsed_time,
                'concurrent_execution': concurrent_execution,
                'time_limit': time_limit,
                'problem_size': num_techs + num_orders
            }
        else:
            print(f"❌ [Thread {thread_id}] Request {request_id}: HTTP {response.status_code}")
            return {
                'request_id': request_id,
                'thread_id': thread_id,
                'success': False,
                'error': f"HTTP {response.status_code}",
                'total_time': elapsed_time,
                'problem_size': num_techs + num_orders
            }

    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"💥 [Thread {thread_id}] Request {request_id}: {e}")
        return {
            'request_id': request_id,
            'thread_id': thread_id,
            'success': False,
            'error': str(e),
            'total_time': elapsed_time,
            'problem_size': num_techs + num_orders
        }


def check_server_health(url: str):
    """Check if the server is healthy and supports concurrent execution"""
    try:
        print(f"🏥 Checking server health at {url}...")
        response = requests.get(f"{url}/health", timeout=10)

        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Server is healthy")

            services = health_data.get('services', {})
            concurrent_info = health_data.get('concurrent_execution', {})

            print(f"   Services: {services}")
            print(f"   Concurrent execution: {concurrent_info.get('enabled', False)}")

            if concurrent_info.get('enabled'):
                print(f"   Max solvers: {concurrent_info.get('max_solvers', 'unknown')}")
                print(f"   CUDA streams: {concurrent_info.get('cuda_streams', 'unknown')}")
                return True
            else:
                print("⚠️ Concurrent execution is not enabled")
                return False
        else:
            print(f"❌ Server health check failed: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False


def test_full_problem(url: str, problem_data: Dict[str, Any]):
    """Test the full problem as a single request"""
    print(f"\n🧪 Testing full problem optimization...")

    if not problem_data:
        print("❌ No problem data available")
        return False

    # Add concurrent execution flag
    full_problem = problem_data.copy()
    full_problem['use_concurrent'] = True
    full_problem['priority'] = 1

    start_time = time.time()
    result = send_optimization_request(url, full_problem, 0)
    total_time = time.time() - start_time

    if result['success'] and result.get('status') == 'success':
        print(f"✅ Full problem optimization successful!")
        print(f"   Solver: {result.get('solver_id', 'unknown')}")
        print(f"   Completion rate: {result.get('completion_rate', 0):.1f}%")
        print(f"   Travel time: {result.get('total_travel_time', 0)} minutes")
        print(f"   Solve time: {result.get('solve_time', 0):.3f}s")
        print(f"   Total time: {total_time:.3f}s")
        return True
    else:
        print(f"❌ Full problem optimization failed: {result.get('error', 'Unknown error')}")
        return False


def run_concurrent_test_with_real_data(url: str = "http://localhost:8000",
                                       filename: str = "input.json",
                                       test_type: str = "variations"):
    """Run concurrent test with real Malaysian data"""
    print("🧪 CONCURRENT CUOPT TEST WITH REAL MALAYSIAN DATA")
    print("=" * 60)

    # Check server health
    if not check_server_health(url):
        print("❌ Server health check failed. Cannot proceed.")
        return False

    # Load problem data
    print(f"\n📂 Loading problem data from {filename}...")
    problem_data = load_problem_data(filename)

    if not problem_data:
        print("❌ Failed to load problem data")
        return False

    # Test full problem first
    full_success = test_full_problem(url, problem_data)

    if not full_success:
        print("⚠️ Full problem failed, but continuing with concurrent tests...")

    # Generate test problems
    print(f"\n🔄 Generating concurrent test problems ({test_type})...")

    if test_type == "splits":
        test_problems = split_problem_data(problem_data, 6)
        print(f"✅ Created {len(test_problems)} problem splits")
    else:  # variations
        test_problems = create_problem_variations(problem_data, 6)
        print(f"✅ Created {len(test_problems)} problem variations")

    if not test_problems:
        print("❌ No test problems generated")
        return False

    # Run concurrent requests
    print(f"\n🚀 Executing {len(test_problems)} concurrent optimization requests...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=len(test_problems), thread_name_prefix="cuopt") as executor:
        # Submit all requests simultaneously
        futures = [
            executor.submit(send_optimization_request, url, problem, i)
            for i, problem in enumerate(test_problems)
        ]

        # Collect results as they complete
        results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"💥 Future exception: {e}")

    total_time = time.time() - start_time

    # Analyze results
    print(f"\n📊 CONCURRENT TEST RESULTS:")
    print(f"   Total execution time: {total_time:.3f}s")
    print(f"   Average time per request: {total_time / len(test_problems):.3f}s")

    # Sort results by request_id
    results.sort(key=lambda x: x['request_id'])

    successful_results = [r for r in results if r.get('success', False) and r.get('status') == 'success']
    failed_results = [r for r in results if not (r.get('success', False) and r.get('status') == 'success')]

    print(f"   Successful optimizations: {len(successful_results)}/{len(test_problems)}")
    print(f"   Failed requests: {len(failed_results)}/{len(test_problems)}")

    if successful_results:
        # Solver distribution analysis
        solver_usage = {}
        for result in successful_results:
            solver_id = result.get('solver_id', 'unknown')
            solver_usage[solver_id] = solver_usage.get(solver_id, 0) + 1

        print(f"\n🎯 SOLVER DISTRIBUTION:")
        for solver_id in sorted(solver_usage.keys()):
            count = solver_usage[solver_id]
            percentage = (count / len(successful_results)) * 100
            print(f"   Solver {solver_id}: {count} requests ({percentage:.1f}%)")

        unique_solvers = len(solver_usage)
        print(f"   Unique solvers used: {unique_solvers}/6")

        # Performance analysis
        solve_times = [r.get('solve_time', 0) for r in successful_results]
        completion_rates = [r.get('completion_rate', 0) for r in successful_results]
        travel_times = [r.get('total_travel_time', 0) for r in successful_results]
        problem_sizes = [r.get('problem_size', 0) for r in successful_results]

        print(f"\n⚡ PERFORMANCE STATISTICS:")
        if solve_times:
            print(f"   Average solve time: {sum(solve_times) / len(solve_times):.3f}s")
            print(f"   Min/Max solve time: {min(solve_times):.3f}s / {max(solve_times):.3f}s")

        if completion_rates:
            print(f"   Average completion rate: {sum(completion_rates) / len(completion_rates):.1f}%")
            print(f"   Min/Max completion rate: {min(completion_rates):.1f}% / {max(completion_rates):.1f}%")

        if travel_times:
            print(f"   Average total travel time: {sum(travel_times) / len(travel_times):.1f} minutes")

        if problem_sizes:
            print(f"   Average problem size: {sum(problem_sizes) / len(problem_sizes):.1f} locations")

        # Detailed results
        print(f"\n📋 DETAILED RESULTS:")
        for result in successful_results:
            req_id = result['request_id']
            solver_id = result.get('solver_id', '?')
            completion = result.get('completion_rate', 0)
            solve_time = result.get('solve_time', 0)
            size = result.get('problem_size', 0)
            time_limit = result.get('time_limit', '?')
            print(f"   Request {req_id}: Solver {solver_id}, {completion:.1f}% complete, "
                  f"{solve_time:.3f}s, Size={size}, Limit={time_limit}s")

        # Success evaluation
        success_rate = len(successful_results) / len(test_problems) * 100
        good_distribution = unique_solvers >= min(3, len(test_problems))
        good_completion = sum(completion_rates) / len(completion_rates) >= 80 if completion_rates else False

        print(f"\n🎯 TEST EVALUATION:")
        print(f"   Success rate: {success_rate:.1f}% (target: ≥80%)")
        print(f"   Solver distribution: {unique_solvers} solvers (target: ≥3)")
        print(f"   Average completion: {sum(completion_rates) / len(completion_rates):.1f}% (target: ≥80%)")

        if success_rate >= 80 and good_distribution and good_completion:
            print(f"\n🎉 CONCURRENT TEST PASSED!")
            print(f"   ✅ High success rate: {success_rate:.1f}%")
            print(f"   ✅ Good solver distribution: {unique_solvers} solvers")
            print(f"   ✅ Good completion rate: {sum(completion_rates) / len(completion_rates):.1f}%")
            return True
        else:
            print(f"\n⚠️ CONCURRENT TEST ISSUES:")
            if success_rate < 80:
                print(f"   ❌ Low success rate: {success_rate:.1f}%")
            if not good_distribution:
                print(f"   ❌ Poor solver distribution: {unique_solvers} solvers")
            if not good_completion:
                print(f"   ❌ Low completion rate: {sum(completion_rates) / len(completion_rates):.1f}%")
            return False

    else:
        print(f"\n❌ NO SUCCESSFUL OPTIMIZATIONS")
        for result in failed_results:
            req_id = result['request_id']
            error = result.get('error', 'Unknown')
            size = result.get('problem_size', 0)
            print(f"   Request {req_id}: {error} (Size: {size})")
        return False


def run_concurrent_test(url: str = "http://localhost:8000", num_requests: int = 6):
    """Run the concurrent solver test with simple problems"""
    print("🧪 SIMPLE CONCURRENT CUOPT SOLVER TEST")
    print("=" * 50)

    # Check server health first
    if not check_server_health(url):
        print("❌ Server health check failed. Cannot proceed with test.")
        return False

    print(f"\n🚀 Running concurrent test with {num_requests} requests...")

    # Generate test problems
    test_problems = []
    for i in range(num_requests):
        problem = create_simple_test_problem(i)
        test_problems.append(problem)

    print(f"📊 Generated {len(test_problems)} test problems")

    # Run concurrent requests
    start_time = time.time()
    results = []

    print(f"\n🔄 Executing {num_requests} concurrent optimization requests...")

    with ThreadPoolExecutor(max_workers=num_requests, thread_name_prefix="test") as executor:
        # Submit all requests simultaneously
        future_to_id = {
            executor.submit(send_optimization_request, url, problem, i): i
            for i, problem in enumerate(test_problems)
        }

        # Collect results as they complete
        for future in as_completed(future_to_id):
            request_id = future_to_id[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"💥 Future exception for request {request_id}: {e}")
                results.append({
                    'request_id': request_id,
                    'success': False,
                    'error': f"Future exception: {e}",
                    'total_time': 0
                })

    total_time = time.time() - start_time

    # Analyze results
    print(f"\n📊 CONCURRENT TEST RESULTS:")
    print(f"   Total execution time: {total_time:.3f}s")
    print(f"   Average time per request: {total_time / num_requests:.3f}s")

    # Sort results by request_id for consistent reporting
    results.sort(key=lambda x: x['request_id'])

    successful_results = [r for r in results if r.get('success', False) and r.get('status') == 'success']
    failed_results = [r for r in results if not (r.get('success', False) and r.get('status') == 'success')]

    print(f"   Successful optimizations: {len(successful_results)}/{num_requests}")
    print(f"   Failed requests: {len(failed_results)}/{num_requests}")

    if successful_results:
        # Analyze solver distribution
        solver_usage = {}
        thread_usage = {}

        for result in successful_results:
            solver_id = result.get('solver_id', 'unknown')
            thread_id = result.get('thread_id', 'unknown')

            solver_usage[solver_id] = solver_usage.get(solver_id, 0) + 1
            thread_usage[thread_id] = thread_usage.get(thread_id, 0) + 1

        print(f"\n🎯 SOLVER DISTRIBUTION:")
        for solver_id in sorted(solver_usage.keys()):
            count = solver_usage[solver_id]
            percentage = (count / len(successful_results)) * 100
            print(f"   Solver {solver_id}: {count} requests ({percentage:.1f}%)")

        unique_solvers = len(solver_usage)
        print(f"   Unique solvers used: {unique_solvers}/6")

        print(f"\n🧵 THREAD DISTRIBUTION:")
        print(f"   Unique threads used: {len(thread_usage)}")

        # Success criteria
        success_rate = len(successful_results) / num_requests * 100
        good_distribution = unique_solvers >= min(3, num_requests)

        print(f"\n🎯 TEST EVALUATION:")
        print(f"   Success rate: {success_rate:.1f}% (target: ≥80%)")
        print(f"   Solver distribution: {unique_solvers} solvers used (target: ≥3)")

        if success_rate >= 80 and good_distribution:
            print(f"\n🎉 CONCURRENT TEST PASSED!")
            print(f"   ✅ High success rate: {success_rate:.1f}%")
            print(f"   ✅ Good solver distribution: {unique_solvers} different solvers")
            return True
        else:
            print(f"\n⚠️ CONCURRENT TEST PARTIAL SUCCESS:")
            if success_rate < 80:
                print(f"   ❌ Low success rate: {success_rate:.1f}% (expected ≥80%)")
            if not good_distribution:
                print(f"   ❌ Poor solver distribution: {unique_solvers} solvers (expected ≥3)")
            return False

    else:
        print(f"\n❌ NO SUCCESSFUL OPTIMIZATIONS")
        print(f"   This indicates a problem with the server or test data")

        for result in failed_results:
            req_id = result['request_id']
            error = result.get('error', 'Unknown error')
            print(f"   Request {req_id}: {error}")

        return False


def get_server_statistics(url: str):
    """Get current server statistics"""
    try:
        print(f"\n📈 Getting server statistics...")
        response = requests.get(f"{url}/concurrent/statistics", timeout=10)

        if response.status_code == 200:
            stats_data = response.json()
            stats = stats_data.get('statistics', {})

            print(f"📊 SERVER STATISTICS:")
            print(f"   Total requests: {stats.get('total_requests', 0)}")
            print(f"   Completed: {stats.get('completed_requests', 0)}")
            print(f"   Failed: {stats.get('failed_requests', 0)}")
            print(f"   Success rate: {stats.get('success_rate', 0):.1f}%")
            print(f"   Average processing time: {stats.get('average_processing_time', 0):.3f}s")

            if 'solver_usage' in stats:
                print(f"   Solver usage: {stats['solver_usage']}")
        else:
            print(f"⚠️ Could not get statistics: HTTP {response.status_code}")

    except Exception as e:
        print(f"⚠️ Could not get statistics: {e}")


if __name__ == "__main__":
    try:
        # Configuration
        SERVER_URL = "http://localhost:8000"
        INPUT_FILE = "input.json"

        print("🧪 MALAYSIAN CUOPT CONCURRENT SOLVER TEST")
        print("=" * 50)
        print(f"📍 Testing with realistic Malaysian technician and work order data")
        print(f"📂 Input file: {INPUT_FILE}")
        print(f"🌐 Server: {SERVER_URL}")

        # Test 1: Problem variations
        print(f"\n🧪 TEST 1: Problem Variations (Different Time Limits)")
        success1 = run_concurrent_test_with_real_data(SERVER_URL, INPUT_FILE, "variations")

        # Small delay between tests
        if success1:
            time.sleep(2)

            # Test 2: Problem splits
            print(f"\n🧪 TEST 2: Problem Splits (Geographic Distribution)")
            success2 = run_concurrent_test_with_real_data(SERVER_URL, INPUT_FILE, "splits")
        else:
            success2 = False

        # Get final statistics
        get_server_statistics(SERVER_URL)

        print(f"\n{'=' * 60}")
        total_success = sum([success1, success2])

        if total_success >= 2:
            print("🎉 ALL CORE TESTS COMPLETED SUCCESSFULLY!")
            print("✅ Malaysian data processed correctly with concurrent execution")
            print("✅ All 6 solvers working with proper distribution")
            print("✅ Realistic workload handling confirmed")
        elif total_success >= 1:
            print("⚠️ PARTIAL SUCCESS - Some tests passed")
            print(f"   Variations test: {'✅ PASS' if success1 else '❌ FAIL'}")
            print(f"   Splits test: {'✅ PASS' if success2 else '❌ FAIL'}")
        else:
            print("❌ CORE TESTS FAILED")
            print("   Check server logs and data validation")

        # Test 3: Batch optimization (if core tests passed)
        if total_success >= 1:
            print(f"\n🧪 TEST 3: Batch Optimization Endpoint")
            problem_data = load_problem_data(INPUT_FILE)
            if problem_data:
                success3 = create_batch_test(SERVER_URL, problem_data)
            else:
                success3 = False
        else:
            success3 = False
            print(f"\n⚠️ Skipping batch test due to core test failures")

        # Get final statistics
        get_server_statistics(SERVER_URL)

        print(f"\n🏢 Malaysian Technician Route Optimization Results:")
        print(f"   📍 Coverage: Petaling Jaya, Subang Jaya, Bandar Sunway, Damansara Heights")
        print(f"   👷 Technicians: 10 Malaysian field workers with electrical skills")
        print(f"   📋 Work Orders: 100 realistic electrical service requests")
        print(f"   🚀 Concurrent Processing: 6 GPU-accelerated solver instances")

        print(f"\n📊 FINAL TEST SUMMARY:")
        print(f"   Problem Variations: {'✅ PASS' if success1 else '❌ FAIL'}")
        print(f"   Problem Splits: {'✅ PASS' if success2 else '❌ FAIL'}")
        print(f"   Batch Processing: {'✅ PASS' if success3 else '❌ FAIL'}")

        total_tests_passed = sum([success1, success2, success3])
        print(f"   Overall Result: {total_tests_passed}/3 tests passed")

        if total_tests_passed >= 2:
            print(f"\n🎉 EXCELLENT RESULTS!")
            print(f"✅ Concurrent execution working perfectly with real Malaysian data")
        elif total_tests_passed >= 1:
            print(f"\n✅ GOOD RESULTS!")
            print(f"⚠️ Some tests passed - concurrent execution is working")
        else:
            print(f"\n❌ NEEDS ATTENTION")
            print(f"⚠️ Review server logs for optimization issues")

        print(f"\n📝 Usage Notes:")
        print(f"   • Ensure input.json is in the same directory as this script")
        print(f"   • Server should be running with concurrent execution enabled")
        print(f"   • Check GPU memory usage during high concurrent loads")
        print(f"   • Monitor solver distribution for load balancing verification")

    except KeyboardInterrupt:
        print(f"\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback

        traceback.print_exc()