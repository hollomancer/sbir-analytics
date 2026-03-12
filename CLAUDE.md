# Claude Code Instructions

See [AGENTS.md](./AGENTS.md) for project context, architecture, and development workflows.

## Default Agent Usage

Use these agents proactively based on task type:

### Testing & Quality
| Trigger | Agent |
|---------|-------|
| Writing or modifying tests | `unit-testing:test-automator` |
| Test failures or unexpected behavior | `unit-testing:debugger` |
| Code review requests | `comprehensive-review:code-reviewer` |

### Architecture & Security
| Trigger | Agent |
|---------|-------|
| Changes to pipeline stages, Neo4j schema, or Dagster assets | `code-review-ai:architect-review` |
| Touching credentials, API keys, AWS config, or auth | `comprehensive-review:security-auditor` |
| Large file refactoring (>500 LOC changes) | `code-refactoring:legacy-modernizer` |

### ML & AI Features
| Trigger | Agent |
|---------|-------|
| CET classifier, embeddings, or ML model work | `llm-application-dev:ai-engineer` |
| Prompt templates or LLM integration | `llm-application-dev:prompt-engineer` |

## Project Agents

Custom agents in `.claude/agents/` for autonomous development:

| Agent | Trigger |
|-------|---------|
| `spec-implementer` | Implementing Kiro spec tasks, "work on [spec-name]" |
| `test-fixer` | Failing tests, improving test coverage |
| `quality-sweep` | Lint errors, type errors, code quality cleanup |
| `autodev-runner` | Autonomous development sessions, "start autodev" |

## Skills

### Project Skills

Custom skills in `.claude/skills/`:

| Skill | Use Case |
|-------|----------|
| `/spec-implement [spec-name]` | Implement pending tasks from a Kiro specification |
| `/fix-tests [path]` | Find and fix failing tests |
| `/autodev-run [max-tasks]` | Start autonomous development session |
| `/review-spec [spec-name\|all]` | Review spec relevance against codebase |

### Plugin Skills

| Skill | Use Case |
|-------|----------|
| `/llm-application-dev:embedding-strategies` | Patent-award similarity, PaECTER optimization |
| `/llm-application-dev:vector-index-tuning` | Similarity search performance |
| `/llm-application-dev:llm-evaluation` | CET classifier metrics and drift detection |

## Autonomous Development

The `src/autodev/` module provides a programmatic autonomous development loop:

```bash
sbir-cli autodev discover    # See all pending work items
sbir-cli autodev specs       # View Kiro spec completion status
sbir-cli autodev run         # Run the autonomous loop (dry-run by default)
sbir-cli autodev sessions    # List previous sessions
```

Use `/autodev-run` or the `autodev-runner` agent for interactive autonomous work.

## Testing Quick Reference

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.
