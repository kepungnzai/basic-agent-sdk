import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from google.adk.tools import ToolContext, FunctionTool

def load_and_display_page(
    page_url:str,
    cdp_url:str ="http://localhost:9222",
    content_selector:str="body",
    timeout:int=30000,
    load_timeout:int=5000,      # Max event wait time (not a fixed sleep)
    output_mode:int=1,           # 1 = text (default), 2 = HTML
    tool_context: ToolContext=None
):
    browser = None
    with sync_playwright() as p:
        try:
            print(f"Connecting to browser at {cdp_url}...", file=sys.stderr)
            browser = p.chromium.connect_over_cdp(cdp_url)
            
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            
            # Reuse existing tab if possible, else create new
            domain = page_url.split("//")[-1].split("/")[0]
            page = next((pg for pg in context.pages if domain in pg.url), None)
            if not page:
                page = context.new_page()

            print(f"Navigating to {page_url}...", file=sys.stderr)
            # EVENT 1: Waits until initial network requests finish & DOM parses
            page.goto(page_url, wait_until="networkidle", timeout=timeout)
            
            # EVENT 2: Waits until your target element is actually rendered in the DOM
            print(f"Waiting for '{content_selector}' to appear...", file=sys.stderr)
            page.wait_for_selector(content_selector, state="visible", timeout=load_timeout)
            
            # EVENT 3: Waits for secondary dynamic requests (e.g., AJAX, WebSockets) to settle
            try:
                page.wait_for_load_state("networkidle", timeout=load_timeout)
            except PlaywrightTimeout:
                print("Note: Page stabilized but network never went fully idle. Proceeding.", file=sys.stderr)

            # Extract output based on mode
            if not page.is_closed():
                locator = page.locator(content_selector)
                if locator.count() > 0:
                    target = locator.first
                    if output_mode == 2:
                        print(target.inner_html())
                    else:
                        print(target.inner_text())
                else:
                    print(f"Error: Selector '{content_selector}' not found.", file=sys.stderr)
                    sys.exit(1)
            else:
                print("Error: Page closed during load.", file=sys.stderr)
                sys.exit(1)

        except Exception as e:
            print(f"An error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if browser:
                try: browser.close()
                except: pass


browser_tool = FunctionTool(load_and_display_page)