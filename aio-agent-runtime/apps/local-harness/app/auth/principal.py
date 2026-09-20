"""可信身份在服务边界构造，不把请求 JSON 本身当授权证明。"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Principal:
    org_id: UUID
    user_id: UUID
    membership_revision: int
    auth_session_id: UUID | None = None
    authentication_level: str = "standard"
    service_actor_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.org_id, UUID) or not isinstance(self.user_id, UUID):
            raise ValueError("Principal requires verified UUID identities")
        if type(self.membership_revision) is not int or self.membership_revision < 0:
            raise ValueError("Invalid membership revision")
