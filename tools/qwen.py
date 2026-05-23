from ast import Dict
import sys
import time
from playwright.sync_api import sync_playwright
from google.adk.tools import ToolContext, FunctionTool

def qwen_chat(
    message:str,
    cdp_url:str="http://localhost:9222",
    chat_url:str="https://qwen.ai/home",
    textarea_selector:str="textarea",
    submit_button_selector:str="div > i.default-iconfont.icon-line-arrow-up",
    response_selector:str=".ds-markdown, [class*='markdown']",
    timeout:int=30000,
    response_timeout:int=900000,
    post_response_sleep:int=2,
    submit_retry_sleep:int=1,
    output_type:str="text",  # "text" or "html"
    tool_context: ToolContext=None
)-> Dict[str, str]:
    """
    Automate interaction with Qwen's web chat interface to send a message and 
    extract the AI-generated response. Designed for ADK tool calling to enable 
    LLM agents to query Qwen programmatically via browser automation.
    
    This function connects to a Chromium browser via Chrome DevTools Protocol (CDP),
    navigates to the Qwen chat UI, injects a user message, triggers submission,
    handles potential new-tab navigation (Qwen often opens chat sessions in new tabs),
    monitors response streaming by detecting content stabilization across multiple 
    render cycles, and extracts the final response content in plain text or HTML format.
    
    Args:
        message (str): The chat message/prompt to send to Qwen. Should be a 
                       complete, well-formed query appropriate for the model.
        cdp_url (str, optional): Chrome DevTools Protocol endpoint for browser 
                                 connection. Defaults to "http://localhost:9222".
        chat_url (str, optional): Base URL of the Qwen chat interface. Defaults 
                                  to "https://qwen.ai/home".
        textarea_selector (str, optional): CSS selector for the message input 
                                           textarea element. Defaults to "textarea" 
                                           but may need adjustment if UI changes.
        submit_button_selector (str, optional): CSS selector for the send/submit 
                                                button (icon-based). Defaults to 
                                                Qwen's arrow-up icon selector.
        response_selector (str, optional): CSS selector pattern for extracting AI 
                                           response content. Supports multiple 
                                           patterns via comma separation to improve 
                                           resilience against UI updates. Defaults 
                                           to ".ds-markdown, [class*='markdown']".
        timeout (int, optional): Maximum time in milliseconds to wait for initial 
                                 page load and input field availability. Defaults 
                                 to 30000 (30 seconds).
        response_timeout (int, optional): Maximum time in milliseconds to wait for 
                                          the full AI response to complete streaming. 
                                          Qwen responses can be lengthy; defaults 
                                          to 900000 (15 minutes).
        post_response_sleep (int, optional): Additional delay in seconds after 
                                             response completes before extraction, 
                                             ensuring all dynamic content is 
                                             fully rendered. Defaults to 2.
        submit_retry_sleep (int, optional): Delay in seconds before retrying submit 
                                            click if button is not immediately 
                                            enabled after filling input. Defaults 
                                            to 1.
        output_type (str, optional): Format of extracted response: "text" for 
                                     plain text via inner_text(), or "html" for 
                                     raw HTML markup via inner_html(). Defaults 
                                     to "text".
    
    Returns:
        Dict[str, str]: A dictionary containing the extracted response under the key "response". 
                         Errors are printed to stderr and trigger sys.exit(1).

    Raises:
        Exception: Any Playwright or runtime error during browser automation 
                   (handled internally with error logging and exit).
    
    Note:
        - Implements robust new-tab handling: Qwen often opens chat sessions in 
          new browser tabs. This function listens for context "page" events and 
          popups, then switches context to the newly created tab for response 
          extraction.
        - Response completion is detected via a stabilization loop: the function 
          polls response content every 3 seconds and considers generation complete 
          when no text changes are detected across consecutive checks.
        - Includes debug logging that dumps all matching response elements during 
          the polling loop (visible in stderr) to aid troubleshooting.
        - Reuses existing browser tabs/pages when possible to maintain session 
          state and avoid redundant logins.
        - All timeouts are in milliseconds except post_response_sleep and 
          submit_retry_sleep which are in seconds for intuitive short delays.
        - Browser is automatically closed in the finally block to prevent resource 
          leaks.
        - Selectors are fragile to UI changes; monitor Qwen's frontend updates 
          and adjust selectors as needed.
    """
    browser = None
    with sync_playwright() as p:
        try:
            print(f"Connecting to browser at {cdp_url}...", file=sys.stderr)
            browser = p.chromium.connect_over_cdp(cdp_url)
            
            if not browser.contexts:
                context = browser.new_context()
            else:
                context = browser.contexts[0]
                
            if not context.pages:
                page = context.new_page()
            else:
                domain = chat_url.split("//")[-1].split("/")[0]
                page = next((pg for pg in context.pages if domain in pg.url), None)
                if not page:
                    page = context.new_page()

            if chat_url not in page.url:
                print(f"Navigating to {chat_url}...", file=sys.stderr)
                page.goto(chat_url, wait_until="networkidle")
            
            print("Waiting for chat input...", file=sys.stderr)
            page.wait_for_selector(textarea_selector, timeout=timeout)
            
            print(f"Sending message: {message[:50]}...", file=sys.stderr)
            page.fill(textarea_selector, message)
            
            submit_button = page.locator(submit_button_selector)
            if not submit_button.is_enabled():
                time.sleep(submit_retry_sleep)
            
            print("Clicking submit...", file=sys.stderr)
            
            # --- RELIABLE NEW TAB HANDLING (FIXED) ---
            # Capture new pages created by the context + popups
            existing_pages = set(context.pages)
            new_chat_page = [None]   # mutable container
            
            def handle_new_page(new_page):
                if new_page not in existing_pages:
                    print(f"New page detected (context listener): {new_page.url}", file=sys.stderr)
                    new_chat_page[0] = new_page

            def handle_popup(popup):
                print(f"Popup detected: {popup.url}", file=sys.stderr)
                new_chat_page[0] = popup
            
            # Listen for new pages from the context (covers normal tab creation)
            context.on("page", handle_new_page)
            # Popup listener as a fallback
            page.on("popup", handle_popup)
            
            submit_button.click()
            
            # Wait up to 15 seconds for any new page to appear
            wait_attempts = 30   # 30 * 0.5s = 15s
            for _ in range(wait_attempts):
                time.sleep(0.5)
                if new_chat_page[0] is not None:
                    break
                # Also check context.pages in case the event was missed
                current_pages = set(context.pages)
                if current_pages - existing_pages:
                    # take the newest page (usually the one we want)
                    new_chat_page[0] = list(current_pages - existing_pages)[-1]
                    print(f"New page caught via page list: {new_chat_page[0].url}", file=sys.stderr)
                    break
            
            if new_chat_page[0] is not None:
                chat_page = new_chat_page[0]
                print(f"Switching to new tab: {chat_page.url}", file=sys.stderr)
                chat_page.bring_to_front()
                # Wait for the page to be fully interactive
                try:
                    chat_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    chat_page.wait_for_load_state("networkidle", timeout=5000)
                except Exception as e:
                    print(f"Warning: New tab load wait timed out: {e}", file=sys.stderr)
            else:
                print("No new tab detected, staying on current page.", file=sys.stderr)
                chat_page = page
            # -------------------------------------------
            
            # Wait a moment for the response content to start appearing
            print("Waiting up to 10s for response container to appear in DOM...", file=sys.stderr)
            try:
                chat_page.wait_for_selector(response_selector, timeout=10000)
            except Exception:
                print("Warning: response selector did not appear within 10s.", file=sys.stderr)
            else:
                print("Response container found.", file=sys.stderr)
            
            # Additional safety sleep to let rendering catch up
            time.sleep(post_response_sleep)
            
            print("Tracking response generation (checking every 3s)...", file=sys.stderr)
            previous_texts = []
            start_time = time.time()
            loop_count = 0
            
            while True:
                loop_count += 1
                if (time.time() - start_time) > (response_timeout / 1000):
                    print(f"Warning: Exceeded max response timeout of {response_timeout/1000}s.", file=sys.stderr)
                    break
                
                try:
                    if chat_page.is_closed():
                        print("Page was closed during generation. Exiting loop.", file=sys.stderr)
                        break
                except Exception:
                    print("Browser/context disconnected during generation. Exiting loop.", file=sys.stderr)
                    break

                time.sleep(3)
                
                try:
                    # Fetch text from ALL matching markdown elements on the page
                    locators = chat_page.locator(response_selector).all()
                    current_texts = []
                    
                    # --- DEBUG DUMP ---
                    print(f"\n--- DEBUG DUMP (Loop #{loop_count}, {len(locators)} elements found) ---", file=sys.stderr)
                    for i, loc in enumerate(locators):
                        try:
                            text = loc.inner_text()
                            current_texts.append(text)
                            snippet = text[:150].replace('\n', ' ').strip()
                            print(f"Element [{i}]: {snippet}...", file=sys.stderr)
                        except Exception as e:
                            current_texts.append("")
                            print(f"Element [{i}]: ERROR reading text ({e})", file=sys.stderr)
                    print("------------------------------------\n", file=sys.stderr)
                    # ------------------
                    
                    # Check if any text is still changing
                    changing = False
                    if len(current_texts) == len(previous_texts):
                        for i in range(len(current_texts)):
                            if current_texts[i] != previous_texts[i]:
                                changing = True
                                break
                    else:
                        changing = True  # Number of elements changed
                        
                    if not changing and previous_texts:
                        print("No new data or elements for 3 seconds. Response complete.", file=sys.stderr)
                        break
                        
                    previous_texts = current_texts
                    
                except Exception as e:
                    print(f"Lost connection to page while reading response: {e}", file=sys.stderr)
                    break

        
            
            
            # Final extraction from the correct chat_page
            if not chat_page.is_closed():
                locators = chat_page.locator(response_selector).all()
                if locators:
                    last_response = locators[-1]
                    output = last_response.inner_html() if output_type == "html" else last_response.inner_text()
                    print(output)  # This is the actual output the user wants
                else:
                    print("Error: Failed to extract response content.", file=sys.stderr)
                    sys.exit(1)
            else:
                print("Error: Cannot extract final response because the page is closed.", file=sys.stderr)
                sys.exit(1)

            return {"response": output}

        except Exception as e:
            print(f"An error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass


qwen_tool = FunctionTool(qwen_chat)