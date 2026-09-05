import os
import json
from typing import Dict, Any, Optional, List
import google.generativeai as genai
from src.models import Runbook, EscalationPackage, Incident, Alert


class GeminiTriageReasoner:
    """
    GenAI Incident Triage Reasoner powered by Gemini.
    Strictly grounded in system runbooks with zero hallucination and explicit escalation discipline.
    """
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.client_available = False
        self.model = None

        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                # Try preferred fast models
                model_name = "gemini-1.5-flash"
                self.model = genai.GenerativeModel(model_name)
                self.client_available = True
            except Exception as e:
                print(f"Warning: Could not initialize Gemini client: {e}")
                self.client_available = False

    def triage_incident(
        self,
        incident_dict: Dict[str, Any],
        matched_runbook: Optional[Runbook],
        confidence: float,
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes triage for an incident:
        - If matched_runbook is present: Generate grounded recommendations citing runbook sections.
        - If matched_runbook is None: Generate structured escalation package without guessing.
        """
        if matched_runbook is None or confidence < 0.45:
            return self._handle_escalation(incident_dict, candidates)
        else:
            return self._handle_runbook_triage(incident_dict, matched_runbook, confidence)

    def _handle_runbook_triage(
        self,
        incident_dict: Dict[str, Any],
        runbook: Runbook,
        confidence: float
    ) -> Dict[str, Any]:
        """Grounded triage citing exact runbook sections and commands."""
        # Check if Gemini can be called
        if self.client_available and self.model:
            try:
                return self._call_gemini_runbook_triage(incident_dict, runbook, confidence)
            except Exception as e:
                print(f"Gemini API call failed, falling back to deterministic triage: {e}")

        # Deterministic fallback logic
        return self._deterministic_runbook_triage(incident_dict, runbook, confidence)

    def _call_gemini_runbook_triage(
        self,
        incident_dict: Dict[str, Any],
        runbook: Runbook,
        confidence: float
    ) -> Dict[str, Any]:
        """LLM-grounded reasoning prompt."""
        alerts_summary = "\n".join([
            f"- [{a.timestamp}] {a.device_id} ({a.severity}) {a.event_type}: {a.message}"
            for a in incident_dict["alerts"][:10]
        ])

        prompt = f"""You are the Telecom NOC Incident Triage Assistant.
You must adhere STRICTLY to the provided runbook. Do NOT invent procedures, CLI commands, or actions not grounded in the runbook.

INCIDENT CONTEXT:
- Incident ID: {incident_dict['id']}
- Priority: {incident_dict['priority']} ({incident_dict['severity']})
- Root Device: {incident_dict['root_cause_device']}
- Affected Devices: {', '.join(incident_dict['affected_devices'])}
- Impact Score: {incident_dict['impact_score']} / Blast Radius: {incident_dict['blast_radius_subscribers']} subscribers

ALERTS TIMELINE:
{alerts_summary}

SYSTEM RUNBOOK REFERENCE (GROUND TRUTH):
- Runbook ID: {runbook.id}
- Title: {runbook.title}
- Domain: {runbook.domain}
- Applicable Devices: {', '.join(runbook.applies_to)}
- Content:
{runbook.raw_markdown}

TASK:
Provide a grounded triage response in valid JSON with this exact structure:
{{
  "triage_summary": "Concise 2-sentence summary of the root cause and why this runbook was cited.",
  "citations": ["Exact Runbook ID and Section titles cited, e.g. 'RB-OPT-01 Section 1.1'"],
  "recommended_actions": [
    {{
      "step": 1,
      "title": "Action title from runbook",
      "command": "Exact CLI command from runbook or blank",
      "purpose": "Why this action is required"
    }}
  ],
  "safety_warnings": ["Safety precautions verbatim or summarized from the runbook"]
}}
Return ONLY valid JSON.
"""
        response = self.model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.1}
        )
        data = json.loads(response.text)

        return {
            "matched_runbook_id": runbook.id,
            "runbook_confidence": confidence,
            "is_escalated": False,
            "escalation_package": None,
            "triage_summary": data.get("triage_summary", f"Grounded response based on {runbook.id}"),
            "citations": data.get("citations", [runbook.id]),
            "recommended_actions": data.get("recommended_actions", []),
            "safety_warnings": data.get("safety_warnings", runbook.safety_warnings),
            "gemini_used": True
        }

    def _deterministic_runbook_triage(
        self,
        incident_dict: Dict[str, Any],
        runbook: Runbook,
        confidence: float
    ) -> Dict[str, Any]:
        """Deterministic compiler for runbook guidance."""
        actions = []
        citations = []

        # Triage verification step
        if runbook.triage_steps:
            actions.append({
                "step": 1,
                "title": "Initial Triage Verification",
                "command": runbook.triage_steps[0] if runbook.triage_steps else "",
                "purpose": f"Confirm physical/logical telemetry on {incident_dict['root_cause_device']}"
            })
            citations.append(f"{runbook.id} Triage Verification Steps")

        # Mitigation sections
        for idx, sec in enumerate(runbook.mitigation_sections, start=2):
            cmd = sec.commands[0] if sec.commands else ""
            actions.append({
                "step": idx,
                "title": sec.title,
                "command": cmd,
                "purpose": sec.description.splitlines()[0] if sec.description else "Mitigation step"
            })
            citations.append(f"{runbook.id} {sec.section_id}")

        summary = (
            f"Incident correlated to root cause on {incident_dict['root_cause_device']}. "
            f"Grounded in approved NOC Runbook {runbook.id} ({runbook.title}) with {int(confidence*100)}% match confidence."
        )

        return {
            "matched_runbook_id": runbook.id,
            "runbook_confidence": confidence,
            "is_escalated": False,
            "escalation_package": None,
            "triage_summary": summary,
            "citations": citations,
            "recommended_actions": actions,
            "safety_warnings": runbook.safety_warnings,
            "gemini_used": False
        }

    def _handle_escalation(
        self,
        incident_dict: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Mandatory escalation workflow:
        When no runbook covers the incident, escalate with structured context assembled so far.
        """
        # Formulate ruled out runbooks
        ruled_out = [c["title"] for c in candidates[:3]] if candidates else ["Standard Core/RAN Runbooks"]

        timeline_lines = [
            f"- {a.timestamp}: {a.device_id} reported {a.event_type} - {a.message}"
            for a in incident_dict["alerts"]
        ]
        timeline_str = "\n".join(timeline_lines)

        # Decide target engineering team
        root_dev = incident_dict["root_cause_device"]
        if "QKD" in root_dev or "QUANTUM" in incident_dict["title"].upper():
            target_team = "L3 Advanced Photonic & Quantum Transport Engineering (Tier 4 / Vendor TAC)"
            suggested_diagnostics = [
                "Attach optical spectrum analyzer to dark-fiber tap port 4",
                "Execute memory register dump: show hardware registers fpga-cryo 0x0..0xFFFF",
                "Engage vendor hardware engineering TAC ticket with severity P1-Critical",
                "Isolate quantum key distribution channel to fallback Classical AES-256 link"
            ]
        else:
            target_team = "L3 Network Infrastructure Systems Architecture Desk"
            suggested_diagnostics = [
                f"Capture live packet trace on uplink interfaces of {root_dev}",
                f"Extract core crash dump and syslogs from {root_dev}",
                "Review recent change window tickets and vendor software advisories"
            ]

        escalation_pkg = EscalationPackage(
            incident_id=incident_dict["id"],
            reason="No authorized troubleshooting runbook matched this anomaly signature. Automatic escalation triggered to prevent unauthorized or speculative intervention.",
            urgency=incident_dict["priority"],
            target_team=target_team,
            affected_devices=incident_dict["affected_devices"],
            timeline_summary=timeline_str,
            evidence_alerts=[
                {"id": a.id, "timestamp": a.timestamp, "device": a.device_id, "event": a.event_type, "message": a.message}
                for a in incident_dict["alerts"]
            ],
            ruled_out_runbooks=ruled_out,
            suggested_diagnostics=suggested_diagnostics
        )

        summary = (
            f"ESCALATION MANDATE: Incident on {root_dev} is NOT covered by any approved NOC runbook. "
            f"The system has assembled the full correlation evidence package and escalated to {target_team} "
            f"so engineers start from documented telemetry rather than from scratch."
        )

        return {
            "matched_runbook_id": None,
            "runbook_confidence": 0.0,
            "is_escalated": True,
            "escalation_package": escalation_pkg,
            "triage_summary": summary,
            "citations": ["NO_RUNBOOK_MATCH (Disciplined Escalation)"],
            "recommended_actions": [
                {
                    "step": idx + 1,
                    "title": f"Escalation Diagnostic Step {idx + 1}",
                    "command": cmd,
                    "purpose": "Evidence capture for L3 engineering"
                }
                for idx, cmd in enumerate(suggested_diagnostics)
            ],
            "safety_warnings": [
                "Do NOT attempt manual reboot or ad-hoc config changes on uncovered hardware.",
                "Preserve all volatile crash dumps and register state before engaging field dispatch."
            ],
            "gemini_used": False
        }
