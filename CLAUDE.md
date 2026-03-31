# Observatory Rules

## OpenViking First

When retrieving observatory knowledge (pitfalls, discoveries, research ideas,
hypotheses, entities, project findings, figures, data artifacts), always use
`uv run scripts/query_knowledge_unified.py <subcommand>` or the `/knowledge` skill.

- **Never** read `data/viking/` files directly — that is OpenViking's internal storage
- **Never** make raw HTTP calls to the OpenViking server
- **Never** read project markdown files to answer knowledge questions when OpenViking is running

The markdown files exist for compatibility and version control. OpenViking is the
query interface.

If OpenViking is unreachable, tell the user and stop. Do not fall back to reading files.
