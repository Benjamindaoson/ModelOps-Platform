"""Validation and safe public API representations."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NAME = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
DIGEST = r"^[a-f0-9]{64}$"


class ArtifactIn(BaseModel):
    name: str = Field(pattern=NAME, max_length=63)
    version: int = Field(ge=1, le=1000000)
    source: str = Field(min_length=3, max_length=300)
    revision: str = Field(min_length=7, max_length=140)
    digest: str = Field(pattern=DIGEST)
    family: Literal["llm", "embedding", "asr", "tts"]

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        if any(x in value for x in ("\n", "\r", "\x00", "\\", "..")):
            raise ValueError("Invalid model source")
        return value


class DatasetIn(BaseModel):
    name: str = Field(pattern=NAME)
    version: int = Field(ge=1)
    uri: str = Field(min_length=4, max_length=500)
    digest: str = Field(pattern=DIGEST)
    train_count: int = Field(ge=1)
    heldout_count: int = Field(ge=20)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, uri: str) -> str:
        if not (uri.startswith("s3://") or uri.startswith("hf://")):
            raise ValueError("Dataset URI must be s3:// or hf://")
        if any(ch in uri for ch in ("\n", "\r", "\x00")) or ".." in uri:
            raise ValueError("Invalid dataset URI")
        return uri


class DeploymentIn(BaseModel):
    # Longest child suffix is -canary-cache (13); Kubernetes names max 63.
    name: str = Field(pattern=NAME, max_length=50)
    artifact_id: str
    engine: Literal["vllm", "sglang", "tei", "llamacpp"]
    replicas: int = Field(default=1, ge=0, le=32)
    gpu: int = Field(default=1, ge=0, le=16)


class ScaleIn(BaseModel):
    replicas: int = Field(ge=0, le=32)
    expected_generation: int = Field(ge=1)


class CanaryReleaseIn(BaseModel):
    artifact_id: str
    approval_id: str = Field(min_length=1, max_length=100)
    weight: int = Field(ge=0, le=100)
    expected_generation: int = Field(ge=1)


class CanaryStopIn(BaseModel):
    expected_generation: int = Field(ge=1)


class ReleaseIn(BaseModel):
    artifact_id: str
    expected_generation: int = Field(ge=1)
    approval_id: str = Field(min_length=1, max_length=100)


class FineTuneIn(BaseModel):
    # Argo Workflow names add -ft; do not exceed Kubernetes DNS length 63.
    name: str = Field(pattern=NAME, max_length=60)
    artifact_id: str
    dataset_id: str
    method: Literal["lora", "qlora", "full"] = "lora"
    epochs: int = Field(default=3, ge=1, le=30)
    batch_size: int = Field(default=1, ge=1, le=256)
    lr: float = Field(default=0.0002, gt=0, le=0.01)
    lora_rank: int = Field(default=8, ge=1, le=256)
    lora_alpha: int = Field(default=16, ge=1, le=512)
    gpu: int = Field(default=1, ge=0, le=16)
    gradient_accumulation_steps: int = Field(default=4, ge=1, le=256)
    output_name: str = Field(pattern=NAME)
    min_token_f1: float = Field(default=0.55, ge=0, le=1)


class EvaluationIn(BaseModel):
    artifact_id: str
    heldout_dataset_id: str
    report_digest: str = Field(pattern=DIGEST)
    model_digest: str = Field(pattern=DIGEST)
    passed: bool = False


class ApprovalIn(BaseModel):
    artifact_id: str
    evaluation_id: str
    reason: str = Field(min_length=6, max_length=1000)
