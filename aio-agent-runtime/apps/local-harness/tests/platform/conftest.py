import os
import secrets
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, insert
from sqlalchemy.engine import make_url

from app.auth.principal import Principal
from app.db import schema as s
from app.db.engine import Database
from app.db.provisioning import provision_runtime_role, provision_identity, provision_agent, provision_budget
from app.runtime.service import PlatformService

import pytest

from app.platform_settings import PlatformSettings
from skill_fixtures import skill_registry as skill_registry
from connector_fixtures import mcp_platform as mcp_platform
from knowledge_fixtures import knowledge_platform as knowledge_platform
from team_fixtures import team_scenario as team_scenario
from oauth_fixtures import oauth_platform as oauth_platform
from stdio_fixtures import stdio_platform as stdio_platform


@pytest.fixture
def platform_env():
    return {
        "HARNESS_MODE": "platform-test",
        "PLATFORM_DATABASE_URL": "postgresql+psycopg://runtime:test-only-password@127.0.0.1:5432/platform_test",
        "PLATFORM_PUBLIC_ORIGIN": "http://127.0.0.1:8080",
        "PLATFORM_OIDC_ISSUER": "https://identity.example.test/tenant/",
        "PLATFORM_OIDC_CLIENT_ID": "platform-tests",
        "PLATFORM_OIDC_CLIENT_SECRET": "fake-idp-secret-for-tests-only",
        "PLATFORM_OIDC_AUTHORIZATION_ENDPOINT": "https://identity.example.test/authorize",
        "PLATFORM_OIDC_TOKEN_ENDPOINT": "https://identity.example.test/token",
        "PLATFORM_OIDC_JWKS_URI": "https://identity.example.test/keys",
    }


@pytest.fixture
def platform_settings(platform_env):
    return PlatformSettings.from_env(platform_env)


@pytest.fixture(scope="module")
def postgres():
    raw = os.environ.get("AIO_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Real PostgreSQL not configured; run scripts/platform/test_postgres.py")
    url = make_url(raw)
    if url.host not in {"127.0.0.1", "localhost", "::1"} or url.database != "aio_platform_test":
        raise RuntimeError("Integration tests require an explicitly named disposable loopback database")
    admin = create_engine(raw, hide_parameters=True)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["database_url"] = raw
    command.upgrade(config, "head")
    password = secrets.token_urlsafe(40)
    role = "aio_test_" + secrets.token_hex(5)
    with admin.begin() as c:
        provision_runtime_role(c, role, password)
    database = Database(url.set(username=role, password=password).render_as_string(hide_password=False))
    database.verify_runtime_role()
    yield database, admin, raw
    database.dispose()
    admin.dispose()


@pytest.fixture
def tenant(postgres, platform_settings):
    db, admin, _ = postgres
    org, alice, bob, other_org, outsider = (uuid4() for _ in range(5))
    tool_id = uuid4()
    with admin.begin() as c:
        for id in (org, other_org):
            c.execute(
                insert(s.organizations).values(
                    id=id, name="test-" + str(id), allowed_classifications=["public", "internal"], denied_actions=[]
                )
            )
        for uid, oid in [(alice, org), (bob, org), (outsider, other_org)]:
            provision_identity(
                c,
                org_id=oid,
                user_id=uid,
                issuer=platform_settings.oidc_issuer,
                subject=str(uid),
                display_name="Synthetic user",
            )
            provision_budget(c, org_id=oid, user_id=uid, hard_limit=Decimal("10"))
        agent = provision_agent(
            c,
            org_id=org,
            owner_id=alice,
            name="Synthetic test agent",
            version="1",
            engine="test-fixture-only",
            instruction="Synthetic fixture; not a production engine",
            manifest={"run_budget": "0.100000", "tools": [{"id": str(tool_id), "name": "test_write", "risk": "R2"}]},
        )
        for action in ("agent.use", "agent.read"):
            c.execute(insert(s.grants).values(org_id=org, id=uuid4(), resource_id=agent, subject_id=bob, action=action))
    pa, pb, po = Principal(org, alice, 0), Principal(org, bob, 0), Principal(other_org, outsider, 0)
    service = PlatformService(db, platform_settings)
    project = service.create_project(pa, "Alice private project")["id"]
    session = service.create_session(pa, project, agent, "Alice private session")["id"]
    return dict(
        db=db,
        admin=admin,
        settings=platform_settings,
        org=org,
        alice=pa,
        bob=pb,
        outsider=po,
        agent=agent,
        tool=tool_id,
        project=project,
        session=session,
        service=service,
    )
