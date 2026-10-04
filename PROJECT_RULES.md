<!-- GSD Project Profile: WEB -->
# PROJECT_RULES.md — VoiceHire Project Rules

> **Single Source of Truth** for VoiceHire development methodology.
>
> Extends the GSD canonical framework with project-specific rules for the VoiceHire platform.
> Model-agnostic. All adapters and extensions reference this file.

---

## Project Identity

| Property | Value |
|----------|-------|
| **Project** | VoiceHire |
| **Type** | Flask Web Application (Monolith) |
| **Database** | Supabase (PostgreSQL) |
| **Primary Language** | Python 3.11+ |
| **Framework** | Flask 3.0.3 |
| **Target Market** | India — Informal Workforce |
| **Main Entry Point** | `app.py` (1488 lines) |
| **Docs Directory** | `docs/` |

---

## VoiceHire-Specific Engineering Rules

### Tech Stack Constraints

- **Flask only** — No FastAPI, Django, or other frameworks without team sign-off
- **Supabase client** — All DB access via `supabase-py`; no raw psycopg2/SQLAlchemy
- **No new dependencies** without updating `requirements.txt` and documenting rationale
- **Local storage only** for file uploads until S3/Supabase Storage migration is approved
- **Jinja2 templates** for all server-rendered pages; no React/Vue SPA without explicit decision

### Indian Market Rules

- **Phone validation** must use `^[6-9]\d{9}$` pattern (10-digit Indian mobile numbers)
- **Language support** — All new UI text must have a translation key in `translations.py`
- **IST timezone** — Display times in IST (UTC+5:30); store in UTC internally
- **Price fields** — Assume INR; no currency conversion logic needed at this stage

### File Upload Safety Rules

- Always call `allowed_file(filename, ALLOWED_SET)` before saving any upload
- Always prefix saved filenames with `uuid.uuid4().hex + '_'`
- Always call `secure_filename()` on user-provided filenames
- Enforce the 16MB `MAX_CONTENT_LENGTH` at config level, never trust client claims
- Never serve uploaded files from a route — only from `static/uploads/`

### QR & Security Rules

- **Booking QR tokens** must use HMAC-SHA256 via `make_qr_token()` — never raw UUID
- **Job completion tokens** must use `secrets.token_urlsafe(32)` minimum
- **Token comparison** must always use `hmac.compare_digest()` — never `==`
- **All tokens** are one-time-use; set to `NULL` after consumption
- **SECRET_KEY** must come from environment; the fallback string must never be used in production

### API Design Rules

- Every protected route must check `'user_id' not in session` as the FIRST guard
- Return `401` for unauthenticated; `403` for authenticated-but-wrong-role
- Use `safe_str()` to sanitize all string inputs from `request.form` or `request.get_json()`
- All JSON error responses must use `{ "error": "message" }` format
- Include role in route guard: `session['role'] != 'worker'` — never assume role from user_id alone

### Database Resilience Rules

- Use `try_select()` for any query that reads `profile_pic` — column may not exist in all deployments
- Always check `if not resp.data:` before accessing `resp.data[0]`
- Wrap all Supabase calls in try/except; log full traceback with `traceback.format_exc()`
- Never expose raw exception messages to the client — return generic 500 + log internally

---

## Core Protocol

**SPEC → PLAN → EXECUTE → VERIFY → COMMIT**

1. **SPEC**: Define requirements in `docs/REQUIREMENTS.md` until status is `FINALIZED`
2. **PLAN**: Decompose into phases in `.gsd/ROADMAP.md`, then detailed plans
3. **EXECUTE**: Implement with atomic commits per task
4. **VERIFY**: Prove completion with empirical evidence
5. **COMMIT**: One task = one commit, message format: `type(scope): description`

**Planning Lock**: No implementation code until `docs/REQUIREMENTS.md` contains "Status: FINALIZED".

---

## Proof Requirements

Every change requires verification evidence:

| Change Type | Required Proof |
|-------------|----------------|
| API endpoint | curl/HTTP response |
| UI change | Screenshot |
| Build/compile | Command output |
| Test | Test runner output |
| Config | Verification command |

**Never accept**: "It looks correct", "This should work", "I've done similar before".

**Always require**: Captured output, screenshot, or test result.

---

## Search-First Discipline

**Before reading any file completely:**

1. **Search first** — Use grep, ripgrep, or IDE search to find relevant snippets
2. **Evaluate snippets** — Determine if full file read is justified
3. **Targeted reads** — Only read specific line ranges when needed

**Benefits:**
- Reduces context pollution
- Faster understanding of large codebases
- Prevents reading irrelevant code

**Anti-pattern**: Reading entire files "to understand the context" without searching first.

---

## Delegation

**Rule:** Orchestrator workflows delegate the work and keep the routing.

Where `invoke_subagent` exists (Antigravity 2.0+), heavy work runs in a subagent with its own
context. The orchestrator reads compact results only.

| Work | Subagent |
|------|----------|
| Plan execution | `gsd-executor` (one per PLAN.md) |
| Plan authoring | `gsd-planner` |
| Phase verification | `gsd-verifier` |
| Mapping and research | `gsd-researcher` |
| Bug diagnosis | `gsd-debugger` |

**Non-negotiable:**
- A subagent inherits **no** conversation history — put every needed fact in its prompt
- Pass **paths**, never file contents
- Never re-read an artifact a subagent already summarized just to confirm it
- Where subagents are unavailable, say so out loud and degrade to one plan per session —
  never claim delegation that did not happen

Full protocol: `.agents/skills/subagent-delegation/SKILL.md`

---

## Wave Execution

Plans are grouped into **waves** based on dependencies:

| Wave | Characteristic | Execution |
|------|----------------|-----------| 
| 1 | Foundation tasks, no dependencies | Run in parallel |
| 2 | Depends on Wave 1 | Wait for Wave 1, then parallel |
| 3 | Depends on Wave 2 | Wait for Wave 2, then parallel |

**Parallelism is real only with subagents.** A wave with multiple plans runs one
`gsd-executor` per plan in `branch` workspace mode (isolated git worktrees), merged when the
wave closes. Without subagents, a "wave" degrades to sequential execution in one context —
plan it as such.

**Wave Completion Protocol:**
1. All tasks in wave verified
2. State snapshot created
3. Commit all wave work
4. Update STATE.md with position

---

## State Snapshots

At the end of each wave or significant work block, create a state snapshot:

```markdown
## Wave N Summary

**Objective:** {what this wave aimed to accomplish}

**Changes:**
- {change 1}
- {change 2}

**Files Touched:**
- {file1}
- {file2}

**Verification:**
- {command}: {result}

**Risks/Debt:**
- {any concerns}

**Next Wave TODO:**
- {item 1}
- {item 2}
```

---

## Model Independence

**Absolute Rule**: No rule, workflow, or skill may require a specific model provider.

**Allowed:**
- Optional adapters with provider-specific enhancements
- Capability-based recommendations (e.g., "use a reasoning model for planning")
- Examples mentioning specific models as illustrations

**Forbidden:**
- Hard dependencies on provider features
- Breaking behavior when a specific model is unavailable
- Duplicating canonical rules in adapters

**Adapter Pattern:**
```
adapters/
├── CLAUDE.md    # Optional Claude enhancements
├── GEMINI.md    # Optional Gemini enhancements
└── GPT_OSS.md   # Optional GPT/OSS enhancements
```

Each adapter must begin with:
> "Everything in this file is optional. For canonical rules, see PROJECT_RULES.md."

---

## Commit Conventions

**Format:**
```
type(scope): description
```

**Types:**
| Type | Usage |
|------|-------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code restructure (no behavior change) |
| `test` | Adding/updating tests |
| `chore` | Maintenance, dependencies |

**Rules:**
- One task = one commit
- Verify before commit
- Scope = phase number for phase work (e.g., `feat(phase-1): ...`)
- **Confirm the commit landed** with `git log -1 --oneline` before starting the next task
- **Never `--allow-empty`** — a task with no tracked change is not complete, and git does not
  track directories

---

## Shell Discipline

**Rule:** one command per invocation. Never chain with `&&` or `||`.

The host shell is not knowable from inside a workflow. Windows PowerShell 5.1 rejects both
operators with a parse error, so `git add X && git commit -m "..."` does not partially run —
it does not run at all, while looking like it did.

| Do | Don't |
|----|-------|
| `git add -A` then `git commit -m "..."` as two calls | `git add -A && git commit -m "..."` |
| Read each command's output before the next | Assume success from absence of a visible error |
| Provide both PowerShell and Bash forms in workflows | Ship a bash-only example as "the" command |

**Why it matters:** a command that never ran produces no error the agent recognises. Work is
reported as done, the worktree is discarded, and the change is gone.

---

## Repository Structure

```
voicehire-final/
├── PROJECT_RULES.md      # ← This file (canonical rules + project-specific rules)
├── GSD-STYLE.md          # Style and conventions
├── README.md             # Project overview, quickstart, architecture + ER diagram
├── app.py                # Main Flask application (single entry point)
├── translations.py       # Translation engine (10+ Indian languages)
├── requirements.txt      # Python dependencies (pinned versions)
├── .env                  # Environment secrets (NEVER COMMIT)
├── .gitignore
│
├── templates/            # Jinja2 HTML templates (15 files)
├── static/               # Static assets + user uploads
│   ├── css/
│   ├── js/
│   └── uploads/          # audio/ video/ ids/ profile_pics/
│
├── docs/                 # Project documentation
│   ├── ARCHITECTURE.md   # System design, data flows, database schema
│   ├── REQUIREMENTS.md   # Functional & non-functional requirements (FINALIZED)
│   └── API.md            # Complete REST API reference
│
├── adapters/             # Optional model-specific enhancements
│   ├── CLAUDE.md
│   ├── GEMINI.md
│   └── GPT_OSS.md
│
├── .agent/
│   └── workflows/        # Slash commands (/plan, /execute, etc.)
│
├── .agents/
│   ├── agents/           # Subagent definitions
│   └── skills/           # Agent specializations
│
├── .gemini/              # Gemini-specific configuration
├── .gsd/                 # Project state files
│   ├── templates/
│   └── examples/
└── scripts/              # Utility scripts
```

---

## Context Management

**Context Quality Thresholds:**

| Usage | Quality |
|-------|---------|
| 0-30% | **PEAK** — Comprehensive, thorough work |
| 30-50% | **GOOD** — Solid, confident output |
| 50-70% | **DEGRADING** — Efficiency mode |
| 70%+ | **POOR** — Rushed, incomplete |

**Context Hygiene Rules:**
- Keep plans under 50% context usage
- Fresh context for each plan execution — enforced by one `gsd-executor` subagent per plan,
  not by hoping the orchestrator stays tidy
- After 3 debugging failures → state dump → fresh session
- STATE.md = memory across sessions

---

## Token Efficiency Rules

**Goal:** Minimize token consumption while maintaining output quality.

### Loading Rules

| Action | Rule |
|--------|------|
| Before reading file | Search first (grep, ripgrep) |
| File >200 lines | Use outline, not full file |
| File already understood | Reference summary, don't reload |
| >5 files needed | Stop, reconsider approach |

### Budget Thresholds

| Usage | Action Required |
|-------|-----------------|
| 0-50% | Proceed normally |
| 50-70% | Switch to outline mode, compress context |
| 70%+ | State dump required, recommend fresh session |

### Compression Protocol

After understanding a file:
1. Create summary in STATE.md or task notes
2. Reference summary instead of re-reading
3. Only reload specific sections if needed

### Per-Wave Efficiency

- Start each wave with minimal context
- Load files just-in-time (when task requires)
- Compress/summarize before moving to next wave
- Document token usage in state snapshots (optional)

**Anti-patterns:**
- Loading files "just in case"
- Re-reading files already understood
- Full file reads when snippets suffice
- Ignoring budget warnings

---

## Quick Reference

```
Before coding     → docs/REQUIREMENTS.md must be FINALIZED
Before file read  → Search first, then targeted read
After each task   → Commit + update STATE.md
After each wave   → State snapshot
After 3 failures  → State dump + fresh session
Before "Done"     → Empirical proof captured
For Indian phone  → Validate: ^[6-9]\d{9}$
For file uploads  → allowed_file() + secure_filename() + uuid prefix
For QR tokens     → HMAC-SHA256 + hmac.compare_digest()
```

---

## VoiceHire Documentation Index

| Document | Purpose | Status |
|----------|---------|--------|
| `README.md` | Project overview, quickstart, architecture diagram, ER diagram | Complete |
| `docs/ARCHITECTURE.md` | System design, data flows, database schema, security | Complete |
| `docs/REQUIREMENTS.md` | Functional & non-functional requirements, use cases | FINALIZED |
| `docs/API.md` | Full REST API reference with request/response examples | Complete |
| `PROJECT_RULES.md` | This file — GSD methodology + VoiceHire-specific rules | Active |
| `GSD-STYLE.md` | Code style and naming conventions | Active |

---

*GSD Methodology — VoiceHire Project Edition*
*Model-agnostic. Extended for the VoiceHire Flask + Supabase platform.*
