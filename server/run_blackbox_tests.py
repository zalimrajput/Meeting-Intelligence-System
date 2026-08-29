"""Black-Box Test Runner for MeetingMind Platform.

Executes external consumer integration tests, HTTP status codes, envelope standards,
media streaming Range 206 chunks, multi-tenant boundaries, and format validations.
"""

import sys
import pytest


def main() -> None:
    print("=" * 75)
    print(" MeetingMind — Executing Comprehensive Black-Box Test Suite")
    print("=" * 75)
    
    args = [
        "-v",
        "--tb=short",
        "tests/test_blackbox_suite.py",
    ]
    exit_code = pytest.main(args)
    if exit_code == 0:
        print("\n" + "=" * 75)
        print(" ALL BLACK-BOX INTEGRATION & SECURITY TESTS PASSED SUCCESSFULLY! (100%)")
        print("=" * 75)
    else:
        print("\n" + "=" * 75)
        print(f" BLACK-BOX TESTS FAILED (Exit Code: {exit_code})")
        print("=" * 75)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
