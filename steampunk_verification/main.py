# main.py
import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord.utils import get
import config
import asyncio
import logging # ADD THIS LINE

# ADD THIS BLOCK FOR DISCORD.PY LOGGING
# Configure logging
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[handler])
# Optionally, set discord.py's logging to DEBUG for more verbose output
# logging.getLogger('discord').setLevel(logging.DEBUG)

# Define intents
intents = discord.Intents.default()
intents.members = True  # Required to track new members and manage roles
intents.message_content = True  # Required to read message content (for commands if any, though not strictly needed for this workflow)
intents.guilds = True  # Required for guild events

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Views for Welcome and Admin Approval ---

class WelcomeView(View):
    def __init__(self):
        super().__init__(timeout=None) # Keep the view active indefinitely

    @discord.ui.button(label=config.VERIFY_BUTTON_LABEL, style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user

        # Check if user already has the Verified role
        verified_role = get(member.guild.roles, id=config.VERIFIED_ROLE_ID)
        if verified_role and verified_role in member.roles:
            await interaction.response.send_message(
                config.VERIFICATION_ALREADY_VERIFIED, ephemeral=True
            )
            return

        # --- MODIFIED: Removed check for Unverified role, as new users won't get it ---
        # If new users don't get the Unverified role automatically, this check is no longer needed
        # If you still want to ensure only "new" users (e.g., those without Verified role) can click,
        # the 'verified_role' check above is sufficient.
        # unverified_role = get(member.guild.roles, id=config.UNVERIFIED_ROLE_ID)
        # if not unverified_role or unverified_role not in member.roles:
        #     await interaction.response.send_message(
        #         config.VERIFICATION_NOT_NEW_MEMBER, ephemeral=True
        #     )
        #     return

        # Show the verification modal
        await interaction.response.send_modal(VerificationModal(title="Verification Form"))

# Add prints to AdminApprovalView as well, in case something is happening there
class AdminApprovalView(View):
    def __init__(self, member_id: int, name: str, team_number: str):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.name = name
        self.team_number = team_number
        print(f"AdminApprovalView init: member_id={member_id}, name={name}, team_number={team_number}") # Diagnostic print

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id="approve_button")
    async def approve_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        print("Approve button clicked.") # Diagnostic print
        await interaction.response.defer() # Acknowledge the interaction immediately

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        if member is None:
            await interaction.followup.send(f"Error: Could not find user with ID {self.member_id}. They might have left the server.", ephemeral=True)
            self.stop() # Stop the view if member is gone
            await interaction.message.delete() # Delete the original log message to clean up
            return

        verified_role = get(guild.roles, id=config.VERIFIED_ROLE_ID)
        # --- MODIFIED: Removed fetching unverified_role if it's not being assigned/removed ---
        # unverified_role = get(guild.roles, id=config.UNVERIFIED_ROLE_ID) 
        
        roles_to_add = []
        if verified_role:
            roles_to_add.append(verified_role)

        # Handle team role
        # if self.team_number: # Only try to get team role if a team number was provided
        #     team_role_id = config.TEAM_ROLE_MAP.get(self.team_number.lower()) # Use .lower() for case-insensitive matching
        #     if team_role_id:
        #         team_role_obj = get(guild.roles, id=team_role_id)
        #         if team_role_obj:
        #             roles_to_add.append(team_role_obj)
        #         else:
        #             await interaction.followup.send(
        #                 f"Warning: Team role for '{self.team_number}' (ID: {team_role_id}) not found in server.",
        #                 ephemeral=True
        #             )
        #     else:
        #         await interaction.followup.send(
        #             f"Warning: No team role mapping found for team number '{self.team_number}'.",
        #             ephemeral=True
        #         )

        roles_to_remove = []
        # if unverified_role and unverified_role in member.roles:
        #     roles_to_remove.append(unverified_role)

        try:
            if roles_to_add:
                # Add roles, if any
                await member.add_roles(*roles_to_add)
                
            if roles_to_remove:
                # Remove roles, if any (this block will be empty now if unverified role isn't removed)
                await member.remove_roles(*roles_to_remove)

            # Update the admin log message
            # self.disable_all_items()
            for child in self.children:
                child.disabled = True
            embed = interaction.message.embeds[0]
            embed.title = config.APPROVED_EMBED_TITLE
            embed.color = discord.Color.green()
            embed.add_field(name="Status", value=f"Approved by {interaction.user.mention}", inline=False)
            await interaction.message.edit(embed=embed, view=self)

            # DM the user
            try:
                await member.send(config.VERIFICATION_APPROVED_MESSAGE)
            except discord.Forbidden:
                print(f"Could not DM {member.name}. User has DMs disabled.")
            except Exception as e:
                print(f"Error DMing user on approval: {e}")

        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to manage roles. Please check my role hierarchy.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"An error occurred during approval: {e}", ephemeral=True
            )
        finally:
            self.stop() # Stop the view after processing

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="deny_button")
    async def deny_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        print("Deny button clicked.") # Diagnostic print
        await interaction.response.defer() # Acknowledge the interaction immediately

        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        if member is None:
            await interaction.followup.send(f"Error: Could not find user with ID {self.member_id}. They might have left the server.", ephemeral=True)
            self.stop()
            await interaction.message.delete() # Delete the original log message to clean up
            return

        # --- MODIFIED: Removed unverified role removal logic if not assigned ---
        # unverified_role = get(guild.roles, id=config.UNVERIFIED_ROLE_ID) 
        # if unverified_role and unverified_role in member.roles:
        #     try:
        #         await member.remove_roles(unverified_role)
        #     except discord.Forbidden:
        #         await interaction.followup.send(
        #             "I don't have permission to remove the unverified role. Please check my role hierarchy.",
        #             ephemeral=True
        #         )
        #     except Exception as e:
        #         await interaction.followup.send(
        #             f"An error occurred during denial (role removal): {e}", ephemeral=True
        #         )
        
        # Update the admin log message
        self.disable_all_items()
        embed = interaction.message.embeds[0]
        embed.title = config.DENIED_EMBED_TITLE
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"Denied by {interaction.user.mention}", inline=False)
        await interaction.message.edit(embed=embed, view=self)

        # DM the user
        try:
            await member.send(config.VERIFICATION_DENIED_MESSAGE)
        except discord.Forbidden:
            print(f"Could not DM {member.name}. User has DMs disabled.")
        except Exception as e:
            print(f"Error DMing user on denial: {e}")
        finally:
            self.stop() # Stop the view after processing

# --- Modal for User Input ---
class VerificationModal(Modal):
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
        print("Modal callback entered.") # Diagnostic print
        member = interaction.user
        name = self.children[0].value
        team_number = self.children[1].value.strip()

        print(f"Modal data received: User={member.id}, Name={name}, Team={team_number}") # Diagnostic print

        admin_channel = bot.get_channel(config.ADMIN_LOG_CHANNEL_ID)
        if not admin_channel:
            print(f"ERROR: Admin log channel not found for ID: {config.ADMIN_LOG_CHANNEL_ID}") # Diagnostic print
            await interaction.response.send_message(
                "Error: Admin log channel not found. Please contact an admin.",
                ephemeral=True
            )
            return
        print(f"Admin channel found: {admin_channel.name} ({admin_channel.id})") # Diagnostic print

        embed = discord.Embed(
            title=config.ADMIN_LOG_EMBED_TITLE,
            color=discord.Color.blue(),
            description=f"User: {member.mention} (`{member.id}`)"
        )
        embed.add_field(name="Submitted Name", value=name, inline=True)
        embed.add_field(name="Submitted Team #", value=team_number if team_number else "N/A", inline=True)
        embed.set_footer(text="Review and approve/deny below.")
        print("Embed created.") # Diagnostic print

        admin_view = AdminApprovalView(member.id, name, team_number)
        print("AdminApprovalView instance created.") # Diagnostic print
        
        try:
            await admin_channel.send(embed=embed, view=admin_view)
            print(f"Successfully sent verification request to admin channel ({admin_channel.name}) for {member.name}.") # Diagnostic print
            await interaction.response.send_message(
                "Your verification request has been submitted! An admin will review it shortly.",
                ephemeral=True
            )
            print("Ephemeral message sent to user.") # Diagnostic print
        except discord.Forbidden:
            print(f"ERROR: Forbidden permission when sending to admin log channel ({admin_channel.name}). Check bot's role hierarchy and channel permissions.") # Diagnostic print
            await interaction.response.send_message(
                "Error: I don't have permission to send to the admin log channel. Please contact an admin.",
                ephemeral=True
            )
        except Exception as e:
            print(f"AN UNEXPECTED ERROR OCCURRED during modal submission callback: {e}") # Diagnostic print
            import traceback
            traceback.print_exc() # Print full traceback to console
            await interaction.response.send_message(
                f"An unexpected error occurred during submission. Error: {e}. Please try again later or contact an admin.",
                ephemeral=True
            )


# --- Bot Events ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # Ensure the welcome message is sent if it's not already there
    await send_welcome_message()

@bot.event
async def on_member_join(member):
    welcome_channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if welcome_channel:
        # --- MODIFIED: Removed automatic assignment of Unverified role ---
        # If you want to automatically assign the Unverified role uncomment the block below
        # and ensure your server's default roles do NOT assign it.
        # unverified_role = get(member.guild.roles, id=config.UNVERIFIED_ROLE_ID)
        # if unverified_role:
        #     try:
        #         await member.add_roles(unverified_role)
        #         print(f"Assigned Unverified role to {member.name}")
        #     except discord.Forbidden:
        #         print(f"ERROR: Bot does not have permissions to assign {unverified_role.name} role. Check role hierarchy.")
        
        # Send the welcome message if not already present
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
            print(f"ERROR: Bot does not have permission to read message history in {welcome_channel.name}.")
            
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
            print(f"Sent welcome message to {welcome_channel.name} for {member.name}.")


async def send_welcome_message():
    """Sends the initial welcome message to the designated channel."""
    welcome_channel = bot.get_channel(config.WELCOME_CHANNEL_ID)
    if welcome_channel:
        # Check if the channel history already contains a message with the custom_id
        # to avoid sending multiple welcome messages on bot restart
        messages = []
        try:
            messages = [msg async for msg in welcome_channel.history(limit=50)]
        except discord.Forbidden:
            print(f"ERROR: Bot does not have permission to read message history in {welcome_channel.name}.")
            
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
            print(f"Initial welcome message sent to {welcome_channel.name}.")
        else:
            print(f"Welcome message already found in {welcome_channel.name}. Not sending again.")

# Run the bot
bot.run(config.BOT_TOKEN)