import sys
import time
from typing import Dict
from playwright.sync_api import sync_playwright
from google.adk.tools import ToolContext, FunctionTool

def deepseek_chat(
    message:str,
    cdp_url:str="http://localhost:9222",
    chat_url:str="https://chat.deepseek.com",
    textarea_selector:str="#root > div > div > div.c3ecdb44 > div._7780f2e > div > div > div._9a2f8e4 > div.aaff8b8f > div > div > div._24fad49 > textarea",
    submit_button_selector:str="#root > div > div > div.c3ecdb44 > div._7780f2e > div > div > div._9a2f8e4 > div.aaff8b8f > div > div > div.ec4f5d61 > div.bf38813a > div:nth-child(3)",
    stop_button_selector:str="button:has-text('Stop'), [role='button']:has-text('Stop')",
    response_selector:str=".ds-markdown",
    timeout:int=30000,
    response_timeout:int=300000,
    stop_button_wait_timeout:int=15000,
    post_response_sleep:int=2,
    submit_retry_sleep:int=1,
    output_type:str="text",  # "text" or "html"
    tool_context: ToolContext=None
)-> Dict[str, str]:
    """
    Automate interaction with DeepSeek's web chat interface to send a message and 
    extract the AI-generated response. Designed for ADK tool calling to enable 
    LLM agents to query DeepSeek programmatically via browser automation.
    
    This function connects to a Chromium browser via Chrome DevTools Protocol (CDP),
    navigates to the DeepSeek chat UI, injects a user message, triggers submission,
    waits for streaming response completion (detected via 'Stop' button visibility),
    and extracts the final response content in plain text or HTML format.
    
    Args:
        message (str): The chat message/prompt to send to DeepSeek. Should be a 
                       complete, well-formed query appropriate for the model.
        cdp_url (str, optional): Chrome DevTools Protocol endpoint for browser 
                                 connection. Defaults to "http://localhost:9222".
        chat_url (str, optional): Base URL of the DeepSeek chat interface. Defaults 
                                  to "https://chat.deepseek.com".
        textarea_selector (str, optional): CSS selector for the message input 
                                           textarea element. Use browser dev tools 
                                           to update if UI changes.
        submit_button_selector (str, optional): CSS selector for the send/submit 
                                                button. Adjust if DeepSeek updates 
                                                their DOM structure.
        stop_button_selector (str, optional): CSS selector identifying the 'Stop' 
                                              button that appears during response 
                                              streaming. Used to detect when 
                                              generation is in-progress vs complete.
        response_selector (str, optional): CSS selector for extracting the AI 
                                           response content. Defaults to ".ds-markdown" 
                                           which targets DeepSeek's markdown container.
        timeout (int, optional): Maximum time in milliseconds to wait for initial 
                                 page load and input field availability. Defaults 
                                 to 30000 (30 seconds).
        response_timeout (int, optional): Maximum time in milliseconds to wait for 
                                          the full AI response to complete streaming. 
                                          Defaults to 300000 (5 minutes).
        stop_button_wait_timeout (int, optional): Time in milliseconds to wait for 
                                                  the 'Stop' button to appear after 
                                                  submission. Short timeout allows 
                                                  graceful fallback for fast responses. 
                                                  Defaults to 15000.
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
        - Reuses existing browser tabs/pages when possible to maintain session state.
        - Response completion is inferred from the visibility state of the 'Stop' 
          button, which appears during streaming and disappears when done.
        - Includes fallback selector logic if the primary response_selector fails 
          to match, improving resilience against minor UI updates.
        - All timeouts are in milliseconds except post_response_sleep and 
          submit_retry_sleep which are in seconds for intuitive short delays.
        - Browser is automatically closed in the finally block to prevent leaks.
        - Sensitive to DeepSeek's DOM structure; selectors may require updates if 
          the web UI changes significantly.
    """
    with sync_playwright() as p:
        try:
            # Connect to existing browser over CDP
            print(f"Connecting to browser at {cdp_url}...", file=sys.stderr)
            browser = p.chromium.connect_over_cdp(cdp_url)
            
            # Get the first context or create one
            if not browser.contexts:
                context = browser.new_context()
            else:
                context = browser.contexts[0]
                
            # Get the page or create one
            if not context.pages:
                page = context.new_page()
            else:
                # Look for an existing deepseek page
                domain = chat_url.split("//")[-1].split("/")[0]
                page = next((pg for pg in context.pages if domain in pg.url), None)
                if not page:
                    page = context.new_page()

            # Navigate if not already there
            if chat_url not in page.url:
                print(f"Navigating to {chat_url}...", file=sys.stderr)
                page.goto(chat_url, wait_until="networkidle")
            
            # Wait for the input box to be available
            print("Waiting for chat input...", file=sys.stderr)
            page.wait_for_selector(textarea_selector, timeout=timeout)
            
            # Fill the message
            print(f"Sending message: {message[:50]}...", file=sys.stderr)
            page.fill(textarea_selector, message)
            
            # Click the submit button
            submit_button = page.locator(submit_button_selector)
            if not submit_button.is_enabled():
                # Sometimes it takes a moment to enable after filling
                time.sleep(submit_retry_sleep)
            
            submit_button.click()
            
            # Wait for the response to start (Stop button appears)
            print("Waiting for response...", file=sys.stderr)
            try:
                page.wait_for_selector(stop_button_selector, state="visible", timeout=stop_button_wait_timeout)
            except:
                print(f"Note: Stop button didn't appear within {stop_button_wait_timeout/1000}s. It might be a very fast response or a different UI version.", file=sys.stderr)
            
            # Wait for the response to finish (Stop button disappears)
            try:
                page.wait_for_selector(stop_button_selector, state="hidden", timeout=response_timeout)
            except Exception as e:
                print(f"Warning: Timed out waiting for response to finish: {e}", file=sys.stderr)
            
            # Small delay to ensure all streaming content is rendered
            time.sleep(post_response_sleep)
            
            # Extract the last response
            response_locator = page.locator(response_selector)
            if response_locator.count() > 0:
                last_response = response_locator.last
                if output_type == "html":
                    print(last_response.inner_html())
                else:
                    print(last_response.inner_text())
            else:
                # Fallback: maybe the class changed
                print(f"Error: Could not find response with {response_selector}. Trying fallback...", file=sys.stderr)
                # Try to find any markdown content in the last message
                fallback = page.locator("[class*='markdown']").last
                if fallback.count() > 0:
                    if output_type == "html":
                        print(fallback.inner_html())
                    else:
                        print(fallback.inner_text())
                else:
                    print("Error: Failed to extract response content.", file=sys.stderr)
                    sys.exit(1)

            return {"response": last_response.inner_text()}

        except Exception as e:
            print(f"An error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()


deepseek_tool = FunctionTool(deepseek_chat)