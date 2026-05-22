import argparse
from playwright.sync_api import sync_playwright
from tools import deepseek_chat

def main():
    parser = argparse.ArgumentParser(description="DeepSeek Chat CLI via CDP")
    parser.add_argument("message", help="Message to send to DeepSeek")
    args = parser.parse_args()
    
    deepseek_chat(args.message)

if __name__ == "__main__":
    main()
