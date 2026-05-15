# Claude vs. Codex Workflow and Recommendations

This document outlines the recommended division of responsibilities
between Claude/Claude Code and Codex for the pickleball simulation
platform, along with a phased AI-assisted development workflow.

## Recommended Responsibility Split

- Claude: architecture interpretation, consistency reviews, terminology
  normalization, orchestration validation, specification refinement, and
  code review.

- Codex: repository scaffolding, ORM model generation, migrations,
  implementation of generation engines, orchestration modules, test
  generation, and debugging.

- Use Claude as the architect and reviewer; use Codex as the
  implementation engineer.

## Recommended Workflow

- Phase 1: Specification review and canonicalization using Claude.

- Phase 2: Establish coding standards, AGENTS.md, configuration schema,
  and invariant rules.

- Phase 3: Use Codex to scaffold repository, Docker, Dev Containers,
  CI/CD, and package structure.

- Phase 4: Use Codex to implement database models, migrations,
  persistence layers, and constraints.

- Phase 5: Implement incremental vertical slices rather than the entire
  system at once.

- Phase 6: Generate unit and integration tests using Codex, then review
  with Claude.

- Phase 7: Continue iterative review, refinement, and refactoring.

## Recommended Initial Vertical Slice

- 1\. Region data ingestion

- 2\. Player generation

- 3\. Player assessment history generation

- 4\. Validation testing

## Recommended Expansion Sequence

- 1\. Club assignment

- 2\. Team generation

- 3\. Match scheduling

- 4\. Game generation

- 5\. Ratings updates

- 6\. Confidence calculations

- 7\. Monthly orchestration

- 8\. Parquet export

## Final Recommendation

- Claude should serve as the architect, reviewer, specification
  validator, and orchestration analyst.

- Codex should serve as the implementation engineer, test generator,
  migration generator, and debugging engine.

- This combined approach substantially reduces architectural drift and
  AI-generated technical debt.
