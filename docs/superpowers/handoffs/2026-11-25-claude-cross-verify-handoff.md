# Session Handoff: `claude-delegate` & `claude-verify` (`agy-skills`)

- **작성 시각**: 2026-11-25 13:24 KST
- **대상 저장소**: `https://github.com/cannedJean/agy-skills.git`
- **체크포인트**: 설계(`/brainstorming` + Builder Check) 및 팀워크/SDD 구현 계획(`/writing-plans`) 확정 후 격리된 Git Worktree(`feat/claude-cross-verify`)에 커밋·업로드 완료 (구현 착수 직전 상태)

---

## 1. 현재 진행 상태 요약 (Current Checkpoint)

### 완료된 항목
1. **레퍼런스 역공학 분석 (`cannedJean/claude-skills`)**:
   - `agy-delegate`(`agy_task.py`, `confine_hook.py`) 및 `agy-outsource`(`outsource.py`, `roles.py`, `isolation.md`)를 포함한 기존 스킬 구조를 분석하여 2계층 실행/검증 구조 및 이종 모델 블라인드 교차검증 원칙 도출.
2. **환경 확인 및 근본 원인 분석 (`/systematic-debugging`)**:
   - 로컬 `claude` CLI(`v2.1.327`, `C:\Users\SSAFY\.local\bin\claude.exe`)가 API 키가 아닌 `claude.ai` `max_5x` OAuth 로그인 상태임을 확인.
   - `agy -> claude` 역이식 시 발생하는 7대 함정 규명 (`--bare` OAuth 실패, `--permission-prompts none` 누락, Claude `PreToolUse` `--settings` JSON 및 Windows 훅 쉘 차이, `stdin` UTF-8 전송을 통한 Windows 32,767자 `WinError 206` 회피, `stream-json --verbose` + `ProcRegistry` 고아 프로세스 차단, `git archive HEAD`를 통한 `CLAUDE.md`/Dirty tree 오염 차단, 범용 아티팩트 지원).
3. **아키텍처 확정 (`/brainstorming` + Builder Check)**:
   - **대안 1 (`claude-delegate` + `claude-verify` 2계층 구조)** 확정.
   - 독립 빌더 리뷰(`Design Spec Builder Reviewer`)를 거쳐 3대 경계 조건(`--repo` 스냅샷 분리, 인라인 `--criteria` 제거 및 `--spec` 단일화, `unconfined`=exit 3 vs `escape_denied`=경고 플래그)을 설계서에 반영.
4. **SDD/팀워크 계획 작성 (`/writing-plans`) & 격리 워크트리 업로드 (`/using-git-worktrees`)**:
   - 이종 모델 `/requesting-code-review`(AGY SDD Task Reviewer + `claude -p` 블라인드 코드 리뷰)가 모든 구현 태스크(Tasks 1~6) 및 최종 통합 리뷰(Task 7)에 게이트로 포함된 계획서 작성 및 GitHub 푸시 완료.

### 남은 작업 (Next Session)
- **Task 0 Step 3**: `claude -p --restricted --permission-prompts none --output-format stream-json --verbose --json-schema ...` 1회 스모크 프로브 실행 (실제 JSON 이벤트 스키마 확정).
- **Wave 1 (병렬 3트랙)**:
  - **Task 1**: `claude-delegate/scripts/claude_confine_hook.py` + 단위테스트
  - **Task 2**: `claude-verify/scripts/verify_gates.py` + `prompts/*.md` + 단위테스트
  - **Task 3**: `/writing-skills` RED 베이스라인 압박 테스트 (`.superpowers/skill-tdd/`)
- **Wave 2**:
  - **Task 4**: `claude-delegate/scripts/claude_task.py` (`preflight`, `run`, `resume`, `batch`) + 테스트 + Opus 교차 리뷰
  - **Task 5**: `claude-verify/scripts/claude_verify.py` (`preflight`, `run`, `reverify`, `status`) + 테스트 + Dogfood Opus 교차 리뷰
- **Wave 3**: **Task 6** (`SKILL.md` / `README.md` 작성, VERIFY GREEN/REFACTOR 압박 테스트, 문서 교차 검증)
- **Wave 4**: **Task 7** (전체 테스트, 라이브 E2E 검증, `~/.gemini/config/skills/` SHA-256 패리티 동기화, `main` 머지·푸시 및 워크트리 정리)

---

## 2. 작업 경로 및 Git 좌표 (Workspace & Git Coordinates)

- **기본 저장소 (`main`)**: `C:\Users\SSAFY\.gemini\antigravity\scratch\repos\agy-skills`
  - `.gitignore`에 `.worktrees/` 및 `.superpowers/` 추가 커밋 반영됨.
- **활성 작업 워크트리 (`feat/claude-cross-verify`)**:
  `C:\Users\SSAFY\.gemini\antigravity\scratch\repos\agy-skills\.worktrees\claude-cross-verify`
- **참조 저장소 (`claude-skills`)**:
  - 로컬 스킬 설치본: `C:\Users\SSAFY\.claude\skills`
  - 로컬 클론: `C:\Users\SSAFY\.gemini\antigravity\scratch\repos\claude-skills`
- **워크트리 내 핵심 문서 경로**:
  - 설계서(Spec): `docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md`
  - 구현 계획서(Plan): `docs/superpowers/plans/2026-11-25-claude-cross-verify-plan.md`
  - 핸드오프(Handoff): `docs/superpowers/handoffs/2026-11-25-claude-cross-verify-handoff.md`

---

## 3. 절대 잊으면 안 되는 핵심 기술 제약 (Critical Guardrails)

1. **`claude --bare` 기본 사용 금지**: OAuth 키체인을 차단하여 `claude.ai` Max 로그인 환경에서 인증 실패한다. 반드시 `--restricted --permission-prompts none --strict-mcp-config --disable-slash-commands`, `--no-session-persistence`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `CLAUDECODE*` env 제거 조합을 사용한다.
2. **UTF-8 `stdin` 전송 & `cp949` 방어**: 프롬프트는 절대 argv에 태우지 않고 UTF-8 `stdin`으로 파이프하며, 모든 Python 스크립트는 시작 직후 `stdout`/`stderr`를 `encoding="utf-8", errors="replace"`로 재설정한다.
3. **Claude `PreToolUse` 훅 스키마 및 Windows 쉘 대응**: `--settings` JSON은 `{"hooks": {"PreToolUse": [...]}}` 래퍼 형식을 따르고, 출력은 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": ...}}`를 사용한다. 경로에 공백·괄호가 포함된 Windows 환경에서 Git Bash(`"shell": "bash"`) 및 `.cmd`/`"powershell"` 폴백이 정상 실행되는지 반드시 테스트한다.
4. **이종 모델 코드 리뷰(`/requesting-code-review`) 필수**: Gemini/AGY 서브에이전트가 작성한 모든 태스크 diff는 AGY Task Reviewer와 Anthropic `claude -p` 블라인드 리뷰어 양쪽을 통과해야 완료 처리한다.
5. **스킬 TDD Iron Law (`/writing-skills`)**: `SKILL.md`는 반드시 Task 3에서 스킬 없이 압박 시나리오를 실행해 실패/합리화 원문을 기록(RED)한 뒤 Task 6에서 작성하고 GREEN/REFACTOR를 검증한다.
6. **격리 스냅샷 및 인용 게이트**: `--git-range` 검증 시 워킹 트리를 직접 마운트하지 않고 `git archive HEAD`로 `<job_dir>/context/`에 추출하며 `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/`.agents/**`/`.claude/**`/`.superpowers/**`/`docs/superpowers/**`/`.env*`를 제거한다. `unverified_quote` 지적은 리포트에서 분리하며 `exit 2`를 유발하지 않는다.

---

## 4. 다음 세션 즉시 재개용 프롬프트 (Copy-Paste Resume Prompt)

```text
/using-superpowers
기존 작업을 이어서 구현까지 완료하려고 해.

- 작업 워크트리: C:\Users\SSAFY\.gemini\antigravity\scratch\repos\agy-skills\.worktrees\claude-cross-verify (브랜치: feat/claude-cross-verify)
- 핸드오프: docs/superpowers/handoffs/2026-11-25-claude-cross-verify-handoff.md
- 설계서: docs/superpowers/specs/2026-11-25-claude-cross-verify-design.md
- 구현 계획서: docs/superpowers/plans/2026-11-25-claude-cross-verify-plan.md

위 설계서, 구현 계획서, 핸드오프를 먼저 읽고 계획을 승인한 상태로 진행해 줘.
Task 0 Step 3(`claude -p` 스키마+스트림 1회 프로브)부터 실행한 뒤, /teamwork 및 /subagent-driven-development 로 Wave 1~4를 병렬 구현하고, 각 태스크마다 /requesting-code-review (이종 모델 claude -p 교차검증 포함)를 통과시켜 줘.
마지막에 /verification-before-completion 으로 전체 테스트와 실전 E2E 검증을 마친 뒤 ~/.gemini/config/skills/ 에 동기화하고, C:\Users\SSAFY\.gemini\antigravity\scratch\repos\agy-skills main 브랜치에 병합·푸시한 다음 워크트리를 정리해 줘.
```
