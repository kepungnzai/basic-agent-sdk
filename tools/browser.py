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
    """
    Load a webpage via a CDP-connected Chromium browser and extract visible content 
    from a specified DOM selector. Outputs the result to stdout for tool consumption.
    
    This function is designed for ADK tool calling to enable web content inspection 
    and extraction in automated agent workflows. It connects to an existing browser 
    instance via Chrome DevTools Protocol, navigates to the target URL, waits for 
    dynamic content to stabilize, and extracts either plain text or inner HTML based 
    on the output mode.
    
    Args:
        page_url (str): The full URL to navigate to (e.g., "https://example.com"). 
                        Must include protocol (http/https).
        cdp_url (str, optional): Chrome DevTools Protocol endpoint for browser 
                                 connection. Defaults to "http://localhost:9222".
        content_selector (str, optional): CSS selector identifying the DOM element 
                                          to extract content from. Defaults to "body".
        timeout (int, optional): Maximum time in milliseconds to wait for the initial 
                                 page navigation and network idle. Defaults to 30000.
        load_timeout (int, optional): Maximum time in milliseconds to wait for the 
                                      target selector to appear and for secondary 
                                      dynamic requests to settle. Defaults to 5000.
        output_mode (int, optional): Format of extracted content: 1 for plain text 
                                     via inner_text(), 2 for raw HTML via inner_html(). 
                                     Defaults to 1.
    
    Returns:
        None: Results are printed to stdout. Errors are printed to stderr and cause 
              sys.exit(1).
    
    Raises:
        PlaywrightTimeout: If page load or selector wait exceeds specified timeouts 
                           (handled internally with fallback behavior).
        Exception: Any unexpected error during browser operation (handled internally).
    
    Note:
        - Reuses an existing browser tab if one already contains the target domain.
        - Uses a 3-stage wait strategy: networkidle → selector visible → secondary networkidle.
        - Browser connection is automatically closed in the finally block.
    """
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