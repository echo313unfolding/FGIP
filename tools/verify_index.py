#!/usr/bin/env python3
"""Verify all existing files in INDEX.jsonl against their stored SHA256 hashes.

Usage: python3 tools/verify_index.py [path/to/INDEX.jsonl]

Skips missing files, prints failures, exits 1 if any mismatch.
"""

import json
import os
import subprocess
import sys


def main():
    if len(sys.argv) > 1:
        idx_path = sys.argv[1]
    else:
        idx_path = os.path.join(
            os.environ.get("RECEIPTS_DIR", "receipts/watch"),
            "INDEX.jsonl"
        )

    if not os.path.exists(idx_path):
        print(f"Missing: {idx_path}")
        sys.exit(2)

    bad = 0
    checked = 0

    with open(idx_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            rec = json.loads(line)
            path = rec.get("file")
            want = rec.get("sha256")

            if not path or not want:
                continue

            if not os.path.exists(path):
                print(f"SKIP (missing): {path}")
                continue

            checked += 1
            got = subprocess.check_output(
                ["sha256sum", path], text=True
            ).split()[0]

            if got != want:
                bad += 1
                print(f"FAIL {rec.get('ts')} {path}")
                print(f"  want: {want}")
                print(f"  got:  {got}")

    if bad:
        print(f"\nFAILED: {bad}/{checked} files")
        sys.exit(1)

    print(f"INDEX VERIFIED OK: {checked} files matched")


if __name__ == "__main__":
    main()
