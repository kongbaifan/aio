"""Platform-only durable worker. Configure an org and explicit model endpoint/secret allowlists."""

import asyncio
import signal

from app.db.engine import Database
from app.observability import scrub
from app.platform_settings import DeploymentMode, WorkerSettings
from app.runtime.execution import ExecutionStore
from app.runtime.model_client import ModelFactory
from app.runtime.worker import DurableWorker, ToolDrivers
from app.execution.coordinator import SandboxCoordinator
from app.execution.sandbox_client import ManagerClient, SandboxPythonDriver
from app.workspaces.storage import BlobStore
from app.workspaces.service import ArtifactService
from app.skills.reader import SkillReferenceDriver
from app.skills.validation import SkillValidationStore
from app.skills.worker import SkillValidationWorker
from app.skills.archive_service import SkillArchiveService
from app.skills.archive_jobs import SkillArchiveJobs
from app.skills.archive_worker import SkillArchiveWorker
from app.connections.client import ConnectorClient
from app.connections.driver import MCPDriver, maintain_connections
from app.connections.service import ConnectionService
from app.knowledge.service import KnowledgeService
from app.knowledge.jobs import KnowledgeJobs
from app.knowledge.embedding import EmbeddingStore, Embedder
from app.knowledge.embedding_client import EmbeddingFactory
from app.knowledge.retrieval import KnowledgeDriver, KnowledgeRetrieval
from app.knowledge.worker import KnowledgeWorker


async def main():
    settings = WorkerSettings.from_env()
    db = Database(settings.database_url)
    scrub.register_process_secrets(settings)
    await asyncio.to_thread(db.verify_runtime_role)
    factory = ModelFactory(
        approved_origins=settings.approved_model_origins,
        secret_names=settings.approved_secret_names,
        production=settings.mode is DeploymentMode.PRODUCTION,
    )
    store = ExecutionStore(db, settings)
    manager_client = None
    connector_client = None
    registry = {"skill.read": SkillReferenceDriver(store)}
    if settings.manager_url:
        artifacts = ArtifactService(db, BlobStore(settings.artifact_root))
        manager_client = ManagerClient(settings.manager_url, settings.manager_token)
        driver = SandboxPythonDriver(SandboxCoordinator(store, artifacts), manager_client)
        registry.update({"sandbox.python": driver, "skill.python": driver})
    if settings.connector_url:
        connector_client = ConnectorClient(settings.connector_url, settings.connector_token)
        mcp_driver = MCPDriver(connector_client)
        registry.update({"mcp.http": mcp_driver, "mcp.stdio": mcp_driver})
    knowledge = KnowledgeService(db, settings, BlobStore(settings.artifact_root) if settings.artifact_root else None)
    knowledge_jobs = KnowledgeJobs(db, settings, knowledge)
    embedder = Embedder(EmbeddingStore(db, settings, knowledge_jobs, store), EmbeddingFactory(settings))
    registry["knowledge.search"] = KnowledgeDriver(KnowledgeRetrieval(db, store, embedder))
    worker = DurableWorker(store, settings.org_id, settings.worker_id, factory, ToolDrivers(registry))
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, worker.stopping.set)
        except NotImplementedError:
            pass
    try:
        tasks = [worker.serve()]
        if manager_client:
            from app.workspaces.checkpoints import maintain_checkpoints

            tasks.append(maintain_checkpoints(store.workspace, manager_client, settings.org_id, worker.stopping))
            validation = SkillValidationWorker(
                SkillValidationStore(db, settings),
                manager_client,
                settings.org_id,
                settings.worker_id + "-skills",
                stopping=worker.stopping,
            )
            tasks.append(validation.serve())
            tasks.append(
                SkillArchiveWorker(
                    SkillArchiveJobs(SkillArchiveService(db, settings, artifacts.blobs)),
                    manager_client,
                    settings.org_id,
                    settings.worker_id[:110] + "-skill-import",
                    stopping=worker.stopping,
                ).serve()
            )
            tasks.append(
                KnowledgeWorker(
                    knowledge_jobs,
                    manager_client,
                    embedder,
                    settings.org_id,
                    settings.worker_id[:110] + "-knowledge",
                    stopping=worker.stopping,
                ).serve()
            )
        if connector_client:
            tasks.append(
                maintain_connections(
                    ConnectionService(db, settings, connector_client), settings.org_id, worker.stopping
                )
            )
        await asyncio.gather(*tasks)
    finally:
        if manager_client:
            await manager_client.close()
        if connector_client:
            await connector_client.close()
        db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
