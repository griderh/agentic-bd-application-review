"""Curated interpretation guidance, never firm facts or evidence approval."""

import hashlib
import json
from importlib.resources import files
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class KnowledgeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    entry_id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,79}$")]
    authority: Text
    applies_to: Text
    guidance: Annotated[tuple[Text, ...], Field(min_length=1, max_length=10)]
    limitations: Annotated[tuple[Text, ...], Field(min_length=1, max_length=10)]


class KnowledgeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Text
    entries: Annotated[tuple[KnowledgeEntry, ...], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        if len({e.entry_id for e in self.entries}) != len(self.entries):
            raise ValueError("Duplicate domain knowledge entries")
        return self


_RAW = files("bd_packet_builder").joinpath("domain_knowledge.json").read_bytes()
REFERENCE = KnowledgeReference.model_validate_json(_RAW)
KNOWLEDGE_SHA256 = hashlib.sha256(_RAW).hexdigest()
KNOWLEDGE_IDS = frozenset(e.entry_id for e in REFERENCE.entries)


def knowledge_context() -> dict[str, Any]:
    return {
        **REFERENCE.model_dump(mode="json"),
        "sha256": KNOWLEDGE_SHA256,
        "trust": "curated_interpretation_not_source_evidence",
    }


def knowledge_instructions() -> str:
    return """
DOMAIN KNOWLEDGE: the following versioned reference replaces scattered business guidance.
It explains interpretation and approved draft policy; it is not source evidence, firm facts,
current corroboration or permission to bypass code checks. Workflow/tool contracts still apply.
Apply entries only in their stated scope. Read actual source pages, cite checked evidence and
record uncertainty. Do not convert an unverified interpretation into an authoritative fact.
For each answer/unresolved outcome report knowledge_applied with entry_id, reference_sha256
(the exact reference hash supplied below) and a short reason
for entries actually used, or [] if none. This is model-reported reasoning, not proof of use.
""" + json.dumps(knowledge_context(), ensure_ascii=True, separators=(",", ":"))
