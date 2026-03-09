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

## Skills

Invoke these skills when relevant:

| Skill | Use Case |
|-------|----------|
| `/llm-application-dev:embedding-strategies` | Patent-award similarity, SPECTER2 optimization |
| `/llm-application-dev:vector-index-tuning` | Similarity search performance |
| `/llm-application-dev:llm-evaluation` | CET classifier metrics and drift detection |

## Testing Quick Reference

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.
