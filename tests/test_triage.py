import json
import os
import unittest
from src.correlator import TopologyGraph, CorrelationEngine
from src.prioritizer import IncidentPrioritizer
from src.retriever import RunbookRetriever
from src.pipeline import IncidentTriagePipeline


class TestTelecomIncidentTriage(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.pipeline = IncidentTriagePipeline()

    def _load_scenario(self, filename: str) -> dict:
        path = os.path.join(self.base_dir, "data", "scenarios", filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_topology_graph(self):
        topo = self.pipeline.topology
        self.assertIn("DWDM-CORE-NYC-BOS", topo.nodes)
        self.assertIn("CR-NYC-01", topo.nodes)
        self.assertTrue(topo.are_topologically_related("DWDM-CORE-NYC-BOS", "CR-NYC-01"))
        self.assertEqual(topo.get_tier("CR-NYC-01"), "Core")

    def test_noise_isolation_scenario_5(self):
        """Scenario 5 has 9 alerts: 3 correlated memory alarms and 6 background noise alarms."""
        sc = self._load_scenario("scenario_5_noisy_stream.json")
        result = self.pipeline.process_alerts(sc["alerts"])
        self.assertEqual(result.incident_count, 1)
        self.assertEqual(result.noise_count, 6)
        noise_ids = {a.id for a in result.noise_alerts}
        self.assertIn("ALT-9501", noise_ids)
        self.assertIn("ALT-9503", noise_ids)

    def test_fiber_cut_correlation_and_grounding(self):
        """Scenario 1: Core fiber break must correlate cascading alarms into 1 P1 incident citing RB-OPT-01."""
        sc = self._load_scenario("scenario_1_fiber_cut.json")
        result = self.pipeline.process_alerts(sc["alerts"])
        self.assertEqual(result.incident_count, 1)
        self.assertEqual(result.noise_count, 4)

        inc = result.incidents[0]
        self.assertEqual(inc.priority, "P1")
        self.assertEqual(inc.root_cause_device, "DWDM-CORE-NYC-BOS")
        self.assertEqual(inc.matched_runbook_id, "RB-OPT-01")
        self.assertFalse(inc.is_escalated)
        self.assertGreaterEqual(len(inc.recommended_actions), 2)
        # Verify citation
        self.assertTrue(any("RB-OPT-01" in c for c in inc.citations))

    def test_5g_auth_storm(self):
        """Scenario 2: 5G RAN signaling overload must cite RB-RAN-03."""
        sc = self._load_scenario("scenario_2_auth_storm.json")
        result = self.pipeline.process_alerts(sc["alerts"])
        self.assertEqual(result.incident_count, 1)
        inc = result.incidents[0]
        self.assertEqual(inc.root_cause_device, "gNB-MAN-101")
        self.assertEqual(inc.matched_runbook_id, "RB-RAN-03")
        self.assertFalse(inc.is_escalated)

    def test_uncovered_anomaly_escalation(self):
        """Scenario 4: Zero-day quantum anomaly without matching runbook MUST escalate with evidence."""
        sc = self._load_scenario("scenario_4_uncovered_anomaly.json")
        result = self.pipeline.process_alerts(sc["alerts"])
        self.assertEqual(result.incident_count, 1)
        inc = result.incidents[0]
        self.assertTrue(inc.is_escalated, "Incident must be escalated because no runbook covers quantum decoherence")
        self.assertIsNone(inc.matched_runbook_id)
        self.assertIsNotNone(inc.escalation_package)
        self.assertIn("Quantum", inc.escalation_package.target_team)
        self.assertGreater(len(inc.escalation_package.suggested_diagnostics), 1)
        self.assertEqual(len(inc.escalation_package.evidence_alerts), 3)

    def test_power_grid_outage(self):
        """Scenario 3: AC mains failure and battery depletion must match RB-PWR-05."""
        sc = self._load_scenario("scenario_3_power_grid.json")
        result = self.pipeline.process_alerts(sc["alerts"])
        self.assertEqual(result.incident_count, 1)
        inc = result.incidents[0]
        self.assertEqual(inc.matched_runbook_id, "RB-PWR-05")
        self.assertFalse(inc.is_escalated)


if __name__ == "__main__":
    unittest.main()
