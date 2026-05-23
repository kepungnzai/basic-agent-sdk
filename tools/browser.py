from typing import Dict, Optional
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from google.adk.tools import ToolContext, FunctionTool

def browser_interact(
    action: str = "extract",
    page_url: Optional[str] = None,
    content_selector: str = "body",
    input_selector: Optional[str] = None,
    text: Optional[str] = None,
    click_selector: Optional[str] = None,
    cdp_url: str = "http://localhost:9222",
    timeout: int = 30000,
    load_timeout: int = 5000,
    output_mode: int = 1,   # 1=text, 2=HTML (only for extract)
    tool_context: ToolContext = None
) -> Dict[str, str]:
    """
    Persistent browser interaction tool for ADK agents.
    
    Supports continuous interaction with a single browser instance:
      - action='load'  : Navigate to `page_url` and store the page.
      - action='extract': Extract visible text/HTML from `content_selector`.
      - action='type'  : Type `text` into `input_selector`.
      - action='click' : Click `click_selector`.
      - action='close' : Close the browser and clean up state.
    
    State is stored in `tool_context.state` and reused across calls.
    """
    # Initialize state if this is the first call
    if tool_context is None:
        state = {}
    else:
        state = tool_context.state
        if not hasattr(state, "setdefault"):  # Ensure it behaves like a dict
            state = {}
            tool_context.state = state

    # Helper to get or create browser connection
    def _get_browser():
        if "browser" not in state or state["browser"] is None:
            print(f"Connecting to browser at {cdp_url}...", file=sys.stderr)
            playwright = sync_playwright().start()
            state["playwright"] = playwright
            browser = playwright.chromium.connect_over_cdp(cdp_url)
            state["browser"] = browser
        return state["browser"]

    def _get_page():
        """Return the stored page, or None."""
        return state.get("page")

    try:
        # ----- ACTION: LOAD -----
        if action == "load":
            if not page_url:
                return {"error": "page_url is required for action='load'"}
            browser = _get_browser()
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            # Reuse existing tab if same domain already open
            domain = page_url.split("//")[-1].split("/")[0]
            page = next((pg for pg in context.pages if domain in pg.url), None)
            if not page:
                page = context.new_page()
            print(f"Navigating to {page_url}...", file=sys.stderr)
            page.goto(page_url, wait_until="networkidle", timeout=timeout)
            print(f"Waiting for '{content_selector}' to appear...", file=sys.stderr)
            page.wait_for_selector(content_selector, state="visible", timeout=load_timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=load_timeout)
            except PlaywrightTimeout:
                print("Note: Network never fully idle, proceeding.", file=sys.stderr)
            state["page"] = page
            return {"response": f"Page loaded: {page_url}"}

        # ----- ACTION: EXTRACT -----
        elif action == "extract":
            page = _get_page()
            if not page or page.is_closed():
                return {"error": "No page loaded. Use action='load' first."}
            locator = page.locator(content_selector)
            if locator.count() == 0:
                return {"error": f"Selector '{content_selector}' not found."}
            target = locator.first
            if output_mode == 2:
                content = target.inner_html()
            else:
                content = target.inner_text()
            # Also print to stdout for backward compatibility
            print(content)
            return {"response": content}

        # ----- ACTION: TYPE -----
        elif action == "type":
            if not input_selector or text is None:
                return {"error": "input_selector and text required for action='type'"}
            page = _get_page()
            if not page or page.is_closed():
                return {"error": "No page loaded. Use action='load' first."}
            page.fill(input_selector, text)
            print(f"Typed '{text}' into {input_selector}", file=sys.stderr)
            return {"response": f"Typed '{text}' into {input_selector}"}

        # ----- ACTION: CLICK -----
        elif action == "click":
            if not click_selector:
                return {"error": "click_selector required for action='click'"}
            page = _get_page()
            if not page or page.is_closed():
                return {"error": "No page loaded. Use action='load' first."}
            page.click(click_selector)
            print(f"Clicked {click_selector}", file=sys.stderr)
            # Wait a moment for any navigation/action to start
            page.wait_for_timeout(1000)
            return {"response": f"Clicked {click_selector}"}

        # ----- ACTION: CLOSE -----
        elif action == "close":
            if "browser" in state:
                try:
                    state["browser"].close()
                except:
                    pass
            if "playwright" in state:
                try:
                    state["playwright"].stop()
                except:
                    pass
            state.clear()
            return {"response": "Browser closed and state cleared."}

        else:
            return {"error": f"Unknown action: {action}"}

    except Exception as e:
        return {"error": str(e)}


# Create the tool
browser_tool = FunctionTool(browser_interact)