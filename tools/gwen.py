import sys
import time
from playwright.sync_api import sync_playwright

def qwen_chat(
    message,
    cdp_url="http://localhost:9222",
    chat_url="https://qwen.ai/home",
    textarea_selector="#GLOBAL_ID\.QWEN_AI_LAYOUT_CONTENT > div.Home--aXgE3ZET > div > div.MessageInput--huaOYrdW.medium--Kgej7Ilm > div.MessageInput__Content--G_9hiWE8.medium--Kgej7Ilm > textarea",
    submit_button_selector="#GLOBAL_ID\.QWEN_AI_LAYOUT_CONTENT > div.Home--aXgE3ZET > div > div.MessageInput--huaOYrdW.medium--Kgej7Ilm > div.MessageInput__Content--G_9hiWE8.medium--Kgej7Ilm > div > i",
    stop_button_selector="button:has-text('Stop'), [role='button']:has-text('Stop')",
    response_selector=".ds-markdown",
    timeout=30000,
    response_timeout=300000,
    stop_button_wait_timeout=15000,
    post_response_sleep=2,
    submit_retry_sleep=1,
    output_type="text"  # "text" or "html"
):
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
                # Look for an existing Qwen page
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

        except Exception as e:
            print(f"An error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()
