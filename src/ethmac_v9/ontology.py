from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Fact:
    subject: str
    predicate: str
    object: Any
    visible_from: int = 0
    expires_after: Optional[int] = None
    provenance: str = ""
    source_channel: str = ""

    def visible(self, round_index: int) -> bool:
        return self.visible_from <= round_index and (
            self.expires_after is None or round_index <= self.expires_after
        )


class KnowledgeGraph:
    """Small auditable graph used by the local rule engine.

    TTL and SHACL files define the portable ontology. This class provides the
    API-free query surface needed for Stage 4 tests without requiring rdflib.
    """

    def __init__(self) -> None:
        self._facts: List[Fact] = []

    def add(self, fact: Fact) -> None:
        if not fact.subject or not fact.predicate:
            raise ValueError("subject and predicate are required")
        if fact.predicate in {"observedEvidence", "supportsAction", "hasProvenance"} and not fact.provenance:
            raise ValueError("evidence-related facts require provenance")
        self._facts.append(fact)

    def add_evidence(
        self,
        evidence_id: str,
        evidence_type: str,
        visible_from: int,
        provenance: str,
        source_channel: str,
        expires_after: Optional[int] = None,
    ) -> None:
        if not provenance or not source_channel:
            raise ValueError("evidence requires provenance and source_channel")
        self._facts.extend(
            [
                Fact(evidence_id, "rdf:type", evidence_type, visible_from, expires_after, provenance, source_channel),
                Fact(evidence_id, "hasProvenance", provenance, visible_from, expires_after, provenance, source_channel),
                Fact(evidence_id, "sourceChannel", source_channel, visible_from, expires_after, provenance, source_channel),
            ]
        )

    def query(
        self,
        round_index: int,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object_value: Any = None,
    ) -> List[Fact]:
        return [
            fact
            for fact in self._facts
            if fact.visible(round_index)
            and (subject is None or fact.subject == subject)
            and (predicate is None or fact.predicate == predicate)
            and (object_value is None or fact.object == object_value)
        ]

    def evidence_provenance(self, evidence_id: str, round_index: int) -> Dict[str, str]:
        facts = self.query(round_index, subject=evidence_id)
        if not facts:
            raise KeyError(evidence_id)
        provenance = next((str(f.object) for f in facts if f.predicate == "hasProvenance"), "")
        channel = next((str(f.object) for f in facts if f.predicate == "sourceChannel"), "")
        if not provenance or not channel:
            raise ValueError("incomplete evidence provenance")
        return {"provenance": provenance, "source_channel": channel}

    def visible_evidence_ids(self, round_index: int) -> List[str]:
        return sorted({f.subject for f in self.query(round_index) if f.predicate == "hasProvenance"})

    def all_facts(self) -> List[Fact]:
        return list(self._facts)

