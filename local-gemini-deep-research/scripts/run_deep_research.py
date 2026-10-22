import argparse
import json
import os
import sys
import time
from playwright.sync_api import sync_playwright

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from patch_gemini_app import CDP_PORT, ensure_gemini_running_with_cdp


HTML_TO_MARKDOWN_JS = r"""
(rootSelector) => {
    const findReportRoot = () => {
        const immersiveMsg = document.querySelector(
            'deep-research-immersive-panel message-content, ' +
            'deep-research-immersive-panel [data-test-id="message-content"], ' +
            'deep-research-immersive-panel .markdown, ' +
            '.deep-research-content .markdown'
        );
        if (immersiveMsg && immersiveMsg.innerText.trim().length > 200) return immersiveMsg;
        const responses = Array.from(document.querySelectorAll('model-response message-content .markdown, model-response message-content'));
        if (responses.length > 0) return responses[responses.length - 1];
        return null;
    };

    const root = rootSelector ? document.querySelector(rootSelector) : findReportRoot();
    if (!root) return { markdown: '', sources: [] };

    const convertNode = (node, listDepth = 0) => {
        if (!node) return '';
        if (node.nodeType === Node.TEXT_NODE) {
            return node.nodeValue || '';
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return '';

        const tag = node.tagName.toLowerCase();
        if (['script', 'style', 'mat-icon', 'gem-icon', 'button', 'remy-processing-state', 'thinking-overlay'].includes(tag)) {
            return '';
        }

        const childrenText = () => Array.from(node.childNodes).map(c => convertNode(c, listDepth)).join('');

        switch (tag) {
            case 'h1': return `\n\n# ${childrenText().trim()}\n\n`;
            case 'h2': return `\n\n## ${childrenText().trim()}\n\n`;
            case 'h3': return `\n\n### ${childrenText().trim()}\n\n`;
            case 'h4': return `\n\n#### ${childrenText().trim()}\n\n`;
            case 'h5': return `\n\n##### ${childrenText().trim()}\n\n`;
            case 'h6': return `\n\n###### ${childrenText().trim()}\n\n`;
            case 'p': return `\n\n${childrenText().trim()}\n\n`;
            case 'br': return '\n';
            case 'hr': return '\n\n---\n\n';
            case 'strong':
            case 'b': {
                const t = childrenText().trim();
                return t ? `**${t}**` : '';
            }
            case 'em':
            case 'i': {
                const t = childrenText().trim();
                return t ? `*${t}*` : '';
            }
            case 'code': {
                if (node.parentElement && node.parentElement.tagName.toLowerCase() === 'pre') {
                    return node.innerText || '';
                }
                const t = childrenText().trim();
                return t ? `\`${t}\`` : '';
            }
            case 'pre': {
                const codeEl = node.querySelector('code');
                const raw = (codeEl ? codeEl.innerText : node.innerText) || '';
                return `\n\n\`\`\`\n${raw.trim()}\n\`\`\`\n\n`;
            }
            case 'blockquote': {
                const lines = childrenText().trim().split('\n').map(l => `> ${l}`).join('\n');
                return `\n\n${lines}\n\n`;
            }
            case 'a': {
                const href = node.getAttribute('href') || '';
                const text = childrenText().trim() || href;
                if (href && href.startsWith('http')) {
                    return `[${text}](${href})`;
                }
                return text;
            }
            case 'ul': {
                const items = Array.from(node.children).filter(c => c.tagName.toLowerCase() === 'li').map(li => {
                    const indent = '  '.repeat(listDepth);
                    return `${indent}- ${convertNode(li, listDepth + 1).trim()}`;
                }).join('\n');
                return `\n${items}\n`;
            }
            case 'ol': {
                const items = Array.from(node.children).filter(c => c.tagName.toLowerCase() === 'li').map((li, idx) => {
                    const indent = '  '.repeat(listDepth);
                    return `${indent}${idx + 1}. ${convertNode(li, listDepth + 1).trim()}`;
                }).join('\n');
                return `\n${items}\n`;
            }
            case 'li': {
                return childrenText().replace(/^\n+|\n+$/g, '');
            }
            case 'table': {
                const rows = Array.from(node.querySelectorAll('tr'));
                if (rows.length === 0) return '';
                const matrix = rows.map(r =>
                    Array.from(r.querySelectorAll('th, td')).map(cell =>
                        (cell.innerText || '').trim().replace(/\s+/g, ' ').replace(/\|/g, '\\|')
                    )
                ).filter(r => r.length > 0);
                if (matrix.length === 0) return '';
                const colCount = Math.max(...matrix.map(r => r.length));
                const norm = matrix.map(r => {
                    while (r.length < colCount) r.push('');
                    return `| ${r.join(' | ')} |`;
                });
                const sep = `| ${Array(colCount).fill('---').join(' | ')} |`;
                norm.splice(1, 0, sep);
                return `\n\n${norm.join('\n')}\n\n`;
            }
            default:
                return childrenText();
        }
    };

    let md = convertNode(root)
        .replace(/\n{3,}/g, '\n\n')
        .trim();

    // Collect external citation links from the page/panel
    const sourceLinks = [];
    const seenUrls = new Set();
    const linkEls = Array.from(document.querySelectorAll('deep-research-immersive-panel a[href^="http"], sources-list a[href^="http"], [data-test-id*="source"] a[href^="http"], model-response a[href^="http"]'));
    for (const a of linkEls) {
        const href = a.getAttribute('href');
        if (!href || href.includes('google.com/search') || href.includes('support.google.com') || seenUrls.has(href)) continue;
        seenUrls.add(href);
        const title = (a.innerText || a.getAttribute('aria-label') || href).trim().replace(/\s+/g, ' ');
        sourceLinks.push({ title: title || href, url: href });
    }

    return { markdown: md, sources: sourceLinks };
}
"""


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_gemini_page(browser, timeout_sec=15):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "gemini.google.com" in pg.url:
                    return pg
        time.sleep(0.5)
    raise RuntimeError("Could not find a gemini.google.com page in the local Gemini app.")


def prevent_background_throttling(page):
    try:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Page.enable")
        cdp.send("Page.setWebLifecycleState", {"state": "active"})
        cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception as e:
        log(f"Note: CDP focus emulation setup warning (non-fatal): {e}")


def activate_deep_research_mode(page):
    page.wait_for_selector('[role="textbox"]', timeout=30000)
    deselect_btn = page.locator(
        '[data-test-id="deselect-drawer-item-gem-button"], button[aria-label*="Deep Research 선택 해제"], button[aria-label*="Deselect Deep Research"]'
    )
    if deselect_btn.count() > 0:
        log("Deep Research mode is already active.")
        return

    log("Activating Deep Research mode...")
    tools_selector = 'button[aria-label="업로드 및 도구"], button[aria-label="Upload and tools"]'
    page.wait_for_selector(tools_selector, timeout=20000)
    tools_btn = page.locator(tools_selector).first

    for attempt in range(5):
        if deselect_btn.count() > 0:
            log("Deep Research mode enabled successfully.")
            return

        if tools_btn.get_attribute("aria-expanded") != "true":
            tools_btn.click()
            time.sleep(1.0)

        more_btn = page.locator('[data-test-id="more-tools-button"]').first
        if more_btn.count() > 0 and page.locator('button:has-text("Deep Research")').count() == 0:
            more_btn.click()
            time.sleep(0.8)

        dr_btn = page.locator('button:has-text("Deep Research")').first
        if dr_btn.count() > 0:
            dr_btn.click()
            time.sleep(1.0)
            if deselect_btn.count() > 0:
                log("Deep Research mode enabled successfully.")
                break

        time.sleep(1.0)
    else:
        raise RuntimeError("Could not activate 'Deep Research' mode from the Tools menu.")

    # Ensure 4 Argon model is selected for reliable Deep Research execution
    mode_btn = page.locator('[data-test-id="bard-mode-menu-button"]').first
    if mode_btn.count() > 0 and "Argon" not in mode_btn.inner_text():
        mode_btn.click()
        time.sleep(0.8)
        argon_opt = page.locator('gem-menu-item:has-text("Argon")').first
        if argon_opt.count() > 0:
            argon_opt.click()
            time.sleep(1.0)
            log(f"Switched model mode to: {mode_btn.inner_text().strip()}")
        else:
            page.keyboard.press("Escape")


def submit_prompt(page, prompt_text):
    log(f"Entering prompt: {prompt_text[:80]}{'...' if len(prompt_text) > 80 else ''}")
    textbox = page.locator('[role="textbox"]').first
    textbox.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(prompt_text)
    time.sleep(0.6)

    send_btn = page.locator('button[aria-label="메시지 보내기"], button[aria-label*="Send"]').first
    if send_btn.count() > 0:
        send_btn.click()
    else:
        textbox.press("Enter")
    log("Prompt submitted. Waiting for Research Plan generation...")


def wait_for_and_confirm_plan(page, plan_only=False, timeout_sec=120):
    start_time = time.time()
    reloaded_once = False
    while time.time() - start_time < timeout_sec:
        elapsed = time.time() - start_time

        # Check for filter refusal message
        resp_el = page.locator("model-response").last
        if resp_el.count() > 0:
            resp_txt = resp_el.inner_text().strip()
            if "도와드릴 수가 없습니다" in resp_txt or "단지 언어 모델일 뿐" in resp_txt:
                raise RuntimeError(
                    f"Gemini Web safety/keyword filter blocked the prompt: '{resp_txt}'. "
                    "Avoid sensitive political/election keywords (e.g., '민주주의', '선거', '정치')."
                )

        confirm_btn = page.locator(
            '[data-test-id="confirm-button"], gem-button[data-test-id="confirm-button"], button[aria-label="연구 시작"], button:has-text("연구 시작"), button:has-text("Start research")'
        ).first
        if confirm_btn.count() > 0:
            plan_el = page.locator('[data-test-id="research-steps"], .research-steps').last
            plan_text = plan_el.inner_text().strip() if plan_el.count() > 0 else ""
            log("Research Plan generated!")
            if plan_text:
                print("\n--- [Research Plan] ---\n" + plan_text + "\n-----------------------\n", flush=True)

            if plan_only:
                return {"status": "plan_ready", "url": page.url, "plan": plan_text}

            log("Clicking '연구 시작' (Confirm Plan) to start Deep Research execution...")
            confirm_btn.click(force=True)
            time.sleep(2.0)
            return {"status": "started", "url": page.url, "plan": plan_text}

        if elapsed > 45 and not reloaded_once and "/app/" in page.url:
            reloaded_once = True
            log("Plan generation taking >45s; reloading conversation page once to refresh state...")
            page.reload(wait_until="domcontentloaded")
            time.sleep(3.0)

        time.sleep(2.0)

    raise TimeoutError(f"Research Plan confirmation button did not appear within {timeout_sec}s.")


def wait_for_report_completion(page, timeout_sec=1200):
    log("Deep Research is running in the background. Monitoring progress...")
    start_time = time.time()
    last_status = ""
    stable_ticks = 0
    last_len = 0
    last_reload_time = time.time()

    while time.time() - start_time < timeout_sec:
        state = page.evaluate(r"""() => {
            const isCardCompleted = !!document.querySelector('immersive-entry-chip gem-processing-card.completed');
            const workingEl = document.querySelector('[data-test-id="remy-processing-state-agent-working"], remy-processing-state');

            const thoughtHeaders = Array.from(document.querySelectorAll('[data-test-id="thought-header"]')).map(e => (e.innerText || '').trim()).filter(Boolean);
            const thoughtBodies = Array.from(document.querySelectorAll('[data-test-id="thought-body"]')).map(e => (e.innerText || '').trim()).filter(Boolean);
            const latestThought = thoughtHeaders.length > 0
                ? `${thoughtHeaders[thoughtHeaders.length - 1]}: ${(thoughtBodies[thoughtBodies.length - 1] || '').slice(0, 80)}`
                : (thoughtBodies[thoughtBodies.length - 1] || '').slice(0, 100);

            const statusTextEl = document.querySelector('[data-test-id="remy-processing-state-text"], [data-test-id="processing-state-container-button"], [data-test-id="status-update-text"]');
            const statusText = (statusTextEl ? (statusTextEl.innerText || '').trim().replace(/\s+/g, ' ') : '') || latestThought;

            const chipEl = document.querySelector('immersive-entry-chip');
            const chipText = chipEl ? (chipEl.innerText || '').trim().replace(/\s+/g, ' ') : '';
            const isChipStillWriting = !isCardCompleted && (chipText.includes('작성 중') || chipText.includes('생성 중') || chipText.includes('Writing'));

            const immersiveChipBtn = document.querySelector('immersive-entry-chip gem-processing-card, button[data-test-id="immersive-entry-chip-view-report-button"], immersive-entry-chip [data-test-id="open-button"] button, immersive-entry-chip');
            const immersiveMsg = document.querySelector(
                'deep-research-immersive-panel message-content, ' +
                'deep-research-immersive-panel [data-test-id="message-content"], ' +
                'deep-research-immersive-panel .markdown, ' +
                '.deep-research-content .markdown'
            );
            const immersivePanel = document.querySelector('deep-research-immersive-panel');

            let reportTextLen = 0;
            if (immersiveMsg) {
                reportTextLen = (immersiveMsg.innerText || '').trim().length;
            } else if (immersivePanel && isCardCompleted) {
                reportTextLen = (immersivePanel.innerText || '').trim().length;
            }

            return {
                isCardCompleted,
                hasWorkingIndicator: !!workingEl,
                statusText,
                chipText,
                isChipStillWriting,
                hasImmersiveChip: !!immersiveChipBtn,
                hasImmersivePanel: !!immersivePanel,
                reportTextLen
            };
        }""")

        status_line = f"{state['chipText']} | {state['statusText']}".strip(" |")
        if status_line and status_line != last_status:
            last_status = status_line
            elapsed = int(time.time() - start_time)
            log(f"[{elapsed}s] Progress: {status_line}")

        if state["hasImmersiveChip"] and not state["hasImmersivePanel"]:
            try:
                chip = page.locator(
                    'immersive-entry-chip gem-processing-card, button[data-test-id="immersive-entry-chip-view-report-button"], immersive-entry-chip'
                ).first
                if chip.count() > 0:
                    chip.click(force=True)
                    time.sleep(1.5)
            except Exception:
                pass

        if state["reportTextLen"] > 400 and (state["isCardCompleted"] or not state["isChipStillWriting"]):
            if state["reportTextLen"] == last_len:
                stable_ticks += 1
            else:
                stable_ticks = 0
                last_len = state["reportTextLen"]

            if stable_ticks >= 1:
                log(f"Deep Research report complete! ({state['reportTextLen']} chars)")
                break
        else:
            stable_ticks = 0
            last_len = state["reportTextLen"]
            if time.time() - last_reload_time > 90:
                last_reload_time = time.time()
                log("Refreshing conversation state from server...")
                page.reload(wait_until="domcontentloaded")
                time.sleep(3.0)

        time.sleep(2.0)
    else:
        raise TimeoutError(f"Deep Research did not finish within {timeout_sec} seconds.")

    # Extract formatted Markdown + sources
    extracted = page.evaluate(HTML_TO_MARKDOWN_JS, None)
    markdown = extracted.get("markdown", "").strip()
    sources = extracted.get("sources", [])

    if sources:
        markdown += "\n\n---\n\n## 참고 출처 (Sources)\n\n"
        for idx, src in enumerate(sources, 1):
            markdown += f"{idx}. [{src['title']}]({src['url']})\n"

    return {
        "status": "completed",
        "url": page.url,
        "markdown": markdown,
        "sources_count": len(sources),
    }


def main():
    parser = argparse.ArgumentParser(description="Run Deep Research using the local Windows Gemini desktop app.")
    parser.add_argument("--prompt", type=str, help="Research prompt/topic to investigate.")
    parser.add_argument("--output", type=str, help="Optional file path to save the resulting Markdown report.")
    parser.add_argument("--plan-only", action="store_true", help="Stop after generating the Research Plan without starting execution.")
    parser.add_argument("--resume-url", type=str, help="Resume an existing Deep Research conversation URL.")
    parser.add_argument("--timeout", type=int, default=900, help="Max wait time in seconds for research completion (default: 900).")
    parser.add_argument("--show", action="store_true", help="Show the local Gemini desktop window instead of running hidden.")
    args = parser.parse_args()

    if not args.prompt and not args.resume_url:
        parser.error("Either --prompt or --resume-url must be provided.")

    app_info = ensure_gemini_running_with_cdp(port=CDP_PORT, hide=not args.show)
    log(f"Local Gemini app ready via CDP ({app_info['cdp_url']}, status={app_info['status']})")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(app_info["cdp_url"])
        page = get_gemini_page(browser)
        prevent_background_throttling(page)

        if args.resume_url:
            if args.resume_url != "current" and page.url != args.resume_url:
                log(f"Navigating to existing conversation: {args.resume_url}")
                page.goto(args.resume_url, wait_until="domcontentloaded")
                time.sleep(2.5)
            plan_el = page.locator('[data-test-id="research-steps"], .research-steps').last
            if plan_el.count() > 0:
                print("\n--- [Research Plan] ---\n" + plan_el.inner_text().strip() + "\n-----------------------\n", flush=True)
            confirm_btn = page.locator('[data-test-id="confirm-button"]:not(.gem-button-disabled) button:not([disabled])').first
            if confirm_btn.count() > 0:
                log("Confirming pending Research Plan ('연구 시작')...")
                confirm_btn.click(force=True)
                time.sleep(2.0)
        else:
            if page.url.rstrip("/") != "https://gemini.google.com/app":
                log("Opening new chat in local Gemini app...")
                new_chat_btn = page.locator('[data-test-id="new-chat-button"] button, a[aria-label="새 채팅"], a[aria-label="New chat"]').first
                if new_chat_btn.count() > 0:
                    new_chat_btn.click(force=True)
                    time.sleep(1.5)
                else:
                    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
                    time.sleep(3.5)
            activate_deep_research_mode(page)
            submit_prompt(page, args.prompt)
            plan_res = wait_for_and_confirm_plan(page, plan_only=args.plan_only)
            if args.plan_only:
                if args.output:
                    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
                    with open(args.output, "w", encoding="utf-8") as f:
                        f.write(f"# Research Plan\n\nURL: {plan_res['url']}\n\n{plan_res['plan']}\n")
                print(json.dumps(plan_res, ensure_ascii=False, indent=2))
                return

        result = wait_for_report_completion(page, timeout_sec=args.timeout)
        if args.output:
            out_path = os.path.abspath(args.output)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(result["markdown"])
            log(f"Saved Markdown report ({len(result['markdown'])} chars) to: {out_path}")

        print("\n=== DEEP RESEARCH REPORT START ===\n")
        print(result["markdown"])
        print("\n=== DEEP RESEARCH REPORT END ===\n")


if __name__ == "__main__":
    main()
