import os
import telebot
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize bot with token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables. Please check your .env file.")

# If running on PythonAnywhere free tier, we MUST configure the proxy explicitly
if "PYTHONANYWHERE_DOMAIN" in os.environ:
    from telebot import apihelper
    apihelper.proxy = {'https': 'http://proxy.server:3128'}

bot = telebot.TeleBot(TOKEN)

# Clear any cached autocomplete commands from Telegram servers
bot.delete_my_commands()

# ------------------------------------------------------------------
# STATE VARIABLES
# ------------------------------------------------------------------

# Dictionary to store the current pending command for each user
user_pending_command = {}

# Dictionary to store commands for active media groups
processed_media_groups = {}

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

# Map team members to their unique Telegram Chat IDs
# Users can find their Chat ID by sending /myid to the bot.
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
    """Generates the help/usage string dynamically based on USAGE_INFO."""
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
    """Handles the welcome and usage guide commands."""
    user_pending_command.pop(message.chat.id, None)
    text = "📚 **News Annotation Bot Commands**\n\n"
    text += "You can use the full name or the short version. Make sure to put the link right after it with a space!\n\n"
    text += get_usage_text()
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['myid'])
def send_id(message):
    """Utility command to allow users to fetch their Chat ID for configuration."""
    user_pending_command.pop(message.chat.id, None)
    chat_id = message.chat.id
    bot.reply_to(message, f"Your Chat ID is: `{chat_id}`", parse_mode="Markdown")

def send_link_to_owner(message, command, link=None, silent=False):
    """Core logic to route the submitted link to the assigned team member.
    If silent=True, just forwards the message without header or confirmation (for album extras)."""
    owner_name = CATEGORIES.get(command)
    owner_id = CHAT_IDS.get(owner_name)
    
    if owner_id and owner_id != "YOUR_ID_HERE":
        try:
            # In silent mode, just copy the message and return (for extra album images)
            if silent:
                bot.copy_message(owner_id, message.chat.id, message.message_id)
                return

            sender_name = message.from_user.first_name or "Unknown"
            if message.from_user.last_name:
                sender_name += f" {message.from_user.last_name}"
            if message.from_user.username:
                sender_name += f" (@{message.from_user.username})"
                
            # Escape Markdown characters in sender_name to prevent parse errors
            sender_name = sender_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                
            # Resolve the full category name for a cleaner notification message
            full_category = command.capitalize()
            for cats in USAGE_INFO.get(owner_name, []):
                if command in cats: 
                    full_category = cats[0].capitalize()
                    break

            # Forward the link or message to the assigned owner
            if link is not None:
                text_to_send = f"📥 **New {full_category} Link from {sender_name}!**\n\n{link}"
                bot.send_message(owner_id, text_to_send, parse_mode="Markdown")
            else:
                text_to_send = f"📥 **New {full_category} Submission from {sender_name}!**"
                bot.send_message(owner_id, text_to_send, parse_mode="Markdown")
                bot.copy_message(owner_id, message.chat.id, message.message_id)

            bot.reply_to(message, f"✅ Successfully sent to **{owner_name}**!", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ Failed to send. Has {owner_name} started a chat with this bot yet?")
    else:
        bot.reply_to(message, f"⚠️ Cannot send! I don't have the Chat ID for **{owner_name}**.", parse_mode="Markdown")

@bot.message_handler(commands=list(CATEGORIES.keys()))
def handle_category(message):
    """Handles category-specific routing commands."""
    parts = message.text.split(maxsplit=1)
    command = parts[0][1:].lower() 
    
    if len(parts) < 2:
        # Prompt the user to provide the article or image in the next message
        user_pending_command[message.chat.id] = command
        bot.reply_to(message, "Please send the article (text, link, or image with caption) now.")
        return
        
    user_pending_command.pop(message.chat.id, None)
    link = parts[1]
    send_link_to_owner(message, command, link)

@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'document', 'audio'])
def handle_message(message):
    """Handles pending commands, media groups, and invalid messages."""
    command = None

    if message.content_type == 'text' and message.text.startswith('/'):
        user_pending_command.pop(message.chat.id, None)
        text = "⚠️ **Error! Invalid command or format.**\n\n"
        text += "You must use one of the following commands along with a link:\n\n"
        text += get_usage_text()
        bot.reply_to(message, text, parse_mode="Markdown")
        return

    # Check if we already know this media_group_id (2nd, 3rd, ... image in album)
    if message.media_group_id and message.media_group_id in processed_media_groups:
        command = processed_media_groups[message.media_group_id]
        send_link_to_owner(message, command, link=None, silent=True)
        return
        
    # Check if there is a pending command
    if message.chat.id in user_pending_command:
        command = user_pending_command[message.chat.id]
        
        # If it's a media group, store the command for other messages in the group
        if message.media_group_id:
            processed_media_groups[message.media_group_id] = command
            # Keep dict bounded to prevent memory leak
            if len(processed_media_groups) > 1000:
                processed_media_groups.pop(next(iter(processed_media_groups)))
            
        user_pending_command.pop(message.chat.id, None)
        send_link_to_owner(message, command, link=None)
        return

    # If we got here, it's an invalid message
    text = "⚠️ **Error! Invalid command or format.**\n\n"
    text += "You must use one of the following commands along with a link:\n\n"
    text += get_usage_text()
    bot.reply_to(message, text, parse_mode="Markdown")

if __name__ == "__main__":
    print("🤖 Telegram routing bot is running! Press Ctrl+C to stop.")
    bot.infinity_polling()
