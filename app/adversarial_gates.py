from __future__ import annotations

import copy
import re
from typing import Any


# These are capability requirements that cannot be repaired by rewriting a CV.
# They must be supported by direct evidence, not adjacent keywords.
HARD_REQUIREMENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "shipped and maintained production AI/ML systems",
        (
            r"shipped and maintained ai/?ml systems",
            r"ship(?:ped)? production[- ]grade ai",
            r"build and ship ai features end[- ]to[- ]end",
            r"production ai systems",
            r"ml models in production",
            r"real[- ]world usage",
        ),
        ("completed production ai", "production ml ownership", "production llm"),
    ),
    (
        "large-scale software engineering ownership",
        (
            r"large[- ]scale python software development",
            r"large[- ]scale or multi[- ]tenant saas",
            r"full domain ownership",
            r"production ownership",
        ),
        ("large-scale software", "multi-tenant", "distributed systems ownership"),
    ),
    (
        "C#/.NET production experience",
        (r"c#", r"\.net core", r"dotnet"),
        ("c#", ".net", "dotnet"),
    ),
    (
        "cloud AI platform experience",
        (r"azure ai foundry", r"aws bedrock", r"cloud ai platform"),
        ("azure ai", "aws bedrock", "cloud ai platform"),
    ),
    (
        "model serving and inference systems",
        (r"\bvllm\b", r"inference / serving", r"model serving", r"latency, cost, and production reliability"),
        ("vllm", "model serving", "inference systems"),
    ),
    (
        "vector database or retrieval infrastructure ownership",
        (r"vector db", r"vector database", r"retrieval infrastructure", r"production retrieval"),
        ("vector database", "retrieval infrastructure", "production retrieval"),
    ),
    (
        "CAD/CAE workflow expertise",
        (r"\bcad\b", r"\bcae\b", r"cfd", r"fea solver", r"hpc cluster"),
        ("cad", "cae", "cfd", "fea", "hpc"),
    ),
)


def _evidence_text(evidence: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for item in evidence:
        chunks.extend(
            str(item.get(key, ""))
            for key in (
                "name",
                "category",
                "status",
                "demonstrated_level",
                "interview_readiness",
                "recruiter_visibility",
                "note",
            )
        )
    return " ".join(chunks).lower()


def _is_directly_supported(evidence_text: str, support_terms: tuple[str, ...]) -> bool:
    return any(term in evidence_text for term in support_terms)


def _hard_gaps(job: dict[str, Any], evidence: list[dict[str, Any]]) -> list[str]:
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    evidence_text = _evidence_text(evidence)
    gaps: list[str] = []
    for label, patterns, support_terms in HARD_REQUIREMENTS:
        if any(re.search(pattern, text, re.I) for pattern in patterns) and not _is_directly_supported(evidence_text, support_terms):
            gaps.append(label)
    return gaps


def _role_key(job: dict[str, Any]) -> str:
    return f"{job.get('company', '')}::{job.get('title', '')}".lower()


def install_adversarial_gates(intelligence: Any) -> None:
    """Wrap deterministic scoring with non-negotiable evidence gates.

    The base scorer is useful for recall. This layer prevents keyword overlap,
    prestige and salary estimates from overriding central mandatory gaps.
    """

    base_analyze = intelligence.analyze_role

    def analyze_role(job: dict[str, Any], evidence: list[dict[str, Any]], salary_floor: int = 120000) -> dict[str, Any]:
        analysis = copy.deepcopy(base_analyze(job, evidence, salary_floor))
        gaps = _hard_gaps(job, evidence)
        key = _role_key(job)

        # Role-specific calibration uses only requirements visible in the
        # official listing. It does not invent employer preferences.
        if "bug bounty switzerland::applied ai engineer" in key:
            required = [
                "shipped and maintained production AI/ML systems",
                "large-scale software engineering ownership",
                "C#/.NET production experience",
                "cloud AI platform experience",
            ]
            gaps = list(dict.fromkeys([*required, *gaps]))
            analysis.update(
                fit_score=min(float(analysis.get("fit_score", 100)), 47.0),
                interview_band="Low",
                interview_probability_range=[8, 22],
                offer_probability_given_interview=[5, 14],
                hiring_opportunity_value=min(float(analysis.get("hiring_opportunity_value", 100)), 2.2),
                mandatory_evidence_strength=min(int(analysis.get("mandatory_evidence_strength", 100)), 36),
                decision="Build evidence first",
                primary_strategy="Do not apply yet; monitor while building genuine production ownership",
                blocker=(
                    "The official must-haves require shipped production AI/ML systems, large-scale Python ownership, "
                    "C#/.NET adaptability and Azure AI Foundry or AWS Bedrock. Current evidence shows strong research "
                    "and prototypes, but not those production requirements."
                ),
                fastest_correction=(
                    "This is not a two-hour wording problem. Reconsider only after a completed production AI artifact, "
                    "or after a credible technical contact confirms that the published must-haves are flexible."
                ),
                urgency="Monitor; do not invest application time now",
                confidence="high",
            )
        elif "a1/bjak::applied ai engineer" in key or "bjak::applied ai engineer" in key:
            gaps = list(dict.fromkeys(["shipped production ML product ownership", "model serving and inference systems", *gaps]))
            analysis.update(
                fit_score=min(float(analysis.get("fit_score", 100)), 60.0),
                interview_band="Moderate",
                interview_probability_range=[14, 30],
                offer_probability_given_interview=[7, 18],
                hiring_opportunity_value=min(float(analysis.get("hiring_opportunity_value", 100)), 3.4),
                mandatory_evidence_strength=min(int(analysis.get("mandatory_evidence_strength", 100)), 48),
                decision="Investigate one blocker",
                primary_strategy="Confirm Swiss employment, compensation and production-experience flexibility before applying",
                blocker=(
                    "The role expects end-to-end production ownership across model behaviour, serving, latency, reliability "
                    "and product debugging. Current evidence is strongest in research, evaluation and bounded demos."
                ),
                fastest_correction=(
                    "First obtain salary and Swiss-employment confirmation plus a technical calibration on whether strong "
                    "research artifacts can substitute for prior production ML ownership."
                ),
                urgency="Resolve the employment and production bar within five days",
                confidence="medium-high",
            )
        elif "neural concept" in key and any(term in key for term in ("workflow", "cad", "cae", "full-stack", "product engineer")):
            if any(gap == "CAD/CAE workflow expertise" for gap in gaps):
                analysis.update(
                    fit_score=min(float(analysis.get("fit_score", 100)), 52.0),
                    interview_band="Low",
                    interview_probability_range=[9, 24],
                    hiring_opportunity_value=min(float(analysis.get("hiring_opportunity_value", 100)), 2.8),
                    mandatory_evidence_strength=min(int(analysis.get("mandatory_evidence_strength", 100)), 42),
                    decision="Build evidence first",
                    primary_strategy="Do not pursue unless the role's CAD/CAE requirement is removed or clarified",
                    blocker="The role's central value is production CAD/CAE automation or distributed engineering software, which is not directly demonstrated.",
                    fastest_correction="Seek a different Neural Concept research or ML role; do not disguise geospatial simulation as CAD/CAE expertise.",
                    urgency="Monitor for a better-matched role",
                    confidence="high",
                )
        elif len(gaps) >= 2:
            analysis.update(
                fit_score=min(float(analysis.get("fit_score", 100)), 54.0),
                interview_band="Low",
                interview_probability_range=[8, 26],
                hiring_opportunity_value=min(float(analysis.get("hiring_opportunity_value", 100)), 3.0),
                mandatory_evidence_strength=min(int(analysis.get("mandatory_evidence_strength", 100)), 44),
                decision="Build evidence first",
                primary_strategy="Do not apply until the central mandatory gap is genuinely resolved",
                blocker=f"Multiple central requirements lack direct evidence: {', '.join(gaps[:3])}.",
                fastest_correction="Do not try to repair multiple hard gaps through résumé language; target a role whose core work matches demonstrated evidence.",
                urgency="No immediate application investment",
                confidence="high",
            )
        elif len(gaps) == 1:
            analysis.update(
                fit_score=min(float(analysis.get("fit_score", 100)), 64.0),
                interview_probability_range=[max(8, analysis.get("interview_probability_range", [8, 28])[0]), min(32, analysis.get("interview_probability_range", [8, 28])[1])],
                hiring_opportunity_value=min(float(analysis.get("hiring_opportunity_value", 100)), 4.2),
                mandatory_evidence_strength=min(int(analysis.get("mandatory_evidence_strength", 100)), 54),
                decision="Investigate one blocker",
                primary_strategy="Resolve the central mandatory gap before preparing a full application",
                blocker=f"Direct recruiter-visible evidence is missing for {gaps[0]}.",
                fastest_correction="Confirm whether the requirement is truly mandatory; if it is, target a better-matched role rather than overclaiming.",
                urgency="Resolve within five days",
                confidence="medium-high",
            )

        analysis["hard_gate_reasons"] = gaps
        analysis["adversarial_gate_applied"] = bool(gaps)
        analysis["analysis_method"] = f"{intelligence.MODEL_PROVIDER}+mandatory_evidence_gates_v1"
        analysis["model_used"] = analysis["analysis_method"]
        analysis["model_fallback"] = True
        return analysis

    intelligence.analyze_role = analyze_role
