import os
import json
import time
from typing import Dict, Any
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# Load local environment if present
load_dotenv()

from src.pipeline import IncidentTriagePipeline
from src.models import Alert

app = Flask(__name__, static_folder="static", static_url_path="")

# Initialize core pipeline
pipeline = IncidentTriagePipeline()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCENARIOS_DIR = os.path.join(BASE_DIR, "data", "scenarios")
RUNBOOKS_DIR = os.path.join(BASE_DIR, "data", "runbooks")
TOPOLOGY_FILE = os.path.join(BASE_DIR, "data", "topology.json")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "Telecom Network Incident Triage Assistant",
        "track_id": "PS07",
        "gemini_api_key_configured": bool(pipeline.reasoner.client_available),
        "runbooks_loaded": len(pipeline.retriever.runbooks),
        "topology_nodes": len(pipeline.topology.nodes)
    })


@app.route("/api/topology", methods=["GET"])
def get_topology():
    if os.path.exists(TOPOLOGY_FILE):
        with open(TOPOLOGY_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"nodes": [], "links": []})


@app.route("/api/scenarios", methods=["GET"])
def list_scenarios():
    scenarios = []
    if os.path.exists(SCENARIOS_DIR):
        for fname in sorted(os.listdir(SCENARIOS_DIR)):
            if fname.endswith(".json"):
                fpath = os.path.join(SCENARIOS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        scenarios.append({
                            "file": fname,
                            "scenario_id": data.get("scenario_id", fname),
                            "title": data.get("title", fname),
                            "description": data.get("description", ""),
                            "alert_count": len(data.get("alerts", [])),
                            "expected_incident_count": data.get("expected_incident_count", 1),
                            "expected_noise_count": data.get("expected_noise_count", 0)
                        })
                except Exception as e:
                    print(f"Error loading scenario {fname}: {e}")
    return jsonify(scenarios)


@app.route("/api/scenarios/<scenario_file>", methods=["GET"])
def get_scenario(scenario_file: str):
    fpath = os.path.join(SCENARIOS_DIR, scenario_file)
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"error": "Scenario not found"}), 404


@app.route("/api/runbooks", methods=["GET"])
def list_runbooks():
    rbs = []
    for r_id, rb in pipeline.retriever.runbooks.items():
        rbs.append({
            "id": rb.id,
            "title": rb.title,
            "domain": rb.domain,
            "severity": rb.severity,
            "applies_to": rb.applies_to,
            "symptoms": rb.symptoms,
            "triage_steps": rb.triage_steps,
            "mitigation_sections": [s.model_dump() for s in rb.mitigation_sections],
            "safety_warnings": rb.safety_warnings,
            "raw_markdown": rb.raw_markdown
        })
    return jsonify(rbs)


@app.route("/api/triage", methods=["POST"])
def triage_alerts():
    """
    Ingest stream of alerts, correlate, prioritize, filter noise,
    and generate grounded triage or escalation.
    """
    payload = request.get_json(force=True)
    alerts_data = payload.get("alerts", [])

    if not alerts_data:
        return jsonify({"error": "No alerts provided"}), 400

    result = pipeline.process_alerts(alerts_data)
    return jsonify(result.model_dump())


@app.route("/api/chat", methods=["POST"])
def copilot_chat():
    """
    Interactive NOC Operator assistant query.
    Can ask clarifying questions about an active incident,
    request alternative verification checks, or draft handover notes.
    """
    payload = request.get_json(force=True)
    query = payload.get("query", "").strip()
    incident_context = payload.get("incident_context", {})

    if not query:
        return jsonify({"error": "No query provided"}), 400

    # If Gemini is configured, use it with grounded context
    if pipeline.reasoner.client_available and pipeline.reasoner.model:
        try:
            prompt = f"""You are the Telecom NOC Operator Copilot. Answer the operator's query accurately, professionally, and concisely.
Context of Active Incident:
{json.dumps(incident_context, indent=2)}

Available System Runbooks:
{', '.join([f'{rb.id}: {rb.title}' for rb in pipeline.retriever.runbooks.values()])}

Operator Query: "{query}"

Respond concisely with clear technical rationale and exact CLI commands when appropriate.
"""
            resp = pipeline.reasoner.model.generate_content(prompt)
            return jsonify({"reply": resp.text, "engine": "Gemini 1.5 Flash"})
        except Exception as e:
            print(f"Gemini copilot chat failed: {e}")

    # Deterministic fallback response
    inc_id = incident_context.get("id", "Active Incident")
    matched_rb = incident_context.get("matched_runbook_id")
    actions = incident_context.get("recommended_actions", [])
    cmds = [a.get("command") for a in actions if a.get("command")]

    if "command" in query.lower() or "cli" in query.lower():
        reply = f"For incident {inc_id} ({matched_rb}), recommended CLI commands are:\n" + "\n".join([f"`{c}`" for c in cmds])
    elif "status" in query.lower() or "priority" in query.lower():
        reply = f"Incident {inc_id} is evaluated at Priority {incident_context.get('priority')} with impact score {incident_context.get('impact_score')} affecting {incident_context.get('blast_radius_subscribers')} subscribers."
    elif "escalat" in query.lower():
        reply = f"Escalation status for {inc_id}: {'ESCALATED to L3' if incident_context.get('is_escalated') else 'Managed by L1/L2 Runbook ' + str(matched_rb)}."
    else:
        reply = f"NOC Copilot [Deterministic Mode]: Incident {inc_id} root cause is {incident_context.get('root_cause_device')}. Follow runbook {matched_rb or 'Escalation Package'} steps."

    return jsonify({"reply": reply, "engine": "Deterministic Fallback Engine"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Telecom Incident Triage Assistant on http://0.0.0.0:{port} ...")
    app.run(host="0.0.0.0", port=port, debug=False)
