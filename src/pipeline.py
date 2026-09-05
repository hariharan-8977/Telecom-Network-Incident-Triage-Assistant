import time
from typing import List, Dict, Any, Optional
from src.models import TriageResult, Incident, Alert
from src.correlator import TopologyGraph, CorrelationEngine
from src.prioritizer import IncidentPrioritizer
from src.retriever import RunbookRetriever
from src.llm_triage import GeminiTriageReasoner


class IncidentTriagePipeline:
    """
    End-to-end incident triage orchestration pipeline.
    Connects:
    1. Alert ingestion & deduplication
    2. Noise isolation
    3. Graph-aware incident correlation
    4. Blast radius impact prioritization (P1-P4)
    5. Local hybrid runbook retrieval
    6. Grounded GenAI reasoner & zero-guess escalation
    """
    def __init__(self):
        self.topology = TopologyGraph()
        self.correlator = CorrelationEngine(self.topology)
        self.prioritizer = IncidentPrioritizer(self.topology)
        self.retriever = RunbookRetriever()
        self.reasoner = GeminiTriageReasoner()

    def process_alerts(self, alerts_data: List[Dict[str, Any]]) -> TriageResult:
        start_time = time.time()

        # Step 1 & 2: Correlation and Noise separation
        clustered_incidents, noise_alerts = self.correlator.correlate(alerts_data)

        # Step 3: Prioritization and impact scoring
        prioritized_incidents = self.prioritizer.prioritize_incidents(clustered_incidents)

        # Step 4 & 5: Runbook retrieval and grounded triage / escalation
        final_incidents: List[Incident] = []
        gemini_any_used = False

        for inc_dict in prioritized_incidents:
            # Retrieve runbook
            matched_rb, confidence, candidates = self.retriever.retrieve_runbook_for_incident(inc_dict)

            # Triage with LLM Reasoner or Escalation
            triage_output = self.reasoner.triage_incident(
                inc_dict,
                matched_rb,
                confidence,
                candidates
            )

            if triage_output.get("gemini_used"):
                gemini_any_used = True

            inc_obj = Incident(
                id=inc_dict["id"],
                title=inc_dict["title"],
                severity=inc_dict["severity"],
                priority=inc_dict["priority"],
                impact_score=inc_dict["impact_score"],
                root_cause_device=inc_dict["root_cause_device"],
                affected_devices=inc_dict["affected_devices"],
                alerts=inc_dict["alerts"],
                first_seen=inc_dict["first_seen"],
                last_seen=inc_dict["last_seen"],
                blast_radius_subscribers=inc_dict["blast_radius_subscribers"],
                matched_runbook_id=triage_output["matched_runbook_id"],
                runbook_confidence=triage_output["runbook_confidence"],
                is_escalated=triage_output["is_escalated"],
                escalation_package=triage_output["escalation_package"],
                triage_summary=triage_output["triage_summary"],
                recommended_actions=triage_output["recommended_actions"],
                safety_warnings=triage_output["safety_warnings"],
                citations=triage_output["citations"]
            )
            final_incidents.append(inc_obj)

        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        return TriageResult(
            total_raw_alerts=len(alerts_data),
            incident_count=len(final_incidents),
            noise_count=len(noise_alerts),
            incidents=final_incidents,
            noise_alerts=noise_alerts,
            execution_time_ms=elapsed_ms,
            gemini_used=gemini_any_used
        )
