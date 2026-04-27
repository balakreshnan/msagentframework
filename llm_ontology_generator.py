"""
LLM-Driven Ontology Generator
=============================

Generates an OWL-style ontology from either:

  1. A natural-language description of a domain
       e.g. "Model a hospital: patients, doctors, appointments, diagnoses,
             prescriptions, departments, insurance policies."

  2. A tabular dataset (CSV)
       The script samples columns and rows, then asks the LLM to infer
       classes, properties, datatypes, and seed individuals.

The LLM call goes to **Azure OpenAI** hosted in **Microsoft (Azure) AI Foundry**.
The result is parsed into the same `Ontology` engine defined in
`ontology_builder.py`, so we get the same reasoning, validation, and
exporters (Turtle / JSON-LD / native JSON) for free.

------------------------------------------------------------------------
Environment variables
------------------------------------------------------------------------
    AZURE_OPENAI_ENDPOINT      e.g. https://my-foundry.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT    deployment name, e.g. "gpt-4o" or "o4-mini"
    AZURE_OPENAI_API_VERSION   default: "2024-10-21"

    Authentication uses Microsoft Entra ID via DefaultAzureCredential
    (az login / managed identity / VS Code / env vars).

------------------------------------------------------------------------
Install
------------------------------------------------------------------------
    pip install openai azure-identity

------------------------------------------------------------------------
Usage
------------------------------------------------------------------------
    # 1) From a natural-language description
    python llm_ontology_generator.py --describe "Model a hospital: patients,
        doctors, appointments, diagnoses, prescriptions, departments."

    # 2) From a CSV dataset
    python llm_ontology_generator.py --dataset path/to/file.csv \
                                     --topic   "Retail orders"

    # 3) Dry run (no Azure call — uses a built-in mocked response so you
    #            can inspect the build/export pipeline locally)
    python llm_ontology_generator.py --describe "Hospital domain" --dry-run

Outputs (written next to the script):
    <slug>.ttl       # Turtle / RDF
    <slug>.jsonld    # JSON-LD
    <slug>.json      # native serialization
    <slug>.raw.json  # the LLM's raw structured response (for debugging)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

# Reuse the engine + worked-example helpers from the prior file.
# Both files must live in the same directory.
from ontology_builder import Ontology  # noqa: E402

from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# 1. Prompt — the contract between us and the LLM
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert knowledge engineer who designs OWL ontologies.

Your job: given a domain description (and optionally a sample of tabular data),
produce a JSON ontology specification that follows the schema below EXACTLY.

Rules:
- Use PascalCase for class names (e.g. "Patient", "MaintenanceEvent").
- Use camelCase for property names (e.g. "hasDiagnosis", "treatedBy").
- Build a DEEP is-a hierarchy: aim for 5-6 levels of subclasses (and never
  fewer than 4) along the main branches. Example for a hospital:
      Thing -> Agent -> Person -> MedicalProfessional -> Physician
            -> Cardiologist -> InterventionalCardiologist
  Do this for MULTIPLE branches of the taxonomy, not just one. A flat
  hierarchy with everything one level under a root is NOT acceptable —
  introduce intermediate abstract classes (e.g. Person, MedicalProfessional,
  Equipment, Asset, Event, ClinicalEvent) to reach the required depth.
- Every leaf class should have at least 3 ancestors above it.
- Every class (except the single top root) MUST list exactly one parent in
  "parents" — and that parent MUST be another class you defined in this
  spec. Do not leave "parents" empty except for the single top-level root.
- Every ObjectProperty MUST have a domain and a range that are class names
  you defined.
- Every DataProperty MUST have a domain and an xsd datatype:
  one of "xsd:string", "xsd:integer", "xsd:double", "xsd:boolean", "xsd:dateTime".
- Use inverse_of when a relationship has a natural inverse (treats / treatedBy).
- Mark a property "transitive" only when transitivity is meaningful
  (partOf, locatedIn, ancestorOf).
- Mark "disjoint_with" for sibling classes that should never overlap
  (Doctor vs Patient, Operator vs Technician).
- Provide 8-20 seed individuals that show how the ontology is used; their
  "types" must be the most-specific (deepest) class names you defined;
  relationships must satisfy declared domains/ranges.
- Use only ASCII identifiers. No spaces. No special characters.
- Size target: 20-40 classes (so the depth target is achievable),
  6-15 object properties, 5-12 data properties.

OUTPUT FORMAT — return JSON ONLY (no prose, no markdown), matching:

{
  "ontology_name": "string (short slug)",
  "iri_base":      "string, e.g. https://example.org/hospital/",
  "prefix":        "string, e.g. hosp",
  "description":   "string",
  "classes": [
    { "name": "string",
      "parents": ["ParentClassName"],
      "comment": "string",
      "disjoint_with": ["OtherClassName"] }
  ],
  "object_properties": [
    { "name": "string",
      "domain": "ClassName",
      "range":  "ClassName",
      "inverse_of": "OtherPropertyName or null",
      "transitive": false,
      "symmetric": false,
      "functional": false,
      "comment": "string" }
  ],
  "data_properties": [
    { "name": "string",
      "domain": "ClassName",
      "datatype": "xsd:string",
      "comment": "string" }
  ],
  "individuals": [
    { "name": "string",
      "types": ["ClassName"],
      "object_props": { "propertyName": ["TargetIndividualName"] },
      "data_props":   { "propertyName": ["literal value"] } }
  ]
}
"""


def build_user_prompt(description: str, dataset_sample: str | None = None) -> str:
    parts = [f"DOMAIN DESCRIPTION:\n{description.strip()}"]
    if dataset_sample:
        parts.append(
            "DATASET SAMPLE (use this to refine class and property choices, "
            "and to seed at least a few realistic individuals):\n"
            + dataset_sample.strip()
        )
    parts.append("Produce the JSON ontology specification now.")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 2. Azure OpenAI client (Foundry)
# ---------------------------------------------------------------------------

def call_azure_openai(system_prompt: str, user_prompt: str) -> dict:
    """Call Azure OpenAI in Foundry with JSON-mode response.

    Authentication uses Microsoft Entra ID via ``DefaultAzureCredential``
    (e.g. ``az login``, managed identity, VS Code, environment variables).
    """
    try:
        from openai import AzureOpenAI
    except ImportError as e:
        raise SystemExit(
            "The 'openai' package is required.  Install with: pip install openai"
        ) from e

    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    except ImportError as e:
        raise SystemExit(
            "The 'azure-identity' package is required.  "
            "Install with: pip install azure-identity"
        ) from e

    endpoint    = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment  = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

    if not (endpoint and deployment):
        raise SystemExit(
            "Missing Azure OpenAI configuration.  Set AZURE_OPENAI_ENDPOINT "
            "and AZURE_OPENAI_DEPLOYMENT."
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
    )

    response = client.chat.completions.create(
        model=deployment,                          # In Azure SDK, "model" is the deployment name.
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},   # JSON-mode — forces valid JSON.
        temperature=0.2,                           # low temp = stable structure
    )

    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 3. Spec  -->  Ontology object
# ---------------------------------------------------------------------------

def spec_to_ontology(spec: dict) -> Ontology:
    """Turn the LLM's structured spec into an Ontology, with sane defaults
    and enough validation to recover from minor model mistakes."""
    iri    = spec.get("iri_base") or "https://example.org/ont/"
    prefix = spec.get("prefix")   or "ex"
    ont = Ontology(iri=iri, prefix=prefix)

    # ---- classes (two passes so subclass references can resolve) ----
    class_specs = spec.get("classes", []) or []
    declared = {c["name"] for c in class_specs if "name" in c}
    for c in class_specs:
        if "name" not in c:
            continue
        ont.add_class(
            name=c["name"],
            parents=[p for p in c.get("parents", []) if p in declared],
            comment=c.get("comment", "") or "",
            disjoint_with=[d for d in c.get("disjoint_with", []) if d in declared],
        )

    # ---- object properties ----
    for p in spec.get("object_properties", []) or []:
        if "name" not in p:
            continue
        domain = p.get("domain") if p.get("domain") in declared else None
        range_ = p.get("range")  if p.get("range")  in declared else None
        ont.add_object_property(
            name=p["name"],
            domain=domain,
            range_=range_,
            inverse_of=p.get("inverse_of") or None,
            transitive=bool(p.get("transitive")),
            symmetric=bool(p.get("symmetric")),
            functional=bool(p.get("functional")),
            comment=p.get("comment", "") or "",
        )

    # ---- data properties ----
    allowed_xsd = {"xsd:string", "xsd:integer", "xsd:double",
                   "xsd:boolean", "xsd:dateTime"}
    for p in spec.get("data_properties", []) or []:
        if "name" not in p:
            continue
        ont.add_data_property(
            name=p["name"],
            domain=p.get("domain") if p.get("domain") in declared else None,
            datatype=p.get("datatype") if p.get("datatype") in allowed_xsd else "xsd:string",
            comment=p.get("comment", "") or "",
        )

    # ---- individuals (two passes: declare first, then assert relations) ----
    ind_specs = spec.get("individuals", []) or []
    declared_inds = set()
    for ind in ind_specs:
        if "name" not in ind:
            continue
        types = [t for t in ind.get("types", []) if t in declared]
        if not types:
            continue
        ont.add_individual(name=ind["name"], types=types)
        declared_inds.add(ind["name"])

    for ind in ind_specs:
        name = ind.get("name")
        if name not in declared_inds:
            continue
        # object properties
        for pname, targets in (ind.get("object_props") or {}).items():
            if pname not in ont.object_properties:
                continue
            for tgt in targets or []:
                if tgt not in declared_inds:
                    continue
                try:
                    ont.assert_object(name, pname, tgt)
                except ValueError as e:
                    print(f"[skip] {name} {pname} {tgt}: {e}", file=sys.stderr)
        # data properties
        for pname, values in (ind.get("data_props") or {}).items():
            if pname not in ont.data_properties:
                continue
            for v in values or []:
                ont.assert_data(name, pname, v)

    return ont


# ---------------------------------------------------------------------------
# 4. Dataset sampling helper
# ---------------------------------------------------------------------------

def sample_csv(path: str, max_rows: int = 8) -> str:
    """Return a small textual sample of a CSV — header + first N rows."""
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"Dataset not found: {path}")
    rows: list[list[str]] = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            rows.append(row)
            if i >= max_rows:
                break
    if not rows:
        return "(empty file)"
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, *body = rows
    out = ["columns: " + ", ".join(header), "sample rows:"]
    for r in body:
        out.append(" | ".join(r))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 5. Mocked spec for --dry-run (lets you exercise the pipeline offline)
# ---------------------------------------------------------------------------

MOCK_SPEC: dict = {
    "ontology_name": "hospital",
    "iri_base": "https://example.org/hospital/",
    "prefix": "hosp",
    "description": "A small hospital domain ontology",
    "classes": [
        {"name": "Person",         "parents": [], "comment": "A human."},
        {"name": "Patient",        "parents": ["Person"], "disjoint_with": ["Doctor"]},
        {"name": "Doctor",         "parents": ["Person"], "disjoint_with": ["Patient"]},
        {"name": "Department",     "parents": []},
        {"name": "Appointment",    "parents": []},
        {"name": "Diagnosis",      "parents": []},
        {"name": "Prescription",   "parents": []},
        {"name": "Medication",     "parents": []},
    ],
    "object_properties": [
        {"name": "treatedBy",   "domain": "Patient",      "range": "Doctor",
         "inverse_of": "treats"},
        {"name": "treats",      "domain": "Doctor",       "range": "Patient",
         "inverse_of": "treatedBy"},
        {"name": "worksIn",     "domain": "Doctor",       "range": "Department"},
        {"name": "scheduledFor","domain": "Appointment",  "range": "Patient"},
        {"name": "withDoctor",  "domain": "Appointment",  "range": "Doctor"},
        {"name": "hasDiagnosis","domain": "Patient",      "range": "Diagnosis"},
        {"name": "prescribes",  "domain": "Doctor",       "range": "Prescription"},
        {"name": "ofMedication","domain": "Prescription", "range": "Medication"},
    ],
    "data_properties": [
        {"name": "fullName",     "domain": "Person",       "datatype": "xsd:string"},
        {"name": "birthDate",    "domain": "Person",       "datatype": "xsd:dateTime"},
        {"name": "appointmentAt","domain": "Appointment",  "datatype": "xsd:dateTime"},
        {"name": "icd10Code",    "domain": "Diagnosis",    "datatype": "xsd:string"},
        {"name": "dosageMg",     "domain": "Prescription", "datatype": "xsd:double"},
    ],
    "individuals": [
        {"name": "Cardiology",   "types": ["Department"]},
        {"name": "DrSmith",      "types": ["Doctor"],
         "object_props": {"worksIn": ["Cardiology"]},
         "data_props":   {"fullName": ["Dr. Jane Smith"]}},
        {"name": "DrLee",        "types": ["Doctor"],
         "object_props": {"worksIn": ["Cardiology"]},
         "data_props":   {"fullName": ["Dr. Hyun Lee"]}},
        {"name": "PatJohn",      "types": ["Patient"],
         "object_props": {"treatedBy": ["DrSmith"]},
         "data_props":   {"fullName": ["John Doe"], "birthDate": ["1980-04-12T00:00:00Z"]}},
        {"name": "Hypertension", "types": ["Diagnosis"],
         "data_props": {"icd10Code": ["I10"]}},
        {"name": "Lisinopril",   "types": ["Medication"]},
        {"name": "Rx_001",       "types": ["Prescription"],
         "object_props": {"ofMedication": ["Lisinopril"]},
         "data_props":   {"dosageMg": [10.0]}},
        {"name": "Appt_001",     "types": ["Appointment"],
         "object_props": {"scheduledFor": ["PatJohn"], "withDoctor": ["DrSmith"]},
         "data_props":   {"appointmentAt": ["2026-05-12T09:30:00Z"]}},
    ],
}


# ---------------------------------------------------------------------------
# 6. Orchestration
# ---------------------------------------------------------------------------

def slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower())
    return s.strip("_") or "ontology"


def generate(description: str, dataset_path: str | None = None,
             topic: str | None = None, dry_run: bool = False,
             out_dir: str = "ontology") -> Ontology:

    user_description = description
    dataset_sample = None
    if dataset_path:
        dataset_sample = sample_csv(dataset_path)
        if topic and topic.strip():
            user_description = f"{topic.strip()}\n\n{description}".strip()

    user_prompt = build_user_prompt(user_description, dataset_sample)

    if dry_run:
        print("[dry-run] Skipping Azure OpenAI call; using built-in mock spec.")
        spec = MOCK_SPEC
    else:
        print("Calling Azure OpenAI (Foundry)...", file=sys.stderr)
        spec = call_azure_openai(SYSTEM_PROMPT, user_prompt)

    # Build the ontology, then export.
    ont = spec_to_ontology(spec)
    name = slugify(spec.get("ontology_name") or topic or description[:32])
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    (out_path / f"{name}.raw.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    (out_path / f"{name}.ttl").write_text(ont.to_turtle(), encoding="utf-8")
    (out_path / f"{name}.jsonld").write_text(json.dumps(ont.to_jsonld(), indent=2),
                                             encoding="utf-8")
    (out_path / f"{name}.json").write_text(json.dumps(ont.to_dict(), indent=2),
                                           encoding="utf-8")

    issues = ont.check_consistency()
    print(f"\nOntology '{name}' built:")
    print(f"  classes:           {len(ont.classes)}")
    print(f"  object properties: {len(ont.object_properties)}")
    print(f"  data properties:   {len(ont.data_properties)}")
    print(f"  individuals:       {len(ont.individuals)}")
    print(f"  consistency:       {'OK' if not issues else 'issues:'}")
    for p in issues:
        print(f"    - {p}")
    print(f"\nWrote {name}.ttl, {name}.jsonld, {name}.json, {name}.raw.json "
          f"to {out_path.resolve()}")
    return ont


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an OWL-style ontology from a description or dataset using Azure OpenAI (Foundry).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python llm_ontology_generator.py --describe "Hospital domain"
              python llm_ontology_generator.py --dataset orders.csv --topic "Retail orders"
              python llm_ontology_generator.py --describe "Hospital" --dry-run
        """),
    )
    parser.add_argument("--describe", help="Natural-language domain description.")
    parser.add_argument("--dataset",  help="Path to a CSV dataset to derive the ontology from.")
    parser.add_argument("--topic",    help="Short topic label when using --dataset.")
    parser.add_argument("--out-dir",  default="ontology",
                        help="Output directory (default: ./ontology).")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Skip the Azure OpenAI call and use a built-in mock spec.")
    args = parser.parse_args()

    if not args.describe and not args.dataset:
        parser.error("Provide --describe or --dataset (or both).")

    description = args.describe or f"Build an ontology for the topic: {args.topic or 'data in this CSV'}."
    generate(
        description=description,
        dataset_path=args.dataset,
        topic=args.topic,
        dry_run=args.dry_run,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()
