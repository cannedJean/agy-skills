# Design Spec: `claude-delegate` & `claude-verify` for Antigravity (`agy-skills`)

## 1. Intent and Why

Antigravity(`agy`, Gemini / Argon / Carbon 계열)가 코드 diff, 구현 계획서, 아키텍처 설계서, 리서치·분석 문서를 생성한 뒤 동일 벤더 모델이나 동일 세션 서브에이전트로 자기 검증을 수행하면 두 가지 구조적 한계가 발생한다.

1. **동일 모델 패밀리 편향(Shared Prior / Self-Preference)**: 작성 모델과 같은 계열의 검증자는 동일한 맹점과 가정에 빠지기 쉽다.
2. **세션 프레이밍 편향(Session Framing Bias)**: 작성 과정의 변명·의도·대화 히스토리가 함께 전달되면 검증자가 작성자의 합리화를 따라가며 결함이나 반례를 놓친다.

이를 해결하기 위해 기존 `cannedJean/claude-skills`의 `agy-delegate` + `agy-outsource` 이종 모델 교차검증 아키텍처를 AGY 측으로 역이식·일반화한 2계층 범용 스킬 세트(**`claude-delegate`** + **`claude-verify`**)를 `https://github.com/cannedJean/agy-skills.git`에 구축하고 `~/.gemini/config/skills/`에 설치한다.

- **`claude-delegate` (Layer 1 — 저수준 격리 실행기)**: OAuth Max 구독과 호환되는 무상태 헤드리스 `claude -p` 실행, UTF-8 `stdin` 프롬프트 스트리밍, `PreToolUse` 경로/도구 격리 훅, `stream-json` 실시간 관측, 프로세스 트리 타임아웃 정리, `resume` 및 병렬 `batch`를 제공한다.
- **`claude-verify` (Layer 2 — 블라인드 교차검증 엔진)**: `claude-delegate` 위에서 AGY 산출물(`diff` | `plan` | `doc` | `custom`)을 세션 히스토리나 자기 합리화 없이 블라인드 패키징하여 Anthropic(`sonnet` / `opus`) 모델의 반례 탐색 및 스펙 대조를 수행하고, 결정론적 사후 게이트(`model_gate`, `confinement_gate`, `grounding_gate`)로 결과를 검증한다.

---

## 2. Reference Architecture Analysis (`cannedJean/claude-skills`)

`cannedJean/claude-skills`는 저수준 CLI 격리 실행기와 고수준 교차검증 오케스트레이터를 엄격히 분리한다.

- **`agy-delegate` (`scripts/agy_task.py`, `scripts/confine_hook.py`)**:
  - `preflight`, `run`, `resume`, `batch` 4단 인터페이스를 제공한다.
  - 작업 디렉터리 스냅샷(`sha256` diff)으로 실제 변경 파일만 확정하고, `PreToolUse` 훅으로 외부 경로·하드링크(`st_nlink > 1`)·경로 우회(`.. `, `...`)·셸/브라우저/MCP·헤드리스 질문(`ask_question`)·인라인 파일 재열람(`--inlined`)을 차단한다.
  - 이벤트 스트림의 도구 호출 수와 훅 로그 수를 비교해 `confinement.enabled`를 검증한다.
- **`agy-outsource` (`scripts/outsource.py`, `scripts/roles.py`, `references/isolation.md`)**:
  - 작성자(`contractor`), 테스트 작성자(`lead`), 감사자/심판(`auditor`/`referee`)의 모델 패밀리 분리를 강제하고 CLI 응답의 `modelUsage`로 실제 실행 모델을 역검증한다.
  - `.git` 저장소 바깥의 독립 잡 디렉터리에서 실행해 컨텍스트 누수를 원천 차단하고, 스크립트가 직접 비편향 프롬프트를 조립한다.

---

## 3. Root-Cause Asymmetries & Fixes (`systematic-debugging`)

기존 `roles.py:run_claude()` 및 `agy-delegate` 패턴을 `agy -> claude` 방향으로 그대로 적용할 때 발생하는 7가지 근본 원인과 해결책은 다음과 같다.

| # | 근본 원인 (Root Cause) | 해결 설계 (Fix) |
|---|---|---|
| 1 | **`--bare` 플래그와 `claude.ai` OAuth 충돌**: 로컬 환경은 `claude.ai` Max OAuth 로그인(`loggedIn: true`) 상태이며, `--bare`는 OAuth/키체인 읽기를 비활성화하고 `ANTHROPIC_API_KEY`만 요구해 즉시 실패한다. | `--bare`를 기본값에서 절대 사용하지 않는다. 대신 `--restricted --permission-prompts none --strict-mcp-config --disable-slash-commands`, `--no-session-persistence`(단 `--keep-session` 제외), `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `CLAUDECODE*` 환경변수 제거로 무상태 격리를 구현한다. |
| 2 | **헤드리스 권한 프롬프트 블로킹**: `--permission-prompts` 기본값 `host`는 비대화형 모드에서 모호한 거절·대기를 유발한다. | 항상 `--permission-prompts none`을 명시하여 승인 프롬프트 없이 즉시 거부·종료되도록 고정한다. |
| 3 | **`--restricted` 경계 한계 및 훅 스키마 차이**: `--restricted`만으로는 하드링크, Windows ADS(`:`), 보호 파일(`.env*`, `CLAUDE.md`), `--inlined` 재열람 차단이 불가능하며, Claude 훅 JSON 스키마(`tool_name`/`tool_input` → `hookSpecificOutput.permissionDecision`)가 `agy`와 다르다. | `--settings <meta_dir>/hook_settings.json`으로 전용 `claude_confine_hook.py`를 주입한다. `{"hooks": {"PreToolUse": [...]}}` 구조를 사용하고, 오류 시 fail-closed(`permissionDecision: "deny"`)로 동작하며, Windows에서는 Git Bash 존재 시 `"shell": "bash"` + forward-slash 인용 경로, 미존재 시 공백/괄호 안전 `.cmd` 래퍼 + `"powershell": "& ..."` 폴백을 구성한다. |
| 4 | **Windows 32,767자 명령줄 한계(`WinError 206`) 및 콘솔 인코딩**: `agy -p`는 argv로 프롬프트를 넘겨 30KB 제한이 있었고, Windows `cp949` 콘솔은 유니코드 출력 시 크래시할 수 있다. | 프롬프트 본문은 항상 UTF-8 `stdin` 파이프(`input=prompt.encode("utf-8")`)로 전달하고, JSON 스키마 및 시스템 프롬프트 추가분은 임시 파일(`--json-schema`, `--append-system-prompt-file`)로 전달해 argv 한계를 없앤다. 모든 Python 스크립트는 시작 시 `stdout`/`stderr`를 UTF-8(`errors="replace"`)로 재설정한다. |
| 5 | **단일 JSON 버퍼링의 관측성·복구·Effort 부재**: 기존 `run_claude()`는 완료까지 무응답이며 `out.index("{")` 파싱이 취약하고 `--effort`·`--fallback-model`·프로세스 트리 강제 종료가 없다. | `--output-format stream-json --verbose`로 실시간 진행 상황을 stderr로 중계하고 최종 `result` 이벤트를 추출한다. `--effort low\|medium\|high\|xhigh\|max` 및 `--fallback-model`을 지원하며, `ProcRegistry` + `kill_tree()`(`taskkill /PID <pid> /T /F` / `os.killpg`)로 타임아웃/Ctrl+C 시 고아 프로세스를 완전히 정리하고 `--keep-session` + `resume`으로 이어한다. |
| 6 | **컨텍스트 누수(Dirty Tree & `CLAUDE.md` 자동 로드)**: `--add-dir <repo>`를 직접 마운트하면 `<repo>/CLAUDE.md`가 자동 로드되어 블라인드 검증이 깨지고, `--git-range BASE..HEAD`와 미커밋 작업 트리의 줄 번호가 어긋난다. | `--repo DIR`은 호스트 측 `git diff` / `git archive` 추출 전용으로만 사용한다. `--git-range` 검증 시 `git archive HEAD`로 `<job_dir>/context/`에 깨끗한 스냅샷을 풀되 `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.agents/**`, `.claude/**`, `.superpowers/**`, `docs/superpowers/**`, `.env*`, `*.pem`, `*.key`를 자동 스트립한다. 외부 `--context-dir` 마운트 시에도 훅이 해당 파일군을 차단한다. |
| 7 | **도메인 범용성 한계**: `agy-outsource`는 Python AST·단위테스트에 묶여 있어 계획서·설계서·리서치·다언어 diff 검증에 쓸 수 없다. | `diff` | `plan` | `doc` | `custom` 4가지 범용 검증 종류와 인용구(`verbatim_quote`) 기반 결정론적 사후 게이트로 일반화한다. |

---

## 4. Goals, Non-Goals, and Anti-Goals

### Goals
- **OAuth & API-Key 양립성**: `claude.ai` Max OAuth(`claude auth status` → `loggedIn: true`)와 `ANTHROPIC_API_KEY` 모두에서 별도 설정 없이 즉시 동작한다.
- **무상태 블라인드 패키징**: `claude-verify` 스크립트가 `--artifact` / `--git-range`와 파일 기반 `--spec`만으로 프롬프트를 생성한다. 인라인 `--criteria TEXT` 같은 자유 서술/변명 플래그는 제공하지 않는다.
- **편향 차단 입력 검증**:
  - `IDENTICAL_ARTIFACT_AND_SPEC` (exit `5`): 산출물과 스펙 파일 내용이 동일하면 거부한다.
  - `PREJUDGING_DIRECTIVE_RE`: 스펙 내 `"do not flag"`, `"ignore"`, `"at most minor"`, `"의도된 것이니 무시"` 등 사전 면죄 지시어를 탐지해 `framing_warnings`에 기록한다.
  - 충돌 방지 백틱 펜스(`fenced()`)로 비신뢰 산출물을 감싸 프롬프트 인젝션을 데이터로 격리한다.
- **3대 결정론적 사후 게이트**:
  1. `model_gate`: `rc == 0`, `is_error == False`, `modelUsage` 기준 Anthropic 계열(`opus`/`sonnet`/`haiku`, `gemini` 금지) 및 요청 모델 패밀리 일치 여부를 검증한다. `--arbiter` 사용 시 `family(arbiter) != family(challenger)`를 강제한다.
  2. `confinement_gate`: 도구 호출(`tool_steps > 0`) 대비 훅 로그가 누락된 `unconfined`(`confinement.enabled == False`)는 **하드 실패(exit `3`)**로 처리한다. 훅이 정상 동작하며 외부/비밀 파일 접근을 막아낸 `escape_denied`(`denied_count > 0`)는 검증 결과를 유지하되 `flags: ["escape_denied"]`로 보고한다.
  3. `grounding_gate`: 모든 지적(`finding`)에 필수 필드(`id`, `severity`, `category`, `location`, `verbatim_quote`, `counterexample`, `why_it_matters`, `suggested_fix`)를 강제하고, `verbatim_quote`가 실제 산출물·diff·컨텍스트 파일에 존재하는지 원문 일치(`verified`) 및 CRLF/공백 정규화 일치(`normalized_match`)로 대조한다. 미확인 인용(`unverified_quote`)은 `report.md` 별도 섹션으로 격리하며 최종 `exit 2` 판정을 유발하지 않는다.
- **다각도 병렬(`--lenses`), 2단 심판(`--arbiter`), 범위 한정 재검증(`reverify`)**:
  - `--lenses` (`spec,counterexample,security,architecture,edge_cases` 중 CSV) 지정 시 `claude-delegate batch`로 병렬 실행 후 위치+인용구 기반 결정론적 중복 제거(`deduplicate_findings`)를 수행한다.
  - `--arbiter <model>` 지정 시 1차 모델명을 제거한 후보 지적 목록만으로 2차 블라인드 심판(`upheld | downgraded | dismissed`)을 실행한다.
  - `reverify --job <job_id>`는 직전 미해결 `critical`/`important` 항목과 신규 diff의 회귀 여부만 점검하며 기본 최대 3라운드(`--max-rounds 3`, 초과 시 `--force` 없으면 exit `5`)로 제한한다.

### Non-Goals
- Python 단위테스트 기반 코드 외주(`DELIVERY.json`, DPAPI 히든테스트 봉인) — `agy-outsource` 영역으로 제외한다.
- `claude-verify`에 의한 사용자 코드 자동 수정 — 검증은 엄격히 읽기 전용이다.
- 자동 로그인 브라우저 조작 — `preflight` 실패 시 `claude auth login` 안내만 출력한다.

### Anti-Goals
- 작성 세션의 대화 히스토리·사고 과정·자기 합리화 문구를 `claude-verify`에 전달하는 행위.
- 타임아웃 또는 Ctrl+C 시 고아 `claude` 프로세스를 방치하는 행위.
- Windows `cp949` 콘솔 인코딩 오류로 JSON 출력을 손실하는 행위.

---

## 5. Approaches Considered

1. **Approach 1 — 2계층 모듈형 (`claude-delegate` + `claude-verify`) [선택]**: `claude-skills`의 `agy-delegate` + 상위 스킬 구조와 대칭을 이룬다. `SKILL.md` 트리거가 명확하고 토큰 효율이 높으며, 향후 다른 AGY→Claude 스킬이 `claude-delegate`를 재사용할 수 있다.
2. **Approach 2 — 단일 통합형 (`claude-verify` 단독) [기각]**: 설치는 단순하나 일반 CLI 위임과 교차검증 규율이 한 스킬에 섞여 에이전트 스킬 선택 정밀도가 저하되고 재사용성이 떨어진다.
3. **Approach 3 — 상시 2단 적대 파이프라인 (`Red-Team -> Arbiter` 고정) [선택 옵션으로 흡수]**: 모든 경량 검증에서도 쿼터와 시간이 2배 소모되므로, Approach 1 내부의 선택 플래그(`--lenses`, `--arbiter`)로 통합했다.

---

## 6. Constraints

- **런타임**: Python 3.10+ 표준 라이브러리만 사용(외부 `pip` 의존성 0개).
- **운영체제**: Windows 11 우선 실전 검증 + macOS/Linux 이식성 유지.
- **저장소 및 설치 경로**: `https://github.com/cannedJean/agy-skills.git`의 `.worktrees/claude-cross-verify` (`feat/claude-cross-verify`)에서 개발하고, 완료 후 `~/.gemini/config/skills/claude-delegate` 및 `~/.gemini/config/skills/claude-verify`로 동기화한다.
- **스킬 작성 규율**: `superpowers:writing-skills` TDD(RED 베이스라인 압박 테스트 → GREEN 스킬 → REFACTOR 합리화 차단 테이블) 준수. `SKILL.md` `description`은 3인칭 `"Use when..."`으로 시작하며 500자 이하로 유지하고 워크플로 요약을 넣지 않는다.
- **교차 모델 코드 리뷰 규율**: 구현 단계에서 AGY(Gemini) 서브에이전트가 작성한 모든 태스크 diff는 AGY SDD Task Reviewer와 Anthropic `claude -p` 블라인드 코드 리뷰어(`requesting-code-review`)를 모두 통과해야 한다.

---

## 7. CLI & File Specifications

### Skill 1: `claude-delegate/`
- `SKILL.md`, `README.md`
- `scripts/claude_task.py`
  - **Exit codes**: `0` ok, `2` non-success / verify-failed / timeout-partial / batch-partial, `3` claude runtime or quota error, `4` preflight failure, `5` bad arguments.
  - **Global options**: `--claude-bin PATH`, `--model SLUG` (`sonnet`, `opus`, `haiku`), `--effort low|medium|high|xhigh|max`, `--fallback-model SLUG`.
  - **Subcommands**:
    - `preflight [--workdir DIR] [--probe-hook]`
    - `run -t TEXT | -f FILE [-w WORKDIR] [-i INPUT ...] [--read-only] [--read-only-dir DIR ...] [--tools TOOLS] [--timeout auto|DURATION] [--max-turns N] [--verify CMD] [--verify-timeout SEC] [--collect DIR] [--inlined REL ...] [--bare] [--no-schema] [--schema-file FILE] [--append-system-prompt-file FILE] [--keep-session] [--allow-bash] [--no-confine] [--dry-run]`
    - `resume SESSION_ID -t TEXT | -f FILE [-w WORKDIR] [--timeout auto|DURATION] [--max-turns N] [--read-only] [--read-only-dir DIR ...]`
    - `batch -m MANIFEST.json [-w BATCH_DIR] [--parallel 3] [--stagger 3.0]`
  - **Observability & Schema**: `claude -p --output-format stream-json --verbose` 기반 실시간 진행 출력 및 최종 `result` JSON 추출(`--json-schema`와 `stream-json --verbose` 동시 호환 여부는 Task 0 Step 3 프로브로 확정, 필요 시 자동 모드 분기 지원).
- `scripts/claude_confine_hook.py`
  - `<meta_dir>/hook_settings.json`을 `--settings`로 주입: `{"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "...", "timeout": 30}]}]}}`
  - `stdin`의 `tool_name`, `tool_input`, `cwd`를 검사해 `CLAUDE_CONFINE_LOG`에 기록하고, 차단 시 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}` 출력, 허용 위임 시 `{}` 출력.
  - 차단 대상: 범위 외 경로, 하드링크(`st_nlink > 1`), Windows UNC/디바이스/ADS(`:`), 우회 경로(`.. `, `...`), 민감 파일(`.env`, `.env.*`, `*.pem`, `*.key`, `*credentials*`), 에이전트/하네스 메타데이터(`.git`, `.agents`, `.claude`, `.superpowers`, `docs/superpowers`, `.claude_task`, `brain`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`), `AskUserQuestion`, 웹/MCP/셸 도구(단 `--allow-bash` 제외), `--inlined` 파일 재열람, `--read-only` / `--read-only-dir` 쓰기 시도.

### Skill 2: `claude-verify/`
- `SKILL.md`, `README.md`
- `prompts/` (`verify_diff.md`, `verify_plan.md`, `verify_doc.md`, `verify_custom.md`, `arbiter.md`, `reverify.md`)
- `scripts/verify_gates.py`: `FINDING_SCHEMA`, `VERIFY_OUTPUT_SCHEMA`, `ARBITER_OUTPUT_SCHEMA`, `REVERIFY_OUTPUT_SCHEMA`, `fenced()`, `validate_inputs()`, `family()`, `model_gate()`, `confinement_gate()`, `grounding_gate()`, `deduplicate_findings()`.
- `scripts/claude_verify.py`
  - **Exit codes**: `0` pass (검증된 `critical`/`important` 미존재), `2` 검증된 `critical` 또는 `important` 지적 존재 (`reverify` 미해결 포함), `3` claude 런타임/쿼터 오류 또는 `unconfined`, `4` preflight/구버전 `claude-delegate`, `5` 잘못된 인자 / `GIT_REPO_ESCAPE` / `IDENTICAL_ARTIFACT_AND_SPEC` / `--max-rounds` 초과.
  - **Isolated jobs root**: `%LOCALAPPDATA%\claude-verify\jobs\<job_id>` (Windows) 또는 `~/.cache/claude-verify/jobs/<job_id>` (POSIX), `CLAUDE_VERIFY_JOBS`로 재정의 가능. `.git` 트리 내부 경로 거부.
  - **Subcommands**:
    - `preflight`
    - `run --kind diff|plan|doc|custom [--job JOB_ID] [--artifact PATH ...] [--git-range BASE..HEAD] [--repo DIR] [--spec PATH] [--context-dir DIR ...] [--model sonnet|opus] [--effort low|medium|high|xhigh|max] [--lenses CSV] [--arbiter MODEL] [--timeout DURATION] [--out REPORT_MD]`
    - `reverify --job JOB_ID [--artifact PATH ...] [--git-range BASE..HEAD] [--repo DIR] [--model sonnet|opus] [--max-rounds 3] [--force] [--out REPORT_MD]`
    - `status --job JOB_ID`
  - **`FINDING_SCHEMA` 필수 필드**: `id`, `severity` (`critical|important|minor`), `category`, `location` (`file`, optional `line_start`, `line_end`, `section`), `verbatim_quote`, `counterexample`, `why_it_matters`, `suggested_fix`.
