from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CompanyCode = Literal["SKO", "SKOH", "SKBM", "SKBA", "SKOJ", "SKOY"]
TransportMode = Literal["SEA", "AIR", "RAIL", "ROAD", "MULTIMODAL"]
EventStatus = Literal["ACTIVE", "WATCH", "IMPROVING", "RESOLVED"]
EventSeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
EventType = Literal[
    "ROUTE_DISRUPTION",
    "PORT_CONGESTION",
    "WEATHER",
    "LABOR_STRIKE",
    "GEOPOLITICAL",
    "INFRASTRUCTURE",
    "CAPACITY_SHORTAGE",
    "CARRIER_ISSUE",
    "RATE_SURGE",
    "REGULATION",
    "DANGEROUS_GOODS",
    "OTHER",
]
ReviewStatus = Literal["PENDING", "APPROVED", "EDITED", "REJECTED"]
# v2.1: 리스크 방향 / 영향 경로 (기존 저장 Run 호환을 위해 기본값 제공)
RiskDirection = Literal["RISK_INCREASE", "RISK_DECREASE"]
ImpactPath = Literal["DIRECT", "INDIRECT"]


class Evidence(BaseModel):
    article_id: str
    title: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""


class ExternalMiCandidate(BaseModel):
    candidate_id: str
    cluster_hint: str = ""
    headline: str
    short_summary: str
    published_from: str = ""
    valid_to_hint: str | None = None
    location_mentions: list[str] = Field(default_factory=list)
    corridor_mentions: list[str] = Field(default_factory=list)
    transport_mode_hints: list[str] = Field(default_factory=list)
    risk_keyword_hints: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class ExternalMiCandidateEnvelope(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = ""
    source_stage: str = "EXTERNAL_GEMINI_CANDIDATES"
    generation_status: str = "SUCCESS"
    warnings: list[str] = Field(default_factory=list)
    input_summary: dict = Field(default_factory=dict)
    candidates: list[ExternalMiCandidate]


class LocationRef(BaseModel):
    code: str = ""
    name: str = ""
    location_type: str = ""
    radius_km: float | None = None


class AffectedLocation(BaseModel):
    code: str
    name: str
    location_type: str
    lat: float
    lon: float
    radius_km: float


class AffectedLane(BaseModel):
    pol_codes: list[str] = Field(default_factory=list)
    pod_codes: list[str] = Field(default_factory=list)
    origin_regions: list[str] = Field(default_factory=list)
    destination_regions: list[str] = Field(default_factory=list)
    corridor: str = ""


class ExpectedDelayDays(BaseModel):
    min: int = 0
    max: int = 0


class RefinedMiEvent(BaseModel):
    event_id: str
    source_type: str = "INTERNAL_REFINED_MI"
    source_candidate_ids: list[str] = Field(default_factory=list)
    cluster_key: str
    status: EventStatus
    event_type: EventType
    severity: EventSeverity
    direction: RiskDirection = "RISK_INCREASE"
    impact_path: ImpactPath = "DIRECT"
    confidence: float = Field(ge=0, le=1)
    headline: str
    summary: str
    first_seen_at: str = ""
    last_updated_at: str = ""
    valid_from: str
    valid_to: str | None = None
    transport_modes: list[TransportMode] = Field(default_factory=list)
    affected_corridors: list[str] = Field(default_factory=list)
    location_refs: list[LocationRef] = Field(default_factory=list)
    affected_locations: list[AffectedLocation] = Field(default_factory=list)
    unresolved_locations: list[LocationRef] = Field(default_factory=list)
    affected_lanes: list[AffectedLane] = Field(default_factory=list)
    expected_delay_days: ExpectedDelayDays | None = None
    impact_types: list[str] = Field(default_factory=list)
    cause_keywords: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    review_status: ReviewStatus = "PENDING"


class RefineRequest(BaseModel):
    candidate_envelope: ExternalMiCandidateEnvelope
    company_codes: list[CompanyCode] = Field(
        default_factory=lambda: ["SKO", "SKOH", "SKBM", "SKBA", "SKOJ", "SKOY"]
    )
    supplemental_context: str = Field(default="", max_length=12000)


class RefineResponse(BaseModel):
    analysis_id: str
    generated_at: datetime
    model_service: str = "ACTIFY"
    source_candidate_count: int
    events: list[RefinedMiEvent]
    warnings: list[str] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    analysis_id: str
    events: list[RefinedMiEvent]


class ReviewResponse(BaseModel):
    analysis_id: str
    approved_count: int
    rejected_count: int
    canonical_payload: dict
