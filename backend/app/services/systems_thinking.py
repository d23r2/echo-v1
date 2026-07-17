"""ECHO Layer 2B — Systems Thinking Engine.

SystemModel is a named, scoped *view* over the existing Cognitive Core
world-model graph (CognitiveConcept / CognitiveRelationship), not a second
graph database — see the class docstrings in models.py. This module adds
the graph algorithms that view needed: dependency-edge extraction scoped to
a system, bottleneck detection, cycle detection, critical-path estimation,
and causal counterfactual lookups drawn from the existing CausalNote table.

Deterministic, no model calls — same convention as cognitive_core.py,
task_understanding_v2.py, context_router.py, etc. Every number here is a
graph-structural count (in-degree, out-degree, path length), never an
invented probability presented as calibrated certainty.
"""

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import CausalNote, CognitiveConcept, CognitiveRelationship, SystemModel, SystemModelNode, _now

# ============================================================================
# SystemModel / SystemModelNode CRUD
# ============================================================================


def create_system_model(
    db: Session, *, name: str, scope: str = "software_architecture", description: str | None = None, project_id: str | None = None
) -> SystemModel:
    model = SystemModel(name=name, scope=scope, description=description, project_id=project_id)
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def get_system_model(db: Session, system_model_id: str) -> SystemModel | None:
    return db.get(SystemModel, system_model_id)


def list_system_models(db: Session, *, project_id: str | None = None, include_archived: bool = False) -> list[SystemModel]:
    q = db.query(SystemModel)
    if not include_archived:
        q = q.filter(SystemModel.archived_at.is_(None))
    if project_id:
        q = q.filter(SystemModel.project_id == project_id)
    return q.order_by(SystemModel.created_at.desc()).all()


def update_system_model(
    db: Session, system_model_id: str, *, name: str | None = None, scope: str | None = None, description: str | None = None
) -> SystemModel | None:
    model = db.get(SystemModel, system_model_id)
    if model is None:
        return None
    if name is not None:
        model.name = name
    if scope is not None:
        model.scope = scope
    if description is not None:
        model.description = description
    db.commit()
    db.refresh(model)
    return model


def archive_system_model(db: Session, system_model_id: str) -> SystemModel | None:
    model = db.get(SystemModel, system_model_id)
    if model is None:
        return None
    model.archived_at = _now()
    db.commit()
    db.refresh(model)
    return model


def add_node(
    db: Session,
    system_model_id: str,
    *,
    concept_id: str,
    node_role: str = "component",
    state: str | None = None,
    owner: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
) -> SystemModelNode:
    existing = (
        db.query(SystemModelNode)
        .filter(SystemModelNode.system_model_id == system_model_id, SystemModelNode.concept_id == concept_id)
        .first()
    )
    if existing is not None:
        existing.node_role = node_role
        existing.state = state
        existing.owner = owner
        existing.evidence = evidence
        existing.confidence = confidence
        db.commit()
        db.refresh(existing)
        return existing

    node = SystemModelNode(
        system_model_id=system_model_id,
        concept_id=concept_id,
        node_role=node_role,
        state=state,
        owner=owner,
        evidence=evidence,
        confidence=confidence,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def remove_node(db: Session, node_id: str) -> bool:
    node = db.get(SystemModelNode, node_id)
    if node is None:
        return False
    db.delete(node)
    db.commit()
    return True


def list_nodes(db: Session, system_model_id: str) -> list[SystemModelNode]:
    return db.query(SystemModelNode).filter(SystemModelNode.system_model_id == system_model_id).all()


# ============================================================================
# Dependency graph — edges are the existing CognitiveRelationship rows,
# scoped down to only those whose both endpoints are members of this
# SystemModel's node set.
# ============================================================================


def scoped_edges(db: Session, system_model_id: str) -> list[CognitiveRelationship]:
    nodes = list_nodes(db, system_model_id)
    concept_ids = {n.concept_id for n in nodes}
    if not concept_ids:
        return []
    rels = (
        db.query(CognitiveRelationship)
        .filter(CognitiveRelationship.from_concept_id.in_(concept_ids), CognitiveRelationship.to_concept_id.in_(concept_ids))
        .all()
    )
    return rels


def _adjacency(nodes: list[SystemModelNode], edges: list[CognitiveRelationship]) -> dict[str, list[str]]:
    concept_ids = {n.concept_id for n in nodes}
    adj: dict[str, list[str]] = {cid: [] for cid in concept_ids}
    for e in edges:
        if e.from_concept_id in adj:
            adj[e.from_concept_id].append(e.to_concept_id)
    return adj


# Edge types that structurally represent "A depends on / is blocked by B" for
# dependency-direction analysis (bottleneck/critical-path). Others (similar_to,
# conflicts_with, verifies, ...) are real edges but not load-bearing here.
_DEPENDENCY_RELATION_TYPES = {"depends_on", "uses", "requires", "blocks", "consumes"}


def detect_bottlenecks(db: Session, system_model_id: str, *, min_degree: int = 3) -> list[dict]:
    """A bottleneck here means 'structurally load-bearing,' not 'broken' —
    high in-degree (many things depend on it) or high out-degree (it
    depends on many things, so its failure/delay ripples widely)."""
    nodes = list_nodes(db, system_model_id)
    edges = [e for e in scoped_edges(db, system_model_id) if e.relation_type in _DEPENDENCY_RELATION_TYPES]
    in_degree: dict[str, int] = defaultdict(int)
    out_degree: dict[str, int] = defaultdict(int)
    for e in edges:
        out_degree[e.from_concept_id] += 1
        in_degree[e.to_concept_id] += 1

    concept_names = {n.concept_id: n.concept_id for n in nodes}
    if nodes:
        concepts = db.query(CognitiveConcept).filter(CognitiveConcept.id.in_([n.concept_id for n in nodes])).all()
        concept_names = {c.id: c.name for c in concepts}

    results = []
    for node in nodes:
        cid = node.concept_id
        ind, outd = in_degree.get(cid, 0), out_degree.get(cid, 0)
        if ind >= min_degree or outd >= min_degree:
            if ind >= min_degree and outd >= min_degree:
                reason = f"{ind} things depend on it and it depends on {outd} things — failure here ripples in both directions"
            elif ind >= min_degree:
                reason = f"{ind} other things depend on it directly"
            else:
                reason = f"it depends on {outd} other things — delays in any of them delay it"
            results.append(
                {
                    "concept_id": cid,
                    "concept_name": concept_names.get(cid, cid),
                    "in_degree": ind,
                    "out_degree": outd,
                    "reason": reason,
                }
            )
    results.sort(key=lambda r: r["in_degree"] + r["out_degree"], reverse=True)
    return results


def detect_cycles(db: Session, system_model_id: str) -> list[list[str]]:
    """DFS-based cycle detection over dependency-type edges only. Returns
    each cycle as an ordered list of concept ids (first == last omitted;
    caller closes the loop when displaying)."""
    nodes = list_nodes(db, system_model_id)
    edges = [e for e in scoped_edges(db, system_model_id) if e.relation_type in _DEPENDENCY_RELATION_TYPES]
    adj = _adjacency(nodes, edges)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adj, WHITE)
    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        path.append(u)
        for v in adj.get(u, []):
            if color.get(v, WHITE) == WHITE:
                dfs(v)
            elif color.get(v) == GRAY:
                idx = path.index(v)
                cycle = path[idx:]
                if cycle not in cycles:
                    cycles.append(list(cycle))
        path.pop()
        color[u] = BLACK

    for node_id in list(adj.keys()):
        if color.get(node_id, WHITE) == WHITE:
            dfs(node_id)

    return cycles


def compute_critical_path(db: Session, system_model_id: str) -> dict | None:
    """Longest dependency chain in the scoped graph (by edge count) — a
    structural estimate of the deepest chain of blocking dependencies, not
    a time/cost-weighted critical path (this app tracks neither duration nor
    cost on CognitiveConcept). Returns None if the graph has a cycle
    (longest-path is undefined on a cyclic graph) or has no dependency
    edges at all."""
    nodes = list_nodes(db, system_model_id)
    if not nodes:
        return None
    edges = [e for e in scoped_edges(db, system_model_id) if e.relation_type in _DEPENDENCY_RELATION_TYPES]
    if not edges:
        return None
    if detect_cycles(db, system_model_id):
        return None

    adj = _adjacency(nodes, edges)
    memo: dict[str, list[str]] = {}

    def longest_from(u: str) -> list[str]:
        if u in memo:
            return memo[u]
        best: list[str] = [u]
        for v in adj.get(u, []):
            candidate = [u, *longest_from(v)]
            if len(candidate) > len(best):
                best = candidate
        memo[u] = best
        return best

    best_path: list[str] = []
    for node_id in adj:
        candidate = longest_from(node_id)
        if len(candidate) > len(best_path):
            best_path = candidate

    if len(best_path) < 2:
        return None

    concepts = db.query(CognitiveConcept).filter(CognitiveConcept.id.in_(best_path)).all()
    names = {c.id: c.name for c in concepts}
    return {
        "node_ids": best_path,
        "node_names": [names.get(cid, cid) for cid in best_path],
        "length": len(best_path) - 1,
    }


# ============================================================================
# Causal counterfactuals — reuses the existing CausalNote table (simple
# cause -> effect facts). A counterfactual here is a plain-language "if the
# cause note's premise didn't hold, the noted effect likely wouldn't either"
# — grounded in an existing recorded note, never a fabricated probability.
# ============================================================================


def relevant_causal_notes(db: Session, system_model_id: str) -> list[CausalNote]:
    nodes = list_nodes(db, system_model_id)
    if not nodes:
        return []
    concepts = db.query(CognitiveConcept).filter(CognitiveConcept.id.in_([n.concept_id for n in nodes])).all()
    names = [c.name for c in concepts if c.name]
    if not names:
        return []
    notes = db.query(CausalNote).filter(CausalNote.archived_at.is_(None)).all()
    matched = []
    for note in notes:
        haystack = f"{note.cause} {note.effect} {note.title}".lower()
        if any(name.lower() in haystack for name in names):
            matched.append(note)
    return matched


def build_counterfactuals(db: Session, system_model_id: str) -> list[dict]:
    """One counterfactual statement per matched CausalNote — explicitly
    labelled as a forecast grounded in a recorded note, never a certainty."""
    notes = relevant_causal_notes(db, system_model_id)
    out = []
    for note in notes:
        out.append(
            {
                "based_on_note": note.title,
                "statement": f"If '{note.cause}' did not hold, then '{note.effect}' would likely not follow either — based on the recorded causal note '{note.title}'.",
                "confidence": note.confidence,
            }
        )
    return out


def build_system_analysis(db: Session, system_model_id: str) -> dict | None:
    model = get_system_model(db, system_model_id)
    if model is None:
        return None
    nodes = list_nodes(db, system_model_id)
    edges = scoped_edges(db, system_model_id)
    return {
        "system_model": model,
        "nodes": nodes,
        "edges": edges,
        "bottlenecks": detect_bottlenecks(db, system_model_id),
        "cycles": detect_cycles(db, system_model_id),
        "critical_path": compute_critical_path(db, system_model_id),
    }
