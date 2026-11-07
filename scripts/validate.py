#!/usr/bin/env python3
"""
CV Data Validation Script

Validates cv_data.yaml against the Pydantic schema to ensure data integrity.

Usage:
    python scripts/validate.py

Exit codes:
    0: Validation successful
    1: Validation failed or error occurred
"""

import sys
import yaml
from pathlib import Path
from pydantic import ValidationError

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_loader import load_cv_data


def validate_cv_data(data_path: Path) -> bool:
    """
    Validate CV data against schema.

    Args:
        data_path: Path to cv_data.yaml file

    Returns:
        True if validation successful, False otherwise
    """
    try:
        cv_data = load_cv_data(data_path.parent.parent, data_path)

        # Success output
        print("✓ CV data is valid!")
        print(
            f"  - Personal: {cv_data.personal_info.first_name} {cv_data.personal_info.last_name}"
        )
        print(f"  - Title: {cv_data.personal_info.title}")
        print(f"  - Experience entries: {len(cv_data.experience)}")
        print(f"  - Education entries: {len(cv_data.education)}")
        print(f"  - Canonical languages: {len(cv_data.sidebar.selection.languages)}")
        print(f"  - Inventory interests: {len(cv_data.sidebar.inventory.interests)}")
        verified_evidence = sum(
            item.state == "verified" for item in cv_data.career_evidence.items
        )
        open_gaps = sum(gap.status == "open" for gap in cv_data.career_evidence.gaps)
        print(f"  - Verified career evidence: {verified_evidence}")
        print(f"  - Open evidence gaps: {open_gaps}")
        verified_practices = sum(
            item.state == "verified" for item in cv_data.practice_evidence.items
        )
        open_practice_gaps = sum(
            gap.status == "open" for gap in cv_data.practice_evidence.gaps
        )
        print(f"  - Verified practice evidence: {verified_practices}")
        print(f"  - Open practice gaps: {open_practice_gaps}")

        # Check profiles
        variants = ["employment", "contracting", "freelance"]
        print(f"  - Profiles: {', '.join(variants)}")

        return True

    except FileNotFoundError as e:
        print(f"✗ Error: Data file not found: {e.filename}")
        return False

    except yaml.YAMLError as e:
        print(f"✗ YAML parsing error:")
        print(f"  {e}")
        return False

    except ValidationError as e:
        print(f"✗ Validation failed:")
        print()

        # Pretty print validation errors
        for error in e.errors():
            location = " -> ".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            print(f"  {location}:")
            print(f"    {message}")
        print()

        return False

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


def main():
    """Main entry point."""
    # Determine data file path
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_path = project_root / "data" / "cv_data.yaml"

    print(f"Validating CV data: {data_path}")
    print()

    # Validate
    if validate_cv_data(data_path):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
