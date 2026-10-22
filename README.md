# AGY Skills (`agy-skills`)

Google Antigravity (`agy`) 에이전트를 위한 커스텀 스킬 모음 저장소입니다.

---

## 포함된 스킬 목록

### 1. [`local-gemini-deep-research`](./local-gemini-deep-research)
API 키나 종량제 과금 없이, Windows에 로컬 설치된 공식 **Google Gemini 데스크톱 앱(`Gemini.exe`)**의 로그인 세션을 그대로 활용하여 **Gemini Deep Research(심층 리서치)**를 백그라운드에서 실행하고 마크다운 보고서 및 참고 출처를 추출하는 스킬입니다.

* **핵심 특징**
  * **무결성 보존 ASAR 패치 (`patch_gemini_app.py`)**: `app.asar` 원본 바이트 길이와 헤더 SHA256 해시를 유지하면서 로컬 CDP 포트(`127.0.0.1:9222`)와 백그라운드 스로틀링 방지(`--disable-renderer-backgrounding`)를 활성화합니다.
  * **완전 백그라운드 동작**: WMI(`Win32_Process.Create`)와 `--hide` 플래그를 통해 작업 표시줄이나 화면 포커스를 방해하지 않고 백그라운드에서 동작합니다.
  * **원문 프롬프트 보존 옵션 (`--raw-prompt`)**: 호출 시점에 전달된 프롬프트 문자열을 에이전트가 임의로 각색하지 않고 원문 그대로 입력하는 모드를 지원합니다.
  * **연구 계획 검증 Hook 및 반복 수정 루프 (`--review-plan`, `--step plan|edit|approve`, `--plan-hook`)**:
    * 연구 계획(`research-steps`)이 생성되었을 때 자동 시작 카운트다운(`cancel-fuse-button`)을 중지하고 `on_plan_generated` 훅을 발생시켜 호출한 에이전트에게 계획을 반환합니다.
    * 호출 에이전트가 계획을 검증한 뒤 수정 사항(`EDIT: ...` 또는 `--step edit --edit-prompt "..."`)을 전달하면 UI의 **`계획 수정`(`edit-button`)**을 클릭해 계획을 수정하고, 수정된 계획(`on_plan_revised`)을 다시 호출 에이전트에게 반환하여 재검증받는 루프를 반복합니다.
    * 최종 승인(`APPROVE` 또는 `--step approve`)을 받으면 루프를 종료하고 **`연구 시작`(`confirm-button`)**을 클릭해 심층 리서치를 실행합니다.
  * **정밀 보고서 추출 (`run_deep_research.py`)**: 완료 감지(`immersive-entry-chip gem-processing-card.completed`) 후 `deep-research-immersive-panel` 내부의 본문 표·목록·인용 출처를 GitHub-Flavored Markdown으로 정밀 추출합니다.

---

## 설치 방법

### 글로벌 스킬로 설치 (모든 프로젝트에서 사용)

```powershell
# PowerShell
New-Item -ItemType Directory -Force -Path "$HOME\.gemini\config\skills" | Out-Null
Copy-Item -Recurse -Force ".\local-gemini-deep-research" "$HOME\.gemini\config\skills\local-gemini-deep-research"
```

### 필수 사전 요구 사항
* Windows용 **Google Gemini 데스크톱 앱** 설치 및 Google 계정 로그인 (`%LOCALAPPDATA%\Google\Gemini`)
* Python 3.10+ 및 `playwright` 패키지 설치:
  ```bash
  pip install playwright
  ```
