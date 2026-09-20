"""Start a finite-lived, loopback-only verification workbench with real PG and optional Docker compute.

The identity provider and language model are explicitly SYNTHETIC verification
fixtures. No company credentials/data are read, no production service is modified.
Press Ctrl+C or wait for --lifetime; only this run's exact labeled resources are removed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import quote
from uuid import UUID, uuid4

import uvicorn

ROOT = Path(__file__).resolve().parents[2]


def docker(*args, env=None):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True, env=env).stdout.strip()


def start_server(app, port: int):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("Verification HTTP service did not start")
        time.sleep(0.05)
    return server, thread


def main():
    sys.path.insert(0, str(ROOT / "apps/local-harness"))
    sys.path.insert(0, str(ROOT / "services/sandbox-manager/src"))
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, insert, select

    from app.admin.contracts import AgentCreate, GrantCreate, ModelCreate, ToolCreate
    from app.admin.service import AdminService
    from app.auth.principal import Principal
    from app.db import schema as s
    from app.db.engine import Database
    from app.db.provisioning import provision_identity, provision_runtime_role
    from app.execution.coordinator import SandboxCoordinator
    from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
    from app.platform_settings import PlatformSettings, _sandbox_profiles
    from app.api.v2.application import create_platform_app
    from app.runtime.execution import ExecutionStore
    from app.runtime.model_client import ModelFactory
    from app.runtime.worker import DurableWorker, ToolDrivers
    from app.skills.reader import SkillReferenceDriver
    from app.skills.validation import SkillValidationStore
    from app.skills.worker import SkillValidationWorker
    from app.skills.archive_service import SkillArchiveService
    from app.skills.archive_jobs import SkillArchiveJobs
    from app.skills.archive_worker import SkillArchiveWorker
    from app.connections.client import ConnectorClient
    from app.connections.service import ConnectionService
    from app.connections.driver import MCPDriver, maintain_connections
    from app.connections.contracts import (
        ServerCreate,
        ConnectionCreate,
        CredentialPrepare,
        CredentialUpload,
        DiscoveryCreate,
        ServerPublish,
        ToolSelection,
    )
    from app.knowledge.service import KnowledgeService
    from app.knowledge.jobs import KnowledgeJobs
    from app.knowledge.embedding import EmbeddingStore, Embedder
    from app.knowledge.embedding_client import EmbeddingFactory
    from app.knowledge.retrieval import KnowledgeDriver, KnowledgeRetrieval
    from app.knowledge.worker import KnowledgeWorker
    from app.workspaces.service import ArtifactService
    from app.workspaces.storage import BlobStore
    from aio_sandbox_manager.api import RemoteGuard, create_app as manager_app
    from aio_sandbox_manager.contracts import Profile
    from aio_sandbox_manager.docker_backend import DockerBackend
    from aio_sandbox_manager.journal import Journal
    from aio_sandbox_manager.service import SandboxManager
    from preview_identity import fixture_app
    from preview_mcp import register_fixture, TOKENS as mcp_tokens
    from preview_knowledge import seed as seed_knowledge
    from preview_handoff import seed as seed_handoff, SyntheticApprovalDriver
    from preview_diagnostics import diagnostic_worker, observe_manager_errors
    from oauth_fixture import OAuthFixture, register_fixture as register_oauth_fixture
    from preview_oauth import seed as seed_oauth
    from app.connections.oauth_settings import public_oauth
    from app.connections.stdio_settings import stdio_policy
    from preview_stdio import seed as seed_stdio
    from preview_dependencies import seed as seed_dependencies
    from aio_runtime_policy import load_trust_keys
    from aio_sandbox_manager.stdio_contracts import StdioProfile
    from aio_sandbox_manager.stdio_service import StdioManager
    from aio_connector_gateway.stdio_client import StdioManagerClient
    from app.workspaces.checkpoints import maintain_checkpoints
    from aio_connector_gateway.contracts import Endpoint
    from aio_connector_gateway.vault import Vault
    from aio_connector_gateway.service import ConnectorGateway, RemoteAuthority
    from aio_connector_gateway.api import create_app as connector_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8120)
    parser.add_argument("--lifetime", type=int, default=1800)
    parser.add_argument("--info-path", type=Path)
    parser.add_argument("--stop-file", type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65532 or not 30 <= args.lifetime <= 3600:
        raise ValueError("Invalid verification port/lifetime")
    if not (ROOT / "web/platform/dist/index.html").is_file():
        raise RuntimeError("Build web/platform before starting preview")
    profile_file = ROOT / "var/verification/sandbox-profile.json"
    if not profile_file.is_file():
        raise RuntimeError("Run scripts/platform/test_sandbox.py to build and verify the compute image first")
    image = json.loads(profile_file.read_text(encoding="utf-8"))["profiles"][0]["image_digest"]
    docker("image", "inspect", image)
    parser_image = json.loads((ROOT / "var/verification/document-profile.json").read_text(encoding="utf-8"))[
        "profiles"
    ][0]["image_digest"]
    docker("image", "inspect", parser_image)
    dependency_file = ROOT / "var/verification/dependency-profile.json"
    runtime_keys_file = ROOT / "var/verification/runtime-trust.json"
    dependency_profile = json.loads(dependency_file.read_text(encoding="utf-8"))["profiles"][0]
    docker("image", "inspect", dependency_profile["image_digest"])
    dependency_catalog = _sandbox_profiles(
        {
            "PLATFORM_SANDBOX_PROFILES": str(dependency_file),
            "PLATFORM_RUNTIME_TRUST_KEYS": str(runtime_keys_file),
            "HARNESS_MODE": "platform-test",
        }
    )
    db_image = "pgvector/pgvector@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f"
    verification = "preview-" + secrets.token_hex(8)
    pg_password = secrets.token_urlsafe(40)
    runtime_password = secrets.token_urlsafe(40)
    model_key = secrets.token_urlsafe(32)
    idp_secret = secrets.token_urlsafe(32)
    manager_token = secrets.token_urlsafe(40)
    control_token = secrets.token_urlsafe(40)
    connector_token = secrets.token_urlsafe(40)
    connector_control_token = secrets.token_urlsafe(40)
    old_model = os.environ.get("AIO_PREVIEW_MODEL_KEY")
    os.environ["AIO_PREVIEW_MODEL_KEY"] = model_key
    old_verification = os.environ.get("AIO_VERIFICATION_RUN_ID")
    os.environ["AIO_VERIFICATION_RUN_ID"] = verification
    container = None
    database = None
    admin_engine = None
    manager = None
    services = []
    worker_loop = None
    worker_future = None
    worker_thread = None
    worker_errors = []
    manager_errors = []
    output = ROOT / "var/verification"
    output.mkdir(parents=True, exist_ok=True)
    preview_info = args.info_path.resolve() if args.info_path else output / "workbench-preview.json"
    stop_file = args.stop_file.resolve() if args.stop_file else None
    for path in [preview_info, stop_file]:
        if path and not path.is_relative_to(output.resolve()):
            raise ValueError("Verification control files must stay under var/verification")
    preview_info.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=verification + "-", dir=output) as temp:
            state = Path(temp).resolve()
            if not state.is_relative_to(output.resolve()):
                raise RuntimeError("Verification state left the workspace")
            try:
                container = docker(
                    "run",
                    "--rm",
                    "--detach",
                    "--name",
                    "aio-" + verification,
                    "--label",
                    "aio.preview=" + verification,
                    "--memory",
                    "512m",
                    "--cpus",
                    "2",
                    "--pids-limit",
                    "128",
                    "--publish",
                    "127.0.0.1::5432",
                    "--env",
                    "POSTGRES_PASSWORD",
                    "--env",
                    "POSTGRES_USER=preview_migrator",
                    "--env",
                    "POSTGRES_DB=aio_preview",
                    db_image,
                    env={**os.environ, "POSTGRES_PASSWORD": pg_password},
                )
                port = docker("port", container, "5432/tcp").rsplit(":", 1)[1]
                admin_url = (
                    f"postgresql+psycopg://preview_migrator:{quote(pg_password, safe='')}@127.0.0.1:{port}/aio_preview"
                )
                admin_engine = create_engine(admin_url, hide_parameters=True, connect_args={"connect_timeout": 2})
                ready = time.monotonic() + 40
                while True:
                    try:
                        with admin_engine.connect() as c:
                            c.execute(select(1))
                        break
                    except Exception:
                        if time.monotonic() > ready:
                            raise RuntimeError("Verification PostgreSQL did not become ready") from None
                        time.sleep(0.2)
                config = Config(str(ROOT / "apps/local-harness/alembic.ini"))
                config.attributes["database_url"] = admin_url
                command.upgrade(config, "head")
                runtime_role = "preview_runtime"
                with admin_engine.begin() as c:
                    provision_runtime_role(c, runtime_role, runtime_password)
                db_url = f"postgresql+psycopg://{runtime_role}:{quote(runtime_password, safe='')}@127.0.0.1:{port}/aio_preview"
                origin = f"http://127.0.0.1:{args.port}"
                issuer = f"http://127.0.0.1:{args.port + 1}"
                manager_url = f"http://127.0.0.1:{args.port + 2}"
                connector_url = f"http://127.0.0.1:{args.port + 3}"
                stdio_token = secrets.token_urlsafe(40)
                stdio_profile = StdioProfile.model_validate(
                    json.loads((ROOT / "var/verification/stdio-profile.json").read_text(encoding="utf-8"))["profiles"][
                        0
                    ]
                )
                stdio_config = {
                    "profile_id": stdio_profile.id,
                    "image_digest": stdio_profile.image_digest,
                    "template_digest": stdio_profile.template_digest,
                    "credential_env": stdio_profile.credential_env,
                    "network_profile": "none",
                }
                if stdio_profile.input_policy != "none":
                    stdio_config["input_policy"] = stdio_profile.input_policy
                stdio_endpoint = Endpoint(
                    "company-stdio",
                    "stdio://" + stdio_profile.id,
                    frozenset({"identity", "isolation_facts", "read_attachment"}),
                    transport="stdio",
                    stdio=stdio_config,
                )
                mcp_endpoint = Endpoint("company-mcp", issuer + "/mcp", frozenset({"identity_lookup"}), test_mode=True)
                oauth_fixture = OAuthFixture(issuer, origin, resource_path="/oauth/mcp")
                oauth_fixture.initial_expiry_seconds = 2
                oauth_endpoint = Endpoint(
                    oauth_fixture.endpoint_id,
                    oauth_fixture.resource_uri,
                    frozenset({"lookup_identity"}),
                    authentication="oauth2",
                    oauth=oauth_fixture.policy(),
                    test_mode=True,
                )
                org = uuid4()
                ids = {key: uuid4() for key in ("admin", "alice", "bob", "reviewer")}
                accounts = {
                    "admin": {"name": "林岚", "role_label": "管理员 · 合成身份"},
                    "alice": {"name": "陈予", "role_label": "销售 · 合成身份"},
                    "bob": {"name": "周宁", "role_label": "财务 · 合成身份"},
                    "reviewer": {"name": "程嘉", "role_label": "Skill 审核人 · 合成身份"},
                }
                env = {
                    "HARNESS_MODE": "platform-test",
                    "PLATFORM_DATABASE_URL": db_url,
                    "PLATFORM_PUBLIC_ORIGIN": origin,
                    "PLATFORM_OIDC_ISSUER": issuer,
                    "PLATFORM_OIDC_CLIENT_ID": "preview-workbench",
                    "PLATFORM_OIDC_CLIENT_SECRET": idp_secret,
                    "PLATFORM_OIDC_AUTHORIZATION_ENDPOINT": issuer + "/authorize",
                    "PLATFORM_OIDC_TOKEN_ENDPOINT": issuer + "/token",
                    "PLATFORM_OIDC_JWKS_URI": issuer + "/jwks",
                    "PLATFORM_MANAGER_URL": manager_url,
                    "PLATFORM_MANAGER_TOKEN": manager_token,
                    "PLATFORM_MANAGER_CONTROL_TOKEN": control_token,
                    "PLATFORM_CONNECTOR_URL": connector_url,
                    "PLATFORM_CONNECTOR_TOKEN": connector_token,
                    "PLATFORM_CONNECTOR_CONTROL_TOKEN": connector_control_token,
                    "PLATFORM_ARTIFACT_ROOT": str(state / "artifacts"),
                    "PLATFORM_MODEL_ALLOWED_ORIGINS": issuer,
                    "PLATFORM_MODEL_SECRET_ENV_ALLOWLIST": "AIO_PREVIEW_MODEL_KEY",
                    "PLATFORM_LOGIN_ORG_ID": str(org),
                    "PLATFORM_ORGANIZATION_LABEL": "本地验证组织 · 合成身份与模型",
                    "PLATFORM_WEB_DIST": str(ROOT / "web/platform/dist"),
                }
                settings = replace(
                    PlatformSettings.from_env(env),
                    sandbox_profiles=(
                        {"id": "standard", "image_digest": image, "max_timeout_seconds": 120},
                        *dependency_catalog,
                    ),
                    skill_import_profile="standard",
                    document_profiles=({"id": "documents", "image_digest": parser_image, "max_timeout_seconds": 60},),
                    connector_profiles=(
                        {
                            "id": mcp_endpoint.id,
                            "url": mcp_endpoint.url,
                            "digest": mcp_endpoint.digest,
                            "authentication": "bearer",
                            "read_tools": ["identity_lookup"],
                            "timeout_seconds": 30,
                        },
                        {
                            "id": oauth_endpoint.id,
                            "url": oauth_endpoint.url,
                            "digest": oauth_endpoint.digest,
                            "authentication": "oauth2",
                            "read_tools": ["lookup_identity"],
                            "timeout_seconds": 30,
                            "oauth": public_oauth(oauth_fixture.policy(), oauth_endpoint.id, oauth_endpoint.url, False),
                        },
                        {
                            "id": stdio_endpoint.id,
                            "url": stdio_endpoint.url,
                            "digest": stdio_endpoint.digest,
                            "transport": "stdio",
                            "authentication": "bearer",
                            "read_tools": sorted(stdio_endpoint.read_tools),
                            "timeout_seconds": 30,
                            "stdio": stdio_policy(stdio_config, stdio_endpoint.url, "bearer"),
                        },
                    ),
                )
                database = Database(db_url)
                database.verify_runtime_role()
                with admin_engine.begin() as c:
                    c.execute(
                        insert(s.organizations).values(
                            id=org,
                            name="验证组织 · 合成数据",
                            allowed_classifications=["public", "internal"],
                            denied_actions=[],
                        )
                    )
                    for key, uid in ids.items():
                        provision_identity(
                            c,
                            org_id=org,
                            user_id=uid,
                            issuer=issuer,
                            subject=key,
                            display_name=accounts[key]["name"],
                            role="org_admin" if key in {"admin", "reviewer"} else "member",
                        )
                principal = Principal(org, ids["admin"], 0)
                admin = AdminService(database, settings)
                sales = admin.create_department(principal, "销售团队")
                finance = admin.create_department(principal, "财务团队")
                admin.set_department_member(principal, sales["id"], ids["alice"], "member")
                admin.set_department_member(principal, finance["id"], ids["bob"], "member")
                for uid in ids.values():
                    admin.set_budget(principal, uid, Decimal("10"))
                model = admin.create_model(
                    principal,
                    ModelCreate(
                        name="本地验收模型（合成）",
                        provider="verification",
                        model="fixture-only",
                        endpoint=issuer + "/v1/chat/completions",
                        secret_env="AIO_PREVIEW_MODEL_KEY",
                        max_output_tokens=2048,
                        max_call_charge=Decimal("0.01"),
                        input_price_per_million=Decimal("1"),
                        output_price_per_million=Decimal("2"),
                    ),
                )
                tool = admin.create_tool(
                    principal,
                    ToolCreate(
                        name="python_compute",
                        description="在无网络 Python 沙箱中生成验收文件。",
                        sandbox_profile="standard",
                        timeout_seconds=30,
                    ),
                )
                for name, department, tool_ids in [
                    ("文件分析助手", sales["id"], (UUID(tool["id"]),)),
                    ("文字整理助手", sales["id"], ()),
                    ("财务资料助手", finance["id"], (UUID(tool["id"]),)),
                ]:
                    agent = admin.create_agent(
                        principal,
                        AgentCreate(
                            name=name,
                            version="1.0",
                            instruction="本地验收用 Agent，模型输出为合成内容；执行和权限链路是真实实现。",
                            model_id=UUID(model["id"]),
                            tool_ids=tool_ids,
                            run_budget=Decimal("0.10"),
                            max_rounds=8 if name == "文件分析助手" else 4,
                            team={"max_steps": 2, "max_step_rounds": 3} if name == "文件分析助手" else None,
                        ),
                    )
                    admin.set_grants(
                        principal,
                        agent["id"],
                        GrantCreate(
                            subject_type="department",
                            subject_id=department,
                            actions=("agent.read", "agent.use"),
                            include_dependencies=True,
                        ),
                    )
                from app.runtime.service import PlatformService

                platform = PlatformService(database, settings)
                platform.create_project(Principal(org, ids["admin"], 0), "管理员验收项目")
                platform.create_project(Principal(org, ids["alice"], 1), "销售数据分析")
                platform.create_project(Principal(org, ids["bob"], 1), "财务资料整理")
                fixtures = fixture_app(
                    issuer, origin + "/auth/callback", "preview-workbench", idp_secret, accounts, model_key
                )
                register_fixture(fixtures)
                register_oauth_fixture(fixtures, oauth_fixture, accounts)
                services.append(start_server(fixtures, args.port + 1))
                services.append(start_server(create_platform_app(settings, database=database), args.port))
                journal = Journal(state / "manager")
                guard = RemoteGuard(origin, control_token, test_mode=True)
                manager = SandboxManager(
                    journal,
                    DockerBackend(journal.installation_id),
                    {
                        "standard": Profile("standard", image),
                        "analytics": Profile(**dependency_profile),
                        "documents": Profile(
                            "documents",
                            parser_image,
                            memory_bytes=512 * 1024 * 1024,
                            artifact_bytes=16 * 1024 * 1024,
                            artifact_files=4,
                            max_timeout_seconds=60,
                        ),
                    },
                    guard,
                    runtime_keys=load_trust_keys(runtime_keys_file),
                    allow_test_runtimes=True,
                )
                StdioManager(manager, {stdio_profile.id: stdio_profile})
                services.append(
                    start_server(
                        observe_manager_errors(
                            manager_app(manager, manager_token, stdio_token=stdio_token), manager_errors
                        ),
                        args.port + 2,
                    )
                )
                credential_gateway = ConnectorGateway(
                    Vault(state / "credentials", secrets.token_bytes(32)),
                    {
                        mcp_endpoint.id: mcp_endpoint,
                        oauth_endpoint.id: oauth_endpoint,
                        stdio_endpoint.id: stdio_endpoint,
                    },
                    RemoteAuthority(origin, connector_control_token, test_mode=True),
                    stdio_manager=StdioManagerClient(manager_url, stdio_token, test_mode=True),
                )
                services.append(start_server(connector_app(credential_gateway, connector_token), args.port + 3))

                async def seed_connections():
                    client = ConnectorClient(connector_url, connector_token)
                    connections = ConnectionService(database, settings, client)
                    try:
                        server = connections.create_server(
                            principal, ServerCreate(name="只读资料 MCP", version="1.0.0", endpoint_id=mcp_endpoint.id)
                        )

                        async def connect_account(p, subject):
                            row = connections.create_connection(
                                p, ConnectionCreate(server_id=server["id"], name="我的合成 MCP 身份")
                            )
                            ticket = connections.prepare_credential(
                                p, row["id"], CredentialPrepare(expected_revision=0, request_id=uuid4())
                            )
                            await connections.upload_credential(
                                p, row["id"], ticket["binding_id"], CredentialUpload(secret=mcp_tokens[subject])
                            )
                            return await connections.discover(p, row["id"], DiscoveryCreate(request_id=uuid4()))

                        discovery = await connect_account(principal, "admin")
                        server = connections.publish(
                            principal,
                            server["id"],
                            ServerPublish(
                                expected_revision=0,
                                discovery_id=discovery["id"],
                                tools=(ToolSelection(remote_name="identity_lookup", alias="mcp_identity"),),
                                acknowledge_readonly_credentials=True,
                            ),
                        )
                        agent = admin.create_agent(
                            principal,
                            AgentCreate(
                                name="MCP 身份资料助手",
                                version="1.0",
                                instruction="只使用获权的 MCP 身份；此模型与源数据为合成验证内容。",
                                model_id=UUID(model["id"]),
                                mcp_server_ids=(server["id"],),
                                run_budget=Decimal("0.10"),
                                max_rounds=8,
                                team={"max_steps": 2, "max_step_rounds": 3},
                            ),
                        )
                        for department in (sales, finance):
                            admin.set_grants(
                                principal,
                                agent["id"],
                                GrantCreate(
                                    subject_type="department",
                                    subject_id=department["id"],
                                    actions=("agent.read", "agent.use"),
                                    include_dependencies=True,
                                ),
                            )
                        await connect_account(Principal(org, ids["alice"], 1), "alice")
                        await connect_account(Principal(org, ids["bob"], 1), "bob")
                    finally:
                        await client.close()

                asyncio.run(seed_connections())
                oauth_info = asyncio.run(
                    seed_oauth(database, settings, org, oauth_fixture, model["id"], (sales["id"], finance["id"]))
                )
                stdio_info = asyncio.run(
                    seed_stdio(database, settings, principal, model["id"], (sales["id"], finance["id"]))
                )

                async def seed_documents():
                    client = ManagerClient(manager_url, manager_token)
                    try:
                        return await seed_knowledge(database, settings, principal, model["id"], sales["id"], client)
                    finally:
                        await client.close()

                knowledge_info = asyncio.run(seed_documents())

                async def seed_dependency_skill():
                    client = ManagerClient(manager_url, manager_token)
                    try:
                        return await seed_dependencies(
                            database,
                            settings,
                            principal,
                            ids["reviewer"],
                            model["id"],
                            (sales["id"], finance["id"]),
                            client,
                        )
                    finally:
                        await client.close()

                dependency_info = asyncio.run(seed_dependency_skill())
                handoff_info = seed_handoff(admin, principal, model["id"], tool["id"], sales["id"], ids["reviewer"])
                worker_loop = asyncio.new_event_loop()

                def run_loop():
                    asyncio.set_event_loop(worker_loop)
                    worker_loop.run_forever()

                worker_thread = threading.Thread(target=run_loop, daemon=True)
                worker_thread.start()

                async def serve_worker():
                    store = ExecutionStore(database, settings)
                    artifacts = ArtifactService(database, BlobStore(settings.artifact_root))
                    client = ManagerClient(manager_url, manager_token)
                    connector = ConnectorClient(connector_url, connector_token)
                    driver = SandboxPythonDriver(SandboxCoordinator(store, artifacts), client)
                    mcp_driver = MCPDriver(connector)
                    knowledge = KnowledgeService(database, settings, artifacts.blobs)
                    knowledge_jobs = KnowledgeJobs(database, settings, knowledge)
                    embedder = Embedder(
                        EmbeddingStore(database, settings, knowledge_jobs, store), EmbeddingFactory(settings)
                    )
                    retrieval = KnowledgeRetrieval(database, store, embedder)
                    worker = diagnostic_worker(DurableWorker, worker_errors)(
                        store,
                        org,
                        "preview-worker",
                        ModelFactory(
                            approved_origins=frozenset({issuer}),
                            secret_names=frozenset({"AIO_PREVIEW_MODEL_KEY"}),
                            production=False,
                        ),
                        ToolDrivers(
                            {
                                "sandbox.python": driver,
                                "skill.python": driver,
                                "skill.read": SkillReferenceDriver(store),
                                "mcp.http": mcp_driver,
                                "mcp.stdio": mcp_driver,
                                "knowledge.search": KnowledgeDriver(retrieval),
                                "preview.approval": SyntheticApprovalDriver(),
                            }
                        ),
                    )
                    try:
                        validation = SkillValidationWorker(
                            SkillValidationStore(database, settings),
                            client,
                            org,
                            "preview-skill-worker",
                            stopping=worker.stopping,
                        )
                        await asyncio.gather(
                            worker.serve(),
                            validation.serve(),
                            SkillArchiveWorker(
                                SkillArchiveJobs(SkillArchiveService(database, settings, artifacts.blobs)),
                                client,
                                org,
                                "preview-archive-worker",
                                stopping=worker.stopping,
                            ).serve(),
                            KnowledgeWorker(
                                knowledge_jobs,
                                client,
                                embedder,
                                org,
                                "preview-knowledge-worker",
                                stopping=worker.stopping,
                            ).serve(),
                            maintain_connections(
                                ConnectionService(database, settings, connector), org, worker.stopping
                            ),
                            maintain_checkpoints(store.workspace, client, org, worker.stopping),
                        )
                    finally:
                        await client.close()
                        await connector.close()

                worker_future = asyncio.run_coroutine_threadsafe(serve_worker(), worker_loop)
                info = {
                    "state": "running",
                    "url": origin,
                    "identity_url": issuer,
                    "manager_url": manager_url,
                    "connector_url": connector_url,
                    "knowledge_fixture": knowledge_info,
                    "handoff_fixture": handoff_info,
                    "oauth_fixture": oauth_info,
                    "stdio_fixture": stdio_info,
                    "dependency_fixture": dependency_info,
                    "org_id": str(org),
                    "fixture": "Synthetic IdP and model; real PostgreSQL, APIs, Web, Docker execution and files",
                    "verification_id": verification,
                    "accounts": accounts,
                    "expires_at_epoch": time.time() + args.lifetime,
                }
                preview_info.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("VERIFICATION_WORKBENCH_READY " + origin, flush=True)
                print(
                    "Synthetic identity/model only; API, PostgreSQL and Docker are real. Press Ctrl+C to clean up.",
                    flush=True,
                )
                deadline = time.monotonic() + args.lifetime
                while time.monotonic() < deadline:
                    if stop_file and stop_file.is_file():
                        break
                    if worker_future.done():
                        worker_future.result()
                        raise RuntimeError("Verification worker stopped unexpectedly")
                    if any(not thread.is_alive() for _, thread in services):
                        raise RuntimeError("Verification server stopped")
                    time.sleep(0.25)
            finally:
                if worker_future:
                    worker_future.cancel()
                    time.sleep(0.2)
                if worker_loop:
                    worker_loop.call_soon_threadsafe(worker_loop.stop)
                if worker_thread:
                    worker_thread.join(timeout=5)
                for server, thread in reversed(services):
                    server.should_exit = True
                    thread.join(timeout=12)
                # Preserve only bounded state/error metadata from this synthetic stack, never prompts,
                # credentials, tool arguments/results or document contents. Cleanup still runs on failure.
                try:
                    lifecycle = {
                        "verification_id": verification,
                        "worker_errors": worker_errors,
                        "manager_errors": manager_errors,
                    }
                    if admin_engine and database:
                        with admin_engine.connect() as connection:
                            for name, table, fields in [
                                ("runs", s.runs, ("id", "state", "generation", "error_code", "cleanup_state")),
                                (
                                    "workspace_checkpoints",
                                    s.workspace_checkpoints,
                                    ("id", "run_id", "generation", "state", "manager_acknowledged"),
                                ),
                                ("discoveries", s.mcp_discoveries, ("id", "state", "error_code")),
                                (
                                    "stdio_leases",
                                    s.mcp_stdio_leases,
                                    ("id", "run_id", "discovery_id", "state", "close_reason"),
                                ),
                            ]:
                                rows = (
                                    connection.execute(
                                        select(*(table.c[field] for field in fields))
                                        .where(table.c.org_id == org)
                                        .limit(100)
                                    )
                                    .mappings()
                                    .all()
                                )
                                lifecycle[name] = [dict(row) for row in rows]
                    if manager:
                        with manager.journal.connect() as connection:
                            lifecycle["manager_cells"] = [
                                dict(row)
                                for row in connection.execute(
                                    "SELECT binding_id,run_id,profile,state,error_code FROM cells LIMIT 100"
                                )
                            ]
                            lifecycle["stdio_rpcs"] = [
                                dict(row)
                                for row in connection.execute(
                                    "SELECT binding_id,state,error_code FROM stdio_rpcs WHERE error_code IS NOT NULL LIMIT 100"
                                )
                            ]
                    (output / "workbench-lifecycle.json").write_text(
                        json.dumps(lifecycle, default=str, indent=2) + "\n", encoding="utf-8"
                    )
                except Exception:
                    print(
                        "Synthetic lifecycle diagnostics unavailable; proceeding with owned-resource cleanup.",
                        flush=True,
                    )
                if database:
                    database.dispose()
                if admin_engine:
                    admin_engine.dispose()
    except KeyboardInterrupt:
        pass
    finally:
        if container:
            inspection = json.loads(docker("inspect", container))[0]
            if inspection["Config"].get("Labels", {}).get("aio.preview") != verification:
                raise RuntimeError("Refusing unrelated preview cleanup")
            docker("rm", "--force", container)
        for name, previous in [("AIO_PREVIEW_MODEL_KEY", old_model), ("AIO_VERIFICATION_RUN_ID", old_verification)]:
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        preview_info.write_text(
            json.dumps({"state": "stopped", "verification_id": verification}, indent=2) + "\n", encoding="utf-8"
        )
        print("Verification workbench stopped and its database cleaned.", flush=True)


if __name__ == "__main__":
    main()
