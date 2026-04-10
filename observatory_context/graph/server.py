"""MCP server exposing the observatory knowledge graph.

Loads a NetworkX MultiDiGraph from ``data/graph/graph.json`` (node-link
format) and exposes query tools via the Model Context Protocol so that
Claude Code / Codex can explore cross-project entity connections,
communities, contradictions, and gaps directly.

Run as::

    python -m observatory_context.graph.server
    uv run python -m observatory_context.graph.server
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Repo / path helpers
# ---------------------------------------------------------------------------


def _find_repo_root() -> Path:
    """Walk up from this file looking for ``pyproject.toml``."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


REPO_ROOT = _find_repo_root()

GRAPH_PATH = Path(
    os.environ.get(
        "BERIL_GRAPH_PATH",
        str(REPO_ROOT / "data" / "graph" / "graph.json"),
    )
)
COMMUNITIES_PATH = GRAPH_PATH.parent / "communities.json"
ALIASES_PATH = GRAPH_PATH.parent / "aliases.json"

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

_graph: nx.MultiDiGraph = nx.MultiDiGraph()
_communities: dict[str, Any] = {}
_aliases: dict[str, list[str]] = {}  # canonical -> [alias, ...]
_reverse_aliases: dict[str, str] = {}  # normalized alias -> canonical
_graph_mtime: float = 0.0

# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Lowercase, strip punctuation/extra whitespace for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def _build_reverse_aliases() -> None:
    """Populate ``_reverse_aliases`` from ``_aliases``."""
    _reverse_aliases.clear()
    for canonical, alts in _aliases.items():
        norm = _normalize(canonical)
        _reverse_aliases[norm] = canonical
        for alt in alts:
            _reverse_aliases[_normalize(alt)] = canonical


def _load_graph() -> None:
    """Load (or reload) the graph and sidecar files from disk."""
    global _graph, _communities, _aliases, _graph_mtime

    if not GRAPH_PATH.exists():
        _graph = nx.MultiDiGraph()
        _graph_mtime = 0.0
        return

    with open(GRAPH_PATH) as f:
        data = json.load(f)
    _graph = nx.node_link_graph(data, directed=True, multigraph=True)
    _graph_mtime = GRAPH_PATH.stat().st_mtime

    if COMMUNITIES_PATH.exists():
        with open(COMMUNITIES_PATH) as f:
            _communities = json.load(f)

    if ALIASES_PATH.exists():
        with open(ALIASES_PATH) as f:
            _aliases = json.load(f)
        _build_reverse_aliases()


def _maybe_reload() -> None:
    """Reload the graph if the file has been modified since last load."""
    if not GRAPH_PATH.exists():
        return
    mtime = GRAPH_PATH.stat().st_mtime
    if mtime > _graph_mtime:
        _load_graph()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _node_attr(node_id: str) -> dict[str, Any]:
    """Return attributes for a node, or empty dict if missing."""
    if node_id in _graph.nodes:
        return dict(_graph.nodes[node_id])
    return {}


def _resolve_entity(name: str) -> str | None:
    """Resolve a user-provided name to an actual graph node.

    Tries: exact match, normalized match via aliases, substring match.
    """
    if name in _graph.nodes:
        return name

    norm = _normalize(name)

    # Alias lookup
    if norm in _reverse_aliases:
        canonical = _reverse_aliases[norm]
        if canonical in _graph.nodes:
            return canonical

    # Normalized node-name match
    for nid in _graph.nodes:
        if _normalize(nid) == norm:
            return nid

    # Substring match (first hit)
    for nid in _graph.nodes:
        if norm in _normalize(nid):
            return nid

    return None


def _format_node(node_id: str) -> str:
    """One-line summary of a node: ``Name (type) [projects]``."""
    attrs = _node_attr(node_id)
    ntype = attrs.get("type", "unknown")
    projects = attrs.get("projects", attrs.get("project_id", ""))
    if isinstance(projects, list):
        projects = ", ".join(projects)
    suffix = f" [{projects}]" if projects else ""
    return f"{node_id} ({ntype}){suffix}"


def _findings_for_entity(entity: str) -> list[dict[str, Any]]:
    """Return finding nodes connected to *entity* via FINDING_ABOUT edges."""
    findings: list[dict[str, Any]] = []
    for u, v, edata in _graph.in_edges(entity, data=True):
        if edata.get("type") == "FINDING_ABOUT":
            attrs = _node_attr(u)
            findings.append({"id": u, **attrs})
    for u, v, edata in _graph.out_edges(entity, data=True):
        if edata.get("type") == "FINDING_ABOUT":
            attrs = _node_attr(v)
            findings.append({"id": v, **attrs})
    # Also check generic ABOUT
    for u, v, edata in _graph.in_edges(entity, data=True):
        if edata.get("type") == "ABOUT":
            attrs = _node_attr(u)
            findings.append({"id": u, **attrs})
    for u, v, edata in _graph.out_edges(entity, data=True):
        if edata.get("type") == "ABOUT":
            attrs = _node_attr(v)
            findings.append({"id": v, **attrs})
    # Deduplicate by id
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for f in findings:
        if f["id"] not in seen:
            seen.add(f["id"])
            unique.append(f)
    return unique


def _projects_for_entity(entity: str) -> list[str]:
    """Return project IDs connected to *entity*."""
    projects: set[str] = set()
    for u, v, edata in _graph.in_edges(entity, data=True):
        if edata.get("type") in ("PROJECT_STUDIES", "STUDIES"):
            projects.add(u)
    for u, v, edata in _graph.out_edges(entity, data=True):
        if edata.get("type") in ("PROJECT_STUDIES", "STUDIES"):
            projects.add(v)
    # Fallback: check node attribute
    attrs = _node_attr(entity)
    if "projects" in attrs:
        p = attrs["projects"]
        if isinstance(p, list):
            projects.update(p)
        elif isinstance(p, str) and p:
            projects.add(p)
    return sorted(projects)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "observatory-graph",
    instructions=(
        "Knowledge graph for the BERIL Research Observatory. "
        "Query cross-project entities, communities, contradictions, and gaps."
    ),
)


@mcp.tool()
def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
) -> str:
    """Find entities by name with fuzzy matching.

    Parameters
    ----------
    query : str
        Search term — matched against entity names and aliases.
    entity_type : str | None
        Filter to a specific type (organism, gene, pathway, etc.).
    limit : int
        Maximum results to return.

    Returns
    -------
    str
        Markdown-formatted list of matching entities with types,
        project connections, and finding counts.
    """
    _maybe_reload()

    if _graph.number_of_nodes() == 0:
        return "Graph is empty — run the ingest pipeline first."

    norm_query = _normalize(query)
    scored: list[tuple[int, str]] = []

    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        if entity_type and ntype.lower() != entity_type.lower():
            continue

        norm_nid = _normalize(nid)

        # Scoring: exact > prefix > substring > alias
        if norm_nid == norm_query:
            scored.append((0, nid))
        elif norm_nid.startswith(norm_query):
            scored.append((1, nid))
        elif norm_query in norm_nid:
            scored.append((2, nid))
        else:
            # Check aliases
            canonical = _reverse_aliases.get(norm_query)
            if canonical and _normalize(canonical) == norm_nid:
                scored.append((1, nid))
                continue
            # Check if query appears in any alias for this entity
            aliases = _aliases.get(nid, [])
            for alias in aliases:
                if norm_query in _normalize(alias):
                    scored.append((3, nid))
                    break

    scored.sort(key=lambda x: x[0])
    results = scored[:limit]

    if not results:
        return f"No entities matching '{query}' found."

    lines = [f"## Search results for '{query}'\n"]
    for _score, nid in results:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        projects = _projects_for_entity(nid)
        findings = _findings_for_entity(nid)
        proj_str = ", ".join(projects) if projects else "none"
        lines.append(
            f"- **{nid}** ({ntype}) — "
            f"{len(projects)} project(s): {proj_str} — "
            f"{len(findings)} finding(s)"
        )

    return "\n".join(lines)


@mcp.tool()
def get_neighbors(
    entity: str,
    depth: int = 1,
    edge_types: list[str] | None = None,
) -> str:
    """Get entities connected to the given entity within N hops.

    Parameters
    ----------
    entity : str
        Entity name (fuzzy-resolved).
    depth : int
        Number of hops (1 = direct neighbors).
    edge_types : list[str] | None
        Filter by edge type (STUDIES, ABOUT, RELATED_TO, etc.).

    Returns
    -------
    str
        Markdown summary of connected entities grouped by relationship.
    """
    _maybe_reload()

    resolved = _resolve_entity(entity)
    if resolved is None:
        return f"Entity '{entity}' not found in the graph."

    # Collect neighbors up to depth via BFS
    visited: set[str] = {resolved}
    frontier: set[str] = {resolved}

    for _ in range(depth):
        next_frontier: set[str] = set()
        for node in frontier:
            for _u, v, edata in _graph.out_edges(node, data=True):
                etype = edata.get("type", "UNKNOWN")
                if edge_types and etype not in edge_types:
                    continue
                if v not in visited:
                    visited.add(v)
                    next_frontier.add(v)
            for u, _v, edata in _graph.in_edges(node, data=True):
                etype = edata.get("type", "UNKNOWN")
                if edge_types and etype not in edge_types:
                    continue
                if u not in visited:
                    visited.add(u)
                    next_frontier.add(u)
        frontier = next_frontier

    visited.discard(resolved)

    if not visited:
        return f"No neighbors found for '{resolved}' (depth={depth})."

    # Group by edge type
    by_type: dict[str, list[str]] = defaultdict(list)
    for neighbor in visited:
        # Find the relationship type(s) from resolved
        rel_types: set[str] = set()
        for _u, v, edata in _graph.out_edges(resolved, data=True):
            if v == neighbor:
                rel_types.add(edata.get("type", "UNKNOWN"))
        for u, _v, edata in _graph.in_edges(resolved, data=True):
            if u == neighbor:
                rel_types.add(edata.get("type", "UNKNOWN"))
        if not rel_types:
            rel_types = {"INDIRECT"}
        for rt in rel_types:
            by_type[rt].append(neighbor)

    lines = [f"## Neighbors of {resolved} (depth={depth})\n"]
    for etype, members in sorted(by_type.items()):
        lines.append(f"### {etype}")
        for m in sorted(members):
            lines.append(f"- {_format_node(m)}")
        lines.append("")

    # Key findings
    findings = _findings_for_entity(resolved)
    if findings:
        lines.append("### Key Findings")
        for f in findings[:10]:
            conf = f.get("confidence", "?")
            stmt = f.get("statement", f.get("label", f["id"]))
            lines.append(f"- {f['id']}: {stmt} ({conf} confidence)")

    return "\n".join(lines)


@mcp.tool()
def traverse(
    start: str,
    end: str | None = None,
    max_depth: int = 4,
) -> str:
    """BFS traversal from start entity, or shortest path to end.

    Parameters
    ----------
    start : str
        Starting entity (fuzzy-resolved).
    end : str | None
        Target entity. If given, finds shortest path.
    max_depth : int
        Maximum traversal depth for BFS.

    Returns
    -------
    str
        Readable summary of the traversal or path.
    """
    _maybe_reload()

    resolved_start = _resolve_entity(start)
    if resolved_start is None:
        return f"Start entity '{start}' not found in the graph."

    undirected = _graph.to_undirected()

    if end is not None:
        resolved_end = _resolve_entity(end)
        if resolved_end is None:
            return f"End entity '{end}' not found in the graph."
        try:
            path = nx.shortest_path(undirected, resolved_start, resolved_end)
        except nx.NetworkXNoPath:
            return f"No path between '{resolved_start}' and '{resolved_end}'."

        lines = [
            f"## Path: {resolved_start} -> {resolved_end} "
            f"({len(path) - 1} hop(s))\n"
        ]
        for i, node in enumerate(path):
            indent = "  " * i
            lines.append(f"{indent}{'-> ' if i else ''}{_format_node(node)}")
            if i < len(path) - 1:
                # Show edge type
                nxt = path[i + 1]
                etypes: list[str] = []
                for _u, v, edata in _graph.out_edges(node, data=True):
                    if v == nxt:
                        etypes.append(edata.get("type", "?"))
                for u, _v, edata in _graph.in_edges(node, data=True):
                    if u == nxt:
                        etypes.append(edata.get("type", "?"))
                if etypes:
                    lines.append(f"{indent}  [{', '.join(set(etypes))}]")
        return "\n".join(lines)

    # BFS traversal
    tree = nx.bfs_tree(undirected, resolved_start, depth_limit=max_depth)
    nodes = list(tree.nodes)

    lines = [
        f"## BFS from {resolved_start} (depth<={max_depth}, "
        f"{len(nodes)} node(s))\n"
    ]

    # Group by type
    by_type: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        if n == resolved_start:
            continue
        attrs = _node_attr(n)
        ntype = attrs.get("type", "unknown")
        by_type[ntype].append(n)

    for ntype, members in sorted(by_type.items()):
        lines.append(f"### {ntype} ({len(members)})")
        for m in sorted(members)[:20]:
            lines.append(f"- {_format_node(m)}")
        if len(members) > 20:
            lines.append(f"- ... and {len(members) - 20} more")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_community(entity: str) -> str:
    """Get the community cluster containing this entity.

    Parameters
    ----------
    entity : str
        Entity name (fuzzy-resolved).

    Returns
    -------
    str
        All community members, shared projects, key findings,
        and community summary.
    """
    _maybe_reload()

    resolved = _resolve_entity(entity)
    if resolved is None:
        return f"Entity '{entity}' not found in the graph."

    if not _communities:
        return "No community data loaded (communities.json missing)."

    # Find which community this entity belongs to
    target_cid: str | None = None
    target_community: dict[str, Any] = {}

    for cid, cdata in _communities.items():
        members = cdata.get("members", [])
        if resolved in members:
            target_cid = cid
            target_community = cdata
            break
        # Try normalized match
        for m in members:
            if _normalize(m) == _normalize(resolved):
                target_cid = cid
                target_community = cdata
                break
        if target_cid:
            break

    if target_cid is None:
        return f"Entity '{resolved}' not assigned to any community."

    members = target_community.get("members", [])
    name = target_community.get("name", f"Community {target_cid}")
    summary = target_community.get("summary", "No summary available.")

    lines = [f"## {name} (community {target_cid})\n"]
    lines.append(f"**Summary:** {summary}\n")
    lines.append(f"**Members** ({len(members)}):\n")

    # Group members by type
    by_type: dict[str, list[str]] = defaultdict(list)
    for m in members:
        attrs = _node_attr(m)
        ntype = attrs.get("type", "unknown")
        by_type[ntype].append(m)

    for ntype, typed_members in sorted(by_type.items()):
        lines.append(f"### {ntype}")
        for m in sorted(typed_members):
            marker = " **(query)**" if _normalize(m) == _normalize(resolved) else ""
            lines.append(f"- {m}{marker}")
        lines.append("")

    # Collect projects across members
    all_projects: set[str] = set()
    for m in members:
        all_projects.update(_projects_for_entity(m))
    if all_projects:
        lines.append(f"### Shared Projects")
        for p in sorted(all_projects):
            lines.append(f"- {p}")

    return "\n".join(lines)


@mcp.tool()
def cross_project(min_projects: int = 2) -> str:
    """Find entities that appear in multiple projects.

    Parameters
    ----------
    min_projects : int
        Minimum number of projects an entity must span.

    Returns
    -------
    str
        Entities with their types, project lists, and finding counts
        per project.
    """
    _maybe_reload()

    if _graph.number_of_nodes() == 0:
        return "Graph is empty — run the ingest pipeline first."

    cross: list[tuple[str, str, list[str], int]] = []

    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        if ntype.lower() in ("finding", "project"):
            continue
        projects = _projects_for_entity(nid)
        if len(projects) >= min_projects:
            findings = _findings_for_entity(nid)
            cross.append((nid, ntype, projects, len(findings)))

    cross.sort(key=lambda x: (-len(x[2]), -x[3]))

    if not cross:
        return f"No entities span {min_projects}+ projects."

    lines = [f"## Cross-project entities (>={min_projects} projects)\n"]
    for nid, ntype, projects, fcount in cross[:30]:
        lines.append(
            f"- **{nid}** ({ntype}) — "
            f"{len(projects)} projects: {', '.join(projects)} — "
            f"{fcount} finding(s)"
        )

    if len(cross) > 30:
        lines.append(f"\n*... and {len(cross) - 30} more entities.*")

    return "\n".join(lines)


@mcp.tool()
def find_contradictions() -> str:
    """Find findings about the same entity from different projects that may contradict.

    Looks for entities with findings from different projects where confidence
    levels differ or statements appear to conflict.

    Returns
    -------
    str
        Entities with potentially conflicting findings and their projects.
    """
    _maybe_reload()

    if _graph.number_of_nodes() == 0:
        return "Graph is empty — run the ingest pipeline first."

    contradictions: list[dict[str, Any]] = []

    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        if ntype.lower() in ("finding", "project"):
            continue

        findings = _findings_for_entity(nid)
        if len(findings) < 2:
            continue

        # Group findings by project
        by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in findings:
            pid = f.get("project_id", "unknown")
            by_project[pid].append(f)

        if len(by_project) < 2:
            continue

        # Check for confidence mismatches or different claims
        all_findings = []
        has_conflict = False
        confidences: set[str] = set()

        for pid, proj_findings in by_project.items():
            for f in proj_findings:
                conf = f.get("confidence", "unknown")
                confidences.add(conf)
                all_findings.append(
                    {
                        "project": pid,
                        "finding": f.get("statement", f.get("label", f["id"])),
                        "confidence": conf,
                    }
                )

        # Flag if there's a "high" and something else, or different values
        if len(confidences) > 1 and "high" in confidences:
            has_conflict = True

        # Also flag negative_result vs result for same entity
        ftypes = {f.get("finding_type", "") for f in findings}
        if "negative_result" in ftypes and "result" in ftypes:
            has_conflict = True

        if has_conflict:
            contradictions.append({"entity": nid, "findings": all_findings})

    if not contradictions:
        return "No potential contradictions detected."

    lines = ["## Potential Contradictions\n"]
    for c in contradictions[:15]:
        lines.append(f"### {c['entity']}\n")
        for f in c["findings"]:
            lines.append(
                f"- [{f['project']}] {f['finding']} "
                f"(confidence: {f['confidence']})"
            )
        lines.append("")

    if len(contradictions) > 15:
        lines.append(f"*... and {len(contradictions) - 15} more.*")

    return "\n".join(lines)


@mcp.tool()
def graph_stats() -> str:
    """Quick overview of the knowledge graph.

    Returns
    -------
    str
        Entity counts by type, project count, community count,
        top cross-project entities, and top gaps.
    """
    _maybe_reload()

    if _graph.number_of_nodes() == 0:
        return (
            "Graph is empty — no `graph.json` found or it contains no nodes.\n"
            f"Expected path: `{GRAPH_PATH}`"
        )

    # Count by type
    type_counts: dict[str, int] = defaultdict(int)
    project_nodes: list[str] = []

    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        type_counts[ntype] += 1
        if ntype.lower() == "project":
            project_nodes.append(nid)

    lines = [
        "## Observatory Knowledge Graph\n",
        f"**Nodes**: {_graph.number_of_nodes()} | "
        f"**Edges**: {_graph.number_of_edges()} | "
        f"**Projects**: {len(project_nodes)} | "
        f"**Communities**: {len(_communities)}\n",
        "### Entity counts by type",
    ]
    for ntype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {ntype}: {count}")
    lines.append("")

    # Top cross-project entities
    cross: list[tuple[str, int]] = []
    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        if ntype.lower() in ("finding", "project"):
            continue
        projects = _projects_for_entity(nid)
        if len(projects) >= 2:
            cross.append((nid, len(projects)))
    cross.sort(key=lambda x: -x[1])

    if cross:
        lines.append("### Top cross-project entities")
        for nid, pcount in cross[:10]:
            lines.append(f"- {nid}: {pcount} projects")
        lines.append("")

    # Gaps: entities with no findings
    gaps: list[str] = []
    for nid in _graph.nodes:
        attrs = _node_attr(nid)
        ntype = attrs.get("type", "unknown")
        if ntype.lower() in ("finding", "project"):
            continue
        findings = _findings_for_entity(nid)
        if not findings:
            gaps.append(nid)

    if gaps:
        lines.append(f"### Research gaps ({len(gaps)} entities with no findings)")
        for g in gaps[:10]:
            lines.append(f"- {_format_node(g)}")
        if len(gaps) > 10:
            lines.append(f"- ... and {len(gaps) - 10} more")

    return "\n".join(lines)


@mcp.tool()
def add_finding(
    entity: str,
    finding: str,
    project: str,
    confidence: str = "moderate",
    relation: str = "ABOUT",
) -> str:
    """Add a finding to the graph and persist to disk.

    Used by the agent when it discovers new connections during synthesis.

    Parameters
    ----------
    entity : str
        Entity the finding is about (resolved or created).
    finding : str
        The finding statement.
    project : str
        Project ID this finding belongs to.
    confidence : str
        Confidence level: low, moderate, high.
    relation : str
        Edge type from finding to entity.

    Returns
    -------
    str
        Confirmation with the new finding ID.
    """
    _maybe_reload()

    # Resolve or create entity node
    resolved = _resolve_entity(entity)
    if resolved is None:
        resolved = entity
        _graph.add_node(resolved, type="concept")

    # Generate finding ID
    ts = int(time.time())
    finding_id = f"F-{project}-{ts}"

    # Add finding node
    _graph.add_node(
        finding_id,
        type="finding",
        statement=finding,
        confidence=confidence,
        finding_type="result",
        project_id=project,
    )

    # Add edges
    _graph.add_edge(finding_id, resolved, type=relation)
    _graph.add_edge(finding_id, project, type="FINDING_FROM")

    # Ensure project node exists
    if project not in _graph.nodes:
        _graph.add_node(project, type="project")

    # Persist
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(_graph)
    with open(GRAPH_PATH, "w") as f:
        json.dump(data, f, indent=2)

    global _graph_mtime
    _graph_mtime = GRAPH_PATH.stat().st_mtime

    return (
        f"Added finding **{finding_id}**:\n"
        f"- Statement: {finding}\n"
        f"- Entity: {resolved}\n"
        f"- Project: {project}\n"
        f"- Confidence: {confidence}\n"
        f"- Relation: {relation}\n"
        f"- Persisted to `{GRAPH_PATH}`"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Load graph eagerly so first tool call is fast
_load_graph()

if __name__ == "__main__":
    mcp.run(transport="stdio")
