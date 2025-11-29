#!/usr/bin/env python3
"""Analyze test failures and categorize them for systematic fixing."""

import re
import subprocess
from collections import defaultdict

def run_tests():
    """Run tests and capture output."""
    result = subprocess.run(
        ["uv", "run", "pytest", "-v", "--tb=no", "--no-header"],
        capture_output=True,
        text=True,
        cwd="/Users/conradhollomon/projects/sbir-analytics"
    )
    return result.stdout + result.stderr

def categorize_failures(output):
    """Categorize test failures by error type."""
    categories = defaultdict(list)

    lines = output.split('\n')
    for line in lines:
        if 'FAILED' in line or 'ERROR' in line:
            # Extract test name
            match = re.search(r'(tests/[^\s]+)::', line)
            if match:
                test_file = match.group(1)

                # Categorize by error pattern
                if 'AttributeError' in line:
                    if "'ApplicabilityModel' object has no attribute" in line:
                        categories['CET_missing_methods'].append(test_file)
                    elif "module 'src.enrichers' has no attribute" in line:
                        categories['import_errors'].append(test_file)
                    else:
                        categories['attribute_errors'].append(test_file)
                elif 'ValidationError' in line or 'pydantic' in line:
                    categories['pydantic_validation'].append(test_file)
                elif 'TypeError' in line:
                    if 'TransitionDetector.__init__()' in line:
                        categories['transition_detector_init'].append(test_file)
                    elif 'PaECTERClient.__init__()' in line:
                        categories['paecter_client_init'].append(test_file)
                    else:
                        categories['type_errors'].append(test_file)
                elif 'ModuleNotFoundError' in line:
                    categories['missing_modules'].append(test_file)
                elif 'KeyError' in line:
                    categories['key_errors'].append(test_file)
                elif 'AssertionError' in line:
                    categories['assertion_errors'].append(test_file)
                else:
                    categories['other'].append(test_file)

    return categories

def main():
    print("Running tests and analyzing failures...")
    output = run_tests()

    categories = categorize_failures(output)

    print("\n=== TEST FAILURE CATEGORIES ===\n")
    for category, tests in sorted(categories.items(), key=lambda x: -len(x[1])):
        print(f"{category}: {len(tests)} failures")
        if len(tests) <= 10:
            for test in tests[:10]:
                print(f"  - {test}")
        else:
            print(f"  (showing first 10 of {len(tests)})")
            for test in tests[:10]:
                print(f"  - {test}")

    print(f"\nTotal categorized: {sum(len(tests) for tests in categories.values())}")

if __name__ == "__main__":
    main()
