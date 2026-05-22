import sys
import time
from playwright.sync_api import sync_playwright

def deepseek_chat(message):
    with sync_playwright() as p:
        try:
            # Connect to existing browser over CDP
            print("Connecting to browser at http://localhost:9222...", file=sys.stderr)
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            
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
                page = next((pg for pg in context.pages if "chat.deepseek.com" in pg.url), None)
                if not page:
                    page = context.new_page()

            # Navigate if not already there
            if "chat.deepseek.com" not in page.url:
                print("Navigating to https://chat.deepseek.com...", file=sys.stderr)
                page.goto("https://chat.deepseek.com", wait_until="networkidle")
            
            # Wait for the input box to be available
            print("Waiting for chat input...", file=sys.stderr)
            page.wait_for_selector("#root > div > div > div.c3ecdb44 > div._7780f2e > div > div > div._9a2f8e4 > div.aaff8b8f > div > div > div._24fad49 > textarea", timeout=30000)
            
            # Fill the message
            print(f"Sending message: {message[:50]}...", file=sys.stderr)
            page.fill("#root > div > div > div.c3ecdb44 > div._7780f2e > div > div > div._9a2f8e4 > div.aaff8b8f > div > div > div._24fad49 > textarea", message)
            
            # Click the submit button
            submit_button = page.locator("#root > div > div > div.c3ecdb44 > div._7780f2e > div > div > div._9a2f8e4 > div.aaff8b8f > div > div > div.ec4f5d61 > div.bf38813a > div:nth-child(3)")
            if not submit_button.is_enabled():
                # Sometimes it takes a moment to enable after filling
                time.sleep(1)
            
            submit_button.click()
            
            # Wait for the response to start (Stop button appears)
            print("Waiting for response...", file=sys.stderr)
            stop_button_selector = "button:has-text('Stop'), [role='button']:has-text('Stop')"
            try:
                page.wait_for_selector(stop_button_selector, state="visible", timeout=15000)
            except:
                print("Note: Stop button didn't appear within 15s. It might be a very fast response or a different UI version.", file=sys.stderr)
            
            # Wait for the response to finish (Stop button disappears)
            try:
                page.wait_for_selector(stop_button_selector, state="hidden", timeout=300000)
            except Exception as e:
                print(f"Warning: Timed out waiting for response to finish: {e}", file=sys.stderr)
            
            # Small delay to ensure all streaming content is rendered
            time.sleep(2)
            
            # Extract the last response HTML
            # DeepSeek uses .ds-markdown for the message content
            # We look for it within the message list to be sure
            response_locator = page.locator(".ds-markdown")
            if response_locator.count() > 0:
                html = response_locator.last.inner_html()
                print(html)
            else:
                # Fallback: maybe the class changed
                print("Error: Could not find response with .ds-markdown. Trying fallback...", file=sys.stderr)
                # Try to find any markdown content in the last message
                fallback = page.locator("[class*='markdown']").last
                if fallback.count() > 0:
                    print(fallback.inner_html())
                else:
                    print("Error: Failed to extract response content.", file=sys.stderr)
                    sys.exit(1)

        except Exception as e:
            print(f"An error occurred: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            browser.close()
