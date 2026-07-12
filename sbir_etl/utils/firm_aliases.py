"""Firm alias-graph construction from name-change/merger evidence.

Exact-name matching is the shared false-negative of every firm-level instrument
in the dark-majority analysis (patent liveness, trademarks, USAspending
recovery): a firm that renamed or was quietly acquired defeats all of them at
once. This module builds an alias graph so a firm's evidence can be found under
any of its names.

The core functions here are pure and unit-tested; the streaming drivers that
feed them the bulk USPTO/USAspending tables live in
``scripts/data/build_firm_alias_graph.py``.

Alias edges are directional evidence but stored symmetrically (a rename is an
equivalence). An edge is only useful if the two names differ *after*
normalization — ``ACME CORP`` → ``ACME CORPORATION`` normalizes to the same
token and carries no new matching power.
"""

from __future__ import annotations

from dataclasses import dataclass

from sbir_etl.utils.text_normalization import normalize_name

# USPTO patent-assignment conveyance types (assignment_conveyance.convey_ty).
# A name change or merger means the assignor and assignee are the *same* economic
# entity under two names — a true alias. A plain "assignment" is an IP transfer
# that may or may not be an acquisition, so it is a lead, not an alias.
ALIAS_CONVEYANCES = frozenset({"namechg", "merger"})
LEAD_CONVEYANCES = frozenset({"assignment"})


@dataclass(frozen=True)
class AliasEdge:
    """One firm ↔ alternate-name edge with provenance."""

    firm_normalized: str
    alias_name: str  # raw alternate name (for display / re-matching)
    alias_normalized: str
    source: str  # patent_assignment | shared_uei
    relation: str  # namechg | merger | shared_uei
    effective_date: str  # ISO date or "" if unknown
    corrob_state: str  # alternate-name state code, "" if unknown


def _norm(name: str) -> str:
    return normalize_name(name, remove_suffixes=True)


def make_alias_edge(
    firm_name: str,
    alias_name: str,
    *,
    source: str,
    relation: str,
    effective_date: str = "",
    corrob_state: str = "",
) -> AliasEdge | None:
    """Build a normalized alias edge, or None if it carries no matching power.

    Returns None when either name is empty or the two names normalize to the
    same token (a suffix-only difference like ``Acme`` vs ``Acme, Inc.``).
    """
    firm_norm = _norm(firm_name)
    alias_norm = _norm(alias_name)
    if not firm_norm or not alias_norm or firm_norm == alias_norm:
        return None
    return AliasEdge(
        firm_normalized=firm_norm,
        alias_name=alias_name.strip(),
        alias_normalized=alias_norm,
        source=source,
        relation=relation,
        effective_date=effective_date,
        corrob_state=(corrob_state or "").strip().upper(),
    )


def classify_conveyance(convey_ty: str) -> str:
    """Map a conveyance type to ``alias`` | ``lead`` | ``ignore``."""
    c = (convey_ty or "").strip().lower()
    if c in ALIAS_CONVEYANCES:
        return "alias"
    if c in LEAD_CONVEYANCES:
        return "lead"
    return "ignore"


def alias_edges_from_shared_uei(
    uei_to_names: dict[str, set[str]],
) -> list[AliasEdge]:
    """Alias edges from recipient names sharing one UEI in USAspending.

    A shared UEI is weak evidence — UEIs are occasionally reused across firms —
    so these edges are emitted for *every* distinct-normalized pair under a UEI
    and MUST be corroborated (state or PI agreement) before use, exactly like a
    generic-name patent match. Names within a UEI that normalize alike collapse
    to one node, so only genuinely different names produce edges.
    """
    edges: list[AliasEdge] = []
    for names in uei_to_names.values():
        # Group raw names by normalized form; one representative per node.
        by_norm: dict[str, str] = {}
        for raw in names:
            nn = _norm(raw)
            if nn:
                by_norm.setdefault(nn, raw)
        reps = sorted(by_norm.items())
        for i, (na, ra) in enumerate(reps):
            for nb, rb in reps[i + 1 :]:
                edge = make_alias_edge(
                    ra, rb, source="shared_uei", relation="shared_uei"
                )
                if edge:
                    edges.append(edge)
    return edges


def build_alias_index(edges: list[AliasEdge]) -> dict[str, set[str]]:
    """Collapse edges into ``{normalized_name -> set(all equivalent normals)}``.

    Computes connected components so a firm reachable through a chain of renames
    (A→B→C) resolves to the full set {A, B, C}. The returned map includes each
    name as a key, and every key's value includes the name itself.
    """
    adj: dict[str, set[str]] = {}
    for e in edges:
        adj.setdefault(e.firm_normalized, set()).add(e.alias_normalized)
        adj.setdefault(e.alias_normalized, set()).add(e.firm_normalized)

    index: dict[str, set[str]] = {}
    for start in adj:
        if start in index:
            continue
        # BFS over the component
        seen = {start}
        stack = [start]
        while stack:
            node = stack.pop()
            for nb in adj.get(node, ()):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        for node in seen:
            index[node] = seen
    return index
