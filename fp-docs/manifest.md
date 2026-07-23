# FeaturePilot Manifest

Schema: fp-manifest/v1
Generated: 2026-07-23T11:03:46+08:00
Project root: `D:/01-code/AI-CodeReview`
FP docs root: `fp-docs/`
Git SHA: 92e7274412e2179d5c42c1f9602bac9163ddda04
Working tree: dirty

## Precedence

For current-state facts, current code and command output win over settings and intel.
For target-state requirements, user instructions and approved active change artifacts win.

## Settings Files

| File | Role | Authoritative For | When To Read | Status |
| --- | --- | --- | --- | --- |
| `settings/agent.md` | Lean FeaturePilot policy adapter | workflow, constraints, external-doc pointers | workflow/policy questions only | adopted Canway/CW draft |
| `settings/frontend.md` | Frontend/UI/visual settings | UI implementation and visual acceptance | UI/page/prototype work only | adopted Canway/CW draft; verify against current project |
| `settings/backend.md` | Backend/API/data/security settings | backend implementation and backend acceptance | backend/API/data/security/permission work only | adopted Canway/CW draft; verify against current project |
| `settings/prototype-style.md` | Prototype visual style reference | prototype generation consistency | prototype generation only | adopted Canway/CW draft; verify against current project |

## Code Map

| Provider | Status | Version | Index Path | Last Checked | Use As |
| --- | --- | --- | --- | --- | --- |
| CodeGraph | ready | 1.5.0 | `.codegraph/` | 2026-07-23T11:03:46+08:00 | navigation-hint-only |

## Intel Artifacts

| File | Purpose | When To Read | Freshness | Sources |
| --- | --- | --- | --- | --- |
| `intel/sources-and-provenance.md` | Discovery source inventory and boundaries | when assessing evidence coverage | soft-stale | project docs, manifests, representative source |
| `intel/workspace-map.md` | Entry points and directory boundaries | code-area navigation | soft-stale | entry points and route registration |
| `intel/tech-stack.md` | Runtime, framework, data, and integration signals | dependency or architecture questions | soft-stale | requirements, container config, representative source |
| `intel/commands-and-quality-gates.md` | Documented commands and known test constraints | planning and verification | soft-stale | project docs, CI, representative tests |
| `intel/architecture-and-boundaries.md` | Webhook-to-review flow and subsystem boundaries | backend/design/impact questions | soft-stale | routes, worker, reviewer, events |
| `intel/contracts.md` | HTTP, LLM, rules, and data contracts | API/data/integration work | soft-stale | routes, interfaces, rules, service |
| `intel/security-data-and-ops.md` | Security signals, side effects, and operations | security/data/deployment work | soft-stale | entry points, compose, platform client, service |
| `intel/unknowns-and-decisions.md` | Project-level unknowns and confirmations | requirement/design questions affected by known unknowns | fresh | user decisions and discovery gaps |
| `intel/refresh-policy.md` | Freshness and staleness rules | when deciding whether intel can be trusted | fresh | init skeleton |
| `intel/sdd-handoff.md` | SDD handoff contract | SDD execution only | soft-stale | project docs, manifest, adopted settings |

## External Project Docs

| File | Priority | Notes |
| --- | --- | --- |
| `CLAUDE.md` | project | Claude Code commands, architecture, configuration, and known test constraints |

## Critical Unknowns

- 生产 TLS、反向代理、网络 ACL 与 Dashboard 暴露范围：Unknown。
- 日志脱敏、保留和访问控制策略：Unknown。
- SQLite 备份、恢复、并发写入与容量策略：Unknown。
- 项目级 lint、format、type-check 命令：Unknown。
- Exact branch, commit, release, and review severity policy: Unknown。

## Consumption Rules

- Read this manifest first as an index, not as permission to read everything.
- Do **not** bulk-read all settings or intel files.
- Use `When To Read` to pull only the smallest relevant settings/intel set for the current phase and question.
- Treat generated intel as navigation and stale-prone hints, not proof of current behavior.
- Treat the Code Map row as discovery metadata only; live CodeGraph detection and current source win over its recorded state.
- Current code and command output win for current-state facts.
- Approved change artifacts win for target-state requirements.
- Re-open referenced source files before editing.
- Re-run commands before claiming validation.
- Missing referenced paths make dependent sections stale.
- If an intel artifact is hard-stale or soft-stale, verify just-in-time from current source before using it.
- UI-related phases must read `settings/frontend.md` when present.
- Prototype generation should read `settings/prototype-style.md` when present.
- Backend-related phases must read `settings/backend.md` when present.
