# Building an Ontology Builder with Microsoft Fabric (Python)

> Companion to `ontology_builder.py`. This document explains *what* an ontology
> is, *why* it matters, *where* it pays off, and *how* to evolve the included
> single-file builder into a Microsoft Fabric–native solution.

---

## 1. What is an ontology?

An **ontology** is a formal, machine-readable description of *the things in a
domain and the relationships between them*. It answers three questions:

| Layer | What it captures | Example (manufacturing) |
|-------|------------------|-------------------------|
| **Vocabulary** | The concepts that exist | *Machine, Sensor, Operator, Product* |
| **Structure** | How concepts relate | *A Sensor `monitors` a Machine* |
| **Rules** | Constraints and inferences | *A CNC is a Machine; a Machine cannot be a Person* |

An ontology is more than a database schema:

- A **schema** says "this column is a string".
- An **ontology** says "this thing is a `TemperatureSensor`, which is a kind
  of `Sensor`, which is a kind of `Equipment`, and it `monitors` a `Machine`
  whose `Operator` is a `Person`."

The classical W3C stack is: **RDF** (data model: subject-predicate-object
triples) → **RDFS** (basic classes & subclasses) → **OWL** (rich logic:
domain, range, inverse, transitive, disjoint, cardinality) → **SPARQL**
(query language) → **SHACL** (data-shape validation).

### Key building blocks (and what our code calls them)

| Concept | OWL term | In `ontology_builder.py` |
|---------|----------|--------------------------|
| Type / concept | `owl:Class` | `OntClass` |
| "Is-a" hierarchy | `rdfs:subClassOf` | `OntClass.parents` |
| Relationship between things | `owl:ObjectProperty` | `ObjectProperty` |
| Attribute / literal value | `owl:DatatypeProperty` | `DataProperty` |
| Concrete entity | `owl:NamedIndividual` | `Individual` |
| Reverse relationship | `owl:inverseOf` | `ObjectProperty.inverse_of` |
| Chained relationship | `owl:TransitiveProperty` | `ObjectProperty.transitive` |
| Mutually-exclusive types | `owl:disjointWith` | `OntClass.disjoint_with` |
| At-most-one rule | `owl:FunctionalProperty` | `ObjectProperty.functional` |

### T-Box vs A-Box (terminology you'll see everywhere)

- **T-Box** (*terminological*): the schema — classes, properties, rules.
- **A-Box** (*assertional*): the data — individuals and the facts about them.

Our example builds both: the T-Box defines `Machine`, `Sensor`, `monitors`,
etc., and the A-Box asserts `TempSensor_1 monitors CNC_001`.

---

## 2. Where ontologies are needed (and where they earn their keep)

Ontologies pay off whenever **meaning has to survive**: across teams,
across systems, across time, or across human↔machine boundaries.

| Need | Without ontology | With ontology |
|------|------------------|---------------|
| **Joining heterogeneous data** | Every team writes column-mapping code; "customer_id" means three different things | One shared vocabulary; mappings are declarative |
| **Semantic search** | Keyword match: "pump" misses "centrifugal compressor" | Hierarchy-aware: a query for `Equipment` returns *all* subtypes |
| **Reasoning / inference** | Hand-coded if/else | Engine derives facts (e.g. "if X is a CNC then X is a Machine") |
| **AI / RAG grounding** | LLM hallucinates relationships | LLM is constrained to a vetted graph |
| **Compliance & lineage** | Spreadsheet of "what means what" | Machine-checkable, queryable, auditable |
| **Interoperability** | Per-partner ETL | Standard formats (RDF, JSON-LD) flow between systems |

### Concrete domains where ontologies dominate

1. **Healthcare & life sciences** — SNOMED CT, ICD-10, MeSH, Gene Ontology.
   Lets a query for *"cardiovascular disease"* match thousands of specific
   conditions without hard-coding every code.
2. **Manufacturing & IIoT** — ISA-95, OPC UA companion specs, Brick Schema.
   A digital twin is fundamentally an ontology.
3. **Financial services** — FIBO (Financial Industry Business Ontology) for
   counterparty risk, derivatives, regulatory reporting.
4. **Knowledge graphs** — Google's Knowledge Graph, Wikidata, enterprise
   "Customer 360" graphs.
5. **AI grounding** — Retrieval-augmented generation against a knowledge graph
   gives an LLM a typed, navigable structure instead of free-text chunks.
6. **Government & open data** — schema.org, DCAT for data catalogs.

### What difference does it actually make?

A worked illustration from our example:

> **Question:** *"List every piece of equipment in the Austin site."*

- **Relational/SQL approach.** You need a table per equipment type
  (`cnc`, `robot`, `conveyor`, `sensor` …) and a `UNION ALL` across all of
  them, joined to `production_line` and `site`. Every new equipment type
  changes the query.
- **Ontology approach.** `instances_of("Equipment")` walks the subclass
  hierarchy and returns CNCs, Robots, Conveyors, and Sensors automatically.
  Add a new `Press` subclass tomorrow — *the same query returns it*.

That property — **queries that don't break when the schema grows** — is the
single biggest practical win.

---

## 3. Worked example: a Smart-Manufacturing ontology

The included Python file builds this T-Box:

```
Asset
├── Equipment
│   ├── Machine
│   │   ├── CNC
│   │   └── Robot
│   ├── Conveyor
│   └── Sensor
│       ├── TemperatureSensor
│       └── VibrationSensor
└── Product

Location
├── Site
└── ProductionLine

Person
├── Operator       (disjoint with Technician)
└── Technician     (disjoint with Operator)

WorkOrder
MaintenanceEvent
```

…and these properties:

| Property | Domain → Range | Characteristics |
|----------|----------------|-----------------|
| `locatedIn` | Asset → Location | transitive |
| `partOf` | Location → Location | transitive |
| `monitors` | Sensor → Equipment | – |
| `operates` | Operator → Machine | inverse of `operatedBy` |
| `operatedBy` | Machine → Operator | inverse of `operates` |
| `performedOn` | MaintenanceEvent → Equipment | – |
| `performedBy` | MaintenanceEvent → Technician | – |
| `produces` | Machine → Product | – |
| `serialNumber` | Equipment → string | data property |
| `readingValue` | Sensor → double | data property |

Some A-Box facts that exercise the rules:

- `Alice operates CNC_001` → engine auto-derives `CNC_001 operatedBy Alice`.
- `MX_42 performedOn CNC_001` and `MX_42 performedBy Bob`.
- `TempSensor_1 monitors CNC_001` and `readingValue = 78.4 °C`.

Negative test the demo runs:

- Asserting `Widget operates CNC_001` is **rejected** because the domain of
  `operates` is `Operator`, and `Widget` is a `Product`. A relational DB
  would happily insert this row.

---

## 4. Strategy & plan

### 4.1 Strategy (the why)

1. **Start with one bounded domain.** Don't try to ontologize the enterprise
   on day one — pick *one* slice (manufacturing assets, customer 360,
   regulatory reporting).
2. **Reuse, don't reinvent.** For most domains a public ontology exists
   (Brick, FIBO, SNOMED, schema.org). Borrow classes; specialise where you
   must.
3. **Treat the ontology as a product.** Versioned, owned, reviewed, tested.
4. **Two artefacts, one source of truth.** Code generates both the
   serialized OWL/Turtle (for tools like Protégé, GraphDB, Stardog,
   Neo4j n10s) **and** the data layer (Lakehouse Delta tables).
5. **Make every fact traceable.** Every triple should know which source
   system / pipeline produced it.

### 4.2 Plan (the how, in five increments)

| Phase | Deliverable | Effort | Dependency |
|-------|-------------|--------|------------|
| **1. Local POC** | `ontology_builder.py` (this repo). Classes, properties, individuals, reasoning, Turtle/JSON-LD export. | 1–2 days | Python only |
| **2. Validation & query** | Add SHACL-style shape checks; add SPARQL via `rdflib`; add a simple CLI. | 2–3 days | `rdflib` |
| **3. Fabric ingestion** | Read T-Box definitions from a Lakehouse table; read A-Box facts from Delta tables; rebuild the in-memory graph. | 3–5 days | Fabric workspace, Lakehouse |
| **4. Fabric materialization** | Persist inferred triples to a Delta `triples` table; expose a Power BI semantic model on top. | 3–5 days | Spark notebook |
| **5. Continuous build** | Fabric Data Pipeline / notebook on schedule: re-ingest sources → rebuild graph → validate → publish OWL to OneLake → refresh Power BI. Optional: GraphRAG over the graph for Copilot. | 1–2 weeks | Pipelines, scheduling |

### 4.3 What "good" looks like

- An analyst can ask **"every asset in Austin and its last maintenance
  event"** without knowing whether Austin is a `Site`, `Region`, or
  `Building`.
- A new equipment type is added by inserting **one row** in the classes
  table — no Power BI model rebuild, no SQL view rewrite.
- A data-quality rule violation (e.g. "a Machine without a
  serialNumber") is caught **before** the data lands in a report.

---

## 5. From the single-file builder to Microsoft Fabric

The included `ontology_builder.py` is **self-contained on purpose** — it
runs anywhere Python 3.10+ runs, with zero dependencies. Below is how each
piece maps to Fabric services when you're ready.

### 5.1 Architecture sketch

```
            ┌──────────── Source systems ────────────┐
            │  ERP   MES   Historian   CMMS   IoT    │
            └──────────────────┬─────────────────────┘
                               │ (Dataflows / Pipelines)
                               ▼
   ┌─────────────────────── Fabric Lakehouse ────────────────────────┐
   │  Bronze: raw tables                                              │
   │  Silver: cleansed entities (assets, sensors, events)             │
   │  Gold:   ontology-aligned tables (one per OntClass + 'triples')  │
   └─────────────────────────────────┬────────────────────────────────┘
                                     │  Spark notebook
                                     ▼
                        ┌────────────────────────┐
                        │  Ontology builder      │  ← this repo
                        │  (rules, inference,    │
                        │   validation, export)  │
                        └─────┬───────────┬──────┘
                              │           │
                              ▼           ▼
                  OneLake Files       Delta `triples`
                  (ontology.ttl,      (subject, predicate,
                   ontology.jsonld)    object, source, ts)
                              │           │
                              ▼           ▼
                  External tools      Power BI semantic model
                  (Protégé, GraphDB,  + Copilot / GraphRAG
                   Neo4j n10s)
```

### 5.2 Where each Fabric service plugs in

| Fabric capability | Role |
|-------------------|------|
| **Lakehouse (Delta)** | Stores both the source data and the materialized triples. Subclass closure can be written as a Delta table for fast joins. |
| **OneLake** | Single place to publish `ontology.ttl` so every workload (Power BI, Real-Time Intelligence, Notebooks) sees the *same* schema. |
| **Spark Notebook** | Hosts the ontology builder. Reads sources, runs the inference, writes the triples table, writes the OWL file. |
| **Data Pipelines** | Orchestrates the rebuild on a schedule or on event triggers. |
| **Real-Time Intelligence (KQL)** | Streams sensor readings into Eventhouse; the ontology gives them typed identity (this row is a `TemperatureSensor.readingValue`). |
| **Power BI** | Consumes the gold tables; the ontology determines the semantic model relationships (no manual modelling). |
| **Copilot / Fabric AI Skills** | Uses the ontology as a grounding graph for GraphRAG — answers like *"which CNCs in Austin had a vibration excursion last week?"* without hand-written SQL. |

### 5.3 The integration points are already marked

Look for `# FABRIC INTEGRATION POINT` in `ontology_builder.py`. The
`FabricAdapter` class at the bottom of the file is a stub showing exactly
the three Spark calls you'll add:

```python
# 1. Ingest A-Box from Lakehouse
df = spark.read.format("delta").load("Tables/equipment")
for row in df.collect():
    ont.add_individual(row.asset_id, types=[row.class_name])

# 2. Persist inferred triples back to a Lakehouse table
spark.createDataFrame(triples, "subject string, predicate string, object string") \
     .write.format("delta").mode("overwrite").save("Tables/triples")

# 3. Publish the OWL/Turtle to OneLake so other workloads can discover it
ont.to_turtle()  # → write to /lakehouse/default/Files/ontology/manufacturing.ttl
```

### 5.4 Why keep v1 Fabric-free

- **Local first, cloud later** — develop, unit-test, and reason locally; the
  semantics don't depend on Spark.
- **Same code, two runtimes** — exactly the same `Ontology` class will run
  inside a Fabric notebook the day you wrap it with the adapter.
- **No vendor lock** — the OWL output is a W3C standard, readable by
  Protégé, rdflib, GraphDB, Stardog, AnzoGraph, Neo4j (via n10s), and
  Microsoft's own tooling.

---

## 6. Running the included code

```bash
python ontology_builder.py
```

What it does:

1. Builds the manufacturing T-Box and A-Box.
2. Demonstrates **subclass inference** (`instances_of("Equipment")` returns
   every CNC, Robot, Conveyor, and Sensor without enumerating them).
3. Demonstrates **inverse inference** (asserting `Alice operates CNC_001`
   makes `CNC_001 operatedBy Alice` queryable).
4. Demonstrates **transitive inference** on `locatedIn`.
5. Runs a **consistency check** (disjoint classes, functional properties).
6. Runs a **negative test** — `Widget operates CNC_001` is rejected by
   domain validation, proving the ontology is enforcing meaning, not just
   storing rows.
7. Exports the graph to:
   - `manufacturing.ttl` — open in Protégé or load with `rdflib`
   - `manufacturing.jsonld` — feed to any JSON-LD aware tool
   - `manufacturing.json` — native serialization for round-tripping

---

## 7. Recommended next steps

1. **Add SPARQL.** `pip install rdflib` and load the Turtle output —
   instantly get a real triple store with a query engine.
2. **Add SHACL shapes.** Replace the ad-hoc `check_consistency()` with
   declarative shape constraints (`pyshacl`).
3. **Add property chains.** Express *"if `locatedIn ∘ partOf` then
   `locatedIn`"* so a CNC is inferred to be `locatedIn Site_Austin` via
   its line.
4. **Wrap the Fabric adapter.** Move from CSV/JSON ingestion to
   `spark.read.format("delta")`. The class hierarchy and reasoning code
   does not change.
5. **Wire it to Copilot.** Publish the Turtle to OneLake; build a Fabric
   AI Skill that uses the ontology as the retrieval graph.

---

## 8. Glossary

| Term | One-line definition |
|------|--------------------|
| RDF | Triple-based data model: *subject–predicate–object*. |
| RDFS | RDF Schema; adds classes and `subClassOf`. |
| OWL | Web Ontology Language; full description-logic semantics. |
| Turtle (.ttl) | The most readable RDF text format. |
| JSON-LD | RDF expressed as JSON; native to many web APIs. |
| SPARQL | The SQL of RDF graphs. |
| SHACL | Shape constraints — like CHECK constraints for graphs. |
| T-Box / A-Box | Schema (terminology) vs data (assertions). |
| Reasoner | Engine that derives implicit facts from explicit ones. |
| Knowledge graph | An ontology plus a lot of A-Box, often at scale. |

---

*Files in this delivery:*

- `ontology_builder.py` — the runnable single-file builder.
- `ontology_builder_guide.md` — this document.
- *(generated on run)* `manufacturing.ttl`, `manufacturing.jsonld`,
  `manufacturing.json`.
