import os
import telebot
from flask import Flask, request
from dotenv import load_dotenv

# Load environment variables (mostly for local testing; Vercel provides these automatically)
load_dotenv()

# Initialize bot with token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables.")

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

# Map team members to their unique Telegram Chat IDs
CHAT_IDS = {
    "Rafsan": "1440433977",
    "Airin": "5836166718",
    "Mansib": "5246681901",
    "Eshika": "1892288693",
    "Faysal": "6340571023"
}

# Map specific commands (both full and short versions) to team members
CATEGORIES = {
    "sports": "Rafsan", "s": "Rafsan",
    "international": "Rafsan", "i": "Rafsan",
    "politics": "Airin", "p": "Airin",
    "entertainment": "Airin", "ent": "Airin",
    "science": "Mansib", "sci": "Mansib",
    "environment": "Mansib", "env": "Mansib",
    "religion": "Eshika", "r": "Eshika",
    "technology": "Eshika", "t": "Eshika",
    "education": "Faysal", "edu": "Faysal",
    "health": "Faysal", "h": "Faysal"
}

# Grouping for generating the /usage command output
USAGE_INFO = {
    "Rafsan": [("sports", "s"), ("international", "i")],
    "Airin": [("politics", "p"), ("entertainment", "ent")],
    "Mansib": [("science", "sci"), ("environment", "env")],
    "Eshika": [("religion", "r"), ("technology", "t")],
    "Faysal": [("education", "edu"), ("health", "h")],
}

# ------------------------------------------------------------------
# UTILITY FUNCTIONS
# ------------------------------------------------------------------

def get_usage_text():
    text = ""
    for owner, cats in USAGE_INFO.items():
        text += f"👤 **{owner}**:\n"
        for long_cat, short_cat in cats:
            text += f"   • `/{long_cat}` (shortcut: `/{short_cat}`)\n"
        text += "\n"
        
    text += "📝 **Example usage:**\n"
    text += "`/p https://news.com`\n"
    text += "`/politics https://news.com`\n\n"
    text += "To get your Chat ID, type: `/myid`"
    return text

# ------------------------------------------------------------------
# COMMAND HANDLERS
# ------------------------------------------------------------------

@bot.message_handler(commands=['usage', 'help', 'start'])
def send_usage(message):
    text = "📚 **News Annotation Bot Commands**\n\n"
    text += "You can use the full name or the short version. Make sure to put the link right after it with a space!\n\n"
    text += get_usage_text()
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['myid'])
def send_id(message):
    chat_id = message.chat.id
    bot.reply_to(message, f"Your Chat ID is: `{chat_id}`", parse_mode="Markdown")

def send_link_to_owner(message, command, link):
    owner_name = CATEGORIES.get(command)
    owner_id = CHAT_IDS.get(owner_name)
    
    if owner_id and owner_id != "YOUR_ID_HERE":
        try:
            sender_name = message.from_user.first_name
            full_category = command.capitalize()
            for cats in USAGE_INFO.get(owner_name, []):
                if command in cats: 
                    full_category = cats[0].capitalize()
                    break

            text_to_send = f"📥 **New {full_category} Link from {sender_name}!**\n\n{link}"
            bot.send_message(owner_id, text_to_send, parse_mode="Markdown")
            bot.reply_to(message, f"✅ Successfully sent to **{owner_name}**!", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Failed to send. Has {owner_name} started a chat with this bot yet?")
    else:
        bot.reply_to(message, f"⚠️ Cannot send! I don't have the Chat ID for **{owner_name}**.", parse_mode="Markdown")

@bot.message_handler(commands=list(CATEGORIES.keys()))
def handle_category(message):
    parts = message.text.split(maxsplit=1)
    command = parts[0][1:].lower() 
    
    if len(parts) < 2:
        msg = f"⚠️ **Error!** You forgot to provide the link.\n\nPlease type it like this:\n`/{command} https://your-link.com`"
        bot.reply_to(message, msg, parse_mode="Markdown")
        return
        
    link = parts[1]
    send_link_to_owner(message, command, link)

@bot.message_handler(func=lambda message: True)
def handle_invalid(message):
    text = "⚠️ **Error! Invalid command or format.**\n\n"
    text += "You must use one of the following commands along with a link:\n\n"
    text += get_usage_text()
    bot.reply_to(message, text, parse_mode="Markdown")


# ------------------------------------------------------------------
# VERCEL WEBHOOK ROUTE
# ------------------------------------------------------------------

@app.route('/', methods=['GET'])
def index():
    return "Telegram Routing Bot is running on Vercel Serverless Functions!", 200

@app.route('/api/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

# Vercel entry point
if __name__ == "__main__":
    app.run(debug=True, port=8000)
