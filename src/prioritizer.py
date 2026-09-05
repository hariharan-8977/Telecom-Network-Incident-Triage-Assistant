from typing import List, Dict, Any
from src.models import Incident, Alert
from src.correlator import TopologyGraph


class IncidentPrioritizer:
    """
    Deterministic prioritization engine for telecom incidents.
    Calculates blast radius, subscriber impact, and priority tier (P1-P4).
    """
    TIER_FACTORS = {
        "Core": 4.0,
        "Aggregation": 2.5,
        "Edge": 1.8,
        "Access": 1.0,
        "Facility": 1.2
    }

    SEVERITY_FACTORS = {
        "CRITICAL": 1.0,
        "MAJOR": 0.75,
        "WARNING": 0.4,
        "INFO": 0.1
    }

    def __init__(self, topology: TopologyGraph):
        self.topology = topology

    def calculate_incident_impact(self, inc_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Compute blast radius and impact score for an incident."""
        root_dev = inc_dict["root_cause_device"]
        root_tier = self.topology.get_tier(root_dev)
        tier_multiplier = self.TIER_FACTORS.get(root_tier, 1.0)
        sev_multiplier = self.SEVERITY_FACTORS.get(inc_dict["severity"], 0.5)

        # Sum unique subscribers impacted across affected devices
        total_subscribers = 0
        counted_parents = set()
        for dev_id in inc_dict["affected_devices"]:
            subs = self.topology.get_subscribers(dev_id)
            # Avoid double counting if parent core already counted
            node = self.topology.nodes.get(dev_id)
            if node and node.get("parent") and node["parent"] in counted_parents:
                continue
            total_subscribers += subs
            counted_parents.add(dev_id)

        # Logarithmic scaling for subscribers (e.g. 500k subs -> ~50 points)
        import math
        sub_score = min(50.0, math.log10(max(10, total_subscribers)) * 8.5)

        # Device spread factor
        spread_score = min(20.0, len(inc_dict["affected_devices"]) * 4.0)

        # Alert volume factor
        alert_score = min(15.0, len(inc_dict["alerts"]) * 1.5)

        # Emergency multiplier for active power or buffer breakdown
        emergency_boost = 0.0
        for a in inc_dict.get("alerts", []):
            if a.event_type in ("EST_BATTERY_RUNTIME_LOW", "LOSS_OF_SIGNAL", "ASIC_MICROCODE_TRAP", "AUTH_FAILURE_BURST"):
                emergency_boost += 12.0
                break

        # Composite impact score
        raw_score = ((sub_score + spread_score + alert_score) * (tier_multiplier / 2.5) * sev_multiplier) + emergency_boost
        impact_score = round(min(100.0, max(5.0, raw_score)), 1)

        # Priority categorization
        if impact_score >= 70.0 or (root_tier == "Core" and inc_dict["severity"] == "CRITICAL"):
            priority = "P1"
        elif impact_score >= 38.0:
            priority = "P2"
        elif impact_score >= 20.0:
            priority = "P3"
        else:
            priority = "P4"

        inc_dict["impact_score"] = impact_score
        inc_dict["priority"] = priority
        inc_dict["blast_radius_subscribers"] = total_subscribers

        return inc_dict

    def prioritize_incidents(self, incident_dicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process all incidents and sort them in descending order of priority and impact."""
        scored = [self.calculate_incident_impact(inc) for inc in incident_dicts]
        priority_rank = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
        scored.sort(key=lambda x: (priority_rank.get(x["priority"], 0), x["impact_score"]), reverse=True)
        return scored
