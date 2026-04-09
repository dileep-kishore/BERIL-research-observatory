"""Integration test: registry → wiki compilation → index generation → lint."""

from observatory_context.registry.schema import EntityRef, Finding, Hypothesis, Project
from observatory_context.wiki.compiler import compile_entity_page, compile_hypothesis_page, compile_topic_page
from observatory_context.wiki.index import WikiEntry, build_index_markdown
from observatory_context.wiki.lint import detect_untested_hypotheses, detect_low_coverage_topics, build_gap_report


def test_full_wiki_generation_flow():
    # 1. Create registry entries
    _project = Project(project_id="metal-stress-eco", title="Metal stress ecotype analysis",
                      status="complete", research_question="Do metal stress genes define ecotypes?",
                      organisms=["Pseudomonas putida"], tags=["metal-stress"])
    findings = [Finding(finding_id="F-023", project_id="metal-stress-eco",
                        title="Czc efflux conserved", statement="44/47 strains carry czc operon",
                        confidence="high", finding_type="result",
                        related_entities=[EntityRef(type="organism", label="Pseudomonas putida"),
                                         EntityRef(type="pathway", label="czc efflux")])]
    hypotheses = [Hypothesis(hypothesis_id="HYP-007",
                             statement="Metal cross-resistance via shared regulation",
                             status="proposed", project_ids=["metal-stress-eco"])]

    # 2. Compile wiki pages
    entity_page = compile_entity_page(entity_type="organism", slug="pseudomonas-putida",
                                      label="Pseudomonas putida", findings=findings,
                                      hypotheses=hypotheses, project_ids=["metal-stress-eco"])
    assert "Pseudomonas putida" in entity_page
    assert "F-023" in entity_page

    topic_page = compile_topic_page(slug="metal-stress", title="Metal Stress Responses",
                                    findings=findings, hypotheses=hypotheses, project_ids=["metal-stress-eco"])
    assert "Metal Stress Responses" in topic_page

    hyp_page = compile_hypothesis_page(hypothesis=hypotheses[0], supporting_findings=findings)
    assert "HYP-007" in hyp_page

    # 3. Generate index
    entries = [WikiEntry(slug="metal-stress", section="topics", summary="Metal stress", source_count=1, coverage="low"),
               WikiEntry(slug="pseudomonas-putida", section="entities/organisms", summary="Model organism", source_count=1, coverage="low"),
               WikiEntry(slug="HYP-007", section="hypotheses", summary="Cross-resistance", source_count=1, coverage="low")]
    index_md = build_index_markdown(entries)
    assert "metal-stress" in index_md

    # 4. Lint
    untested = detect_untested_hypotheses(hypotheses)
    assert len(untested) == 1
    low_cov = detect_low_coverage_topics({"metal-stress": findings})
    assert len(low_cov) == 1
    gap_report = build_gap_report(untested + low_cov)
    assert "HYP-007" in gap_report
    assert "metal-stress" in gap_report
