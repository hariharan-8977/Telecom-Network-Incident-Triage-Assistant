TRACK_ID=PS07
# Telecom Network Incident Triage Assistant

Autonomous Network Operations Center (NOC) alarm correlation, blast-radius prioritization, runbook grounding, and disciplined incident escalation assistant for telecommunications operators.

---

## 1. What the Project Does

When something breaks in a modern telecommunications network, it never raises a single isolated alert—it triggers a storm of dozens of cascading, overlapping alarms across optical transport, IP routing, wireless access (5G RAN), and facility infrastructure.

The **Telecom Network Incident Triage Assistant** solves this operational bottleneck:
1. **Deduplication & Correlation**: Ingests raw multi-vendor streams of alarms and syslog events, clusters causally related failures across network topology tiers, and identifies the true root-cause failure.
2. **Strict Noise Filtering**: Alerts that do not belong to an active incident (e.g. routine clock synchronizations, background health checks, single benign authentication retries) are isolated into a dedicated Noise Drawer and never forced into an incident.
3. **Blast-Radius & Impact Prioritization**: Evaluates topological hierarchy (Core, Aggregation, Edge, Access, Facility), affected subscriber counts, and SLA criticality to assign deterministic priorities (`P1-Critical`, `P2-High`, `P3-Medium`, `P4-Low`).
4. **Grounded Runbook Consultation**: Employs local hybrid retrieval (BM25 keyword matching + local vector cosine similarity) over an authentic library of telecom troubleshooting runbooks. Recommends immediate mitigation actions with exact CLI commands and safety precautions, citing the exact runbook ID and section numbers.
5. **Disciplined Escalation for Uncovered Incidents**: When an incident does not match any approved runbook (e.g., zero-day optical anomalies or uncatalogued firmware microcode crashes), the system explicitly refuses to guess or hallucinate. Instead, it compiles a structured **Escalation Package** with grouped alert timelines, affected blast radius, ruled-out runbooks, and suggested L3 diagnostics so senior engineering starts from evidence, not from scratch.
6. **Dual-Mode Engine (Resilient & Grounded)**: Seamlessly utilizes **Gemini** (`gemini-1.5-flash`) via `GEMINI_API_KEY` for natural language reasoning and grounded explanations, while retaining an instantaneous deterministic fallback mode when operating offline or without an API key.

---

## 2. Architecture & Design Principles

```
  [ Raw Stream of Alarms & Syslogs ]
                  │
                  ▼
   ┌──────────────────────────────┐
   │  Topology-Aware Correlator   │ ──(Unrelated singletons/info)──► [ Noise Isolation Drawer ]
   │    & Deduplication Engine    │
   └──────────────┬───────────────┘
                  │ (Correlated alarm clusters)
                  ▼
   ┌──────────────────────────────┐
   │  Blast-Radius Prioritizer    │ ──► Assigns P1, P2, P3, P4
   │   (Subscribers, SLA, Tier)   │
   └──────────────┬───────────────┘
                  │
                  ▼
   ┌──────────────────────────────┐
   │    Local Runbook Retriever   │
   │  (BM25 + Cosine Similarity)  │
   └──────┬────────────────┬──────┘
          │ (Score >= 0.48)│ (Score < 0.48 / Uncovered)
          ▼                ▼
   ┌──────────────┐ ┌───────────────────────────────────┐
   │ Gemini/Local │ │   Disciplined Escalation Engine   │
   │ Grounded RB  │ │ (Ruled-out checks, L3 Handover,   │
   │  Citations   │ │  Diagnostics, Zero Hallucinations)│
   └──────┬───────┘ └─────────────────┬─────────────────┘
          └───────────────┬───────────┘
                          ▼
            [ Cybernetic NOC Dashboard ]
             http://localhost:8000
```

### Clean Separation of Concerns
- **Deterministic Pipeline (`src/correlator.py`, `src/prioritizer.py`, `src/retriever.py`)**: Responsible for graph traversal, temporal windowing, subscriber blast-radius math, and vector cosine similarity. Fast, repeatable, and transparent.
- **GenAI Reasoning (`src/llm_triage.py`)**: Responsible for synthesis, runbook grounding, citation extraction, and structured escalation packaging.

---

## 3. How to Run

### Requirements
- Python 3.11+
- Web browser (Chrome, Edge, Firefox, Safari)

### Single-Command Quickstart
From the repository root:
```bash
pip install -r requirements.txt
python app.py
```

Then open your browser to:
```
http://localhost:8000
```

### Environment Variable (Optional)
To enable Gemini generative synthesis:
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your-gemini-api-key"

# Linux / macOS
export GEMINI_API_KEY="your-gemini-api-key"
```
*Note: If `GEMINI_API_KEY` is not provided, the application automatically runs in deterministic local mode with 100% feature availability.*

---

## 4. Benchmark Datasets & Runbooks Generated

All benchmark data and knowledge documents are self-contained in `data/`:

### 1. Multi-Tier Network Topology (`data/topology.json`)
Covers the full telecom hierarchy across the Northeast and Mid-Atlantic corridors:
- **Core Optical Transport**: `DWDM-CORE-NYC-BOS`, `DWDM-CORE-NYC-PHL` (100G links, 450,000 subscribers)
- **IP/MPLS Core Routers**: `CR-NYC-01`, `CR-NYC-02`, `CR-BOS-01`
- **Metro Aggregation Nodes**: `AGG-MAN-01`, `AGG-BKLYN-01`, `AGG-BOS-NORTH`
- **Edge Access Gateways**: `BNG-MAN-01`
- **5G Radio Access Sites**: `gNB-MAN-101`, `gNB-MAN-102`, `gNB-BKLYN-201`, `gNB-BOS-301`
- **Auxiliary Facility & Power**: `PWR-SITE-MAN-101`, `PWR-SITE-BKLYN-201`

### 2. Telecom Troubleshooting Runbooks (`data/runbooks/`)
- `RB-OPT-01-fiber-cut.md`: DWDM Core Optical Fiber Cut, OTDR Span Isolation, and Protection Switching.
- `RB-BGP-02-route-flapping.md`: Core/Peering BGP Route Flapping and Route Flap Damping (RFD).
- `RB-RAN-03-gnb-auth-storm.md`: 5G gNodeB Signaling & Authentication Storm, Access Barring, and NGAP Recovery.
- `RB-MEM-04-switch-memory-leak.md`: MPLS Switch Memory Leak, Route Cache Flushes, and Non-Stop Routing (NSR).
- `RB-PWR-05-site-power-failure.md`: Cell Site AC Mains Failure, Battery Float Depletion, and Generator Overrides.
- `embeddings.json`: Precomputed local vector embeddings for instant offline retrieval without startup latency.

### 3. Realistic Evaluation Scenarios (`data/scenarios/`)
- **`scenario_1_fiber_cut.json`** (Normal Critical Case): Core optical fiber break triggering 12 cascading alarms across DWDM, BGP, and OSPF, plus 4 background noise alarms. Correlates to 1 P1 incident, cites `RB-OPT-01`, isolates 4 noise events.
- **`scenario_2_auth_storm.json`** (Radio Control Plane Surge): 5G cell site authentication surge with RRC rejection spikes and 3 background noise alarms. Correlates to 1 P2 incident, cites `RB-RAN-03`.
- **`scenario_3_power_grid.json`** (Facility Storm): Utility power grid drop at cell site with decaying battery runtime. Correlates to 1 P2 incident, cites `RB-PWR-05`.
- **`scenario_4_uncovered_anomaly.json`** (Difficult Zero-Day Edge Case): Quantum photonic phase decoherence and microcode lockup on `QKD-EXP-01`. Demonstrates disciplined escalation: flags zero runbook match, refuses to invent, and generates an L3 Quantum Engineering escalation dossier.
- **`scenario_5_noisy_stream.json`** (High Noise Filtering Case): Dominated by benign telemetry flutters with 1 genuine memory leak on `AGG-BKLYN-01`. Demonstrates non-forcing of noise alerts (6 noise events cleanly isolated).

---

## 5. Automated Verification & Testing

Run the automated test suite covering correlation, noise filtering, prioritization, runbook retrieval, and escalation:
```bash
python -m unittest tests/test_triage.py
```

Expected output:
```
......
Ran 6 tests in 0.021s
OK
```

---

## 6. Demo Video Link
- **Demo Video**: `https://youtu.be/telecom-noc-incident-triage-demo` *(replace with recorded walkthrough video link)*

---

## 7. Submission Checklist Verification
- [x] Backend is Python (Flask + NumPy + Pydantic + Google-GenerativeAI)
- [x] Served on `http://localhost:8000` via `python app.py`
- [x] First line of README.md is `TRACK_ID=PS07`
- [x] Only external API is Gemini (`GEMINI_API_KEY`)
- [x] Local hybrid vector retrieval (NumPy cosine similarity + precomputed embeddings cache)
- [x] Zero-hallucination escalation for uncovered incidents
- [x] Real Git commit history with progressive milestones
