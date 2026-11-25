# `claude-delegate` & `claude-verify` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, cross-model review, pressure-test, and publish the `claude-delegate` and `claude-verify` Antigravity skills so AGY can run confined headless `claude` CLI tasks and receive blind cross-vendor verification with deterministic quote grounding.

**Architecture:** A two-layer Python 3.10+ stdlib-only skill suite inside `agy-skills`. Layer 1 (`claude-delegate`) wraps `claude -p` with OAuth-safe stateless flags, UTF-8 `stdin` transport, a cross-platform `PreToolUse` confinement hook, `stream-json` telemetry, process-tree cleanup, and parallel batching. Layer 2 (`claude-verify`) stages clean blind review packages outside any `.git` repo, runs single-pass, multi-lens batch, or 2-stage arbiter reviews, and validates `modelUsage`, hook confinement, and `verbatim_quote` grounding deterministically.

**Tech Stack:** Python 3.10+ (stdlib only), `unittest`, Git (`git diff` / `git archive` / `git worktree`), Claude Code CLI `v2.1+` (`claude -p`), GitHub CLI (`gh`).

**Spec:** `docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md`

## Global Constraints

- Python 3.10+ standard library only — zero third-party `pip` dependencies in runtime or test scripts.
- Never invoke `claude --bare` by default (breaks `claude.ai` Max OAuth login); enforce isolation with `--restricted --permission-prompts none --strict-mcp-config --disable-slash-commands`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and removal of `CLAUDECODE*` env vars.
- Never pass prompt bodies on the CLI argv; always pipe UTF-8 bytes via `stdin` and reconfigure Python `stdout`/`stderr` to `encoding="utf-8", errors="replace"`.
- Every `SKILL.md` frontmatter `description` must be third-person, start with `"Use when..."`, stay under 500 chars, and contain zero workflow summaries (`superpowers:writing-skills`).
- **Cross-Model Review Rule (`superpowers:requesting-code-review`)**: Every task implemented by an AGY (Gemini) subagent MUST pass (1) an AGY SDD Task Reviewer (`task-reviewer-prompt.md`) AND (2) a blind **Anthropic Claude CLI (`claude -p --model sonnet` or `opus`)** code review on `BASE_SHA..HEAD_SHA` before the task is marked complete (`writer_family != reviewer_family`).

## Review Focus

1. **CRLF/LF & trailing-space drift in `verbatim_quote`** (`diff`/files on Windows have `\r\n` while Claude JSON emits `\n`) -> `grounding_gate` returns `"verified"` on exact match and `"normalized_match"` on CRLF/whitespace-normalized match before falling back to `"unverified_quote"` (pinned in Task 2).
2. **Nested backtick fence escape in Markdown artifacts** (reviewing a `SKILL.md` containing ```` ``` ```` or ````` ```` ````` breaks naive prompt blocks) -> `fenced()` uses `max_backticks + 1` (pinned in Task 2).
3. **Literal `"429"` or `"rate_limit_error"` inside reviewed source code** falsely tripping quota detection -> `CLAUDE_QUOTA_RE` checks only CLI error states (`is_error == True` or `rc != 0` stderr), never normal assistant output (pinned in Task 4).
4. **Spaces and parentheses in Windows paths for `PreToolUse` hooks** breaking PowerShell/CMD/Git Bash command parsing -> `build_hook_command()` tested against paths containing spaces and `(` on Windows (pinned in Task 4).
5. **Dirty working tree & `<repo>/CLAUDE.md` leakage during `--git-range BASE..HEAD`** -> `extract_git_snapshot()` archives `HEAD` into `<job_dir>/context/` while stripping `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.agents/**`, `.claude/**`, `.superpowers/**`, `docs/superpowers/**`, and `.env*` (pinned in Task 5).

---

## File Structure & Parallel Execution Map

```text
agy-skills/ (isolated git worktree: feat/claude-cross-verify)
├── README.md                                        # [Modify: Task 6]
├── docs/superpowers/
│   ├── specs/2026-11-25-claude-cross-verify-design.md  # [Create: Task 0]
│   ├── plans/2026-11-25-claude-cross-verify-plan.md    # [Create: Task 0]
│   └── handoffs/2026-11-25-claude-cross-verify-handoff.md
├── claude-delegate/
│   ├── SKILL.md                                     # [Create: Task 6 (after Task 3 RED)]
│   ├── README.md                                    # [Create: Task 6]
│   └── scripts/
│       ├── claude_confine_hook.py                   # [Create: Task 1 - Wave 1 Parallel A]
│       ├── claude_task.py                           # [Create: Task 4 - Wave 2]
│       └── tests/
│           ├── fake_claude.py                       # [Create: Task 4]
│           ├── test_claude_confine.py               # [Create: Task 1 - Wave 1 Parallel A]
│           ├── test_claude_task.py                  # [Create: Task 4]
│           └── test_batch_timeout.py                # [Create: Task 4]
└── claude-verify/
    ├── SKILL.md                                     # [Create: Task 6 (after Task 3 RED)]
    ├── README.md                                    # [Create: Task 6]
    ├── prompts/
    │   ├── verify_diff.md                           # [Create: Task 2 - Wave 1 Parallel B]
    │   ├── verify_plan.md                           # [Create: Task 2]
    │   ├── verify_doc.md                            # [Create: Task 2]
    │   ├── verify_custom.md                         # [Create: Task 2]
    │   ├── arbiter.md                               # [Create: Task 2]
    │   └── reverify.md                              # [Create: Task 2]
    └── scripts/
        ├── verify_gates.py                          # [Create: Task 2 - Wave 1 Parallel B]
        ├── claude_verify.py                         # [Create: Task 5 - Wave 2]
        └── tests/
            ├── test_verify_gates.py                 # [Create: Task 2 - Wave 1 Parallel B]
            └── test_claude_verify.py                # [Create: Task 5]
```

**Execution Waves (`/teamwork` + `/subagent-driven-development`)**:
- **Wave 0 (Foundation)**: Task 0 (Repo sync, isolated Git Worktree setup, Spec/Plan commit, 1-shot `claude -p` schema+stream probe).
- **Wave 1 (3-Way Parallel Dispatch — Disjoint Files)**: Task 1 (`claude_confine_hook.py`) || Task 2 (`verify_gates.py` + `prompts/`) || Task 3 (`writing-skills` RED baseline pressure tests).
- **Wave 2 (Core Runners + Cross-Model Review)**: Task 4 (`claude_task.py`) -> Task 5 (`claude_verify.py` + dogfood cross-review).
- **Wave 3 (Skill TDD GREEN/REFACTOR)**: Task 6 (`SKILL.md`s + `README.md`s + pressure-test compliance verification).
- **Wave 4 (Final Verification & Release)**: Task 7 (Live E2E verification, `~/.gemini/config/skills/` sync, whole-branch cross-model review, GitHub push/PR).

---

### Task 0: Isolated Worktree Setup, Spec/Plan Commit & Runtime Probe

**Files:**
- Create: `docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md`
- Create: `docs/superpowers/plans/2026-11-25-claude-cross-verify-plan.md`
- Modify: `.gitignore` (ensure `.worktrees/` and `.superpowers/` are git-ignored)

**Interfaces:**
- Produces: Isolated worktree on branch `feat/claude-cross-verify` from `cannedJean/agy-skills` `main`; verified `claude` CLI capability record in `.superpowers/sdd/progress.md` confirming `--output-format stream-json --verbose --json-schema` behavior on `claude` 2.1.327.

- [x] **Step 1: Sync reference `claude-skills` & target `agy-skills` clones and create worktree (`using-git-worktrees`)**
  Run `git pull --ff-only` on `scratch/repos/agy-skills`, add `.worktrees/` and `.superpowers/` to `.gitignore`, commit on `main`, and run `git worktree add .worktrees/claude-cross-verify -b feat/claude-cross-verify`.
- [x] **Step 2: Write design spec and implementation plan files into the worktree and commit**
  Save `docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md` and `docs/superpowers/plans/2026-11-25-claude-cross-verify-plan.md`, then commit.
- [ ] **Step 3: Run one minimal non-destructive `claude -p` capability probe**
  Verify exact JSON event keys emitted by `claude -p --restricted --permission-prompts none --output-format stream-json --verbose --json-schema '{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}' --max-turns 2` with stdin `"Reply with {\"ok\": true}"`, recording exact `result` / `structured_output` / `modelUsage` field names in `.superpowers/sdd/progress.md`.

---

### Task 1: `claude-delegate` PreToolUse Confinement Hook (`Wave 1 — Parallel Track A`)

**Files:**
- Create: `claude-delegate/scripts/claude_confine_hook.py`
- Test: `claude-delegate/scripts/tests/test_claude_confine.py`

**Interfaces:**
- Produces:
  - `decide(payload: dict, root: str, *, read_only: bool = False, read_only_dirs: tuple[str, ...] = (), inlined: frozenset[str] = frozenset(), allow_bash: bool = False) -> tuple[str, str, list[tuple], str]` returning `(decision: "allow_defer"|"deny", reason: str, hits: list, rule: str)` where `rule` in `{"", "shell", "tool", "path", "hard_link", "protected", "secret", "readonly", "inlined", "error"}`.
  - CLI entrypoint reading Claude `PreToolUse` JSON (`tool_name`, `tool_input`, `cwd`) on `stdin`, logging JSONL to `CLAUDE_CONFINE_LOG`, and writing `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}` on deny or `{}` on defer (fail-closed on any exception).
  - Environment contract: `CLAUDE_CONFINE_ROOT`, `CLAUDE_CONFINE_LOG`, `CLAUDE_CONFINE_READ_ONLY` (`"1"`), `CLAUDE_CONFINE_RO_DIRS` (JSON list), `CLAUDE_CONFINE_INLINED` (JSON list), `CLAUDE_CONFINE_ALLOW_BASH` (`"1"`).

- [ ] **Step 1: Write failing unit tests in `claude-delegate/scripts/tests/test_claude_confine.py`**
  Cover: out-of-root `Read`/`Write`/`Edit`/`Glob`/`Grep`, traversal look-alikes (`.. `, `...`), Windows UNC/device/ADS (`file.txt:zone`), hard-linked files (`os.link`), blocked tools (`Bash`, `PowerShell`, `WebFetch`, `WebSearch`, `AskUserQuestion`, `mcp__x`), blocked agent/secret files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.git/HEAD`, `.agents/x`, `.claude/x`, `.superpowers/x`, `docs/superpowers/x`, `.env`, `.env.local`, `id.pem`), `--read-only` blocking `Write`/`Edit` inside `root`, `--read-only-dir` allowing `Read` but denying `Write`, `--inlined` denying `Read` only when no higher-severity rule fires, and malformed stdin failing closed (`permissionDecision == "deny"`, `rule == "error"`).
- [ ] **Step 2: Run tests to verify RED failure**
  Run: `python -m unittest discover -s claude-delegate/scripts/tests -p "test_claude_confine.py" -v`
  Expected: FAIL (`ModuleNotFoundError: claude_confine_hook`).
- [ ] **Step 3: Implement `claude-delegate/scripts/claude_confine_hook.py`**
  Implement canonical path resolution (`os.path.normcase(os.path.realpath(...))`), argument scanner across `tool_input` (`file_path`, `path`, `pattern`, `notebook_path`, path-like strings), rule evaluation, atomic JSONL audit append, and Claude `hookSpecificOutput` stdout serializer.
- [ ] **Step 4: Run tests to verify GREEN pass**
  Run: `python -m unittest discover -s claude-delegate/scripts/tests -p "test_claude_confine.py" -v`
  Expected: PASS (0 failures, pristine output).
- [ ] **Step 5: Commit & Cross-Model Code Review (`/requesting-code-review`)**
  Commit changes, then run both AGY SDD Task Reviewer (`task-reviewer-prompt.md`) AND blind `claude -p --restricted --permission-prompts none --model sonnet` (`code-reviewer.md` on `BASE_SHA..HEAD_SHA`). Fix any Critical/Important findings before marking complete.

---

### Task 2: `claude-verify` Deterministic Gates & Blind Prompt Templates (`Wave 1 — Parallel Track B`)

**Files:**
- Create: `claude-verify/scripts/verify_gates.py`
- Create: `claude-verify/prompts/verify_diff.md`
- Create: `claude-verify/prompts/verify_plan.md`
- Create: `claude-verify/prompts/verify_doc.md`
- Create: `claude-verify/prompts/verify_custom.md`
- Create: `claude-verify/prompts/arbiter.md`
- Create: `claude-verify/prompts/reverify.md`
- Test: `claude-verify/scripts/tests/test_verify_gates.py`

**Interfaces:**
- Produces:
  - `FINDING_SCHEMA: dict`, `VERIFY_OUTPUT_SCHEMA: dict`, `ARBITER_OUTPUT_SCHEMA: dict`, `REVERIFY_OUTPUT_SCHEMA: dict`
  - `fenced(text: str, lang: str = "") -> str`
  - `validate_inputs(artifacts: dict[str, str], spec_text: str | None, *, kind: str) -> tuple[list[str], list[str]]` returning `(errors, framing_warnings)` (enforces non-empty artifacts, required `spec_text` for `kind == "custom"`, `IDENTICAL_ARTIFACT_AND_SPEC` error, and `PREJUDGING_DIRECTIVE_RE` warnings).
  - `family(model: str | None) -> str` (`"opus" | "sonnet" | "haiku" | "gemini" | ...`)
  - `model_gate(res: dict, requested_model: str, *, forbid_families: tuple[str, ...] = ("gemini",)) -> dict`
  - `confinement_gate(conf: dict, *, tool_steps: int) -> dict` (`ok: False, code: "unconfined"` when `tool_steps > 0 and not conf.get("enabled")`; `ok: True, flags: ["escape_denied"]` when `conf.get("denied_count", 0) > 0`).
  - `grounding_gate(findings: list[dict], corpus: dict[str, str]) -> tuple[list[dict], dict]` tagging each finding `grounding` in `{"verified", "normalized_match", "unverified_quote"}` and computing summary counts.
  - `deduplicate_findings(findings: list[dict]) -> list[dict]` (deterministic merge across `--lenses` keeping highest severity).

- [ ] **Step 1: Write failing unit tests in `claude-verify/scripts/tests/test_verify_gates.py`**
  Include Review Focus #1 (CRLF vs LF and internal whitespace normalization in `grounding_gate`), Review Focus #2 (nested 3- and 4-backtick fences in `fenced()`), `IDENTICAL_ARTIFACT_AND_SPEC` rejection, `PREJUDGING_DIRECTIVE_RE` detection (`"do not flag"`, `"ignore this"`), `model_gate` rejecting `gemini` or mismatched family (`asked opus, ran sonnet`), `confinement_gate` distinguishing `unconfined` vs `escape_denied`, `grounding_gate` catching fabricated quotes (`unverified_quote`), and `deduplicate_findings` merging multi-lens overlaps.
- [ ] **Step 2: Run tests to verify RED failure**
  Run: `python -m unittest discover -s claude-verify/scripts/tests -p "test_verify_gates.py" -v`
  Expected: FAIL (`ModuleNotFoundError: verify_gates`).
- [ ] **Step 3: Implement `verify_gates.py` and the 6 non-leading prompt templates under `claude-verify/prompts/`**
  Ensure prompt templates treat fenced artifacts strictly as untrusted data (anti-prompt-injection) and demand concrete `verbatim_quote` + `counterexample` per finding.
- [ ] **Step 4: Run tests to verify GREEN pass**
  Run: `python -m unittest discover -s claude-verify/scripts/tests -p "test_verify_gates.py" -v`
  Expected: PASS (0 failures).
- [ ] **Step 5: Commit & Cross-Model Code Review (`/requesting-code-review`)**
  Commit changes, run AGY SDD Task Reviewer + blind `claude -p --model sonnet` review on `BASE_SHA..HEAD_SHA`, and resolve any Critical/Important issues.

---

### Task 3: `/writing-skills` RED Phase — Baseline Pressure Scenarios Without Skills (`Wave 1 — Parallel Track C`)

**Files:**
- Create: `.superpowers/skill-tdd/pressure_scenarios.md` (git-ignored test artifact)
- Create: `.superpowers/skill-tdd/red_baseline_results.md` (git-ignored verbatim baseline record)

**Interfaces:**
- Produces: 4 multi-pressure scenarios (3+ combined pressures each: time + sunk cost + authority + pragmatic shortcut) and verbatim baseline failures/rationalizations from fresh subagents run WITHOUT `claude-delegate` / `claude-verify`:
  1. **Scenario S1 (OAuth `--bare` + CLI argv trap)**: Agent asked under urgent deadline to invoke `claude` headlessly in clean stateless mode with a 40 KB diff prompt.
  2. **Scenario S2 (Framing / Leading-the-Witness bias)**: Agent spent 3 hours designing a complex architecture, senior says "just have Claude quickly rubber-stamp our rationale before 5pm merge".
  3. **Scenario S3 (Phantom-quote blind obedience)**: Blind reviewer flags a "Critical" bug citing a function line that doesn't exist; user says "fix everything Claude found immediately".
  4. **Scenario S4 (Git-repo context leakage)**: Agent runs `claude -p` directly inside a dirty repo containing `CLAUDE.md` and `.env` while verifying a historical commit range.

- [ ] **Step 1: Write the 4 concrete A/B/C/action pressure scenarios in `.superpowers/skill-tdd/pressure_scenarios.md`**
* [ ] **Step 2: Dispatch fresh subagents WITHOUT the skills and capture verbatim choices & rationalizations in `.superpowers/skill-tdd/red_baseline_results.md`**
  Verify RED: confirm which rationalizations occur naturally so Task 6 authors `SKILL.md` directly against observed failures (`superpowers:writing-skills` Iron Law).

---

### Task 4: `claude-delegate` Headless Runner, Session Resume & Parallel Batch (`Wave 2`)

**Files:**
- Create: `claude-delegate/scripts/claude_task.py`
- Create: `claude-delegate/scripts/tests/fake_claude.py`
- Test: `claude-delegate/scripts/tests/test_claude_task.py`
- Test: `claude-delegate/scripts/tests/test_batch_timeout.py`

**Interfaces:**
- Consumes: `claude-delegate/scripts/claude_confine_hook.py` (Task 1).
- Produces: `claude_task.py` CLI (`preflight`, `run`, `resume`, `batch`) with exit codes `0|2|3|4|5`, JSON summary (`status`, `claude_exit_code`, `session_id`, `model`, `models`, `cost_usd`, `workdir`, `changes`, `structured`, `response`, `confinement`, `verify`, `quota`, `timeout`), `ProcRegistry` + `kill_tree()` (`taskkill /PID <pid> /T /F` on Windows / `os.killpg` on POSIX), and cross-platform `build_hook_command()` supporting spaces/parentheses on Windows.

- [ ] **Step 1: Write `fake_claude.py` stand-in and failing unit tests in `test_claude_task.py` & `test_batch_timeout.py`**
  Include Review Focus #3 (literal `"429"` / `"rate_limit_error"` in normal assistant output does NOT trigger quota error), Review Focus #4 (Windows workdir/python paths containing spaces and `(` execute `PreToolUse` hook cleanly), UTF-8 `stdin` > 40,000 chars without `WinError 206`, `CLAUDECODE` env var scrubbing, `--bare` absent by default, `--read-only` + `--read-only-dir`, `--inlined` counting `inlined_denied_count` separately from `denied_count`, `confinement.enabled` false when hook never logs a tool step, `timeout-partial` + `kill_tree()`, `--keep-session` + `resume`, and parallel `batch` (`ok` / `partial` / `failed`).
- [ ] **Step 2: Run tests to verify RED failure**
  Run: `python -m unittest discover -s claude-delegate/scripts/tests -v`
  Expected: `test_claude_confine` PASS, `test_claude_task` & `test_batch_timeout` FAIL (`claude_task` missing).
- [ ] **Step 3: Implement `claude-delegate/scripts/claude_task.py`**
  Implement `preflight`, `cmd_run`, `cmd_resume`, `cmd_batch`, `Confinement` (`<meta_dir>/hook_settings.json` passed via `--settings`), `stream-json` live event reader + `result` extractor, SHA-256 `snapshot()`/`diff_snapshots()`, and `--verify` / `--collect`.
- [ ] **Step 4: Run tests to verify GREEN pass**
  Run: `python -m unittest discover -s claude-delegate/scripts/tests -v`
  Expected: ALL PASS (0 failures).
- [ ] **Step 5: Commit & Cross-Model Code Review (`/requesting-code-review`)**
  Commit changes, run AGY SDD Task Reviewer + blind `claude -p --model opus` code review on `BASE_SHA..HEAD_SHA`, and resolve any Critical/Important findings.

---

### Task 5: `claude-verify` Orchestrator, Clean Git Snapshot, Multi-Lens, Arbiter & Scoped Re-Verify (`Wave 2`)

**Files:**
- Create: `claude-verify/scripts/claude_verify.py`
- Test: `claude-verify/scripts/tests/test_claude_verify.py`

**Interfaces:**
- Consumes: `claude-delegate/scripts/claude_task.py` (Task 4), `claude-verify/scripts/verify_gates.py` & `prompts/*.md` (Task 2).
- Produces: `claude_verify.py` CLI (`preflight`, `run`, `reverify`, `status`) with exit codes `0|2|3|4|5`, out-of-repo isolated job dirs (`%LOCALAPPDATA%\claude-verify\jobs\<id>`, `GIT_REPO_ESCAPE` guard), `extract_git_snapshot(repo: Path, base: str, head: str, dst: Path) -> dict`, single-pass blind review, `--lenses` parallel batch + dedup, `--arbiter` 2-stage blind adjudication (`family(arbiter) != family(challenger)`), `reverify --job <id>` (`--max-rounds 3`), and `<out>.md` + `<out>.json` output generation.

- [ ] **Step 1: Write failing unit & integration tests in `claude-verify/scripts/tests/test_claude_verify.py` (using `CLAUDE_BIN=fake_claude.py`)**
  Include Review Focus #5 (`--git-range BASE..HEAD` on a repo with dirty uncommitted edits and a poisoned `<repo>/CLAUDE.md` + `.env` extracts clean `HEAD` files only and strips `CLAUDE.md`/`.env`), `GIT_REPO_ESCAPE` rejection, `IDENTICAL_ARTIFACT_AND_SPEC` exit `5`, `diff`/`plan`/`doc`/`custom` runs, `unverified_quote` findings isolated from blocking verdict (exit `0` when only unverified quotes exist, exit `2` when verified `critical`/`important` findings exist), `--lenses spec,counterexample,security` parallel batch merge, `--arbiter opus` rejecting same-family challenger (`--model opus --arbiter opus` -> exit `5`) and filtering dismissed findings when `sonnet` -> `opus`, and `reverify` tracking `resolved`/`still_open` and refusing round 4 without `--force`.
- [ ] **Step 2: Run tests to verify RED failure**
  Run: `python -m unittest discover -s claude-verify/scripts/tests -v`
  Expected: `test_verify_gates` PASS, `test_claude_verify` FAIL (`claude_verify` missing).
- [ ] **Step 3: Implement `claude-verify/scripts/claude_verify.py`**
* [ ] **Step 4: Run tests to verify GREEN pass**
  Run: `python -m unittest discover -s claude-verify/scripts/tests -v`
  Expected: ALL PASS (0 failures).
- [ ] **Step 5: Commit & Dogfood Cross-Model Code Review (`/requesting-code-review`)**
  Commit changes, run AGY SDD Task Reviewer AND run **live `claude_verify.py run --kind diff --git-range <BASE>..<HEAD> --spec <task-5-brief> --model opus`** to dogfood our new cross-verifier against real Claude Opus! Fix all verified Critical/Important findings.

---

### Task 6: Author `SKILL.md` & `README.md` via `/writing-skills` TDD (GREEN & REFACTOR) (`Wave 3`)

**Files:**
- Create: `claude-delegate/SKILL.md`
- Create: `claude-delegate/README.md`
- Create: `claude-verify/SKILL.md`
- Create: `claude-verify/README.md`
- Modify: `README.md` (root `agy-skills/README.md`: add `claude-delegate` & `claude-verify` documentation and install commands)

**Interfaces:**
- Consumes: `.superpowers/skill-tdd/red_baseline_results.md` (Task 3), `claude_task.py` (Task 4), `claude_verify.py` (Task 5).
- Produces: Bulletproof `SKILL.md` files (frontmatter `name` + third-person `"Use when..."` `description` with zero workflow summary, concise token budget, positive command recipes, rationalization counter-table built from Task 3 RED transcripts, red flags, and how to act on `unverified_quote` / `escape_denied` per `receiving-code-review`) + human setup/usage `README.md`s.

- [ ] **Step 1: Draft `claude-delegate/SKILL.md`, `claude-verify/SKILL.md`, both `README.md`s, and update root `README.md`**
  Verify word counts and YAML frontmatter rules (`description` < 500 chars, starts with `"Use when..."`, no workflow summary).
- [ ] **Step 2: Run `/writing-skills` VERIFY GREEN pressure tests with fresh subagents**
  Re-run Scenarios S1-S4 from Task 3 WITH `claude-delegate/SKILL.md` and `claude-verify/SKILL.md` loaded. Confirm 100% compliance under pressure.
- [ ] **Step 3: Run `/writing-skills` REFACTOR loop if any new rationalization appears**
  Plug any loophole with explicit counter + rationalization table row and re-test until all 4 scenarios pass cleanly.
- [ ] **Step 4: Commit & Cross-Model Doc Verification (`/requesting-code-review`)**
  Commit docs, run AGY SDD Task Reviewer + live `claude_verify.py run --kind doc` (`--model opus`) against the new `SKILL.md`s and design spec, and fix any verified gaps.

---

### Task 7: Final Live E2E Verification (`/verification-before-completion`), Local Install & GitHub Upload (`Wave 4`)

**Files:**
- Sync to local AGY config: `C:\Users\SSAFY\.gemini\config\skills\claude-delegate` & `C:\Users\SSAFY\.gemini\config\skills\claude-verify`

**Interfaces:**
- Consumes: Completed `feat/claude-cross-verify` branch (Tasks 0-6).
- Produces: Freshly verified test suites, live E2E verification artifacts, SHA-256 parity-verified local global skills installation, whole-branch cross-model review sign-off, and pushed/merged `main` on `https://github.com/cannedJean/agy-skills.git` with clean worktree teardown (`finishing-a-development-branch`).

- [ ] **Step 1: Run complete automated unit test suites (`verification-before-completion`)**
  Run:
  `python -m unittest discover -s claude-delegate/scripts/tests -v`
  `python -m unittest discover -s claude-verify/scripts/tests -v`
  Expected: Exit `0`, 0 failures, 0 skipped, pristine output.
- [ ] **Step 2: Run live E2E preflight & whole-branch cross-verification against real Claude CLI (`v2.1.327`, Max OAuth)**
  1. `python claude-delegate/scripts/claude_task.py preflight --probe-hook` -> Expect `ok: true`, `confinement_probe.enabled: true`.
  2. `python claude-verify/scripts/claude_verify.py preflight` -> Expect `ok: true`.
  3. Whole-branch cross-model review: `python claude-verify/scripts/claude_verify.py run --kind diff --repo . --git-range main..HEAD --spec docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md --lenses spec,counterexample,security --arbiter opus --out .superpowers/sdd/final_cross_verify.md`. Fix any verified Critical/Important findings and re-run `reverify` if needed!
- [ ] **Step 3: Sync skills to `~/.gemini/config/skills/` and verify byte-for-byte SHA-256 parity**
  Copy `claude-delegate` and `claude-verify` into `C:\Users\SSAFY\.gemini\config\skills\` and run a parity verification script confirming 100% hash match across all files.
- [ ] **Step 4: Merge/Push to `https://github.com/cannedJean/agy-skills.git` & clean up temporary `.superpowers/` scratch**
  Fast-forward merge `feat/claude-cross-verify` into `main` (after clean `git status`), `git push origin main`, verify remote HEAD via `gh api repos/cannedJean/agy-skills/commits/HEAD`, and clean up the worktree cleanly.
