import os
import telebot
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("[Error] TELEGRAM_BOT_TOKEN not found in .env file!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

def setup():
    print("Welcome to the Vercel Webhook Setup!")
    print("Please enter the URL of your deployed Vercel app.")
    print("Example: https://my-fake-news-bot.vercel.app")
    
    url = input("\nYour Vercel URL: ").strip()
    
    # Remove trailing slash if present
    if url.endswith('/'):
        url = url[:-1]
        
    if not url.startswith("https://"):
        print("[Error] URL must start with https://")
        return

    webhook_url = f"{url}/api/webhook"
    
    print(f"\nSetting webhook to: {webhook_url}")
    
    try:
        # First remove any existing webhook
        bot.remove_webhook()
        # Set the new webhook
        success = bot.set_webhook(url=webhook_url)
        
        if success:
            print("[Success] Webhook successfully set!")
            print("Telegram will now send all messages directly to your Vercel app.")
            print("You can close this script. Do NOT run the polling bot script anymore!")
        else:
            print("[Error] Failed to set webhook. Please check your token and URL.")
            
    except Exception as e:
        print(f"[Error] An error occurred: {e}")

if __name__ == "__main__":
    setup()
