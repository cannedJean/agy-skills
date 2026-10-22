# AGY Skills (`agy-skills`)

Google Antigravity (`agy`) 에이전트를 위한 커스텀 스킬 모음 저장소입니다.

---

## 포함된 스킬 목록

### 1. [`local-gemini-deep-research`](./local-gemini-deep-research)
API 키나 종량제 과금 없이, Windows에 로컬 설치된 공식 **Google Gemini 데스크톱 앱(`Gemini.exe`)**의 로그인 세션을 그대로 활용하여 **Gemini Deep Research(심층 리서치)**를 백그라운드에서 실행하고 마크다운 보고서 및 참고 출처를 추출하는 스킬입니다.

* **핵심 특징**
  * **무결성 보존 ASAR 패치 (`patch_gemini_app.py`)**: `app.asar` 원본 바이트 길이와 헤더 SHA256 해시를 유지하면서 로컬 CDP 포트(`127.0.0.1:9222`)와 백그라운드 스로틀링 방지(`--disable-renderer-backgrounding`)를 활성화합니다.
  * **완전 백그라운드 동작**: WMI(`Win32_Process.Create`)와 `--hide` 플래그를 통해 작업 표시줄이나 화면 포커스를 방해하지 않고 백그라운드에서 동작합니다.
  * **엔드투엔드 자동화 (`run_deep_research.py`)**: Deep Research 모드 활성화 → `Argon` 모델 전환 → 연구 계획(`research-steps`) 생성 및 자동 승인(`연구 시작`) → 완료 감지(`gem-processing-card.completed`) → 본문 표·목록·인용 출처의 GitHub-Flavored Markdown 변환까지 전 과정을 자동 수행합니다.

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
