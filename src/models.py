from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class Alert(BaseModel):
    id: str
    timestamp: str
    device_id: str
    device_tier: str = "Access"  # Core, Aggregation, Edge, Access, Facility
    severity: str = "INFO"      # CRITICAL, MAJOR, WARNING, INFO
    event_type: str
    message: str
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    source_subsystem: Optional[str] = None
    is_noise: bool = False


class NetworkNode(BaseModel):
    id: str
    name: str
    tier: str
    type: str
    location: str
    subscribers_impacted: int = 0
    parent: Optional[str] = None


class RunbookSection(BaseModel):
    section_id: str
    title: str
    description: str
    commands: List[str] = []


class Runbook(BaseModel):
    id: str
    title: str
    domain: str
    applies_to: List[str] = []
    severity: str
    symptoms: List[str] = []
    triage_steps: List[str] = []
    mitigation_sections: List[RunbookSection] = []
    safety_warnings: List[str] = []
    raw_markdown: str = ""


class EscalationPackage(BaseModel):
    incident_id: str
    reason: str
    urgency: str
    target_team: str
    affected_devices: List[str]
    timeline_summary: str
    evidence_alerts: List[Dict[str, Any]]
    ruled_out_runbooks: List[str]
    suggested_diagnostics: List[str]


class Incident(BaseModel):
    id: str
    title: str
    severity: str
    priority: str  # P1, P2, P3, P4
    impact_score: float
    root_cause_device: str
    affected_devices: List[str]
    alerts: List[Alert]
    first_seen: str
    last_seen: str
    blast_radius_subscribers: int
    matched_runbook_id: Optional[str] = None
    runbook_confidence: float = 0.0
    is_escalated: bool = False
    escalation_package: Optional[EscalationPackage] = None
    triage_summary: Optional[str] = None
    recommended_actions: List[Dict[str, Any]] = []
    safety_warnings: List[str] = []
    citations: List[str] = []


class TriageResult(BaseModel):
    total_raw_alerts: int
    incident_count: int
    noise_count: int
    incidents: List[Incident]
    noise_alerts: List[Alert]
    execution_time_ms: float
    gemini_used: bool
