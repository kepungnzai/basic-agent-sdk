import argparse
from playwright.sync_api import sync_playwright
from tools import deepseek_chat, qwen_chat, load_and_display_page


def main():
    parser = argparse.ArgumentParser(description="DeepSeek Chat CLI via CDP")
    parser.add_argument("message", help="Message to send to DeepSeek")
    args = parser.parse_args()
    
    #deepseek_chat(args.message)
    #qwen_chat(args.message)
    load_and_display_page("https://www.bing.com/search?q=playwright+python", output_mode = 2)

if __name__ == "__main__":
    main()
