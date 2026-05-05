"""
Ontology Builder — Single-File Reference Implementation
=======================================================

A self-contained ontology builder demonstrating the core concepts of an
ontology: classes, properties (object + data), individuals, axioms,
relationships, simple reasoning (subclass inference, domain/range checks,
transitive closure), and export to RDF/OWL (Turtle) and JSON-LD.

This first version intentionally has NO Microsoft Fabric dependency so it
runs anywhere with Python 3.10+. Integration points for Fabric (Lakehouse,
OneLake, Data Warehouse, Real-Time Intelligence) are clearly marked with
`# FABRIC INTEGRATION POINT` comments and a stub adapter class at the bottom.

Worked example: a Smart Manufacturing ontology (factories, lines, machines,
sensors, products, operators, maintenance events).

Run:
    python ontology_builder.py

Outputs:
    - prints inference results to stdout
    - writes manufacturing.ttl     (Turtle / RDF)
    - writes manufacturing.jsonld  (JSON-LD)
    - writes manufacturing.json    (native serialization)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Core ontology primitives
# ---------------------------------------------------------------------------

@dataclass
class OntClass:
    """A concept / type. Equivalent to OWL Class."""
    name: str
    parents: set[str] = field(default_factory=set)
    comment: str = ""
    disjoint_with: set[str] = field(default_factory=set)


@dataclass
class ObjectProperty:
    """A relationship between two individuals. Equivalent to OWL ObjectProperty."""
    name: str
    domain: str | None = None      # class name
    range_: str | None = None      # class name
    inverse_of: str | None = None
    transitive: bool = False
    symmetric: bool = False
    functional: bool = False
    comment: str = ""


@dataclass
class DataProperty:
    """An attribute on an individual. Equivalent to OWL DatatypeProperty."""
    name: str
    domain: str | None = None
    datatype: str = "xsd:string"   # xsd:string | xsd:integer | xsd:double | xsd:boolean | xsd:dateTime
    comment: str = ""


@dataclass
class Individual:
    """An instance / named entity belonging to one or more classes."""
    name: str
    types: set[str] = field(default_factory=set)
    object_props: dict[str, set[str]] = field(default_factory=dict)
    data_props: dict[str, list[Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The ontology itself
# ---------------------------------------------------------------------------

class Ontology:
    """
    A small but real ontology engine.

    Responsibilities:
      * register classes, object properties, data properties, individuals
      * validate domain / range constraints
      * compute subclass closure and transitive property closure
      * answer queries (instances of, related to, etc.)
      * serialize to RDF Turtle, JSON-LD, and native JSON
    """

    def __init__(self, iri: str = "https://example.org/ont/", prefix: str = "ex"):
        self.iri = iri.rstrip("/") + "/"
        self.prefix = prefix
        self.classes: dict[str, OntClass] = {}
        self.object_properties: dict[str, ObjectProperty] = {}
        self.data_properties: dict[str, DataProperty] = {}
        self.individuals: dict[str, Individual] = {}

    # ------------------------------ schema --------------------------------

    def add_class(self, name: str, parents: Iterable[str] = (), comment: str = "",
                  disjoint_with: Iterable[str] = ()) -> OntClass:
        cls = OntClass(name=name, parents=set(parents), comment=comment,
                       disjoint_with=set(disjoint_with))
        self.classes[name] = cls
        return cls

    def add_object_property(self, name: str, domain: str | None = None,
                            range_: str | None = None, **kwargs) -> ObjectProperty:
        prop = ObjectProperty(name=name, domain=domain, range_=range_, **kwargs)
        self.object_properties[name] = prop
        # Make inverse symmetric in registration: if A inverseOf B,
        # ensure B inverseOf A so assertions in either direction propagate.
        if prop.inverse_of and prop.inverse_of in self.object_properties:
            other = self.object_properties[prop.inverse_of]
            if not other.inverse_of:
                other.inverse_of = name
        return prop

    def add_data_property(self, name: str, domain: str | None = None,
                          datatype: str = "xsd:string", comment: str = "") -> DataProperty:
        prop = DataProperty(name=name, domain=domain, datatype=datatype, comment=comment)
        self.data_properties[name] = prop
        return prop

    # ------------------------------ A-Box ---------------------------------

    def add_individual(self, name: str, types: Iterable[str] = ()) -> Individual:
        for t in types:
            if t not in self.classes:
                raise ValueError(f"Unknown class '{t}' for individual '{name}'")
        ind = Individual(name=name, types=set(types))
        self.individuals[name] = ind
        return ind

    def assert_object(self, subject: str, predicate: str, object_: str) -> None:
        self._check_individual(subject)
        self._check_individual(object_)
        if predicate not in self.object_properties:
            raise ValueError(f"Unknown object property '{predicate}'")
        prop = self.object_properties[predicate]

        # Domain / range type-checking using subclass closure.
        if prop.domain and not self._is_instance_of(subject, prop.domain):
            raise ValueError(
                f"Domain violation: {subject} is not a {prop.domain} for {predicate}"
            )
        if prop.range_ and not self._is_instance_of(object_, prop.range_):
            raise ValueError(
                f"Range violation: {object_} is not a {prop.range_} for {predicate}"
            )

        self.individuals[subject].object_props.setdefault(predicate, set()).add(object_)

        # Symmetric properties: assert inverse direction automatically.
        if prop.symmetric:
            self.individuals[object_].object_props.setdefault(predicate, set()).add(subject)

        # Inverse properties: assert the inverse triple automatically.
        if prop.inverse_of:
            self.individuals[object_].object_props.setdefault(prop.inverse_of, set()).add(subject)

    def assert_data(self, subject: str, predicate: str, value: Any) -> None:
        self._check_individual(subject)
        if predicate not in self.data_properties:
            raise ValueError(f"Unknown data property '{predicate}'")
        self.individuals[subject].data_props.setdefault(predicate, []).append(value)

    # ------------------------------ reasoning -----------------------------

    def superclasses_of(self, cls: str) -> set[str]:
        """Transitive closure of rdfs:subClassOf."""
        if cls not in self.classes:
            return set()
        seen, stack = set(), [cls]
        while stack:
            c = stack.pop()
            for p in self.classes[c].parents:
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        return seen

    def _is_instance_of(self, individual: str, cls: str) -> bool:
        if individual not in self.individuals:
            return False
        types = self.individuals[individual].types
        if cls in types:
            return True
        for t in types:
            if cls in self.superclasses_of(t):
                return True
        return False

    def instances_of(self, cls: str, include_subclasses: bool = True) -> list[str]:
        """All individuals that are (directly or via subclass) of `cls`."""
        results: list[str] = []
        for name, ind in self.individuals.items():
            if cls in ind.types:
                results.append(name)
            elif include_subclasses:
                for t in ind.types:
                    if cls in self.superclasses_of(t):
                        results.append(name)
                        break
        return sorted(results)

    def related(self, subject: str, predicate: str, transitive: bool | None = None) -> set[str]:
        """Follow an object property; optionally compute transitive closure."""
        if subject not in self.individuals:
            return set()
        prop = self.object_properties.get(predicate)
        is_transitive = prop.transitive if (transitive is None and prop) else bool(transitive)

        direct = self.individuals[subject].object_props.get(predicate, set())
        if not is_transitive:
            return set(direct)

        seen, stack = set(direct), list(direct)
        while stack:
            cur = stack.pop()
            for nxt in self.individuals.get(cur, Individual(cur)).object_props.get(predicate, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def check_consistency(self) -> list[str]:
        """Return a list of violations found (empty == consistent)."""
        problems: list[str] = []
        for ind in self.individuals.values():
            # Disjointness check.
            for t in ind.types:
                cls = self.classes.get(t)
                if not cls:
                    continue
                for d in cls.disjoint_with:
                    if d in ind.types:
                        problems.append(f"{ind.name}: classes {t} and {d} are disjoint")
            # Functional property check.
            for pname, targets in ind.object_props.items():
                prop = self.object_properties.get(pname)
                if prop and prop.functional and len(targets) > 1:
                    problems.append(
                        f"{ind.name}: functional property {pname} has {len(targets)} values"
                    )
        return problems

    # ------------------------------ helpers -------------------------------

    def _check_individual(self, name: str) -> None:
        if name not in self.individuals:
            raise ValueError(f"Unknown individual '{name}'")

    # ------------------------------ export --------------------------------

    def to_turtle(self) -> str:
        """Minimal RDF/Turtle serialization. Good enough for round-tripping in Protégé / rdflib."""
        lines = [
            f"@prefix {self.prefix}: <{self.iri}> .",
            "@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
            "@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .",
            "",
            f"<{self.iri.rstrip('/')}> a owl:Ontology .",
            "",
        ]

        for cls in self.classes.values():
            lines.append(f"{self.prefix}:{cls.name} a owl:Class ;")
            for p in sorted(cls.parents):
                lines.append(f"    rdfs:subClassOf {self.prefix}:{p} ;")
            for d in sorted(cls.disjoint_with):
                lines.append(f"    owl:disjointWith {self.prefix}:{d} ;")
            if cls.comment:
                lines.append(f'    rdfs:comment "{cls.comment}" ;')
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        for prop in self.object_properties.values():
            types = ["owl:ObjectProperty"]
            if prop.transitive:  types.append("owl:TransitiveProperty")
            if prop.symmetric:   types.append("owl:SymmetricProperty")
            if prop.functional:  types.append("owl:FunctionalProperty")
            lines.append(f"{self.prefix}:{prop.name} a {', '.join(types)} ;")
            if prop.domain:    lines.append(f"    rdfs:domain {self.prefix}:{prop.domain} ;")
            if prop.range_:    lines.append(f"    rdfs:range  {self.prefix}:{prop.range_} ;")
            if prop.inverse_of:lines.append(f"    owl:inverseOf {self.prefix}:{prop.inverse_of} ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        for prop in self.data_properties.values():
            lines.append(f"{self.prefix}:{prop.name} a owl:DatatypeProperty ;")
            if prop.domain:   lines.append(f"    rdfs:domain {self.prefix}:{prop.domain} ;")
            lines.append(f"    rdfs:range  {prop.datatype} .")
            lines.append("")

        for ind in self.individuals.values():
            type_iris = ", ".join(f"{self.prefix}:{t}" for t in sorted(ind.types)) or "owl:NamedIndividual"
            lines.append(f"{self.prefix}:{ind.name} a {type_iris} ;")
            for pname, targets in ind.object_props.items():
                joined = ", ".join(f"{self.prefix}:{t}" for t in sorted(targets))
                lines.append(f"    {self.prefix}:{pname} {joined} ;")
            for pname, values in ind.data_props.items():
                joined = ", ".join(_lit(v) for v in values)
                lines.append(f"    {self.prefix}:{pname} {joined} ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        return "\n".join(lines)

    def to_jsonld(self) -> dict:
        ctx = {
            self.prefix: self.iri,
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl":  "http://www.w3.org/2002/07/owl#",
            "xsd":  "http://www.w3.org/2001/XMLSchema#",
        }
        graph: list[dict] = []
        for cls in self.classes.values():
            graph.append({
                "@id": f"{self.prefix}:{cls.name}",
                "@type": "owl:Class",
                "rdfs:subClassOf": [{"@id": f"{self.prefix}:{p}"} for p in sorted(cls.parents)],
            })
        for ind in self.individuals.values():
            node: dict[str, Any] = {
                "@id": f"{self.prefix}:{ind.name}",
                "@type": [f"{self.prefix}:{t}" for t in sorted(ind.types)],
            }
            for pname, targets in ind.object_props.items():
                node[f"{self.prefix}:{pname}"] = [
                    {"@id": f"{self.prefix}:{t}"} for t in sorted(targets)
                ]
            for pname, values in ind.data_props.items():
                node[f"{self.prefix}:{pname}"] = values
            graph.append(node)
        return {"@context": ctx, "@graph": graph}

    # --------------------------- RDF/XML + N-Triples ----------------------
    # Both formats are W3C-standard RDF serializations that can be loaded
    # directly into any RDF-compatible triplestore (GraphDB, Stardog, Apache
    # Jena Fuseki, Blazegraph, AnzoGraph, Neo4j n10s, AWS Neptune, etc.).
    # If `rdflib` is installed we use it for a fully-spec-compliant round-trip
    # via Turtle; otherwise we emit a minimal but valid serialization
    # directly from the in-memory model.

    def _expand(self, local: str) -> str:
        """Expand a local name to a full IRI under this ontology's namespace."""
        return f"{self.iri}{local}"

    _XSD = "http://www.w3.org/2001/XMLSchema#"
    _RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    _RDFS = "http://www.w3.org/2000/01/rdf-schema#"
    _OWL = "http://www.w3.org/2002/07/owl#"

    def _xsd_iri(self, qname: str) -> str:
        """Turn 'xsd:string' into the full XSD IRI."""
        if qname.startswith("xsd:"):
            return self._XSD + qname.split(":", 1)[1]
        return qname

    def _iter_triples(self) -> Iterable[tuple[str, str, tuple[str, str | None]]]:
        """
        Yield (subject_iri, predicate_iri, (object, kind)) where kind is
        either 'iri' or an XSD datatype IRI for literals.
        """
        ont_iri = self.iri.rstrip("/")
        yield (ont_iri, self._RDF + "type", (self._OWL + "Ontology", "iri"))

        # Classes
        for cls in self.classes.values():
            s = self._expand(cls.name)
            yield (s, self._RDF + "type", (self._OWL + "Class", "iri"))
            for p in sorted(cls.parents):
                yield (s, self._RDFS + "subClassOf", (self._expand(p), "iri"))
            for d in sorted(cls.disjoint_with):
                yield (s, self._OWL + "disjointWith", (self._expand(d), "iri"))
            if cls.comment:
                yield (s, self._RDFS + "comment", (cls.comment, self._XSD + "string"))

        # Object properties
        for prop in self.object_properties.values():
            s = self._expand(prop.name)
            yield (s, self._RDF + "type", (self._OWL + "ObjectProperty", "iri"))
            if prop.transitive:
                yield (s, self._RDF + "type", (self._OWL + "TransitiveProperty", "iri"))
            if prop.symmetric:
                yield (s, self._RDF + "type", (self._OWL + "SymmetricProperty", "iri"))
            if prop.functional:
                yield (s, self._RDF + "type", (self._OWL + "FunctionalProperty", "iri"))
            if prop.domain:
                yield (s, self._RDFS + "domain", (self._expand(prop.domain), "iri"))
            if prop.range_:
                yield (s, self._RDFS + "range", (self._expand(prop.range_), "iri"))
            if prop.inverse_of:
                yield (s, self._OWL + "inverseOf", (self._expand(prop.inverse_of), "iri"))

        # Data properties
        for prop in self.data_properties.values():
            s = self._expand(prop.name)
            yield (s, self._RDF + "type", (self._OWL + "DatatypeProperty", "iri"))
            if prop.domain:
                yield (s, self._RDFS + "domain", (self._expand(prop.domain), "iri"))
            yield (s, self._RDFS + "range", (self._xsd_iri(prop.datatype), "iri"))
            if prop.comment:
                yield (s, self._RDFS + "comment", (prop.comment, self._XSD + "string"))

        # Individuals (A-Box)
        for ind in self.individuals.values():
            s = self._expand(ind.name)
            yield (s, self._RDF + "type", (self._OWL + "NamedIndividual", "iri"))
            for t in sorted(ind.types):
                yield (s, self._RDF + "type", (self._expand(t), "iri"))
            for pname, targets in ind.object_props.items():
                p_iri = self._expand(pname)
                for tgt in sorted(targets):
                    yield (s, p_iri, (self._expand(tgt), "iri"))
            for pname, values in ind.data_props.items():
                p_iri = self._expand(pname)
                dp = self.data_properties.get(pname)
                dt_iri = self._xsd_iri(dp.datatype) if dp else self._XSD + "string"
                for v in values:
                    if isinstance(v, bool):
                        yield (s, p_iri, ("true" if v else "false", self._XSD + "boolean"))
                    elif isinstance(v, int):
                        yield (s, p_iri, (str(v), self._XSD + "integer"))
                    elif isinstance(v, float):
                        yield (s, p_iri, (str(v), self._XSD + "double"))
                    else:
                        yield (s, p_iri, (str(v), dt_iri))

    def to_ntriples(self) -> str:
        """W3C N-Triples serialization (one triple per line). RFC-compliant."""

        def _esc(s: str) -> str:
            return (s.replace("\\", "\\\\")
                     .replace('"', '\\"')
                     .replace("\n", "\\n")
                     .replace("\r", "\\r")
                     .replace("\t", "\\t"))

        lines: list[str] = []
        for s, p, (o, kind) in self._iter_triples():
            if kind == "iri":
                obj = f"<{o}>"
            else:
                obj = f'"{_esc(o)}"^^<{kind}>'
            lines.append(f"<{s}> <{p}> {obj} .")
        return "\n".join(lines) + "\n"

    def to_rdf_xml(self) -> str:
        """
        RDF/XML serialization. Prefers rdflib (round-trip via Turtle) for
        a fully canonical output; falls back to a flat rdf:Description-based
        emission that is still valid RDF/XML.
        """
        try:
            import rdflib  # type: ignore

            g = rdflib.Graph()
            g.parse(data=self.to_turtle(), format="turtle")
            g.bind(self.prefix, rdflib.Namespace(self.iri))
            return g.serialize(format="xml")
        except Exception:
            pass

        from xml.sax.saxutils import escape, quoteattr

        ns_to_prefix = {
            self._RDF: "rdf",
            self._RDFS: "rdfs",
            self._OWL: "owl",
            self._XSD: "xsd",
            self.iri: self.prefix,
        }

        def _qname(iri: str) -> str:
            for ns_uri, pfx in ns_to_prefix.items():
                if iri.startswith(ns_uri):
                    return f"{pfx}:{iri[len(ns_uri):]}"
            # Unknown namespace — emit as rdf:Description child with full IRI
            # is not legal as an element name, so wrap under a generic prefix.
            return f"ex:{iri.rsplit('/', 1)[-1].rsplit('#', 1)[-1]}"

        out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
        out.append(
            f'<rdf:RDF xmlns:rdf={quoteattr(self._RDF)} '
            f'xmlns:rdfs={quoteattr(self._RDFS)} '
            f'xmlns:owl={quoteattr(self._OWL)} '
            f'xmlns:xsd={quoteattr(self._XSD)} '
            f'xmlns:{self.prefix}={quoteattr(self.iri)}>'
        )

        by_subject: dict[str, list[tuple[str, tuple[str, str | None]]]] = {}
        for s, p, obj in self._iter_triples():
            by_subject.setdefault(s, []).append((p, obj))

        for subject, preds in by_subject.items():
            out.append(f'  <rdf:Description rdf:about={quoteattr(subject)}>')
            for p, (o, kind) in preds:
                tag = _qname(p)
                if kind == "iri":
                    out.append(f'    <{tag} rdf:resource={quoteattr(o)} />')
                else:
                    out.append(
                        f'    <{tag} rdf:datatype={quoteattr(kind)}>'
                        f'{escape(o)}</{tag}>'
                    )
            out.append("  </rdf:Description>")

        out.append("</rdf:RDF>")
        return "\n".join(out) + "\n"

    def to_dict(self) -> dict:
        return {
            "iri": self.iri,
            "classes": {n: c.__dict__ | {"parents": sorted(c.parents),
                                         "disjoint_with": sorted(c.disjoint_with)}
                        for n, c in self.classes.items()},
            "object_properties": {n: p.__dict__ for n, p in self.object_properties.items()},
            "data_properties":   {n: p.__dict__ for n, p in self.data_properties.items()},
            "individuals": {n: {"types": sorted(i.types),
                                "object_props": {k: sorted(v) for k, v in i.object_props.items()},
                                "data_props": i.data_props}
                            for n, i in self.individuals.items()},
        }


def _lit(v: Any) -> str:
    if isinstance(v, bool):  return "true" if v else "false"
    if isinstance(v, (int, float)): return str(v)
    return f'"{v}"'


# ---------------------------------------------------------------------------
# Worked example: Smart Manufacturing ontology
# ---------------------------------------------------------------------------

def build_manufacturing_ontology() -> Ontology:
    o = Ontology(iri="https://example.org/mfg/", prefix="mfg")

    # ---- T-Box: classes ------------------------------------------------
    o.add_class("Asset",        comment="Anything tangible the plant owns or operates.")
    o.add_class("Location",     comment="A physical place.")
    o.add_class("Person",       comment="A human in the system.")

    o.add_class("Site",         parents=["Location"])
    o.add_class("ProductionLine", parents=["Location"])

    o.add_class("Equipment",    parents=["Asset"])
    o.add_class("Machine",      parents=["Equipment"])
    o.add_class("CNC",          parents=["Machine"])
    o.add_class("Robot",        parents=["Machine"])
    o.add_class("Conveyor",     parents=["Equipment"])
    o.add_class("Sensor",       parents=["Equipment"])
    o.add_class("TemperatureSensor", parents=["Sensor"])
    o.add_class("VibrationSensor",   parents=["Sensor"])

    o.add_class("Product",      parents=["Asset"])
    o.add_class("WorkOrder")
    o.add_class("MaintenanceEvent")

    o.add_class("Operator",   parents=["Person"])
    o.add_class("Technician", parents=["Person"])
    # An individual cannot be both Operator and Technician at the same time:
    o.classes["Operator"].disjoint_with.add("Technician")
    o.classes["Technician"].disjoint_with.add("Operator")

    # ---- T-Box: properties ---------------------------------------------
    o.add_object_property("locatedIn", domain="Asset", range_="Location", transitive=True,
                          comment="Asset physically resides in a location; transitive up the hierarchy.")
    o.add_object_property("partOf",    domain="Location", range_="Location", transitive=True)
    o.add_object_property("monitors",  domain="Sensor",   range_="Equipment")
    o.add_object_property("operates",  domain="Operator", range_="Machine")
    o.add_object_property("operatedBy", domain="Machine", range_="Operator", inverse_of="operates")
    o.add_object_property("performedOn", domain="MaintenanceEvent", range_="Equipment")
    o.add_object_property("performedBy", domain="MaintenanceEvent", range_="Technician")
    o.add_object_property("produces",  domain="Machine",  range_="Product")

    o.add_data_property("serialNumber", domain="Equipment", datatype="xsd:string")
    o.add_data_property("installDate",  domain="Equipment", datatype="xsd:dateTime")
    o.add_data_property("readingValue", domain="Sensor",    datatype="xsd:double")
    o.add_data_property("readingUnit",  domain="Sensor",    datatype="xsd:string")

    # ---- A-Box: individuals --------------------------------------------
    o.add_individual("Site_Austin", types=["Site"])
    o.add_individual("Line_A",      types=["ProductionLine"])
    o.add_individual("Line_B",      types=["ProductionLine"])

    o.add_individual("CNC_001", types=["CNC"])
    o.add_individual("CNC_002", types=["CNC"])
    o.add_individual("Robot_01", types=["Robot"])
    o.add_individual("Conv_01",  types=["Conveyor"])

    o.add_individual("TempSensor_1", types=["TemperatureSensor"])
    o.add_individual("VibSensor_1",  types=["VibrationSensor"])

    o.add_individual("Widget", types=["Product"])

    o.add_individual("Alice", types=["Operator"])
    o.add_individual("Bob",   types=["Technician"])

    o.add_individual("MX_42", types=["MaintenanceEvent"])

    # Relationships
    o.assert_object("Line_A", "partOf", "Site_Austin")
    o.assert_object("Line_B", "partOf", "Site_Austin")

    o.assert_object("CNC_001",  "locatedIn", "Line_A")
    o.assert_object("CNC_002",  "locatedIn", "Line_A")
    o.assert_object("Robot_01", "locatedIn", "Line_B")
    o.assert_object("Conv_01",  "locatedIn", "Line_B")

    o.assert_object("TempSensor_1", "monitors", "CNC_001")
    o.assert_object("VibSensor_1",  "monitors", "Robot_01")
    o.assert_object("TempSensor_1", "locatedIn", "Line_A")
    o.assert_object("VibSensor_1",  "locatedIn", "Line_B")

    o.assert_object("Alice", "operates", "CNC_001")        # auto-asserts inverse operatedBy
    o.assert_object("MX_42", "performedOn", "CNC_001")
    o.assert_object("MX_42", "performedBy", "Bob")
    o.assert_object("CNC_001", "produces", "Widget")

    # Data values
    o.assert_data("CNC_001", "serialNumber", "SN-CNC-001")
    o.assert_data("CNC_001", "installDate",  "2023-04-01T00:00:00Z")
    o.assert_data("TempSensor_1", "readingValue", 78.4)
    o.assert_data("TempSensor_1", "readingUnit",  "celsius")
    o.assert_data("VibSensor_1",  "readingValue", 0.21)
    o.assert_data("VibSensor_1",  "readingUnit",  "g")

    return o


# ---------------------------------------------------------------------------
# Demo: build, reason, query, export
# ---------------------------------------------------------------------------

def demo() -> None:
    o = build_manufacturing_ontology()

    print("=" * 70)
    print("Smart-Manufacturing ontology built.")
    print("=" * 70)
    print(f"  classes:           {len(o.classes)}")
    print(f"  object properties: {len(o.object_properties)}")
    print(f"  data properties:   {len(o.data_properties)}")
    print(f"  individuals:       {len(o.individuals)}")

    print("\n-- Inferences ------------------------------------------------")
    print("All Equipment in the plant (subclass closure):")
    for x in o.instances_of("Equipment"):
        print(f"   * {x}  (types: {sorted(o.individuals[x].types)})")

    print("\nWhat is CNC_001 located in (transitive)?")
    print("  ", sorted(o.related("CNC_001", "locatedIn", transitive=True)))
    # Expected: {Line_A, Site_Austin} — Line_A is partOf Site_Austin, but
    # locatedIn is transitive only over locatedIn itself; combining with partOf
    # would require a property chain (left as an exercise).

    print("\nWho operates CNC_001?")
    print("  ", o.related("CNC_001", "operatedBy"))   # auto-derived inverse

    print("\n-- Consistency -----------------------------------------------")
    issues = o.check_consistency()
    print("   OK (no issues)" if not issues else "\n".join(f"   - {p}" for p in issues))

    print("\n-- Negative test (domain violation) --------------------------")
    try:
        o.assert_object("Widget", "operates", "CNC_001")  # Product cannot operate
    except ValueError as e:
        print(f"   correctly rejected: {e}")

    # ---- export ----
    with open("manufacturing.ttl", "w", encoding="utf-8") as f:
        f.write(o.to_turtle())
    with open("manufacturing.jsonld", "w", encoding="utf-8") as f:
        json.dump(o.to_jsonld(), f, indent=2)
    with open("manufacturing.json", "w", encoding="utf-8") as f:
        json.dump(o.to_dict(), f, indent=2)
    print("\nWrote: manufacturing.ttl, manufacturing.jsonld, manufacturing.json")


# ---------------------------------------------------------------------------
# Microsoft Fabric integration stubs (intentionally not wired in v1)
# ---------------------------------------------------------------------------

class FabricAdapter:
    """
    Placeholder adapter showing where Microsoft Fabric would plug in.

    In a Fabric notebook the recipe is:

        # FABRIC INTEGRATION POINT — Lakehouse read
        df = spark.read.format("delta").load("Tables/equipment")
        for row in df.collect():
            ont.add_individual(row.asset_id, types=[row.class_name])
            ont.assert_data(row.asset_id, "serialNumber", row.serial_number)

        # FABRIC INTEGRATION POINT — Lakehouse write (materialize triples)
        triples = [(s, p, o) for s, ind in ont.individuals.items()
                              for p, ts in ind.object_props.items()
                              for o in ts]
        spark.createDataFrame(triples, "subject string, predicate string, object string") \
             .write.format("delta").mode("overwrite").save("Tables/triples")

        # FABRIC INTEGRATION POINT — OneLake shortcut to publish ontology.ttl
        # Save manufacturing.ttl into the Files section of the Lakehouse so that
        # Power BI semantic models, Copilot, and Real-Time Intelligence can
        # discover the schema.
    """
    def __init__(self, ontology: Ontology):
        self.ontology = ontology

    def from_lakehouse(self, table: str): ...
    def to_lakehouse_triples(self, table: str): ...
    def publish_to_onelake(self, path: str): ...


if __name__ == "__main__":
    demo()
