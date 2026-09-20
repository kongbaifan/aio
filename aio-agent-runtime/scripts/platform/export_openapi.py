"""Export actual FastAPI v2 request schemas without connecting to any identity/model/database service."""

from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/api/platform-v2.openapi.json")
    args = parser.parse_args()
    path = args.output.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("API contract output must remain in the project")
    sys.path.insert(0, str(ROOT / "apps/local-harness"))
    from app.platform_settings import PlatformSettings
    from app.db.engine import Database
    from app.auth.oidc import OIDCClient
    from app.api.v2.application import create_platform_app

    settings = PlatformSettings.from_env(
        {
            "HARNESS_MODE": "platform-test",
            "PLATFORM_DATABASE_URL": "postgresql+psycopg://schema_export:synthetic-password@127.0.0.1:1/schema_export",
            "PLATFORM_PUBLIC_ORIGIN": "http://127.0.0.1:8080",
            "PLATFORM_OIDC_ISSUER": "https://identity.example.test",
            "PLATFORM_OIDC_CLIENT_ID": "schema-export",
            "PLATFORM_OIDC_CLIENT_SECRET": "not-a-real-secret",
            "PLATFORM_OIDC_AUTHORIZATION_ENDPOINT": "https://identity.example.test/authorize",
            "PLATFORM_OIDC_TOKEN_ENDPOINT": "https://identity.example.test/token",
            "PLATFORM_OIDC_JWKS_URI": "https://identity.example.test/keys",
        }
    )
    db = Database(settings.database_url)
    oidc = OIDCClient(settings)
    try:
        app = create_platform_app(settings, database=db, oidc_client=oidc)
        schema = app.openapi()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("Exported", len(schema["paths"]), "actual API paths to", path)
    finally:
        db.dispose()
        asyncio.run(oidc.close())


if __name__ == "__main__":
    main()
