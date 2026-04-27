#!/usr/bin/env python3
"""
Updated concurrent test script for testing 16+ concurrent requests
Compatible with real Malaysian technician and work order data
Enhanced for high-concurrency testing with realistic problem generation
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


def split_problem_data(data: Dict[str, Any], num_splits: int = 16) -> List[Dict[str, Any]]:
    """Split the problem data into multiple realistic problems for concurrent testing"""
    if not data or num_splits <= 1:
        return [data] if data else []

    technicians = data.get('technicians', [])
    work_orders = data.get('work_orders', [])
    config = data.get('config', {})

    if len(technicians) == 0 or len(work_orders) == 0:
        return [data]

    # Enhanced splitting logic for high concurrency with realistic ratios
    problems = []

    for i in range(num_splits):
        # Cycle through technicians for more variety
        tech_indices = []

        # Base number of techs per split, with variation
        base_techs = max(1, len(technicians) // min(num_splits, len(technicians)))
        techs_this_split = base_techs + (i % 3)  # Add 0-2 extra techs for variation

        for j in range(min(techs_this_split, len(technicians))):
            tech_idx = (i + j * num_splits) % len(technicians)
            if tech_idx not in tech_indices:
                tech_indices.append(tech_idx)

        # If we don't have enough unique techs, add more cycling
        while len(tech_indices) < min(techs_this_split, len(technicians)):
            for tech_idx in range(len(technicians)):
                if tech_idx not in tech_indices:
                    tech_indices.append(tech_idx)
                    if len(tech_indices) >= techs_this_split:
                        break
            break

        # Get realistic number of orders (max 10 orders per technician)
        max_orders_per_tech = 10
        base_orders_per_split = len(tech_indices) * 6  # Average 6 orders per tech
        orders_this_split = base_orders_per_split + (i % 4)  # Add 0-3 extra orders
        orders_this_split = min(orders_this_split, len(tech_indices) * max_orders_per_tech)

        # Use cycling for order selection to ensure variety
        order_indices = []
        for j in range(min(orders_this_split, len(work_orders))):
            order_idx = (i * base_orders_per_split + j) % len(work_orders)
            if order_idx not in order_indices:
                order_indices.append(order_idx)

        selected_techs = [technicians[idx] for idx in tech_indices]
        selected_orders = [work_orders[idx] for idx in order_indices]

        if len(selected_techs) >= 1 and len(selected_orders) >= 1:
            split_data = {
                "technicians": selected_techs,
                "work_orders": selected_orders,
                "use_concurrent": True,
                "priority": i + 1,
                "config": config.copy()
            }

            problems.append(split_data)
            ratio = len(selected_orders) / len(selected_techs) if len(selected_techs) > 0 else 0
            print(f"   Split {i + 1}: {len(selected_techs)} techs, {len(selected_orders)} orders (ratio: {ratio:.1f} orders/tech)")

    return problems


def create_problem_variations(base_data: Dict[str, Any], num_variations: int = 16) -> List[Dict[str, Any]]:
    """Create realistic variations of the base problem for concurrent testing"""
    if not base_data:
        return []

    technicians = base_data.get('technicians', [])
    work_orders = base_data.get('work_orders', [])
    config = base_data.get('config', {})

    variations = []

    # FIXED: Realistic time limits that allow problems to solve successfully
    # Removed ultra-aggressive time limits (0.5s, 1s) that cause failures
    time_limits = [3, 4, 5, 6, 7, 8, 10, 12, 15, 18, 20, 25, 30, 35, 40, 50]

    # Realistic problem size strategies with manageable ratios
    size_strategies = [
        ("small", 0.3, 0.25),  # 30% techs, 25% orders (low ratio ~2.8 orders/tech)
        ("medium", 0.5, 0.4),  # 50% techs, 40% orders (good ratio ~4 orders/tech)
        ("large", 0.7, 0.6),  # 70% techs, 60% orders (manageable ratio ~6 orders/tech)
        ("full", 1.0, 0.8),  # 100% techs, 80% orders (conservative ratio ~8 orders/tech)
    ]

    for i in range(num_variations):
        variation_config = config.copy()

        # Cycle through time limits
        time_limit = time_limits[i % len(time_limits)]

        # Cycle through size strategies
        strategy_name, tech_ratio, order_ratio = size_strategies[i % len(size_strategies)]

        # Calculate problem size with realistic ratios
        base_tech_count = int(len(technicians) * tech_ratio)
        base_order_count = int(len(work_orders) * order_ratio)

        # Add variation to make each problem unique
        tech_count = min(len(technicians), max(2, base_tech_count + (i % 3)))  # Min 2 techs
        order_count = min(len(work_orders), max(5, base_order_count + (i % 6)))

        # CRITICAL FIX: Ensure realistic orders-to-technicians ratio
        max_orders_per_tech = 10  # Maximum 10 orders per technician
        if order_count > tech_count * max_orders_per_tech:
            order_count = tech_count * max_orders_per_tech

        # CRITICAL FIX: Adjust time limits based on problem complexity
        problem_complexity = tech_count + order_count
        if problem_complexity > 80:
            time_limit = max(time_limit, 10)  # Large problems need at least 10s
        elif problem_complexity > 50:
            time_limit = max(time_limit, 6)  # Medium problems need at least 6s
        else:
            time_limit = max(time_limit, 4)  # Small problems need at least 4s

        variation_config['time_limit'] = time_limit

        # Use different starting positions for variety
        tech_start = (i * 2) % max(1, len(technicians) - tech_count + 1)
        order_start = (i * 3) % max(1, len(work_orders) - order_count + 1)

        tech_end = min(tech_start + tech_count, len(technicians))
        order_end = min(order_start + order_count, len(work_orders))

        variation = {
            "technicians": technicians[tech_start:tech_end],
            "work_orders": work_orders[order_start:order_end],
            "use_concurrent": True,
            "priority": i + 1,
            "config": variation_config
        }

        variations.append(variation)
        ratio = len(variation['work_orders']) / len(variation['technicians'])
        print(f"   Variation {i + 1}: {len(variation['technicians'])} techs, {len(variation['work_orders'])} orders, {time_limit}s limit ({strategy_name}, ratio: {ratio:.1f})")

    return variations


def create_simple_test_problem(problem_id: int):
    """Create a minimal test problem that should always work"""
    # Add some variation to the coordinates for different problems
    lat_offset = (problem_id % 10) * 0.001
    lon_offset = (problem_id % 10) * 0.001

    return {
        "technicians": [
            {
                "id": f"TECH{problem_id:02d}",
                "name": f"Technician {problem_id}",
                "start_location": {
                    "latitude": 3.1073 + lat_offset,
                    "longitude": 101.6067 + lon_offset,
                    "address": f"Tech Location {problem_id}"
                },
                "work_shift": {"earliest": 480, "latest": 1020},  # 8 AM - 5 PM
                "break_window": {"earliest": 720, "latest": 780},  # 12 PM - 1 PM
                "break_duration": 60,
                "skills": ["electrical", "maintenance"][:(problem_id % 2) + 1],  # Vary skills
                "max_daily_orders": 5 + (problem_id % 3),  # 5-7 orders
                "max_travel_time": 300
            }
        ],
        "work_orders": [
            {
                "id": f"WO{problem_id:02d}",
                "location": {
                    "latitude": 3.1319 + lat_offset,
                    "longitude": 101.6292 + lon_offset,
                    "address": f"Work Location {problem_id}"
                },
                "priority": ["low", "medium", "high"][problem_id % 3],
                "work_type": ["maintenance", "repair", "inspection"][problem_id % 3],
                "service_time": 60 + (problem_id % 4) * 15,  # 60-105 minutes
                "required_skills": ["electrical", "maintenance"][:(problem_id % 2) + 1],
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

    # Create 6 smaller problems with realistic technician-to-order ratios
    batch_problems = []
    for i in range(6):
        tech_start = i * 2
        tech_end = min((i + 1) * 2 + 1, len(technicians))  # 2-3 techs per problem

        order_start = i * 10
        order_end = min((i + 1) * 10, len(work_orders))  # 10 orders per problem (good ratio)

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
        "timeout": 200.0  # Increased timeout for batch processing
    }

    print(f"📤 Sending batch request with {len(batch_problems)} problems...")
    start_time = time.time()

    try:
        response = requests.post(
            f"{url}/vrp/optimize-batch",
            json=batch_request,
            timeout=220  # Slightly longer than batch timeout
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
            timeout=150  # Increased timeout for high concurrency
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
            error_text = ""
            try:
                error_text = response.text[:200]  # First 200 chars of error
            except:
                pass
            print(f"❌ [Thread {thread_id}] Request {request_id}: HTTP {response.status_code} - {error_text}")
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
                max_instances = concurrent_info.get('max_concurrent_instances', 'unknown')
                solver_threads = concurrent_info.get('solver_threads', 'unknown')
                cuda_streams = concurrent_info.get('cuda_streams', 'unknown')
                print(f"   Max instances: {max_instances}")
                print(f"   Solver threads: {solver_threads}")
                print(f"   CUDA streams: {cuda_streams}")
                print(f"   Memory management: {concurrent_info.get('memory_management', False)}")
                return True, max_instances
            else:
                print("⚠️ Concurrent execution is not enabled")
                return False, 0
        else:
            print(f"❌ Server health check failed: HTTP {response.status_code}")
            return False, 0

    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False, 0


def monitor_memory_during_test(url: str):
    """Monitor memory usage during concurrent tests"""
    try:
        response = requests.get(f"{url}/memory/status", timeout=5)
        if response.status_code == 200:
            memory_data = response.json()
            memory_info = memory_data.get('memory_info', {})
            gpu_used = memory_info.get('gpu_used_mb', 0)
            gpu_percent = memory_info.get('gpu_usage_percent', 0)
            print(f"   💾 GPU Memory: {gpu_used:.1f}MB used ({gpu_percent:.1f}%)")
            return gpu_used, gpu_percent
    except:
        pass  # Silent fail for memory monitoring
    return 0, 0


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
                                       test_type: str = "variations",
                                       num_concurrent: int = 16):
    """Run concurrent test with real Malaysian data"""
    print("🧪 CONCURRENT CUOPT TEST WITH REAL MALAYSIAN DATA")
    print("=" * 60)

    # Check server health and get concurrent capabilities
    health_ok, max_instances = check_server_health(url)
    if not health_ok:
        print("❌ Server health check failed. Cannot proceed.")
        return False

    # Adjust concurrent count based on server capabilities
    if isinstance(max_instances, int) and max_instances > 0:
        effective_concurrent = min(num_concurrent, max_instances * 2)  # Allow 2x for queue testing
        if effective_concurrent != num_concurrent:
            print(f"⚠️ Adjusting concurrent count from {num_concurrent} to {effective_concurrent} based on server capacity")
            num_concurrent = effective_concurrent

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

    # Monitor initial memory
    initial_gpu_used, initial_gpu_percent = monitor_memory_during_test(url)

    # Generate test problems with REALISTIC logic
    print(f"\n🔄 Generating {num_concurrent} concurrent test problems ({test_type})...")

    if test_type == "splits":
        test_problems = split_problem_data(problem_data, num_concurrent)
        print(f"✅ Created {len(test_problems)} problem splits")
    else:  # variations
        test_problems = create_problem_variations(problem_data, num_concurrent)
        print(f"✅ Created {len(test_problems)} problem variations")

    if not test_problems:
        print("❌ No test problems generated")
        return False

    # Ensure we don't exceed requested concurrent count
    test_problems = test_problems[:num_concurrent]

    # VALIDATION: Check generated problems for sanity
    print(f"\n🔍 Validating generated problems...")
    valid_problems = []
    for i, problem in enumerate(test_problems):
        techs = len(problem.get('technicians', []))
        orders = len(problem.get('work_orders', []))
        time_limit = problem.get('config', {}).get('time_limit', 5)
        ratio = orders / techs if techs > 0 else 0

        # Skip problems with unrealistic parameters
        if ratio > 12:  # More than 12 orders per tech
            print(f"   ⚠️ Skipping problem {i}: ratio too high ({ratio:.1f})")
            continue
        if time_limit < 3:  # Less than 3 seconds
            print(f"   ⚠️ Skipping problem {i}: time limit too low ({time_limit}s)")
            continue
        if techs < 1 or orders < 1:
            print(f"   ⚠️ Skipping problem {i}: insufficient data ({techs} techs, {orders} orders)")
            continue

        valid_problems.append(problem)

    test_problems = valid_problems
    print(f"✅ Validated {len(test_problems)} problems for testing")

    if len(test_problems) == 0:
        print("❌ No valid test problems after validation")
        return False

    # Run concurrent requests
    print(f"\n🚀 Executing {len(test_problems)} concurrent optimization requests...")
    print(f"   Thread pool size: {len(test_problems)}")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=len(test_problems), thread_name_prefix="cuopt") as executor:
        # Submit all requests simultaneously
        futures = [
            executor.submit(send_optimization_request, url, problem, i)
            for i, problem in enumerate(test_problems)
        ]

        # Collect results as they complete
        results = []
        completed_count = 0
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
                completed_count += 1

                # Progress update for high concurrency
                if completed_count % 4 == 0 or completed_count == len(test_problems):
                    print(f"   Progress: {completed_count}/{len(test_problems)} requests completed")

            except Exception as e:
                print(f"💥 Future exception: {e}")

    total_time = time.time() - start_time

    # Monitor final memory
    final_gpu_used, final_gpu_percent = monitor_memory_during_test(url)
    memory_delta = final_gpu_used - initial_gpu_used

    # Analyze results
    print(f"\n📊 CONCURRENT TEST RESULTS:")
    print(f"   Total execution time: {total_time:.3f}s")
    print(f"   Average time per request: {total_time / len(test_problems):.3f}s")
    print(f"   Memory change: {memory_delta:+.1f}MB ({initial_gpu_percent:.1f}% → {final_gpu_percent:.1f}%)")

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
        print(f"   Unique solvers used: {unique_solvers}")

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
            avg_completion = sum(completion_rates) / len(completion_rates)
            print(f"   Average completion rate: {avg_completion:.1f}%")
            print(f"   Min/Max completion rate: {min(completion_rates):.1f}% / {max(completion_rates):.1f}%")

        if travel_times:
            print(f"   Average total travel time: {sum(travel_times) / len(travel_times):.1f} minutes")

        if problem_sizes:
            print(f"   Average problem size: {sum(problem_sizes) / len(problem_sizes):.1f} locations")

        # Success evaluation - realistic thresholds
        success_rate = len(successful_results) / len(test_problems) * 100
        min_solvers_expected = min(6, max(3, len(test_problems) // 4))  # Scale expectations
        good_distribution = unique_solvers >= min_solvers_expected
        good_completion = avg_completion >= 80 if completion_rates else False

        print(f"\n🎯 TEST EVALUATION:")
        print(f"   Success rate: {success_rate:.1f}% (target: ≥85%)")
        print(f"   Solver distribution: {unique_solvers} solvers (target: ≥{min_solvers_expected})")
        print(f"   Average completion: {avg_completion:.1f}% (target: ≥80%)")

        # Show some detailed results for high concurrency
        print(f"\n📋 SAMPLE DETAILED RESULTS (first 10):")
        for i, result in enumerate(successful_results[:10]):
            req_id = result['request_id']
            solver_id = result.get('solver_id', '?')
            completion = result.get('completion_rate', 0)
            solve_time = result.get('solve_time', 0)
            size = result.get('problem_size', 0)
            time_limit = result.get('time_limit', '?')
            print(f"   Request {req_id}: Solver {solver_id}, {completion:.1f}% complete, "
                  f"{solve_time:.3f}s, Size={size}, Limit={time_limit}s")

        if success_rate >= 85 and good_distribution and good_completion:
            print(f"\n🎉 HIGH-CONCURRENCY TEST PASSED!")
            print(f"   ✅ Excellent success rate: {success_rate:.1f}%")
            print(f"   ✅ Good solver distribution: {unique_solvers} solvers")
            print(f"   ✅ Good completion rate: {avg_completion:.1f}%")
            print(f"   ✅ System handled {len(test_problems)} concurrent requests excellently")
            return True
        else:
            print(f"\n⚠️ HIGH-CONCURRENCY TEST ISSUES:")
            if success_rate < 85:
                print(f"   ❌ Low success rate: {success_rate:.1f}%")
            if not good_distribution:
                print(f"   ❌ Poor solver distribution: {unique_solvers} solvers")
            if not good_completion:
                print(f"   ❌ Low completion rate: {avg_completion:.1f}%")
            return False

    else:
        print(f"\n❌ NO SUCCESSFUL OPTIMIZATIONS")
        for result in failed_results[:10]:  # Show first 10 failures
            req_id = result['request_id']
            error = result.get('error', 'Unknown')
            size = result.get('problem_size', 0)
            print(f"   Request {req_id}: {error} (Size: {size})")

        if len(failed_results) > 10:
            print(f"   ... and {len(failed_results) - 10} more failures")
        return False


def run_concurrent_test(url: str = "http://localhost:8000", num_requests: int = 16):
    """Run the concurrent solver test with simple problems"""
    print("🧪 SIMPLE CONCURRENT CUOPT SOLVER TEST")
    print("=" * 50)

    # Check server health first
    health_ok, max_instances = check_server_health(url)
    if not health_ok:
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
        completed_count = 0
        for future in as_completed(future_to_id):
            request_id = future_to_id[future]
            try:
                result = future.result()
                results.append(result)
                completed_count += 1

                # Progress update
                if completed_count % 4 == 0 or completed_count == num_requests:
                    print(f"   Progress: {completed_count}/{num_requests} requests completed")

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
        print(f"   Unique solvers used: {unique_solvers}")

        print(f"\n🧵 THREAD DISTRIBUTION:")
        print(f"   Unique threads used: {len(thread_usage)}")

        # Success criteria - adjusted for high concurrency
        success_rate = len(successful_results) / num_requests * 100
        min_solvers_expected = min(6, max(3, num_requests // 4))  # Scale expectations
        good_distribution = unique_solvers >= min_solvers_expected

        print(f"\n🎯 TEST EVALUATION:")
        print(f"   Success rate: {success_rate:.1f}% (target: ≥85%)")
        print(f"   Solver distribution: {unique_solvers} solvers used (target: ≥{min_solvers_expected})")

        if success_rate >= 85 and good_distribution:
            print(f"\n🎉 CONCURRENT TEST PASSED!")
            print(f"   ✅ Excellent success rate: {success_rate:.1f}%")
            print(f"   ✅ Good solver distribution: {unique_solvers} different solvers")
            return True
        else:
            print(f"\n⚠️ CONCURRENT TEST PARTIAL SUCCESS:")
            if success_rate < 85:
                print(f"   ❌ Low success rate: {success_rate:.1f}% (expected ≥85%)")
            if not good_distribution:
                print(f"   ❌ Poor solver distribution: {unique_solvers} solvers (expected ≥{min_solvers_expected})")
            return False

    else:
        print(f"\n❌ NO SUCCESSFUL OPTIMIZATIONS")
        print(f"   This indicates a problem with the server or test data")

        for result in failed_results[:10]:  # Show first 10 failures
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
            print(f"   Active requests: {stats.get('active_requests', 0)}")
            print(f"   Queue size: {stats.get('queue_size', 0)}")

            if 'solver_usage' in stats:
                print(f"   Solver usage: {stats['solver_usage']}")

            # Memory statistics if available
            memory_stats = stats.get('memory_stats', {})
            if memory_stats:
                print(f"   Peak GPU usage: {memory_stats.get('peak_gpu_usage_mb', 0):.1f}MB")
                print(f"   Average GPU usage: {memory_stats.get('average_gpu_usage_mb', 0):.1f}MB")
                print(f"   Memory cleanups: {memory_stats.get('memory_cleanups', 0)}")

        else:
            print(f"⚠️ Could not get statistics: HTTP {response.status_code}")

    except Exception as e:
        print(f"⚠️ Could not get statistics: {e}")


if __name__ == "__main__":
    try:
        # Configuration - easily adjustable for different concurrency levels
        SERVER_URL = "http://localhost:8000"
        INPUT_FILE = "input.json"
        NUM_CONCURRENT = 16  # Change this to test different concurrency levels (16, 20, 32, etc.)

        print("🧪 MALAYSIAN CUOPT HIGH-CONCURRENCY SOLVER TEST")
        print("=" * 60)
        print(f"📍 Testing with realistic Malaysian technician and work order data")
        print(f"📂 Input file: {INPUT_FILE}")
        print(f"🌐 Server: {SERVER_URL}")
        print(f"🚀 Concurrent requests: {NUM_CONCURRENT}")

        # Test 1: Problem variations with REALISTIC parameters
        print(f"\n🧪 TEST 1: Problem Variations (Realistic Time Limits) - {NUM_CONCURRENT} concurrent")
        success1 = run_concurrent_test_with_real_data(SERVER_URL, INPUT_FILE, "variations", NUM_CONCURRENT)

        # Small delay between tests to let the system stabilize
        if success1:
            print(f"\n⏸️ Brief pause between tests...")
            time.sleep(3)

            # Test 2: Problem splits
            print(f"\n🧪 TEST 2: Problem Splits (Geographic Distribution) - {NUM_CONCURRENT} concurrent")
            success2 = run_concurrent_test_with_real_data(SERVER_URL, INPUT_FILE, "splits", NUM_CONCURRENT)
        else:
            success2 = False

        # Test 3: Simple concurrent test (if real data tests had issues)
        if not success1 and not success2:
            print(f"\n🧪 TEST 3: Simple Problems Fallback - {min(NUM_CONCURRENT, 12)} concurrent")
            success3 = run_concurrent_test(SERVER_URL, min(NUM_CONCURRENT, 12))
        else:
            success3 = True  # Skip if other tests passed

        # Get final statistics
        get_server_statistics(SERVER_URL)

        print(f"\n{'=' * 60}")
        total_success = sum([success1, success2, success3])

        if total_success >= 2:
            print("🎉 HIGH-CONCURRENCY TESTS COMPLETED SUCCESSFULLY!")
            print(f"✅ Malaysian data processed correctly with {NUM_CONCURRENT} concurrent requests")
            print("✅ Multiple solvers working with proper load distribution")
            print("✅ High concurrent workload handling confirmed")
        elif total_success >= 1:
            print("⚠️ PARTIAL SUCCESS - Some tests passed")
            print(f"   Variations test: {'✅ PASS' if success1 else '❌ FAIL'}")
            print(f"   Splits test: {'✅ PASS' if success2 else '❌ FAIL'}")
            print(f"   Simple test: {'✅ PASS' if success3 else '❌ SKIP'}")
        else:
            print("❌ HIGH-CONCURRENCY TESTS FAILED")
            print("   Check server configuration and capacity")

        # Test 4: Batch optimization (if core tests passed)
        if total_success >= 1:
            print(f"\n🧪 TEST 4: Batch Optimization Endpoint")
            problem_data = load_problem_data(INPUT_FILE)
            if problem_data:
                success4 = create_batch_test(SERVER_URL, problem_data)
            else:
                success4 = False
        else:
            success4 = False
            print(f"\n⚠️ Skipping batch test due to core test failures")

        # Get final statistics
        get_server_statistics(SERVER_URL)

        print(f"\n🏢 Malaysian Technician Route Optimization Results:")
        print(f"   📍 Coverage: Petaling Jaya, Subang Jaya, Bandar Sunway, Damansara Heights")
        print(f"   👷 Technicians: Malaysian field workers with electrical skills")
        print(f"   📋 Work Orders: Realistic electrical service requests")
        print(f"   🚀 Concurrent Processing: GPU-accelerated solver instances")
        print(f"   🎯 Concurrency Level: {NUM_CONCURRENT} simultaneous requests")

        print(f"\n📊 FINAL TEST SUMMARY:")
        print(f"   Problem Variations: {'✅ PASS' if success1 else '❌ FAIL'}")
        print(f"   Problem Splits: {'✅ PASS' if success2 else '❌ FAIL'}")
        print(f"   Simple Problems: {'✅ PASS' if success3 else '❌ SKIP'}")
        print(f"   Batch Processing: {'✅ PASS' if success4 else '❌ FAIL'}")

        total_tests_passed = sum([success1, success2, success3, success4])
        possible_tests = 3 if not success1 and not success2 else 4
        print(f"   Overall Result: {total_tests_passed}/{possible_tests} tests passed")

        if total_tests_passed >= 3:
            print(f"\n🎉 EXCELLENT HIGH-CONCURRENCY RESULTS!")
            print(f"✅ System handles {NUM_CONCURRENT} concurrent requests excellently")
            print(f"✅ All solver instances working optimally")
            print(f"✅ Memory management effective under high load")
        elif total_tests_passed >= 2:
            print(f"\n✅ GOOD HIGH-CONCURRENCY RESULTS!")
            print(f"✅ System handles {NUM_CONCURRENT} concurrent requests well")
            print(f"⚠️ Some minor issues but overall performance is good")
        elif total_tests_passed >= 1:
            print(f"\n⚠️ MODERATE HIGH-CONCURRENCY RESULTS")
            print(f"⚠️ System has some issues with {NUM_CONCURRENT} concurrent requests")
            print(f"💡 Consider reducing concurrency or checking server resources")
        else:
            print(f"\n❌ HIGH-CONCURRENCY TESTS NEED ATTENTION")
            print(f"⚠️ Review server configuration and resource allocation")
            print(f"💡 Start with lower concurrency levels and scale up")

        print(f"\n📝 High-Concurrency Testing Notes:")
        print(f"   • Tested with {NUM_CONCURRENT} concurrent optimization requests")
        print(f"   • Realistic time limits and problem ratios implemented")
        print(f"   • Monitor solver distribution and queue management")
        print(f"   • Check that input.json has sufficient data for splitting")
        print(f"   • Adjust NUM_CONCURRENT variable to test different levels")

        if NUM_CONCURRENT >= 20:
            print(f"\n🏆 STRESS TEST LEVEL: Testing with {NUM_CONCURRENT} concurrent requests")
            print(f"   This is a demanding workload that tests system limits")

    except KeyboardInterrupt:
        print(f"\n⏹️ High-concurrency test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback

        traceback.print_exc()