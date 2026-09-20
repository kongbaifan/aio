"""Administrative routes share authentication/CSRF middleware and never expose database/runtime credentials."""

from uuid import UUID
import asyncio

from fastapi import Depends, Query
from pydantic import Field

from ..api.v2.contracts import RequestContract
from .contracts import (
    AgentCreate,
    BudgetUpdate,
    SharedBudgetUpdate,
    DepartmentCreate,
    DepartmentMember,
    GrantCreate,
    MemberCreate,
    MemberUpdate,
    ModelCreate,
    OrganizationPolicy,
    ResourceStatus,
    ToolCreate,
)
from .service import AdminService


class DepartmentStatus(RequestContract):
    active: bool = Field(strict=True)


def register_admin_routes(app, admin: AdminService, principal):
    @app.get("/api/v2/directory")
    async def directory(identity=Depends(principal)):
        return await asyncio.to_thread(admin.directory, identity)

    @app.get("/api/v2/admin/options")
    async def options(identity=Depends(principal)):
        return await asyncio.to_thread(admin.options, identity)

    @app.get("/api/v2/admin/members")
    async def members(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.members, identity)}

    @app.post("/api/v2/admin/members", status_code=201)
    async def create_member(body: MemberCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.create_member, identity, body)

    @app.patch("/api/v2/admin/members/{user_id}")
    async def update_member(user_id: UUID, body: MemberUpdate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.update_member, identity, user_id, body)

    @app.get("/api/v2/admin/departments")
    async def departments(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.departments, identity)}

    @app.post("/api/v2/admin/departments", status_code=201)
    async def create_department(body: DepartmentCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.create_department, identity, body.name)

    @app.patch("/api/v2/admin/departments/{department_id}")
    async def set_department_status(department_id: UUID, body: DepartmentStatus, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_department_active, identity, department_id, body.active)

    @app.put("/api/v2/admin/departments/{department_id}/members")
    async def set_department_member(department_id: UUID, body: DepartmentMember, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_department_member, identity, department_id, body.user_id, body.role)

    @app.delete("/api/v2/admin/departments/{department_id}/members/{user_id}")
    async def remove_department_member(department_id: UUID, user_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_department_member, identity, department_id, user_id, None)

    @app.get("/api/v2/resources/{resource_id}/grants")
    async def grants(resource_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(admin.grants, identity, resource_id)

    @app.put("/api/v2/resources/{resource_id}/grants")
    async def set_grants(resource_id: UUID, body: GrantCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_grants, identity, resource_id, body)

    @app.delete("/api/v2/resources/{resource_id}/grants/{grant_id}")
    async def remove_grant(
        resource_id: UUID,
        grant_id: UUID,
        subject_type: str = Query(pattern="^(user|department)$"),
        identity=Depends(principal),
    ):
        return await asyncio.to_thread(admin.remove_grant, identity, resource_id, grant_id, subject_type)

    @app.patch("/api/v2/resources/{resource_id}/status")
    async def set_resource_status(resource_id: UUID, body: ResourceStatus, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_status, identity, resource_id, body.status, body.expected_revision)

    @app.get("/api/v2/admin/models")
    async def models(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.models, identity)}

    @app.post("/api/v2/admin/models", status_code=201)
    async def create_model(body: ModelCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.create_model, identity, body)

    @app.get("/api/v2/admin/tools")
    async def tools(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.tools, identity)}

    @app.post("/api/v2/admin/tools", status_code=201)
    async def create_tool(body: ToolCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.create_tool, identity, body)

    @app.get("/api/v2/admin/agents")
    async def agents(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.agents, identity)}

    @app.post("/api/v2/admin/agents", status_code=201)
    async def create_agent(body: AgentCreate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.create_agent, identity, body)

    @app.get("/api/v2/admin/budgets")
    async def budgets(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.budgets, identity)}

    @app.get("/api/v2/admin/shared-budgets")
    async def shared_budgets(identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.shared_budgets, identity)}

    @app.put("/api/v2/admin/shared-budgets/organization")
    async def organization_budget(body: SharedBudgetUpdate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_shared_budget, identity, None, body.hard_limit, body.expected_revision)

    @app.put("/api/v2/admin/shared-budgets/departments/{department_id}")
    async def department_budget(department_id: UUID, body: SharedBudgetUpdate, identity=Depends(principal)):
        return await asyncio.to_thread(
            admin.set_shared_budget, identity, department_id, body.hard_limit, body.expected_revision
        )

    @app.put("/api/v2/admin/budgets/{user_id}")
    async def set_budget(user_id: UUID, body: BudgetUpdate, identity=Depends(principal)):
        return await asyncio.to_thread(admin.set_budget, identity, user_id, body.hard_limit)

    @app.get("/api/v2/usage")
    async def own_usage(identity=Depends(principal)):
        return await asyncio.to_thread(admin.own_budget, identity)

    @app.get("/api/v2/admin/audit")
    async def audit(limit: int = Query(default=100, ge=1, le=200), identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.audit_events, identity, limit)}

    @app.get("/api/v2/admin/runs")
    async def operations(limit: int = Query(default=100, ge=1, le=200), identity=Depends(principal)):
        return {"items": await asyncio.to_thread(admin.operations, identity, limit)}

    @app.post("/api/v2/admin/runs/{run_id}/stop")
    async def stop_run(run_id: UUID, identity=Depends(principal)):
        return await asyncio.to_thread(admin.stop_run, identity, run_id)

    @app.get("/api/v2/admin/policy")
    async def policy(identity=Depends(principal)):
        return await asyncio.to_thread(admin.policy, identity)

    @app.put("/api/v2/admin/policy")
    async def update_policy(body: OrganizationPolicy, identity=Depends(principal)):
        return await asyncio.to_thread(admin.update_policy, identity, body)
