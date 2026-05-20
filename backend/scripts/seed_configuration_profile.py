"""Seed the default generation configuration profile."""
from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import upsert_default_configuration_profile  # noqa: E402
from app.db.session import session_scope  # noqa: E402


def main() -> None:
    with session_scope() as session:
        profile_version = upsert_default_configuration_profile(session)
        print(f"profile_id={profile_version.profile_id}")
        print(f"version_number={profile_version.version_number}")
        print(f"config_schema_version={profile_version.config_schema_version}")
        print(f"lifecycle_status={profile_version.lifecycle_status}")


if __name__ == "__main__":
    main()
