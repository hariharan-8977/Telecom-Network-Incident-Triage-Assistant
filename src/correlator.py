import json
import os
from datetime import datetime
from typing import List, Dict, Tuple, Set, Optional
from src.models import Alert, Incident


class TopologyGraph:
    """Represents telecom network topology with path and hierarchy awareness."""
    def __init__(self, topology_path: Optional[str] = None):
        if not topology_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            topology_path = os.path.join(base_dir, "data", "topology.json")

        self.nodes: Dict[str, dict] = {}
        self.adjacency: Dict[str, Set[str]] = {}
        self.parents: Dict[str, str] = {}
        self.children: Dict[str, Set[str]] = {}

        if os.path.exists(topology_path):
            with open(topology_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for node in data.get("nodes", []):
                    nid = node["id"]
                    self.nodes[nid] = node
                    self.adjacency[nid] = set()
                    self.children[nid] = set()
                    if node.get("parent"):
                        self.parents[nid] = node["parent"]

                for link in data.get("links", []):
                    src, tgt = link["source"], link["target"]
                    if src in self.adjacency and tgt in self.adjacency:
                        self.adjacency[src].add(tgt)
                        self.adjacency[tgt].add(src)

                for child, parent in self.parents.items():
                    if parent in self.children:
                        self.children[parent].add(child)

    def are_topologically_related(self, dev1: str, dev2: str, max_hops: int = 3) -> bool:
        """Check if two devices are close or hierarchical in the network topology."""
        if dev1 == dev2:
            return True
        if dev1 not in self.nodes or dev2 not in self.nodes:
            # If not in catalog, treat same device as related, others not
            return dev1 == dev2

        # Check direct parent/child
        if self.parents.get(dev1) == dev2 or self.parents.get(dev2) == dev1:
            return True

        # Check common parent
        p1 = self.parents.get(dev1)
        p2 = self.parents.get(dev2)
        if p1 and p2 and p1 == p2:
            return True

        # Check BFS within max_hops
        visited = {dev1}
        queue = [(dev1, 0)]
        while queue:
            curr, dist = queue.pop(0)
            if curr == dev2:
                return True
            if dist < max_hops:
                for neighbor in self.adjacency.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, dist + 1))
        return False

    def get_tier(self, device_id: str) -> str:
        if device_id in self.nodes:
            return self.nodes[device_id].get("tier", "Access")
        return "Access"

    def get_subscribers(self, device_id: str) -> int:
        if device_id in self.nodes:
            return self.nodes[device_id].get("subscribers_impacted", 5000)
        return 5000


class CorrelationEngine:
    """
    Deterministic alert grouping, deduplication, and noise separation engine.
    Ensures noise is NOT forced into incidents.
    """
    # Known benign / routine events that do not constitute an active outage unless clustered
    NOISE_EVENT_TYPES = {
        "NTP_OFFSET_DRIFT", "NTP_SYNC_OK", "ROUTINE_STATS_UPLOAD", "FAN_SPEED_STEP",
        "SSH_AUTH_FAIL_SINGLE", "SNMP_POLL_TIMEOUT_TRANSIENT", "RECTIFIER_HEALTH_CHECK",
        "DHCP_LEASE_RENEW_NORMAL", "CONFIG_COMMIT_LOG", "LLDP_NEIGHBOR_DISCOVERY",
        "ROUTINE_GPS_LOCK", "RADIUS_ACCOUNTING_BATCH", "USER_ATTACH_MILESTONE",
        "CABINET_DOOR_OPEN", "PORT_TRAFFIC_SHAPER_BURST", "LASER_BIAS_CURRENT_NORMAL",
        "NEIGHBOR_BEACON_DISCOVERY"
    }

    # Causal relationship domains for alert clustering
    CAUSAL_DOMAINS = {
        "OPTICAL_TRANSPORT": {"LOSS_OF_SIGNAL", "OSC_FRAME_LOSS", "INTERFACE_DOWN", "BGP_NEIGHBOR_DOWN",
                              "OSPF_ADJACENCY_CHANGE", "HIGH_PACKET_LOSS", "BACKHAUL_LATENCY_HIGH",
                              "ROUTE_WITHDRAWAL_BURST", "AUTOMATIC_PROTECTION_SWITCH_FAILED",
                              "RRC_DROP_RATE_SPIKE"},
        "RADIO_SIGNALING": {"AUTH_FAILURE_BURST", "RRC_CONNECTION_REJECT_HIGH", "NGAP_SETUP_FAILURE",
                            "CELL_HANDOVER_CONGESTION", "HIGH_CONTROL_PLANE_LATENCY", "S1AP_TRANSPORT_TIMEOUT"},
        "FACILITY_POWER": {"MAINS_AC_POWER_FAIL", "BATTERY_DISCHARGE_ACTIVE", "POWER_ANOMALY_DOWNGRADE",
                           "EST_BATTERY_RUNTIME_LOW", "RECTIFIER_FAIL", "GENERATOR_START_FAIL"},
        "ROUTER_RESOURCES": {"HIGH_MEMORY_USAGE", "BUFFER_ALLOCATION_FAILURE", "PACKET_DROP_QUEUE",
                             "CPU_HIGH_RPD", "ROUTE_CACHE_EXHAUSTION"},
        "QUANTUM_OPTICAL": {"QUANTUM_PHASE_DECOHERENCE", "ASIC_MICROCODE_TRAP", "SYNC_TOKEN_RING_CORRUPTION"}
    }

    def __init__(self, topology: Optional[TopologyGraph] = None):
        self.topology = topology or TopologyGraph()

    def parse_time(self, ts_str: str) -> float:
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return 0.0

    def is_likely_noise(self, alert: Alert, all_alerts: List[Alert]) -> bool:
        """
        Identify standalone noise alerts:
        1. Explicitly matched benign/routine telemetry
        2. Or INFO severity alerts with no related alarms in the time window
        3. Or single isolated minor warnings on non-critical subsystems
        """
        if alert.event_type in self.NOISE_EVENT_TYPES:
            return True

        if alert.severity == "INFO":
            return True

        if alert.severity == "WARNING":
            # Check if there is any other related alert on the same device or topological neighbor
            has_related = False
            for other in all_alerts:
                if other.id == alert.id:
                    continue
                if self.topology.are_topologically_related(alert.device_id, other.device_id, max_hops=1):
                    if other.severity in ("CRITICAL", "MAJOR"):
                        has_related = True
                        break
            if not has_related:
                return True

        return False

    def are_alerts_causally_related(self, a1: Alert, a2: Alert) -> bool:
        """Determine if two alerts share causal affinity or topological proximity."""
        # Check topological connection
        topo_related = self.topology.are_topologically_related(a1.device_id, a2.device_id, max_hops=3)

        # Check if they share a causal failure domain
        domain_match = False
        for domain, event_types in self.CAUSAL_DOMAINS.items():
            if a1.event_type in event_types and a2.event_type in event_types:
                domain_match = True
                break

        # If both are from the exact same device, they are related unless one is explicit noise
        if a1.device_id == a2.device_id:
            return True

        # If topologically related AND share causal domain
        if topo_related and domain_match:
            return True

        # Special case: Downstream impact (e.g. Core Optical/IP causing Access latency or RRC drops)
        if topo_related and (a1.severity == "CRITICAL" or a2.severity == "CRITICAL"):
            return True

        return False

    def correlate(self, alerts_data: List[dict]) -> Tuple[List[dict], List[Alert]]:
        """
        Main correlation workflow:
        1. Parse input alert objects
        2. Separate noise alerts from actionable signal
        3. Cluster correlated alerts by time window and topological/causal affinity
        4. Deduplicate and elect root cause device
        """
        raw_alerts = [Alert(**a) if isinstance(a, dict) else a for a in alerts_data]

        noise_alerts: List[Alert] = []
        actionable_alerts: List[Alert] = []

        for a in raw_alerts:
            if self.is_likely_noise(a, raw_alerts):
                a.is_noise = True
                noise_alerts.append(a)
            else:
                a.is_noise = False
                actionable_alerts.append(a)

        if not actionable_alerts:
            return [], noise_alerts

        # Sort actionable alerts by timestamp
        actionable_alerts.sort(key=lambda a: self.parse_time(a.timestamp))

        # Disjoint-set / Graph clustering
        clusters: List[List[Alert]] = []

        for alert in actionable_alerts:
            t_alert = self.parse_time(alert.timestamp)
            matched_cluster = None

            for cluster in clusters:
                # Check temporal window with cluster (15 min / 900 seconds)
                t_cluster_last = max(self.parse_time(c.timestamp) for c in cluster)
                if abs(t_alert - t_cluster_last) <= 900:
                    # Check causal or topological relation to any member in cluster
                    if any(self.are_alerts_causally_related(alert, member) for member in cluster):
                        matched_cluster = cluster
                        break

            if matched_cluster is not None:
                matched_cluster.append(alert)
            else:
                clusters.append([alert])

        # Convert clusters to raw incident dictionaries for prioritizer
        clustered_incidents = []
        for idx, cluster in enumerate(clusters, start=1):
            # Sort cluster by timestamp
            cluster.sort(key=lambda a: self.parse_time(a.timestamp))
            first_seen = cluster[0].timestamp
            last_seen = cluster[-1].timestamp

            # Identify root cause candidate (earliest critical alert or highest hierarchy tier)
            tier_weights = {"Core": 4, "Aggregation": 3, "Edge": 2, "Access": 1, "Facility": 1}
            severity_weights = {"CRITICAL": 4, "MAJOR": 3, "WARNING": 2, "INFO": 1}

            def root_score(a: Alert) -> float:
                tw = tier_weights.get(self.topology.get_tier(a.device_id), 1)
                sw = severity_weights.get(a.severity, 1)
                # Severe alerts take precedence over minor alerts on higher tiers
                # E.g. CRITICAL on Access >> WARNING on Aggregation
                sev_bonus = 6.0 if a.severity == "CRITICAL" else (3.0 if a.severity == "MAJOR" else 0.0)
                # Earlier alerts get slight preference
                t_diff = (self.parse_time(a.timestamp) - self.parse_time(first_seen))
                t_penalty = min(5.0, t_diff / 10.0)
                return (sev_bonus + sw * 2.0 + tw * 1.2) - t_penalty

            root_alert = max(cluster, key=root_score)
            root_device = root_alert.device_id

            # Affected unique devices
            affected_devices = list(dict.fromkeys(a.device_id for a in cluster))

            # Deduplicate alerts if identical device + event_type within seconds
            deduped_alerts: List[Alert] = []
            seen_signatures = set()
            for a in cluster:
                sig = f"{a.device_id}:{a.event_type}:{a.severity}"
                if sig not in seen_signatures:
                    seen_signatures.add(sig)
                    deduped_alerts.append(a)

            # Title formulation
            title = f"{root_alert.event_type.replace('_', ' ').title()} on {root_device}"
            if len(affected_devices) > 1:
                title += f" impacting {len(affected_devices)} devices"

            # Maximum severity in cluster
            has_crit = any(a.severity == "CRITICAL" for a in cluster)
            has_maj = any(a.severity == "MAJOR" for a in cluster)
            cluster_sev = "CRITICAL" if has_crit else ("MAJOR" if has_maj else "WARNING")

            incident_dict = {
                "id": f"INC-{idx:04d}",
                "title": title,
                "severity": cluster_sev,
                "root_cause_device": root_device,
                "root_alert": root_alert,
                "affected_devices": affected_devices,
                "alerts": deduped_alerts,
                "first_seen": first_seen,
                "last_seen": last_seen
            }
            clustered_incidents.append(incident_dict)

        return clustered_incidents, noise_alerts
