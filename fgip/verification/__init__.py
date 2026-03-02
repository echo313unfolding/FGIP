"""FGIP Verification Module - Easter egg validation and pipeline health.

Easter eggs are known-true facts that agents MUST discover.
They serve as validation canaries for the data pipeline.

Usage:
    from fgip.verification import run_verification, EASTER_EGGS

    report = run_verification(conn)
    print(f"Found {report.eggs_found}/{report.eggs_total} easter eggs")
"""

from .easter_eggs import (
    EasterEgg,
    EASTER_EGGS,
    check_egg,
    check_all_eggs,
    get_eggs_for_agent,
)
from .verifier import (
    VerificationReport,
    run_verification,
    save_verification_report,
    quick_verify,
)

__all__ = [
    # Easter egg types and data
    "EasterEgg",
    "EASTER_EGGS",
    "check_egg",
    "check_all_eggs",
    "get_eggs_for_agent",
    # Verification reporting
    "VerificationReport",
    "run_verification",
    "save_verification_report",
    "quick_verify",
]
