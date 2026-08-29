"""White-Box Test Runner for MeetingMind Platform.

Executes all internal unit tests, security cryptography checks, regex timestamp
parsers, formatters, and error envelope mappers.
"""

import sys
import pytest


def main() -> None:
    print("=" * 75)
    print(" MeetingMind — Executing Comprehensive White-Box Test Suite")
    print("=" * 75)
    
    args = [
        "-v",
        "--tb=short",
        "tests/test_whitebox_suite.py",
    ]
    exit_code = pytest.main(args)
    if exit_code == 0:
        print("\n" + "=" * 75)
        print(" ALL WHITE-BOX UNIT & LOGIC TESTS PASSED SUCCESSFULLY! (100%)")
        print("=" * 75)
    else:
        print("\n" + "=" * 75)
        print(f" WHITE-BOX TESTS FAILED (Exit Code: {exit_code})")
        print("=" * 75)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
