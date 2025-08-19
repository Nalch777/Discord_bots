import os

# Get the bot token from environment variables
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Get role and channel IDs from environment variables.
# It's good practice to convert them to int, as getenv returns strings.
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID")) if os.getenv("VERIFIED_ROLE_ID") else None
ADMIN_LOG_CHANNEL_ID = int(os.getenv("ADMIN_LOG_CHANNEL_ID")) if os.getenv("ADMIN_LOG_CHANNEL_ID") else None
BOT_LOG_CHANNEL_ID = int(os.getenv("BOT_LOG_CHANNEL_ID")) if os.getenv("BOT_LOG_CHANNEL_ID") else None
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID")) if os.getenv("WELCOME_CHANNEL_ID") else None

# Add checks for None if these are critical and might not be set
if BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set.")
if VERIFIED_ROLE_ID is None:
    raise ValueError("VERIFIED_ROLE_ID environment variable not set.")
if ADMIN_LOG_CHANNEL_ID is None:
    raise ValueError("ADMIN_LOG_CHANNEL_ID environment variable not set.")
if WELCOME_CHANNEL_ID is None:
    raise ValueError("WELCOME_CHANNEL_ID environment variable not set.")
if BOT_LOG_CHANNEL_ID is None:
    raise ValueError("BOT_LOG_CHANNEL_ID environment variable not set.")

# Keep other non-sensitive configurations as they are
VERIFY_BUTTON_LABEL = "Verify Me!"
VERIFICATION_ALREADY_VERIFIED = "You are already a verified member!"
VERIFICATION_NOT_NEW_MEMBER = "You are not a new member eligible for verification."
VERIFICATION_APPROVED_MESSAGE = "You have been approved! Welcome to the server."
VERIFICATION_DENIED_MESSAGE = "Your verification request has been denied."
VERIFY_EMBED_TITLE = "Welcome to the Server!"
VERIFY_EMBED_DESCRIPTION = "Please click the button below to verify yourself and gain access."
ADMIN_LOG_EMBED_TITLE = "New Verification Request"
APPROVED_EMBED_TITLE = "Verification Request Approved"
DENIED_EMBED_TITLE = "Verification Request Denied"

# Example for TEAM_ROLE_MAP (can remain hardcoded if not sensitive or too large)
TEAM_ROLE_MAP = {
    "1577": 123456789012345679, # Team 1577 Role ID
    # Add more teams if needed: "team_number": ROLE_ID
}
