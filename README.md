

Install the dependencies

uv pip install .

Run chrome in debug mode

"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\chrome-debug

And then run the following code from the command line

python main.py "Write a hello world program in Python"


# 1. Load a page
browser_interact(action="load", page_url="https://example.com/login", tool_context=ctx)

# 2. Type into username field
browser_interact(action="type", input_selector="#username", text="myuser", tool_context=ctx)

# 3. Type password
browser_interact(action="type", input_selector="#password", text="pass123", tool_context=ctx)

# 4. Click login button
browser_interact(action="click", click_selector="#login-btn", tool_context=ctx)

# 5. Extract the resulting dashboard
result = browser_interact(action="extract", content_selector=".dashboard", tool_context=ctx)
print(result["response"])

# 6. Done – close the browser when finished
browser_interact(action="close", tool_context=ctx)