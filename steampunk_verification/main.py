# main.py
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord.utils import get
import config
import asyncio
import logging
import os
from flask import Flask, request # Import request to access incoming request data
import threading
import sys


# --- Redirect stdout/stderr into logging ---
class StreamToLogger:
    def __init__(self, logger, log_level):
        self.logger = logger
        self.log_level = log_level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())

    def flush(self):
        pass

stdout_logger = logging.getLogger("STDOUT")
stderr_logger = logging.getLogger("STDERR")

sys.stdout = StreamToLogger(stdout_logger, logging.INFO)
sys.stderr = StreamToLogger(stderr_logger, logging.ERROR)

# --- Discord logging handler ---
class DiscordHandler(logging.Handler):
    def __init__(self, bot, channel_id: int):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

    def emit(self, record):
        if record.levelno >= logging.WARNING:
            log_entry = self.format(record)
            # schedule coroutine safely
            asyncio.run_coroutine_threadsafe(self._send_log(log_entry, record.levelname), self.bot.loop)

    async def _send_log(self, message: str, levelname: str):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.channel_id)
        if channel:
            try:
                # prevent flooding: Discord message max 2000 chars
                if len(message) > 1900:
                    message = message[:1900] + "… (truncated)"
                await channel.send(f"📜 `{levelname}`: {message}")
            except Exception as e:
                logging.error(f"Failed to send log to Discord: {e}")

def setup_discord_logging(bot, log_channel_id: int):
    discord_handler = DiscordHandler(bot, log_channel_id)
    discord_handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logging.getLogger().addHandler(discord_handler)
    
# Configure logging for discord.py
# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
#logging.basicConfig(level=logging.INFO, handlers=[handler])
logging.basicConfig(level=logging.INFO)
# Optionally, set discord.py's logging to DEBUG for more verbose output
# logging.getLogger('discord').setLevel(logging.DEBUG)

# Define intents
intents = discord.Intents.default()
intents.members = True  # Required to track new members and manage roles
intents.message_content = True  # Required to read message content (for commands if any, though not strictly needed for this workflow)
intents.guilds = True  # Required for guild events

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Create a Flask app instance
app = Flask(__name__)

# Configure Flask logging
flask_logger = logging.getLogger('flask_app')
flask_logger.setLevel(logging.INFO)
flask_logger.propagate = True
# flask_logger.addHandler(handler) # Use the same handler as discord.py for consistency

@app.before_request
def log_request_info():
    """Logs information about incoming requests."""
    flask_logger.warning(f"Incoming Request: {request.method} {request.url}")
    if request.data:
        flask_logger.warning(f"Request Data: {request.data.decode('utf-8')}")

@app.after_request
def log_response_info(response):
    """Logs information about outgoing responses."""
    flask_logger.warning(f"Outgoing Response: Status {response.status_code}")
    # You might want to log response data only for certain content types or if it's not too large
    # if response.is_json:
    #     flask_logger.info(f"Response Data: {response.get_data(as_text=True)}")
    return response

@app.route('/')
def home():
    """Home route for the Flask app, indicates the bot is running."""
    flask_logger.warning("Serving / route.")
    return "Bot is running!"

def run_flask():
    """Starts the Flask server."""
    port = int(os.environ.get("PORT", 5000)) # Render provides PORT env var
    flask_logger.warning(f"Flask app starting on host 0.0.0.0, port {port}")
    app.run(host='0.0.0.0', port=port)

# --- Views for Welcome and Admin Approval ---

class WelcomeView(View):
    """
    A persistent view that contains the verification button for new members.
    This view remains active indefinitely (timeout=None).
    """
    def __init__(self):
        super().__init__(timeout=None) # Keep the view active indefinitely

    @discord.ui.button(label=config.VERIFY_BUTTON_LABEL, style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Callback for the 'Verify' button.
        Checks if the user is already verified and, if not, presents the verification modal.
        """
        member = interaction.user
        logging.warning(f"Verify button clicked by {member.name} (ID: {member.id}).")

        # Check if user already has the Verified role
        verified_role = get(member.guild.roles, id=config.VERIFIED_ROLE_ID)
        if verified_role and verified_role in member.roles:
            logging.warning(f"{member.name} already has the Verified role. Sending ephemeral message.")
            await interaction.response.send_message(
                config.VERIFICATION_ALREADY_VERIFIED, ephemeral=True
            )
            return

        # Show the verification modal
        logging.warning(f"Presenting VerificationModal to {member.name}.")
        await interaction.response.send_modal(VerificationModal(title="Verification Form"))

class AdminApprovalView(View):
    """
    A view presented to administrators in the log channel, allowing them to
    approve or deny a user's verification request.
    """
    def __init__(self, member_id: int, name: str, team_number: str):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.name = name
        self.team_number = team_number
        logging.warning(f"AdminApprovalView init: member_id={member_id}, name={name}, team_number={team_number}")

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Callback for the 'Approve' button.
        Assigns the Verified role (and optionally a team role) to the user and updates the log message.
        """
        logging.warning(f"Approve button clicked by {interaction.user.name} for member ID: {self.member_id}.")
        await interaction.response.defer() # Acknowledge the interaction immediately

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        if member is None:
            logging.error(f"User with ID {self.member_id} not found during approval (might have left).")
            await interaction.followup.send(f"Error: Could not find user with ID {self.member_id}. They might have left the server.", ephemeral=True)
            self.stop() # Stop the view if member is gone
            await interaction.message.delete() # Delete the original log message to clean up
            return

        verified_role = get(guild.roles, id=config.VERIFIED_ROLE_ID)
        
        roles_to_add = []
        if verified_role:
            roles_to_add.append(verified_role)
            logging.warning(f"Adding role: {verified_role.name} ({verified_role.id}) to {member.name}.")

        # Handle team role (uncomment if you re-enable team role assignment)
        # if self.team_number:
        #     team_role_id = config.TEAM_ROLE_MAP.get(self.team_number.lower())
        #     if team_role_id:
        #         team_role_obj = get(guild.roles, id=team_role_id)
        #         if team_role_obj:
        #             roles_to_add.append(team_role_obj)
        #             logging.info(f"Adding team role: {team_role_obj.name} ({team_role_obj.id}) to {member.name}.")
        #         else:
        #             logging.warning(f"Team role for '{self.team_number}' (ID: {team_role_id}) not found in server.")
        #             await interaction.followup.send(
        #                 f"Warning: Team role for '{self.team_number}' (ID: {team_role_id}) not found in server.",
        #                 ephemeral=True
        #             )
        #     else:
        #         logging.info(f"No team role mapping found for team number '{self.team_number}'.")
        #         await interaction.followup.send(
        #             f"Warning: No team role mapping found for team number '{self.team_number}'.",
        #             ephemeral=True
        #         )

        try:
            if roles_to_add:
                await member.add_roles(*roles_to_add)
                logging.warning(f"Successfully added roles to {member.name}.")
            
            # Update the admin log message
            for child in self.children:
                child.disabled = True
            embed = interaction.message.embeds[0]
            embed.title = config.APPROVED_EMBED_TITLE
            embed.color = discord.Color.green()
            embed.add_field(name="Status", value=f"Approved by {interaction.user.mention}", inline=False)
            await interaction.message.edit(embed=embed, view=self)
            logging.warning(f"Admin log message updated to 'Approved' for {member.name}.")

            # DM the user
            try:
                await member.send(config.VERIFICATION_APPROVED_MESSAGE)
                logging.warning(f"Sent approval DM to {member.name}.")
            except discord.Forbidden:
                logging.warning(f"Could not DM {member.name}. User has DMs disabled.")
            except Exception as e:
                logging.error(f"Error DMing user {member.name} on approval: {e}")

        except discord.Forbidden:
            logging.error(f"Bot lacks permissions to manage roles for {member.name}. Check role hierarchy.")
            await interaction.followup.send(
                "I don't have permission to manage roles. Please check my role hierarchy.",
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"An error occurred during approval for {member.name}: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred during approval: {e}", ephemeral=True
            )
        finally:
            self.stop() # Stop the view after processing

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="deny_button")
    async def deny_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Callback for the 'Deny' button.
        Updates the log message and DMs the user about the denial.
        """
        logging.warning(f"Deny button clicked by {interaction.user.name} for member ID: {self.member_id}.")
        await interaction.response.defer() # Acknowledge the interaction immediately

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        if member is None:
            logging.warning(f"User with ID {self.member_id} not found during denial (might have left).")
            await interaction.followup.send(f"Error: Could not find user with ID {self.member_id}. They might have left the server.", ephemeral=True)
            self.stop()
            await interaction.message.delete() # Delete the original log message to clean up
            return
        
        # Update the admin log message
        for child in self.children:
            child.disabled = True
        embed = interaction.message.embeds[0]
        embed.title = config.DENIED_EMBED_TITLE
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"Denied by {interaction.user.mention}", inline=False)
        await interaction.message.edit(embed=embed, view=self)
        logging.warning(f"Admin log message updated to 'Denied' for {member.name}.")

        # DM the user
        try:
            await member.send(config.VERIFICATION_DENIED_MESSAGE)
            logging.warning(f"Sent denial DM to {member.name}.")
        except discord.Forbidden:
            logging.warning(f"Could not DM {member.name}. User has DMs disabled.")
        except Exception as e:
            logging.error(f"Error DMing user {member.name} on denial: {e}")
        finally:
            self.stop() # Stop the view after processing

# --- Modal for User Input ---
class VerificationModal(Modal):
    """
    A modal form presented to users to collect their name and team number for verification.
    """
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.add_item(
            TextInput(
                label="Your Name",
                placeholder="e.g., John Doe",
                required=True,
                max_length=100,
                custom_id="name_input",
            )
        )
        self.add_item(
            TextInput(
                label="Team Number (if applicable)",
                placeholder="e.g., 1, 2, 3 (leave blank if no team)",
                required=False,
                max_length=20,
                custom_id="team_input",
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        """
        Callback when the verification modal is submitted.
        Collects user input and sends it to the admin log channel for review.
        """
        logging.warning(f"VerificationModal submitted by {interaction.user.name} (ID: {interaction.user.id}).")
        member = interaction.user
        name = self.children[0].value
        team_number = self.children[1].value.strip()

        logging.warning(f"Modal data received: User={member.id}, Name='{name}', Team='{team_number}'.")

        admin_channel = bot.get_channel(config.ADMIN_LOG_CHANNEL_ID)
        if not admin_channel:
            logging.error(f"Admin log channel not found for ID: {config.ADMIN_LOG_CHANNEL_ID}. Cannot send verification request.")
            await interaction.response.send_message(
                "Error: Admin log channel not found. Please contact an admin.",
                ephemeral=True
            )
            return
        logging.warning(f"Admin channel found: {admin_channel.name} ({admin_channel.id}).")

        embed = discord.Embed(
            title=config.ADMIN_LOG_EMBED_TITLE,
            color=discord.Color.blue(),
            description=f"User: {member.mention} (`{member.id}`)"
        )
        embed.add_field(name="Submitted Name", value=name, inline=True)
        embed.add_field(name="Submitted Team #", value=team_number if team_number else "N/A", inline=True)
        embed.set_footer(text="Review and approve/deny below.")
        logging.warning("Verification request embed created.")

        admin_view = AdminApprovalView(member.id, name, team_number)
        logging.warning("AdminApprovalView instance created for the request.")
        
        try:
            await admin_channel.send(embed=embed, view=admin_view)
            logging.warning(f"Successfully sent verification request to admin channel ({admin_channel.name}) for {member.name}.")
            await interaction.response.send_message(
                "Your verification request has been submitted! An admin will review it shortly.",
                ephemeral=True
            )
            logging.warning("Ephemeral message sent to user confirming submission.")
        except discord.Forbidden:
            logging.error(f"Forbidden permission when sending to admin log channel ({admin_channel.name}). Check bot's role hierarchy and channel permissions.", exc_info=True)
            await interaction.response.send_message(
                "Error: I don't have permission to send to the admin log channel. Please contact an admin.",
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"An unexpected error occurred during modal submission callback for {member.name}: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An unexpected error occurred during submission. Error: {e}. Please try again later or contact an admin.",
                ephemeral=True
            )


# --- Bot Events ---

@bot.event
async def on_ready():
    """
    Event handler that runs when the bot successfully connects to Discord.
    Ensures the welcome message is sent to the designated channel.
    """
    logging.warning(f"Logged in as {bot.user} (ID: {bot.user.id})")
    setup_discord_logging(bot, config.BOT_LOG_CHANNEL_ID)
    # Ensure the welcome message is sent if it's not already there
    await send_welcome_message()

@bot.event
async def on_member_join(member):
    """
    Event handler that runs when a new member joins the guild.
    Sends a welcome message to the designated channel if one isn't already present.
    """
    logging.warning(f"Member joined: {member.name} (ID: {member.id}).")
    welcome_channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if welcome_channel:
        embed = discord.Embed(
            title=config.VERIFY_EMBED_TITLE,
            description=config.VERIFY_EMBED_DESCRIPTION,
            color=discord.Color.blue()
        )
        
        # Check if the channel history already contains a message with the custom_id
        # to avoid sending multiple welcome messages. We look for bot's own message with the button.
        messages = []
        try:
            messages = [msg async for msg in welcome_channel.history(limit=50)]
        except discord.Forbidden:
            logging.error(f"Bot does not have permission to read message history in {welcome_channel.name}.")
            
        found_welcome_message = False
        for msg in messages:
            if msg.author == bot.user and msg.embeds and msg.components:
                # Check for a component with the specific custom_id
                for component_row in msg.components:
                    for component in component_row.children:
                        if isinstance(component, discord.ui.Button) and component.custom_id == "verify_button":
                            found_welcome_message = True
                            break
                    if found_welcome_message:
                        break
            if found_welcome_message:
                break
        
        if not found_welcome_message:
            await welcome_channel.send(embed=embed, view=WelcomeView())
            logging.warning(f"Sent welcome message to {welcome_channel.name} for new member {member.name}.")
        else:
            logging.wawrning(f"Welcome message already found in {welcome_channel.name}. Not sending again on member join.")


async def send_welcome_message():
    """
    Sends the initial welcome message to the designated channel.
    This function is called on bot startup to ensure the message is present.
    """
    welcome_channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if welcome_channel:
        # Check if the channel history already contains a message with the custom_id
        # to avoid sending multiple welcome messages on bot restart
        messages = []
        try:
            messages = [msg async for msg in welcome_channel.history(limit=50)]
        except discord.Forbidden:
            logging.error(f"Bot does not have permission to read message history in {welcome_channel.name}.")
            
        found_welcome_message = False
        for msg in messages:
            if msg.author == bot.user and msg.embeds and msg.components:
                for component_row in msg.components:
                    for component in component_row.children:
                        if isinstance(component, discord.ui.Button) and component.custom_id == "verify_button":
                            found_welcome_message = True
                            break
                    if found_welcome_message:
                        break
            if found_welcome_message:
                break
        
        if not found_welcome_message:
            embed = discord.Embed(
                title=config.VERIFY_EMBED_TITLE,
                description=config.VERIFY_EMBED_DESCRIPTION,
                color=discord.Color.blue()
            )
            await welcome_channel.send(embed=embed, view=WelcomeView())
            logging.warning(f"Initial welcome message sent to {welcome_channel.name}.")
        else:
            logging.warning(f"Welcome message already found in {welcome_channel.name}. Not sending again on startup.")

if __name__ == '__main__':
    # Start the Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start the Discord bot
    bot.run(config.BOT_TOKEN)

