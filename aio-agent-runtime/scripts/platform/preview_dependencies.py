"""Synthetic workbench fixture backed by a real signed NumPy/Pandas image and distinct Skill reviewer."""

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select


async def seed(database, settings, principal, reviewer_id, model_id, departments, manager_client):
    from app.admin.contracts import AgentCreate, GrantCreate
    from app.admin.service import AdminService
    from app.auth.principal import Principal
    from app.db import schema as s
    from app.platform_settings import DeploymentMode
    from app.skills.contracts import DependencySkillPackage, SkillCreate, SkillValidate, SkillReview
    from app.skills.service import SkillService
    from app.skills.validation import SkillValidationStore
    from app.skills.worker import SkillValidationWorker

    if settings.mode is not DeploymentMode.TEST:
        raise RuntimeError("Dependency fixtures are never a production approval")
    root = Path(__file__).resolve().parents[2]
    package = DependencySkillPackage.model_validate_json(
        (root / "config/skill-packages/example-analytics.json").read_bytes()
    )
    service = SkillService(database, settings)
    skill = service.create(principal, SkillCreate(package=package, sandbox_profile="analytics"))
    service.submit(principal, skill["id"], SkillValidate(expected_revision=0, reviewer_id=reviewer_id))
    result = await SkillValidationWorker(
        SkillValidationStore(database, settings), manager_client, principal.org_id, "dependency-seed-" + uuid4().hex[:8]
    ).run_once()
    if not result or result["state"] != "passed":
        raise RuntimeError("Actual dependency Skill validation did not pass")
    with database.scoped(principal.org_id, reviewer_id) as c:
        revision = c.execute(
            select(s.memberships.c.revision).where(
                s.memberships.c.org_id == principal.org_id, s.memberships.c.user_id == reviewer_id
            )
        ).scalar_one()
    reviewer = Principal(principal.org_id, reviewer_id, revision)
    detail = service.detail(principal, skill["id"])
    service.review(
        reviewer,
        skill["id"],
        SkillReview(
            expected_revision=detail["revision"],
            decision="approve",
            note="Synthetic workbench fixture; exact dependency/runtime tests passed and cell cleanup confirmed.",
        ),
    )
    admin = AdminService(database, settings)
    agent = admin.create_agent(
        principal,
        AgentCreate(
            name="固定依赖分析助手",
            version="1",
            instruction="使用经审核的固定 NumPy/Pandas 环境计算；不安装包或修改系统环境。",
            model_id=UUID(str(model_id)),
            skill_ids=(skill["id"],),
            run_budget=Decimal(".1"),
            max_rounds=4,
        ),
    )
    for department in departments:
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
    return {
        "agent_id": str(agent["id"]),
        "skill_id": str(skill["id"]),
        "runtime_manifest_digest": package.runtime_manifest_digest,
    }
