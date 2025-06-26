#!/usr/bin/env python3
"""
Debug script to find and test cuOpt library imports and functionality
"""

import sys
import pkgutil
import importlib
import traceback
from typing import Any, Dict, List


def print_header(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def check_installed_packages():
    """Check what cuOpt-related packages are installed"""
    print_header("INSTALLED cuOpt PACKAGES")

    cuopt_modules = []
    for importer, modname, ispkg in pkgutil.iter_modules():
        if 'cuopt' in modname.lower():
            cuopt_modules.append(modname)
            print(f"✅ Found module: {modname} (package: {ispkg})")

    if not cuopt_modules:
        print("❌ No cuOpt modules found")

    return cuopt_modules


def test_import_approaches():
    """Test different ways to import cuOpt"""
    print_header("TESTING IMPORT APPROACHES")

    import_tests = [
        # Direct imports
        ("import cuopt", "cuopt"),
        ("import cuopt_cu12", "cuopt_cu12"),
        ("import cuopt_server_cu12", "cuopt_server_cu12"),
        ("import cuopt_sh_client", "cuopt_sh_client"),

        # Routing module imports
        ("from cuopt import routing", "routing"),
        ("from cuopt_cu12 import routing", "routing"),
        ("import cuopt.routing", "cuopt.routing"),
        ("import cuopt_cu12.routing", "cuopt_cu12.routing"),

        # Alternative patterns
        ("from cuopt_cu12.routing import DataModel", "DataModel"),
        ("from cuopt_cu12.routing import Solve", "Solve"),
    ]

    successful_imports = {}

    for import_stmt, module_name in import_tests:
        try:
            # Clear any previous imports
            if module_name in sys.modules:
                del sys.modules[module_name]

            exec(import_stmt)
            module = eval(module_name)

            print(f"✅ SUCCESS: {import_stmt}")
            print(f"   Location: {getattr(module, '__file__', 'N/A')}")
            print(f"   Type: {type(module)}")

            # Store successful import
            successful_imports[module_name] = {
                'import_stmt': import_stmt,
                'module': module
            }

        except Exception as e:
            print(f"❌ FAILED: {import_stmt}")
            print(f"   Error: {str(e)}")

    return successful_imports


def explore_module_contents(successful_imports: Dict[str, Any]):
    """Explore the contents of successfully imported modules"""
    print_header("EXPLORING MODULE CONTENTS")

    for module_name, info in successful_imports.items():
        print(f"\n--- {module_name} ---")
        module = info['module']

        try:
            # Get module attributes
            attrs = [attr for attr in dir(module) if not attr.startswith('_')]
            print(f"Public attributes: {attrs[:10]}{'...' if len(attrs) > 10 else ''}")

            # Look for key cuOpt classes
            key_classes = ['DataModel', 'Solve', 'SolverSettings', 'routing']
            found_classes = {}

            for class_name in key_classes:
                if hasattr(module, class_name):
                    found_classes[class_name] = getattr(module, class_name)
                    print(f"✅ Found {class_name}: {type(found_classes[class_name])}")

            # If this is a routing module, explore further
            if 'routing' in module_name or hasattr(module, 'DataModel'):
                print(f"🔍 This looks like a routing module!")

                # Try to find version info
                if hasattr(module, '__version__'):
                    print(f"   Version: {module.__version__}")

                # Check for DataModel
                if hasattr(module, 'DataModel'):
                    print(f"   DataModel available: {module.DataModel}")

                # Check for Solve function
                if hasattr(module, 'Solve'):
                    print(f"   Solve function available: {module.Solve}")

        except Exception as e:
            print(f"❌ Error exploring {module_name}: {e}")


def test_cudf_integration():
    """Test cuDF integration which is required for cuOpt"""
    print_header("TESTING cuDF INTEGRATION")

    try:
        import cudf
        print(f"✅ cuDF imported successfully")
        print(f"   Version: {cudf.__version__}")
        print(f"   Location: {cudf.__file__}")

        # Test basic cuDF functionality
        test_df = cudf.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        print(f"✅ cuDF DataFrame creation works")
        print(f"   Test DataFrame shape: {test_df.shape}")

        return True

    except Exception as e:
        print(f"❌ cuDF test failed: {e}")
        print(f"   This is required for cuOpt to work")
        return False


def test_cuopt_functionality(successful_imports: Dict[str, Any]):
    """Test actual cuOpt functionality if possible"""
    print_header("TESTING cuOpt FUNCTIONALITY")

    # Look for a routing module
    routing_module = None
    for module_name, info in successful_imports.items():
        module = info['module']
        if hasattr(module, 'DataModel') and hasattr(module, 'Solve'):
            routing_module = module
            print(f"✅ Found usable routing module: {module_name}")
            break

    if not routing_module:
        print("❌ No usable routing module found")
        return False

    try:
        # Test DataModel creation
        print("🔍 Testing DataModel creation...")
        data_model = routing_module.DataModel(4, 2)  # 4 locations, 2 vehicles
        print("✅ DataModel created successfully")

        # Test basic matrix creation
        print("🔍 Testing matrix operations...")
        import cudf
        test_matrix = cudf.DataFrame([
            [0, 1, 2, 3],
            [1, 0, 1, 2],
            [2, 1, 0, 1],
            [3, 2, 1, 0]
        ])
        data_model.add_cost_matrix(test_matrix)
        print("✅ Cost matrix added successfully")

        # Test solver settings
        if hasattr(routing_module, 'SolverSettings'):
            print("🔍 Testing SolverSettings...")
            settings = routing_module.SolverSettings()
            settings.set_time_limit(10)
            print("✅ SolverSettings created successfully")

        print("🎉 cuOpt appears to be working correctly!")
        return True

    except Exception as e:
        print(f"❌ cuOpt functionality test failed: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        return False


def provide_usage_guidance(successful_imports: Dict[str, Any], cuopt_working: bool):
    """Provide guidance on how to use cuOpt in the application"""
    print_header("USAGE GUIDANCE")

    if cuopt_working:
        print("🎉 cuOpt is working! Here's how to use it in your application:")

        # Find the best import
        for module_name, info in successful_imports.items():
            module = info['module']
            if hasattr(module, 'DataModel') and hasattr(module, 'Solve'):
                print(f"\n✅ Recommended import for your solver:")
                print(f"   {info['import_stmt']}")
                print(f"   # Then use: routing = {module_name}")
                break

        print(f"\n📝 Update your core/solver.py with:")
        print(f"   # Replace the current import section with the working import above")

    else:
        print("❌ cuOpt is not working properly. Potential issues:")

        if not successful_imports:
            print("   - No cuOpt modules could be imported")
            print("   - Check if cuOpt was installed correctly")
            print("   - Try: pip install --extra-index-url=https://pypi.nvidia.com cuopt")

        else:
            print("   - cuOpt modules found but DataModel/Solve not available")
            print("   - This might be a server-client setup")
            print("   - Check cuOpt documentation for server setup")

    print(f"\n🔧 Next steps:")
    print(f"   1. Use the working import in your solver")
    print(f"   2. Test with your FastAPI application")
    print(f"   3. If still issues, check cuOpt server setup")


def main():
    """Main debug function"""
    print("🚀 cuOpt Debug Script Started")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")

    # Step 1: Check installed packages
    cuopt_modules = check_installed_packages()

    # Step 2: Test imports
    successful_imports = test_import_approaches()

    # Step 3: Explore module contents
    if successful_imports:
        explore_module_contents(successful_imports)

    # Step 4: Test cuDF
    cudf_working = test_cudf_integration()

    # Step 5: Test cuOpt functionality
    cuopt_working = False
    if successful_imports and cudf_working:
        cuopt_working = test_cuopt_functionality(successful_imports)

    # Step 6: Provide guidance
    provide_usage_guidance(successful_imports, cuopt_working)

    print(f"\n🏁 Debug script completed")
    print(f"   cuOpt modules found: {len(cuopt_modules)}")
    print(f"   Successful imports: {len(successful_imports)}")
    print(f"   cuDF working: {cudf_working}")
    print(f"   cuOpt working: {cuopt_working}")


if __name__ == "__main__":
    main()