#!/usr/bin/env python
"""Generate a changelog from commits since the last git tag.

Usage:
    python scripts/generate_changelog.py [FROM_REF]

If FROM_REF is not provided, the most recent tag is used.
"""

import subprocess
import sys
import re

def get_previous_tag():
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# example: git log v2025.1..HEAD --first-parent --merges --format=%s
def get_commit_subjects(from_ref):
    result = subprocess.run(
        ["git", "log", f"{from_ref}..HEAD", "--first-parent", "--merges", "--format=%s"],
        capture_output=True,
        text=True,
    )
    forge_link = "https://farga.pangea.org/ereuse/devicehub-django/pulls"
    return [
        re.sub(
            r"^Merge pull request '(.*)' \(#(\d+)\) from .*",
            rf"\1 ([#\2]({forge_link}/\2))",
            line,
        )
        for line in result.stdout.splitlines()
        if line
    ]

def main():
    from_ref = sys.argv[1] if len(sys.argv) > 1 else get_previous_tag()
    if not from_ref:
        print("Error: could not determine previous tag", file=sys.stderr)
        sys.exit(1)

    print(f"# Changelog: {from_ref}..HEAD\n", file=sys.stderr)

    subjects = get_commit_subjects(from_ref)
    if not subjects:
        print("No commits found.", file=sys.stderr)
        sys.exit(0)

    for subject in subjects:
        # Skip release commits
        if subject.startswith("Release "):
            continue
        print(f"- {subject}")


if __name__ == "__main__":
    main()
