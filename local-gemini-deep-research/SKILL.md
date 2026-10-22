---
name: local-gemini-deep-research
description: >-
  Use this skill when the user asks to run Gemini Deep Research (딥리서치), perform
  exhaustive web research using their Google Gemini subscription without API keys,
  or automate the locally installed Windows Gemini desktop app (`Gemini.exe`).
---

# Local Gemini App Deep Research Skill

This skill automates the locally installed **Google Gemini Windows Desktop App** (`%LOCALAPPDATA%\Google\Gemini\app-*\Gemini.exe`) via Chrome DevTools Protocol (CDP) and Playwright to execute **Gemini Deep Research** using the user's logged-in Google account without requiring an API key.

## Architecture & How It Works

1. **Automatic CDP Enablement ([patch_gemini_app.py](./scripts/patch_gemini_app.py))**:
   - Locates the latest installed `%LOCALAPPDATA%\Google\Gemini\app-*\resources\app.asar`.
   - Creates a safe backup (`app.asar.bak`) and patches `src/main.js` (preserving exact byte length and SHA256 header integrity) to enable `--remote-debugging-port=9222` and `--disable-renderer-backgrounding`.
   - Launches `Gemini.exe --hide` persistently in the background via WMI (`Win32_Process.Create`) so the window stays hidden and does not steal focus.
2. **Deep Research Execution ([run_deep_research.py](./scripts/run_deep_research.py))**:
   - Connects to `http://127.0.0.1:9222` using Playwright (`connect_over_cdp`).
   - Opens a new chat (`https://gemini.google.com/app`), enables **Deep Research** (`업로드 및 도구` → `도구 더보기` → `Deep Research`), and switches the model selector (`[data-test-id="bard-mode-menu-button"]`) to **Argon** for reliable plan generation.
   - Submits the prompt using native keyboard input events (`keyboard.insert_text`) and checks for any safety/keyword filter refusal messages.
   - Waits for the **Research Plan (`[data-test-id="research-steps"]`)** and automatically clicks **`연구 시작` (`[data-test-id="confirm-button"]`)** (unless `--plan-only` is specified).
   - Monitors live research thoughts (`[data-test-id="thought-header"]` / `[data-test-id="thought-body"]`) until `immersive-entry-chip gem-processing-card.completed` indicates completion.
   - Extracts the pure report body from `deep-research-immersive-panel message-content` (`[data-test-id="message-content"]`) and citation links into GitHub-Flavored Markdown.

---

## Usage Instructions for the Agent

### 1. Full End-to-End Deep Research (Recommended)

Because Deep Research typically takes **5 to 15 minutes** to browse sources and synthesize the report, run the script and allow it to complete in the background:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python "$HOME\.gemini\config\skills\local-gemini-deep-research\scripts\run_deep_research.py" `
  --prompt "<DETAILED_RESEARCH_PROMPT>" `
  --output "<OUTPUT_MARKDOWN_FILE_PATH>"
```

* **Prompt Guidelines**: Avoid sensitive political/election keywords (e.g., `민주주의`, `선거`, `정치`) in Korean prompts, as Gemini Web's Korean content filter may block plan generation. Frame topics in academic/technical terms instead.
* When `run_command` backgrounds the task, **do not poll in a loop**. End your turn and wait for the system notification when the background task finishes.
* Once completed, read the generated Markdown file at `<OUTPUT_MARKDOWN_FILE_PATH>` (or create an Artifact with it) and present the findings to the user.

### 2. Two-Step Interactive Mode (Plan First, Confirm Later)

If the user wants to review the Research Plan before starting the multi-minute execution:

1. **Generate the Research Plan only**:
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   python "$HOME\.gemini\config\skills\local-gemini-deep-research\scripts\run_deep_research.py" `
     --prompt "<DETAILED_RESEARCH_PROMPT>" `
     --plan-only
   ```
2. Show the output plan and `url` to the user. Once approved, **resume and execute** (pass the URL or `current` for the active page):
   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   python "$HOME\.gemini\config\skills\local-gemini-deep-research\scripts\run_deep_research.py" `
     --resume-url "current" `
     --output "<OUTPUT_MARKDOWN_FILE_PATH>"
   ```

### 3. Troubleshooting & Maintenance

* **Check / Start Local Gemini App with CDP only**:
  ```powershell
  python "$HOME\.gemini\config\skills\local-gemini-deep-research\scripts\patch_gemini_app.py"
  ```
* **Show the Local Gemini App Window** (if the user wants to watch visually or re-authenticate):
  Add `--show` to either `patch_gemini_app.py` or `run_deep_research.py`.
* **Restore Original Unpatched `app.asar`**:
  ```powershell
  python "$HOME\.gemini\config\skills\local-gemini-deep-research\scripts\patch_gemini_app.py" --restore
  ```
