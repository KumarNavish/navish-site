from __future__ import annotations

import hashlib
import html
import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

import httpx
from bs4 import BeautifulSoup

APP_REVISION = "2026.08.06-live.4"
MODEL_PROVIDER = "deterministic_gates_v4"
SWISS_PLACES = (
    "switzerland", "schweiz", "suisse", "zurich", "zürich", "basel", "rüschlikon",
    "lausanne", "geneva", "genève", "bern", "zug", "winterthur", "baden", "st. gallen",
)
TARGET_TERMS = (
    "machine learning", "artificial intelligence", " ai ", "research scientist", "research engineer",
    "applied scientist", "applied ai", "ml engineer", "algorithm engineer", "optimization",
    "computer vision", "robotics", "scientific software", "computational scientist", "model evaluation",
    "llm", "language model", "agentic", "inference", "decision science",
)
EXCLUDE_TERMS = ("sales", "account executive", "marketing", "office manager", "recruiter", "hr business")

OFFICIAL_SOURCES: tuple[dict[str, str], ...] = (
    {"name": "Exa official Ashby", "kind": "ashby", "slug": "exa"},
    {"name": "DeepJudge official Ashby", "kind": "ashby", "slug": "deepjudge"},
    {"name": "Jua official Ashby", "kind": "ashby", "slug": "jua"},
    {"name": "A1/Bjak official Ashby", "kind": "ashby", "slug": "bjakcareer"},
    {"name": "Lyceum official Ashby", "kind": "ashby", "slug": "lyceum"},
    {"name": "RIVR official Lever", "kind": "lever", "slug": "rivr"},
    {"name": "ANYbotics official Greenhouse", "kind": "greenhouse", "slug": "anybotics"},
    {"name": "Scandit official Greenhouse", "kind": "greenhouse", "slug": "scandit"},
    {"name": "Lakera official Greenhouse", "kind": "greenhouse", "slug": "lakera"},
)

SKILL_EVIDENCE: dict[str, tuple[str, ...]] = {
    "python": ("python",),
    "pytorch": ("pytorch",),
    "transformers": ("hugging face transformers", "lora and parameter-efficient adaptation"),
    "llm": ("hugging face transformers", "insurance agentic ai workflow"),
    "optimization": ("optimization for machine learning", "natural-gradient variational inference"),
    "continual learning": ("continual learning", "cl-plo"),
    "mlflow": ("mlflow", "cl-plo"),
    "docker": ("docker", "aalto figma plugin"),
    "ci/cd": ("ci/cd and automated testing", "cl-plo"),
    "testing": ("ci/cd and automated testing",),
    "typescript": ("typescript and vite", "aalto figma plugin"),
    "fastapi": ("fastapi", "safepin"),
    "causal": ("causal inference and off-policy evaluation", "promopilot"),
    "geospatial": ("geospatial simulation", "green last mile", "safepin"),
    "simulation": ("geospatial simulation", "green last mile"),
    "statistics": ("causal inference and off-policy evaluation", "experimental design"),
    "experimental design": ("experimental design", "experimental design and reproducibility"),
    "research": ("phd in optimization for machine learning systems", "peer-reviewed research record"),
}

SKILL_PATTERNS: dict[str, str] = {
    "python": r"\bpython\b",
    "pytorch": r"\bpytorch\b",
    "transformers": r"transformer|hugging\s*face|attention",
    "llm": r"\bllm\b|large language model|generative ai|agentic",
    "optimization": r"optimi[sz]ation|gradient|convex|variational",
    "continual learning": r"continual learning|catastrophic forgetting|online learning",
    "mlflow": r"\bmlflow\b|model registry",
    "docker": r"\bdocker\b|container",
    "ci/cd": r"ci/cd|github actions|release gate|continuous integration",
    "testing": r"pytest|unit test|integration test|test automation",
    "typescript": r"typescript|javascript|react|vite",
    "fastapi": r"fastapi|rest api|api service",
    "causal": r"causal|off-policy|counterfactual|treatment effect",
    "geospatial": r"geospatial|geopandas|postgis|h3|shapely",
    "simulation": r"simulation|simulator|scenario sweep",
    "statistics": r"statistics|probability|statistical|experimental design",
    "experimental design": r"experiment|ablation|benchmark|evaluation",
    "distributed systems": r"distributed systems|kubernetes|spark|ray|multi-node",
    "large-scale training": r"large-scale training|distributed training|multi-gpu|multi-node training",
    "c++": r"c\+\+",
    "robotics": r"robotics|imitation learning|reinforcement learning|embodied",
    "computer vision": r"computer vision|image|vision model|opencv",
}


def canonical_evidence() -> list[dict[str, Any]]:
    """Return source-bounded evidence extracted from the supplied CV and confirmed project context."""

    def item(name: str, category: str, source: str, status: str, demonstrated: str, ready: str, visible: str, note: str) -> dict[str, Any]:
        return {
            "name": name,
            "category": category,
            "source": source,
            "status": status,
            "demonstrated_level": demonstrated,
            "interview_readiness": ready,
            "recruiter_visibility": visible,
            "market_recognition": "high" if category in {"education", "publication"} else "medium",
            "confidence": "high",
            "note": note,
            "verified": True,
        }

    return [
        item("PhD in Optimization for Machine Learning Systems", "education", "CV pp.1,3", "ongoing", "advanced research", "strong", "high", "University of Basel; completion approximately 2027."),
        item("Optimization for machine learning", "research", "CV pp.2–3", "completed and ongoing", "advanced", "strong", "high", "Natural gradients, variational inference, stability and convergence analysis."),
        item("Natural-gradient variational inference", "research", "CV p.2 publication 1", "completed research", "advanced", "strong", "high", "First-author preprint with stability and convergence guarantees."),
        item("Continual learning", "research", "CV p.1 CL-PLO", "completed artifact and ongoing research", "advanced", "strong", "high", "Update evaluation, data-shift checks, regression gates and rollback decisions."),
        item("Python", "technical", "CV pp.1–3", "demonstrated", "advanced", "strong", "high", "Used across research, simulation, evaluation and deployed demos."),
        item("PyTorch", "technical", "CV pp.1,3", "demonstrated", "advanced", "strong", "high", "Used for continual learning, transformer updates and controlled training experiments."),
        item("Hugging Face Transformers", "technical", "CV p.1", "demonstrated", "intermediate", "moderate", "high", "Used in CL-PLO; does not imply transformer implementation from scratch."),
        item("Docker", "production", "CV pp.1–2", "demonstrated", "intermediate", "moderate", "high", "Dockerized backend and deployment-oriented project work; not large-scale platform ownership."),
        item("MLflow", "production", "CV p.1", "demonstrated", "intermediate", "moderate", "high", "Model registry and release-gate workflow in CL-PLO."),
        item("CI/CD and automated testing", "production", "CV p.1", "demonstrated", "intermediate", "moderate", "high", "GitHub Actions, pytest and evaluation gates."),
        item("TypeScript and Vite", "technical", "CV pp.1–2", "demonstrated", "intermediate", "moderate", "high", "Interactive demos and Figma-plugin work."),
        item("FastAPI", "production", "CV p.1 SafePin", "demonstrated", "intermediate", "moderate", "medium", "API-backed decision demo; does not prove high-scale service ownership."),
        item("Geospatial simulation", "technical", "CV pp.1–2", "demonstrated", "advanced", "strong", "high", "GeoPandas, H3, Shapely, scenario sweeps and operational constraints."),
        item("Causal inference and off-policy evaluation", "technical", "CV p.1 PromoPilot", "demonstrated", "intermediate", "moderate", "high", "IPS and doubly robust evaluation with policy export."),
        item("SafePin", "project", "CV p.1", "completed demo", "intermediate", "strong", "high", "Inspectable hazard evidence and route-aware decision support."),
        item("CL-PLO", "project", "CV p.1", "completed demo", "advanced", "strong", "high", "Continual model-update evaluation with release gates and rollback."),
        item("PromoPilot", "project", "CV p.1", "completed demo", "intermediate", "strong", "high", "Decision policy evaluation from biased logs."),
        item("Green Last Mile", "experience", "CV p.2", "completed", "advanced", "strong", "high", "Applied ML/research engineering and a published geospatial simulator."),
        item("Aalto Figma plugin", "experience", "CV p.2", "completed", "intermediate", "strong", "high", "TypeScript plugin plus Dockerized backend for design-rule linting."),
        item("Optimization Guarantees for Square-Root Natural-Gradient VI", "publication", "CV p.2 publication 1", "completed", "advanced", "strong", "high", "First-author 2025 arXiv preprint."),
        item("Cargo-bike logistics modelling", "publication", "CV p.2 publication 2", "completed", "advanced", "strong", "high", "Operational simulation research, arXiv 2023."),
        item("Spectral graph theory publications", "publication", "CV p.2 publications 3,5", "completed", "advanced", "strong", "high", "Peer-reviewed LAA paper plus gain-graph preprint."),
        item("Experimental design and reproducibility", "research", "CV p.3 ETH training", "completed and ongoing", "advanced", "strong", "medium", "Deterministic scripts, ablations, controlled sweeps and failure isolation."),
        item("Insurance agentic AI workflow", "industry", "User-confirmed Mobiliar Lab Analytics context", "ongoing", "developing", "moderate", "medium", "Agentic claim-handling knowledge-base work; no completed production impact is claimed."),
    ]


def strip_html(value: str) -> str:
    if not value:
        return ""
    return " ".join(BeautifulSoup(html.unescape(value), "html.parser").get_text(" ").split())


def source_endpoint(source: dict[str, str]) -> str:
    if source["kind"] == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{source['slug']}"
    if source["kind"] == "lever":
        return f"https://api.lever.co/v0/postings/{source['slug']}?mode=json"
    return f"https://boards-api.greenhouse.io/v1/boards/{source['slug']}/jobs?content=true"


def fetch_source(source: dict[str, str], timeout: float = 18.0) -> tuple[list[dict[str, Any]], str | None]:
    """Retrieve an official public ATS feed and normalize its transport shape."""

    try:
        response = httpx.get(source_endpoint(source), timeout=timeout, follow_redirects=True, headers={"User-Agent": "SwissCareerIntelligence/1.0"})
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"

    rows: list[dict[str, Any]] = []
    if source["kind"] == "ashby":
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        for raw in jobs:
            rows.append({
                "source_identifier": str(raw.get("id") or raw.get("jobUrl") or raw.get("title")),
                "title": str(raw.get("title") or ""),
                "company": source["name"].split(" official", 1)[0],
                "location": str(raw.get("location") or raw.get("workplaceType") or ""),
                "url": str(raw.get("jobUrl") or raw.get("applyUrl") or ""),
                "description": strip_html(str(raw.get("descriptionHtml") or raw.get("description") or "")),
                "published_at": raw.get("publishedAt") or raw.get("updatedAt"),
            })
    elif source["kind"] == "lever":
        jobs = payload if isinstance(payload, list) else []
        for raw in jobs:
            categories = raw.get("categories") or {}
            lists = " ".join(strip_html(str(x.get("content") or "")) for x in (raw.get("lists") or []))
            rows.append({
                "source_identifier": str(raw.get("id") or raw.get("hostedUrl") or raw.get("text")),
                "title": str(raw.get("text") or ""),
                "company": source["name"].split(" official", 1)[0],
                "location": str(categories.get("location") or ""),
                "url": str(raw.get("hostedUrl") or raw.get("applyUrl") or ""),
                "description": " ".join(filter(None, [strip_html(str(raw.get("descriptionPlain") or raw.get("description") or "")), lists, strip_html(str(raw.get("additionalPlain") or ""))])),
                "published_at": datetime.fromtimestamp(int(raw.get("createdAt", 0)) / 1000, UTC).isoformat() if raw.get("createdAt") else None,
            })
    else:
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        for raw in jobs:
            rows.append({
                "source_identifier": str(raw.get("id") or raw.get("absolute_url") or raw.get("title")),
                "title": str(raw.get("title") or ""),
                "company": source["name"].split(" official", 1)[0],
                "location": str((raw.get("location") or {}).get("name") or ""),
                "url": str(raw.get("absolute_url") or ""),
                "description": strip_html(str(raw.get("content") or "")),
                "published_at": raw.get("updated_at"),
            })
    return rows, None


def swiss_eligible(location: str, description: str = "") -> bool:
    haystack = f" {location} {description[:2500]} ".lower()
    if any(place in haystack for place in SWISS_PLACES):
        return True
    return "remote" in haystack and ("switzerland" in haystack or "swiss" in haystack)


def target_role(title: str, description: str) -> bool:
    text = f" {title} {description[:3500]} ".lower()
    if any(term in text for term in EXCLUDE_TERMS):
        return False
    return any(term in text for term in TARGET_TERMS)


def extract_years(text: str) -> int:
    values = [int(value) for value in re.findall(r"(?:at least|minimum|min\.?|\+)\s*(\d{1,2})\s*(?:\+\s*)?years?|(?:\b)(\d{1,2})\s*\+?\s*years?", text.lower()) for value in value if value]
    return max(values, default=0)


def _years(text: str) -> int:
    candidates = [int(x) for pair in re.findall(r"(?:at least|minimum|min\.?|\+)\s*(\d{1,2})\s*(?:\+\s*)?years?|\b(\d{1,2})\s*\+?\s*years?", text.lower()) for x in pair if x]
    return max(candidates, default=0)


def decompose_requirements(description: str) -> dict[str, Any]:
    text = " ".join(description.split())
    chunks = [part.strip(" -•\t") for part in re.split(r"(?<=[.;])\s+|\s+[•▪◦]\s+", text) if len(part.strip()) > 25]
    mandatory: list[str] = []
    preferred: list[str] = []
    for chunk in chunks[:120]:
        low = chunk.lower()
        if any(key in low for key in ("required", "must", "minimum", "you have", "we expect", "qualification")):
            mandatory.append(chunk[:420])
        elif any(key in low for key in ("preferred", "nice to have", "bonus", "ideally", "advantage")):
            preferred.append(chunk[:420])
    skills = [skill for skill, pattern in SKILL_PATTERNS.items() if re.search(pattern, text, re.I)]
    return {
        "mandatory": mandatory[:14],
        "preferred": preferred[:10],
        "skills": skills,
        "years_required": _years(text),
        "degree_required": "phd" if re.search(r"\bph\.?d\b|doctorate", text, re.I) else ("masters" if re.search(r"master'?s|msc", text, re.I) else "unconfirmed"),
    }


def classify_compensation(title: str, description: str, salary_floor: int = 120000) -> dict[str, Any]:
    combined = f"{title} {description}"
    published = re.search(r"(?:CHF|Fr\.?|SFr\.?)[\s’',]*(\d{2,3})[\s’',]*(\d{3})\s*(?:-|–|to)\s*(?:CHF|Fr\.?|SFr\.?)?[\s’',]*(\d{2,3})[\s’',]*(\d{3})", combined, re.I)
    if published:
        low = int(published.group(1) + published.group(2))
        high = int(published.group(3) + published.group(4))
        context = combined[max(0, published.start() - 140):published.end() + 180].lower()
        total_markers = (
            "total compensation", "total annual compensation", "including bonus",
            "including equity", "cash and equity", "on-target earnings", "ote",
        )
        base_markers = (
            "base salary", "annual base", "base compensation", "gross annual salary",
            "fixed salary", "base pay",
        )
        if any(marker in context for marker in total_markers):
            comp_type = "published total compensation"
        elif any(marker in context for marker in base_markers):
            comp_type = "published base"
        else:
            comp_type = "published compensation; base status unconfirmed"
        return {"label": f"CHF {low:,}–{high:,} {comp_type}", "low": low, "high": high, "type": comp_type, "confidence": "high"}

    low_title = title.lower()
    if any(term in low_title for term in ("staff", "principal", "lead", "senior research scientist")):
        low, high = 135000, 175000
    elif any(term in low_title for term in ("research scientist", "applied scientist", "research engineer", "optimization scientist")):
        low, high = 118000, 152000
    elif any(term in low_title for term in ("machine learning", "ml engineer", "ai engineer", "algorithm")):
        low, high = 112000, 145000
    else:
        low, high = 105000, 138000
    position = "likely above preferred base" if high >= salary_floor and low >= salary_floor - 5000 else "uncertain relative to preferred base"
    return {"label": f"Estimated base CHF {low:,}–{high:,}; {position}", "low": low, "high": high, "type": "estimated base", "confidence": "medium-low"}


def _normalized_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", str(value).lower()).split())


def evidence_index(evidence: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_normalized_label(str(item.get("name", ""))): item for item in evidence}


def _evidence_for_alias(index: dict[str, dict[str, Any]], alias: str) -> dict[str, Any] | None:
    normalized = _normalized_label(alias)
    if normalized in index:
        return index[normalized]
    # Aliases are curated and source-bounded. Allow a canonical evidence name to
    # extend an alias (for example "experimental design and reproducibility")
    # without treating arbitrary semantic similarity as proof.
    candidates = [
        item
        for name, item in index.items()
        if normalized and (normalized in name or name in normalized)
    ]
    return min(candidates, key=lambda item: len(_normalized_label(item.get("name", ""))), default=None)


def match_evidence(requirements: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    index = evidence_index(evidence)
    direct: list[dict[str, Any]] = []
    missing: list[str] = []
    for skill in requirements["skills"]:
        matches = [
            match
            for alias in SKILL_EVIDENCE.get(skill, ())
            if (match := _evidence_for_alias(index, alias)) is not None
        ]
        if matches:
            best = matches[0]
            direct.append({"requirement": skill, "evidence": best["name"], "source": best["source"], "strength": "direct" if skill not in {"llm", "transformers", "docker", "fastapi"} else "partial or direct"})
        else:
            missing.append(skill)
    return {"direct": direct, "missing": missing, "coverage": len(direct) / max(1, len(requirements["skills"]))}


def analyze_role(job: dict[str, Any], evidence: list[dict[str, Any]], salary_floor: int = 120000) -> dict[str, Any]:
    title, description, location = job["title"], job["description"], job["location"]
    requirements = decompose_requirements(description)
    matches = match_evidence(requirements, evidence)
    comp = classify_compensation(title, description, salary_floor)
    years = requirements["years_required"]
    senior_title = bool(re.search(r"\b(senior|staff|principal|lead|head|director)\b", title, re.I))
    severe_seniority = years >= 6 or any(term in title.lower() for term in ("principal", "staff", "director", "head of"))
    target_strength = min(1.0, sum(1 for term in TARGET_TERMS if term in f" {title} {description[:3000]} ".lower()) / 5)
    coverage = matches["coverage"]
    production_terms = sum(1 for term in ("docker", "mlflow", "ci/cd", "testing", "fastapi") if term in [m["requirement"] for m in matches["direct"]])
    production_strength = min(1.0, production_terms / 3)
    salary_quality = min(1.0, max(0.25, (comp["high"] - 95000) / 65000))
    seniority_fit = 0.25 if severe_seniority else (0.55 if senior_title or years >= 4 else 0.9)
    swiss = swiss_eligible(location, description)
    deterministic_fit = 100 * (
        0.30 * coverage + 0.18 * target_strength + 0.14 * seniority_fit + 0.12 * production_strength
        + 0.12 * salary_quality + 0.08 * (1.0 if swiss else 0.0) + 0.06 * 0.8
    )
    if severe_seniority:
        deterministic_fit = min(deterministic_fit, 42.0)
    if not swiss:
        deterministic_fit = min(deterministic_fit, 20.0)
    deterministic_fit = round(max(0.0, min(100.0, deterministic_fit)), 1)

    interview_mid = max(5, min(70, int(0.62 * deterministic_fit + 8 * (coverage >= 0.7) - 18 * severe_seniority)))
    if matches["missing"]:
        # A role with an unresolved mandatory requirement must not be presented
        # as a "Very strong" screening case, regardless of aggregate overlap.
        interview_mid = min(interview_mid, 48 if len(matches["missing"]) == 1 else 38)
    interview_low = max(3, interview_mid - 10)
    interview_high = min(80, interview_mid + 10)
    offer_mid = max(8, min(45, int(10 + 0.30 * deterministic_fit - 8 * severe_seniority)))
    offer_range = [max(5, offer_mid - 7), min(55, offer_mid + 7)]
    if interview_mid >= 60:
        band = "Very strong"
    elif interview_mid >= 43:
        band = "Strong"
    elif interview_mid >= 25:
        band = "Moderate"
    elif interview_mid >= 12:
        band = "Low"
    else:
        band = "Very low"

    mandatory_strength = min(1.0, coverage * seniority_fit + 0.15)
    career_value = 0.86 if any(term in title.lower() for term in ("research", "scientist", "machine learning", "ai", "optimization")) else 0.65
    personal_fit = min(1.0, 0.58 + 0.35 * target_strength)
    preparation_cost = min(1.0, 0.15 + 0.11 * len(matches["missing"]) + (0.35 if severe_seniority else 0))
    hov = 100 * (interview_mid / 100) * (offer_mid / 100) * salary_quality * career_value * personal_fit * mandatory_strength * (1 - 0.35 * preparation_cost)
    hov = round(max(0.0, min(100.0, hov)), 1)

    direct_names = [m["evidence"] for m in matches["direct"][:5]]
    why = (
        f"This team may interview Navish because his visible {', '.join(direct_names[:4]) or 'optimization-focused ML research'} "
        f"evidence maps to the role’s central work, while his research-to-implementation profile provides differentiation beyond generic keyword overlap."
    )
    if severe_seniority:
        blocker = f"The role signals a material seniority mismatch ({years or 'senior'} years/level); research depth cannot substitute for required production ownership."
        fastest = "Reject this exact level and monitor the same team for an individual-contributor role aligned with a graduating PhD."
        decision = "Do not pursue"
        strategy = "Reject"
    elif matches["missing"]:
        central = matches["missing"][0]
        blocker = f"Recruiter-visible evidence for {central} is missing or insufficient; adjacent experience must not be presented as direct ownership."
        fastest = f"Use a two-hour evidence correction: expose the closest completed artifact and state the {central} gap explicitly rather than building a broad new project."
        decision = "Investigate one blocker" if deterministic_fit >= 55 else "Build evidence first"
        strategy = "Apply after a two-hour evidence correction" if deterministic_fit >= 55 else "Obtain one missing fact"
    elif interview_mid >= 48 and comp["high"] >= salary_floor:
        blocker = "Production scope and work-authorization handling must be made explicit without inflating academic experience."
        fastest = "Apply immediately with the evidence-linked research-engineer narrative and verify permit handling during screening."
        decision = "Strongly pursue"
        strategy = "Apply immediately"
    elif interview_mid >= 32:
        blocker = "The application must translate academic depth into fast recruiter-visible delivery evidence."
        fastest = "Reorder existing projects and publications around the employer’s central technical problem before applying."
        decision = "Pursue"
        strategy = "Apply after a two-hour evidence correction"
    else:
        blocker = "The central requirements are not sufficiently covered by direct, visible evidence."
        fastest = "Do not invest until one central missing requirement or level assumption is resolved."
        decision = "Build evidence first"
        strategy = "Obtain one missing fact"

    prohibited = [
        "Do not claim that PyTorch use proves large-scale or distributed training.",
        "Do not claim that Transformers-library use proves transformer implementation from scratch.",
        "Do not convert research years into unqualified production-infrastructure tenure.",
        "Do not describe ongoing Mobiliar work as completed production impact.",
    ]
    return {
        "fit_score": deterministic_fit,
        "interview_band": band,
        "interview_probability_range": [interview_low, interview_high],
        "offer_probability_given_interview": offer_range,
        "hiring_opportunity_value": hov,
        "compensation": comp,
        "career_value": round(career_value * 100),
        "personal_fit": round(personal_fit * 100),
        "mandatory_evidence_strength": round(mandatory_strength * 100),
        "preparation_cost": round(preparation_cost * 100),
        "confidence": "medium" if len(requirements["skills"]) >= 3 else "low-medium",
        "decision": decision,
        "primary_strategy": strategy,
        "why_interview": why,
        "blocker": blocker,
        "fastest_correction": fastest,
        "urgency": "Apply within 48 hours" if decision in {"Strongly pursue", "Pursue"} else "Resolve within five days",
        "requirements": requirements,
        "matches": matches,
        "prohibited_claims": prohibited,
        "severe_seniority_mismatch": severe_seniority,
        "analysis_method": MODEL_PROVIDER,
        "model_used": MODEL_PROVIDER,
        "model_fallback": True,
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


def source_hash(job: dict[str, Any]) -> str:
    payload = "|".join(str(job.get(key, "")) for key in ("source_identifier", "title", "company", "location", "url", "description"))
    return hashlib.sha256(payload.encode()).hexdigest()


def serious(analysis: dict[str, Any]) -> bool:
    return analysis["decision"] in {"Strongly pursue", "Pursue", "Investigate one blocker"} and not analysis["severe_seniority_mismatch"]


PROJECT_SKILL_SIGNALS: dict[str, set[str]] = {
    "cl plo": {"python", "pytorch", "transformers", "optimization", "continual learning", "mlflow", "ci/cd", "testing", "experimental design"},
    "safepin": {"python", "fastapi", "geospatial", "llm", "testing"},
    "promopilot": {"python", "causal", "statistics", "experimental design"},
    "green last mile": {"python", "geospatial", "simulation", "experimental design"},
    "aalto figma plugin": {"typescript", "docker", "testing"},
    "insurance agentic ai workflow": {"python", "llm", "experimental design"},
    "optimization guarantees for square root natural gradient vi": {"optimization", "statistics", "experimental design", "research"},
    "cargo bike logistics modelling": {"python", "geospatial", "simulation", "experimental design", "research"},
    "spectral graph theory publications": {"optimization", "research"},
}


def _rank_evidence_for_job(
    evidence: list[dict[str, Any]],
    job: dict[str, Any],
    requirements: dict[str, Any],
    categories: set[str],
) -> list[dict[str, Any]]:
    terms = [*requirements.get("skills", []), *TARGET_TERMS]
    required_skills = {_normalized_label(skill) for skill in requirements.get("skills", [])}
    job_text = _normalized_label(f"{job.get('title', '')} {job.get('description', '')}")

    def score(item: dict[str, Any]) -> tuple[int, int, int, str]:
        name = _normalized_label(item.get("name", ""))
        item_text = _normalized_label(f"{item.get('name', '')} {item.get('note', '')}")
        overlap = sum(1 for term in terms if _normalized_label(term) in item_text and _normalized_label(term) in job_text)
        direct = sum(1 for skill in required_skills if skill in item_text)
        alias_hits = sum(
            1
            for skill in requirements.get("skills", [])
            if any(_normalized_label(alias) in item_text for alias in SKILL_EVIDENCE.get(skill, ()))
        )
        explicit_signals = PROJECT_SKILL_SIGNALS.get(name, set())
        signal_hits = len(required_skills.intersection({_normalized_label(skill) for skill in explicit_signals}))
        completed = 1 if "completed" in str(item.get("status", "")).lower() else 0
        visibility = 1 if str(item.get("recruiter_visibility", "")).lower() == "high" else 0
        return (
            signal_hits * 12 + alias_hits * 8 + direct * 5 + overlap * 2 + completed + visibility,
            signal_hits,
            completed,
            str(item.get("name", "")),
        )

    rows = [item for item in evidence if item.get("category") in categories]
    return sorted(rows, key=score, reverse=True)


def application_package(job: dict[str, Any], analysis: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    index = evidence_index(evidence)
    selected: list[dict[str, Any]] = []
    for match in analysis["matches"]["direct"][:7]:
        item = _evidence_for_alias(index, match["evidence"])
        if item and item not in selected:
            selected.append(item)
    if not selected:
        selected = [item for item in evidence if item["category"] in {"education", "research", "project", "experience"}][:6]

    project_rows = _rank_evidence_for_job(
        evidence,
        job,
        analysis["requirements"],
        {"project", "experience", "industry"},
    )[:3]
    publication_rows = _rank_evidence_for_job(
        evidence,
        job,
        analysis["requirements"],
        {"publication"},
    )[:3]
    claims = [
        {"text": item["note"], "evidence": item["name"], "source": item["source"], "status": item["status"], "validated": True}
        for item in selected
    ]
    matrix = [
        {"requirement": match["requirement"], "evidence": match["evidence"], "source": match["source"], "strength": match["strength"]}
        for match in analysis["matches"]["direct"]
    ]
    for gap in analysis["matches"]["missing"]:
        matrix.append({"requirement": gap, "evidence": "Current gap", "source": "No verified direct evidence", "strength": "missing"})

    strongest = [match["evidence"] for match in analysis["matches"]["direct"][:4]]
    top_reasons = [
        analysis["why_interview"],
        f"Strongest visible evidence: {', '.join(strongest) if strongest else 'evidence review required'}.",
        f"Fastest credible route: {analysis['primary_strategy']}.",
    ]
    objections = [analysis["blocker"]]
    objections.extend(f"No direct evidence yet for {gap}." for gap in analysis["matches"]["missing"][:3])
    objections = list(dict.fromkeys(objections))

    return {
        "headline": "Optimization-focused Applied ML Researcher–Engineer | PyTorch, reliable adaptation, rigorous evaluation",
        "professional_summary": (
            f"University of Basel PhD researcher translating optimization, continual-learning and evaluation methods into auditable ML systems. "
            f"For {job['company']}, the strongest fit is the combination of rigorous experimentation, PyTorch implementation and release-oriented evidence—not unsupported claims of large-scale production tenure."
        ),
        "top_reasons": top_reasons,
        "evidence_claims": claims,
        "requirement_matrix": matrix,
        "recruiter_pitch": (
            f"Navish is completing a Basel PhD in optimization for ML systems and has public evidence in continual adaptation, PyTorch experimentation, evaluation gates and applied decision systems. "
            f"The credible reason to screen him for {job['title']} is direct overlap with the role’s technical core plus unusually rigorous failure analysis."
        ),
        "hiring_manager_note": (
            f"I am interested in {job['title']} because the role’s central problem overlaps with my work on reliable model updates, optimization and evidence-driven evaluation. "
            "I would be glad to walk through one concrete result, its failure modes and the implementation decisions behind it."
        ),
        "projects": [item["name"] for item in project_rows],
        "publications": [item["name"] for item in publication_rows],
        "screening_objections": objections,
        "truthful_responses": [
            analysis["fastest_correction"],
            "Separate research depth from production tenure and state exact ownership boundaries.",
        ],
        "compensation_positioning": f"Target base CHF 120,000+; source interpretation: {analysis['compensation']['label']}. Verify base versus total before final-stage commitment.",
        "cover_note": "Use a concise motivation note only when the application benefits from role-specific context; omit a generic cover letter.",
        "referral_recommendation": "Do not request a referral from an unverified stranger. Seek technical calibration first when a credible shared context exists.",
        "prohibited_claims": analysis["prohibited_claims"],
        "submission_checklist": [
            "Verify the official listing is still active.",
            "Review every evidence-linked claim.",
            "Confirm work-authorization wording.",
            "Confirm base-compensation interpretation.",
            "Submit manually and then explicitly mark Applied.",
        ],
        "external_action_executed": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def interview_plan(job: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    skills = analysis["requirements"]["skills"]
    missing = analysis["matches"]["missing"]
    sessions = [
        {"competency": "Recruiter screen", "duration": 25, "prompt": f"Give a 90-second evidence-bounded explanation of why your PhD, completed artifacts and availability fit {job['title']}; address work authorization without speculation."},
        {"competency": "Research and project deep dive", "duration": 40, "prompt": "Explain one result, baseline, failure mode, ablation and implementation choice from CL-PLO or your optimization research. Separate what is published, demonstrated and ongoing."},
        {"competency": "ML system design", "duration": 45, "prompt": f"Design the model lifecycle implied by this role: data validation, evaluation gates, deployment, monitoring, rollback and cost. Tie every answer to {', '.join(skills[:5]) or 'the actual job requirements'}."},
    ]
    if any(skill in skills for skill in ("python", "pytorch", "testing")):
        sessions.append({"competency": "Timed Python/PyTorch diagnostic", "duration": 35, "prompt": "Implement a small, tested evaluation or adaptation component under time pressure; explain complexity, failure cases and reproducibility."})
    if missing:
        sessions.append({"competency": f"Objection handling: {missing[0]}", "duration": 20, "prompt": f"Prepare a truthful response to the missing {missing[0]} requirement. State transferable evidence, the exact gap and how quickly you can ramp up—without claiming prior ownership."})
    sessions.append({"competency": "Compensation and availability", "duration": 20, "prompt": "Practice stating availability, CHF 120k preferred base, flexibility on level only when scope and recurring total compensation justify it, and the need to verify permit handling."})
    return sessions[:6]
