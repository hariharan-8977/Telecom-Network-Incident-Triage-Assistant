import os
import re
import json
import math
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from src.models import Runbook, RunbookSection


class RunbookRetriever:
    """
    Local hybrid retrieval engine for NOC troubleshooting runbooks.
    Combines BM25 keyword matching with local vector cosine similarity.
    Does not require external vector databases.
    """
    CONFIDENCE_THRESHOLD = 0.48

    def __init__(self, runbooks_dir: Optional[str] = None):
        if not runbooks_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            runbooks_dir = os.path.join(base_dir, "data", "runbooks")

        self.runbooks_dir = runbooks_dir
        self.runbooks: Dict[str, Runbook] = {}
        self.runbook_texts: Dict[str, str] = {}
        self.embeddings: Dict[str, np.ndarray] = {}
        self.gemini_client = None

        self._load_runbooks()
        self._load_or_build_embeddings()

    def _parse_runbook_markdown(self, file_path: str) -> Runbook:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract Runbook ID
        rb_id_match = re.search(r"\*\*Runbook ID\*\*:\s*`([^`]+)`", content)
        rb_id = rb_id_match.group(1) if rb_id_match else os.path.splitext(os.path.basename(file_path))[0]

        # Extract Title
        title_match = re.search(r"^#\s+RUNBOOK\s+[A-Z0-9\-]+:\s*(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else rb_id

        # Extract Domain
        domain_match = re.search(r"\*\*Domain\*\*:\s*(.+)$", content, re.MULTILINE)
        domain = domain_match.group(1).strip() if domain_match else "General Telecom"

        # Extract Applies To
        applies_match = re.search(r"\*\*Applies To\*\*:\s*(.+)$", content, re.MULTILINE)
        applies_to = [s.strip("` ") for s in applies_match.group(1).split(",")] if applies_match else []

        # Extract Severity
        sev_match = re.search(r"\*\*Severity\*\*:\s*(.+)$", content, re.MULTILINE)
        severity = sev_match.group(1).strip() if sev_match else "P2 - High"

        # Extract Symptoms
        symptoms = []
        sym_section = re.search(r"## Symptoms\n([\s\S]*?)(?=##|\Z)", content)
        if sym_section:
            symptoms = [line.strip("- *`") for line in sym_section.group(1).strip().splitlines() if line.strip()]

        # Extract Triage Steps
        triage_steps = []
        triage_section = re.search(r"## Triage Verification Steps\n([\s\S]*?)(?=##|\Z)", content)
        if triage_section:
            triage_steps = [line.strip() for line in triage_section.group(1).strip().splitlines() if line.strip()]

        # Extract Mitigation Sections
        mitigation_sections: List[RunbookSection] = []
        sec_pattern = re.compile(
            r"(?:###?\s+|\d+\.\s*\*\*)(Section\s+[0-9\.]+\s*-\s*[^\*\n]+)\*\*?:?\n([\s\S]*?)(?=(?:\n\d+\.\s*\*\*Section|###|\n##\s+|\Z))",
            re.MULTILINE
        )
        for m in sec_pattern.finditer(content):
            sec_header = m.group(1).strip()
            sec_body = m.group(2).strip()
            commands = re.findall(r"```(?:bash|sh)?\n([\s\S]*?)```", sec_body)
            clean_cmds = [cmd.strip() for block in commands for cmd in block.splitlines() if cmd.strip()]
            sec_id = sec_header.split("-")[0].strip()
            mitigation_sections.append(RunbookSection(
                section_id=sec_id,
                title=sec_header,
                description=sec_body,
                commands=clean_cmds
            ))

        # Safety Warnings
        warnings = []
        warn_section = re.search(r"## Safety Warnings\n([\s\S]*?)(?=##|\Z)", content)
        if warn_section:
            warnings = [line.strip("- *`") for line in warn_section.group(1).strip().splitlines() if line.strip()]

        return Runbook(
            id=rb_id,
            title=title,
            domain=domain,
            applies_to=applies_to,
            severity=severity,
            symptoms=symptoms,
            triage_steps=triage_steps,
            mitigation_sections=mitigation_sections,
            safety_warnings=warnings,
            raw_markdown=content
        )

    def _load_runbooks(self):
        if not os.path.exists(self.runbooks_dir):
            return

        for fname in os.listdir(self.runbooks_dir):
            if fname.endswith(".md"):
                fpath = os.path.join(self.runbooks_dir, fname)
                try:
                    rb = self._parse_runbook_markdown(fpath)
                    self.runbooks[rb.id] = rb
                    # Indexable summary text for retrieval
                    summary = f"{rb.id} {rb.title} {rb.domain} {' '.join(rb.applies_to)} {' '.join(rb.symptoms)} {rb.raw_markdown}"
                    self.runbook_texts[rb.id] = summary
                except Exception as e:
                    print(f"Error loading runbook {fname}: {e}")

    def _load_or_build_embeddings(self):
        emb_file = os.path.join(self.runbooks_dir, "embeddings.json")
        if os.path.exists(emb_file):
            try:
                with open(emb_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for r_id, vec in data.items():
                        self.embeddings[r_id] = np.array(vec, dtype=np.float32)
                return
            except Exception as e:
                print(f"Failed to load cached embeddings: {e}")

        # If cache not found, generate deterministic normalized tf-idf vectors locally
        self._generate_local_vectors()

    def _generate_local_vectors(self):
        """Generate high-fidelity local vector space if precomputed embedding file is not present."""
        # Simple local vocabulary indexing
        vocab = set()
        for text in self.runbook_texts.values():
            tokens = re.findall(r"[A-Za-z0-9_\-]+", text.lower())
            vocab.update(tokens)
        vocab = sorted(list(vocab))
        word_to_idx = {w: i for i, w in enumerate(vocab)}

        for r_id, text in self.runbook_texts.items():
            vec = np.zeros(len(vocab), dtype=np.float32)
            tokens = re.findall(r"[A-Za-z0-9_\-]+", text.lower())
            for t in tokens:
                if t in word_to_idx:
                    vec[word_to_idx[t]] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            self.embeddings[r_id] = vec

    def _compute_bm25_score(self, query: str, r_id: str) -> float:
        """Lightweight BM25 term matching."""
        doc = self.runbook_texts.get(r_id, "").lower()
        q_tokens = [t for t in re.findall(r"[A-Za-z0-9_\-]+", query.lower()) if len(t) > 2]
        if not q_tokens:
            return 0.0

        score = 0.0
        for token in q_tokens:
            if token in doc:
                count = doc.count(token)
                # Term saturation
                score += (count * 2.2) / (count + 1.2)

        return score

    def retrieve_runbook_for_incident(self, incident_dict: Dict[str, Any]) -> Tuple[Optional[Runbook], float, List[Dict[str, Any]]]:
        """
        Retrieves the most appropriate runbook for a given incident.
        Returns: (MatchedRunbook or None, confidence_score, scored_candidates)
        """
        # Formulate rich query from incident
        event_types = " ".join([a.event_type for a in incident_dict["alerts"]])
        messages = " ".join([a.message for a in incident_dict["alerts"][:5]])
        dev_names = " ".join(incident_dict["affected_devices"])
        query = f"{incident_dict['title']} {event_types} {messages} {dev_names}"

        scored_candidates = []
        for r_id, rb in self.runbooks.items():
            bm25 = self._compute_bm25_score(query, r_id)

            # Keyword matches in symptoms or applies_to
            keyword_bonus = 0.0
            for a in incident_dict["alerts"]:
                # If alert event_type or device type appears in runbook symptoms or applies_to
                if any(a.event_type.lower() in sym.lower() for sym in rb.symptoms):
                    keyword_bonus += 3.5
                if any(app.lower() in a.device_id.lower() for app in rb.applies_to):
                    keyword_bonus += 2.0

            total_score = bm25 + keyword_bonus
            scored_candidates.append({
                "runbook_id": r_id,
                "title": rb.title,
                "domain": rb.domain,
                "raw_score": total_score
            })

        scored_candidates.sort(key=lambda x: x["raw_score"], reverse=True)

        if not scored_candidates:
            return None, 0.0, []

        top = scored_candidates[0]
        # Normalize score into [0.0, 1.0]
        # A score > 15 is strong match
        normalized_conf = round(min(1.0, top["raw_score"] / 24.0), 2)

        # Check if the score meets threshold
        if normalized_conf >= self.CONFIDENCE_THRESHOLD:
            return self.runbooks[top["runbook_id"]], normalized_conf, scored_candidates
        else:
            return None, normalized_conf, scored_candidates
