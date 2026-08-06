from __future__ import annotations

# Curated official ATS boards with plausible Swiss research/engineering scope.
# Broad job-board ingestion is intentionally excluded; every feed is an official
# employer source and the downstream gates retain only Swiss, technically deep
# roles with sufficient job-description evidence.
LIVE_SOURCES: tuple[dict[str, str], ...] = (
    {"name": "Exa official Ashby", "kind": "ashby", "slug": "exa"},
    {"name": "DeepJudge official Ashby", "kind": "ashby", "slug": "deepjudge"},
    {"name": "Jua official Ashby", "kind": "ashby", "slug": "jua"},
    {"name": "A1/Bjak official Ashby", "kind": "ashby", "slug": "bjakcareer"},
    {"name": "Lyceum official Ashby", "kind": "ashby", "slug": "lyceum"},
    {"name": "Mistral AI official Ashby", "kind": "ashby", "slug": "mistral.ai"},
    {"name": "GenPeach AI official Ashby", "kind": "ashby", "slug": "genpeach"},
    {"name": "Tzafon official Ashby", "kind": "ashby", "slug": "tzafon"},
    {"name": "Odyssey official Ashby", "kind": "ashby", "slug": "odysseyml"},
    {"name": "Sereact official Ashby", "kind": "ashby", "slug": "sereact"},
    {"name": "Cradle official Ashby", "kind": "ashby", "slug": "cradlebio"},
    {"name": "Neural Concept official Ashby", "kind": "ashby", "slug": "neuralconcept"},
    {"name": "Lakera official Ashby", "kind": "ashby", "slug": "lakera.ai"},
    {"name": "Bug Bounty Switzerland official Ashby", "kind": "ashby", "slug": "bug-bounty-switzerland"},
    {"name": "Harmattan AI official Ashby", "kind": "ashby", "slug": "harmattan-ai"},
    {"name": "Bleu Robotics official Ashby", "kind": "ashby", "slug": "bleu-robotics"},
    {"name": "RIVR official Lever", "kind": "lever", "slug": "rivr"},
    {"name": "Robotics and AI Institute official Lever", "kind": "lever", "slug": "rai"},
    {"name": "ANYbotics official Greenhouse", "kind": "greenhouse", "slug": "anybotics"},
    {"name": "Scandit official Greenhouse", "kind": "greenhouse", "slug": "scandit"},
    {"name": "DFINITY official Greenhouse", "kind": "greenhouse", "slug": "dfinity"},
)
