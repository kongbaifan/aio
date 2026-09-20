from decimal import Decimal
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from ..api.v2.contracts import RequestContract


class KnowledgeCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    parser_profile: str = Field(min_length=1, max_length=64)
    embedding_model_id: UUID | None = None


class DocumentCreate(RequestContract):
    title: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=200)
    max_bytes: int = Field(ge=1, le=8388608, strict=True)
    visibility: Literal["restricted", "inherited"] = "restricted"
    document_id: UUID | None = None
    expected_revision: int | None = Field(default=None, ge=0, strict=True)

    @field_validator("filename")
    @classmethod
    def file_name(cls, value):
        if (
            any(ch in value for ch in ("/", "\\", ":"))
            or any(ord(ch) < 32 for ch in value)
            or PurePosixPath(value).suffix.lower() not in {".txt", ".md", ".csv", ".pdf", ".docx", ".xlsx"}
        ):
            raise ValueError("A supported document filename is required")
        return value


class DocumentVisibility(RequestContract):
    expected_revision: int = Field(ge=0, strict=True)
    visibility: Literal["restricted", "inherited"]


class KnowledgeSearch(RequestContract):
    query: str = Field(min_length=1, max_length=2048)
    request_id: UUID
    limit: int = Field(default=5, ge=1, le=10, strict=True)


class EmbeddingCreate(RequestContract):
    name: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=1024)
    secret_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    dimensions: int = Field(ge=1, le=3072, strict=True)
    input_price_per_million: Decimal = Field(ge=0, le=10000, max_digits=12, decimal_places=6)
    max_call_charge: Decimal = Field(gt=0, le=100, max_digits=12, decimal_places=6)
    batch_size: int = Field(default=32, ge=1, le=64, strict=True)


class EmbeddingReconciliation(RequestContract):
    amount: Decimal = Field(ge=0, le=100, max_digits=12, decimal_places=6)
    evidence_ref: str = Field(min_length=1, max_length=256)
