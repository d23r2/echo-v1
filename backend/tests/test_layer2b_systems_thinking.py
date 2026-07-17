"""ECHO Layer 2B — systems_thinking.py: SystemModel/SystemModelNode CRUD,
dependency-graph extraction, bottleneck detection, cycle detection,
critical-path estimation, causal counterfactuals. Deterministic, DB-backed
via the isolated db_session fixture (see tests/conftest.py)."""

from app.models import CausalNote, CognitiveConcept, CognitiveRelationship
from app.services import systems_thinking as st


def _concept(db_session, name, **kw):
    c = CognitiveConcept(name=name, **kw)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def _rel(db_session, a, b, relation_type="depends_on"):
    r = CognitiveRelationship(from_concept_id=a.id, to_concept_id=b.id, relation_type=relation_type)
    db_session.add(r)
    db_session.commit()
    return r


# ---- SystemModel CRUD ----


def test_create_and_get_system_model(db_session):
    model = st.create_system_model(db_session, name="Backend Architecture", scope="software_architecture")
    fetched = st.get_system_model(db_session, model.id)
    assert fetched is not None
    assert fetched.name == "Backend Architecture"
    assert fetched.archived_at is None


def test_list_system_models_excludes_archived_by_default(db_session):
    m1 = st.create_system_model(db_session, name="Active model")
    m2 = st.create_system_model(db_session, name="To archive")
    st.archive_system_model(db_session, m2.id)
    names = [m.name for m in st.list_system_models(db_session)]
    assert m1.name in names
    assert m2.name not in names
    all_names = [m.name for m in st.list_system_models(db_session, include_archived=True)]
    assert m2.name in all_names


def test_update_system_model(db_session):
    model = st.create_system_model(db_session, name="Original name")
    updated = st.update_system_model(db_session, model.id, name="Renamed", description="new desc")
    assert updated.name == "Renamed"
    assert updated.description == "new desc"


def test_update_system_model_404_for_unknown_id(db_session):
    assert st.update_system_model(db_session, "does-not-exist", name="x") is None


# ---- SystemModelNode CRUD ----


def test_add_node_and_list_nodes(db_session):
    model = st.create_system_model(db_session, name="Sys")
    concept = _concept(db_session, "API Gateway")
    node = st.add_node(db_session, model.id, concept_id=concept.id, node_role="component")
    nodes = st.list_nodes(db_session, model.id)
    assert len(nodes) == 1
    assert nodes[0].id == node.id


def test_add_node_upserts_on_duplicate_concept(db_session):
    model = st.create_system_model(db_session, name="Sys")
    concept = _concept(db_session, "Database")
    st.add_node(db_session, model.id, concept_id=concept.id, node_role="component", owner="alice")
    st.add_node(db_session, model.id, concept_id=concept.id, node_role="resource", owner="bob")
    nodes = st.list_nodes(db_session, model.id)
    assert len(nodes) == 1
    assert nodes[0].node_role == "resource"
    assert nodes[0].owner == "bob"


def test_remove_node(db_session):
    model = st.create_system_model(db_session, name="Sys")
    concept = _concept(db_session, "Cache")
    node = st.add_node(db_session, model.id, concept_id=concept.id)
    assert st.remove_node(db_session, node.id) is True
    assert st.list_nodes(db_session, model.id) == []


def test_remove_node_404_for_unknown_id(db_session):
    assert st.remove_node(db_session, "does-not-exist") is False


# ---- Dependency graph / scoped edges ----


def test_scoped_edges_only_includes_edges_within_system(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    outside = _concept(db_session, "Outside")
    _rel(db_session, a, b)
    _rel(db_session, a, outside)  # outside is not a member of this system model
    st.add_node(db_session, model.id, concept_id=a.id)
    st.add_node(db_session, model.id, concept_id=b.id)

    edges = st.scoped_edges(db_session, model.id)
    assert len(edges) == 1
    assert edges[0].from_concept_id == a.id
    assert edges[0].to_concept_id == b.id


def test_scoped_edges_empty_for_system_with_no_nodes(db_session):
    model = st.create_system_model(db_session, name="Empty sys")
    assert st.scoped_edges(db_session, model.id) == []


# ---- Bottleneck detection ----


def test_detect_bottlenecks_flags_high_degree_node(db_session):
    model = st.create_system_model(db_session, name="Sys")
    hub = _concept(db_session, "Auth Service")
    dependents = [_concept(db_session, f"Client {i}") for i in range(4)]
    st.add_node(db_session, model.id, concept_id=hub.id)
    for d in dependents:
        st.add_node(db_session, model.id, concept_id=d.id)
        _rel(db_session, d, hub, relation_type="depends_on")

    bottlenecks = st.detect_bottlenecks(db_session, model.id, min_degree=3)
    assert len(bottlenecks) == 1
    assert bottlenecks[0]["concept_name"] == "Auth Service"
    assert bottlenecks[0]["in_degree"] == 4


def test_detect_bottlenecks_empty_when_below_threshold(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    st.add_node(db_session, model.id, concept_id=a.id)
    st.add_node(db_session, model.id, concept_id=b.id)
    _rel(db_session, a, b)
    assert st.detect_bottlenecks(db_session, model.id, min_degree=3) == []


# ---- Cycle detection ----


def test_detect_cycles_finds_real_cycle(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    c = _concept(db_session, "C")
    for x in (a, b, c):
        st.add_node(db_session, model.id, concept_id=x.id)
    _rel(db_session, a, b)
    _rel(db_session, b, c)
    _rel(db_session, c, a)

    cycles = st.detect_cycles(db_session, model.id)
    assert len(cycles) == 1
    assert set(cycles[0]) == {a.id, b.id, c.id}


def test_detect_cycles_empty_for_dag(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    c = _concept(db_session, "C")
    for x in (a, b, c):
        st.add_node(db_session, model.id, concept_id=x.id)
    _rel(db_session, a, b)
    _rel(db_session, b, c)
    assert st.detect_cycles(db_session, model.id) == []


# ---- Critical path ----


def test_critical_path_finds_longest_chain(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    c = _concept(db_session, "C")
    d = _concept(db_session, "D")
    for x in (a, b, c, d):
        st.add_node(db_session, model.id, concept_id=x.id)
    _rel(db_session, a, b)
    _rel(db_session, b, c)
    _rel(db_session, c, d)
    _rel(db_session, a, d)  # shortcut edge — the real critical path is still A->B->C->D

    path = st.compute_critical_path(db_session, model.id)
    assert path is not None
    assert path["length"] == 3
    assert path["node_names"] == ["A", "B", "C", "D"]


def test_critical_path_none_on_cyclic_graph(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    for x in (a, b):
        st.add_node(db_session, model.id, concept_id=x.id)
    _rel(db_session, a, b)
    _rel(db_session, b, a)
    assert st.compute_critical_path(db_session, model.id) is None


def test_critical_path_none_with_no_dependency_edges(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    st.add_node(db_session, model.id, concept_id=a.id)
    assert st.compute_critical_path(db_session, model.id) is None


# ---- Causal counterfactuals ----


def test_build_counterfactuals_matches_relevant_causal_notes(db_session):
    model = st.create_system_model(db_session, name="Sys")
    ollama = _concept(db_session, "Ollama")
    st.add_node(db_session, model.id, concept_id=ollama.id)
    db_session.add(
        CausalNote(title="Ollama offline note", cause="Ollama is offline", effect="local chat fails", confidence="high")
    )
    db_session.add(CausalNote(title="Unrelated note", cause="disk full", effect="uploads fail", confidence="medium"))
    db_session.commit()

    counterfactuals = st.build_counterfactuals(db_session, model.id)
    assert len(counterfactuals) == 1
    assert "Ollama offline note" == counterfactuals[0]["based_on_note"]
    assert "would likely not follow" in counterfactuals[0]["statement"]


def test_build_counterfactuals_empty_when_no_notes_match(db_session):
    model = st.create_system_model(db_session, name="Sys")
    concept = _concept(db_session, "Something Unrelated To Any Note")
    st.add_node(db_session, model.id, concept_id=concept.id)
    assert st.build_counterfactuals(db_session, model.id) == []


# ---- build_system_analysis ----


def test_build_system_analysis_returns_none_for_unknown_model(db_session):
    assert st.build_system_analysis(db_session, "does-not-exist") is None


def test_build_system_analysis_bundles_everything(db_session):
    model = st.create_system_model(db_session, name="Sys")
    a = _concept(db_session, "A")
    b = _concept(db_session, "B")
    for x in (a, b):
        st.add_node(db_session, model.id, concept_id=x.id)
    _rel(db_session, a, b)

    analysis = st.build_system_analysis(db_session, model.id)
    assert analysis["system_model"].id == model.id
    assert len(analysis["nodes"]) == 2
    assert len(analysis["edges"]) == 1
    assert analysis["cycles"] == []
