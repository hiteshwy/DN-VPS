import discord
from discord.ext import commands
import asyncio
import subprocess
import os
import random
import string
import json
import shutil
import glob
from datetime import datetime, timedelta

# ==================================================
# CONFIGURATION
# ==================================================
TOKEN = "YOUR_BOT_TOKEN"
GUILD_ID = 123456789012345678
ADMIN_IDS = [111111111111111111, 222222222222222222]  # replace with your admin IDs
database_file = "database.txt"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==================================================
# DATABASE HELPERS
# ==================================================

def add_to_database(user_id, container_name, ssh_command, ram_limit=None, cpu_limit=None, creator=None, expiry=None, os_type="Ubuntu 22.04"):
    with open(database_file, 'a') as f:
        f.write(f"{user_id}|{container_name}|{ssh_command}|{ram_limit or '2048'}|{cpu_limit or '1'}|{creator or user_id}|{os_type}|{expiry or 'None'}\n")

def get_user_servers(user_id: int):
    if not os.path.exists(database_file):
        return []
    servers = []
    with open(database_file, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if parts and parts[0] == str(user_id):
                servers.append(line.strip())
    return servers

def get_container_id_from_database(user_id: int, container_name=None):
    servers = get_user_servers(user_id)
    if servers:
        if container_name:
            for server in servers:
                parts = server.split('|')
                if len(parts) >= 2 and container_name == parts[1]:
                    return parts[1]
            return None
        else:
            return servers[0].split('|')[1]
    return None

def remove_from_database(container_id):
    if not os.path.exists(database_file):
        return
    with open(database_file, 'r') as f:
        lines = f.readlines()
    with open(database_file, 'w') as f:
        for line in lines:
            if not line.startswith(container_id):
                f.write(line)

# ==================================================
# MIGRATION
# ==================================================

async def migrate_database():
    if not os.path.exists(database_file):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{database_file}.backup_{timestamp}"
    try:
        shutil.copy2(database_file, backup_file)
        print(f"🛡 Backup created: {backup_file}")
    except Exception as e:
        print(f"⚠️ Backup failed: {e}")
    migrated_lines = []
    changed = False
    with open(database_file, 'r') as f:
        lines = f.readlines()
    for line in lines:
        parts = line.strip().split('|')
        if not parts:
            continue
        first = parts[0]
        if first.isdigit():
            migrated_lines.append(line.strip())
            continue
        if "#" in first:
            name, discrim = first.split("#", 1)
            user_obj = discord.utils.get(bot.users, name=name, discriminator=discrim)
            if user_obj:
                parts[0] = str(user_obj.id)
                migrated_lines.append("|".join(parts))
                changed = True
                continue
        migrated_lines.append(line.strip())
    if changed:
        temp_file = database_file + ".migrated"
        with open(temp_file, 'w') as f:
            for l in migrated_lines:
                f.write(l + "\n")
        os.replace(temp_file, database_file)
        print("✅ Database migrated to user IDs (backup kept).")
    else:
        print("ℹ️ Database already using IDs.")

# ==================================================
# EVENTS
# ==================================================

@bot.event
async def on_ready():
    await migrate_database()
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"🔗 Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

# ==================================================
# /list COMMAND
# ==================================================

@bot.tree.command(name="list", description="📋 List all your VPS instances")
async def list_servers(interaction: discord.Interaction):
    user_id = interaction.user.id
    servers = get_user_servers(user_id)
    await interaction.response.defer()
    if not servers:
        preview = "No entries for this user."
        if os.path.exists(database_file):
            with open(database_file, 'r') as f:
                lines = [l.strip() for l in f if l.strip().startswith(str(user_id)+"|")]
            preview = "\n".join(lines) if lines else preview
        embed = discord.Embed(
            title="📋 Your VPS",
            description=f"❌ No VPS instances found.\n\n**Your DB entries:**\n```\n{preview}\n```",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed)
        return
    embed = discord.Embed(
        title="📋 Your VPS",
        description=f"**You have {len(servers)} VPS instance(s)**",
        color=0x2400ff
    )
    for server in servers:
        parts = server.split('|')
        container_id = parts[1] if len(parts) > 1 else "Unknown"
        try:
            status_out = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Status}}", container_id],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            status = "🟢 Running" if status_out == "running" else "🔴 Stopped"
        except Exception:
            status = "🔴 Stopped"
        ram_limit = parts[3] if len(parts) > 3 else "N/A"
        cpu_limit = parts[4] if len(parts) > 4 else "N/A"
        creator = parts[5] if len(parts) > 5 else "N/A"
        os_type = parts[6] if len(parts) > 6 else "Unknown"
        expiry = parts[7] if len(parts) > 7 else "None"
        embed.add_field(
            name=f"🖥️ {container_id} ({status})",
            value=(
                f"💾 **RAM:** {ram_limit}GB\n"
                f"🔥 **CPU:** {cpu_limit} cores\n"
                f"💾 **Storage:** 10000 GB (Shared)\n"
                f"🧊 **OS:** {os_type}\n"
                f"👑 **Created by:** {creator}\n"
                f"⏱️ **Expires:** {expiry}"
            ),
            inline=False
        )
    await interaction.followup.send(embed=embed)
# ==================================================
# REGEN SSH COMMAND
# ==================================================

async def regen_ssh_command(interaction: discord.Interaction, container_name: str):
    user_id = interaction.user.id
    container_id = get_container_id_from_database(user_id, container_name)
    if not container_id:
        servers = get_user_servers(user_id)
        preview = "\n".join(servers) if servers else "No entries for this user."
        embed = discord.Embed(
            title="❌ Not Found",
            description=f"No active instance found with that name.\n\n**Your DB entries:**\n```\n{preview}\n```",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed)
        return
    await interaction.response.defer()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", container_id, "tmate", "-F",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        ssh_session_line = None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            s = line.decode(errors='ignore').strip()
            if s and ("ssh " in s or "tmate ssh" in s):
                ssh_session_line = s
                break
        await proc.wait()
    except Exception as e:
        await interaction.followup.send(
            embed=discord.Embed(title="❌ Error", description=f"Failed to run tmate: {e}", color=0xff0000)
        )
        return
    if ssh_session_line:
        if os.path.exists(database_file):
            with open(database_file, 'r') as f:
                lines = f.readlines()
            with open(database_file, 'w') as f:
                for line in lines:
                    parts = line.strip().split('|')
                    if len(parts) >= 3 and parts[1] == container_id and parts[0] == str(user_id):
                        parts[2] = ssh_session_line
                        f.write('|'.join(parts) + '\n')
                    else:
                        f.write(line)
        dm = discord.Embed(
            title="🔄 New SSH Session Generated",
            description="Your SSH session has been regenerated successfully.",
            color=0x2400ff
        )
        dm.add_field(name="🔑 SSH Connection Command", value=f"```{ssh_session_line}```", inline=False)
        try:
            await interaction.user.send(embed=dm)
        except discord.Forbidden:
            pass
        await interaction.followup.send(
            embed=discord.Embed(title="✅ SSH Session Regenerated", description="Check your DMs for details.", color=0x00ff00)
        )
    else:
        await interaction.followup.send(
            embed=discord.Embed(
                title="❌ Failed",
                description="Could not generate a new SSH session. Make sure `tmate` is installed inside the container.",
                color=0xff0000
            )
        )

# ==================================================
# ADMIN: RESTORE DB
# ==================================================

@bot.tree.command(name="restore-db", description="♻️ Admin: Restore database from the latest backup")
async def restore_db(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Access Denied", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    backup_files = sorted(glob.glob(f"{database_file}.backup_*"), reverse=True)
    if not backup_files:
        await interaction.followup.send("⚠️ No backups found.", ephemeral=True)
        return
    latest_backup = backup_files[0]
    try:
        shutil.copy2(latest_backup, database_file)
        await interaction.followup.send(f"✅ Restored from backup:\n```{os.path.basename(latest_backup)}```", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Restore failed: {e}", ephemeral=True)

# ==================================================
# ADMIN: LIST BACKUPS
# ==================================================

class BackupListView(discord.ui.View):
    def __init__(self, backups, page=0):
        super().__init__(timeout=120)
        self.backups = backups
        self.page = page
        self.page_size = 5
        self.refresh_buttons()
    def refresh_buttons(self):
        self.clear_items()
        start = self.page * self.page_size
        end = start + self.page_size
        for backup in self.backups[start:end]:
            label = os.path.basename(backup)
            self.add_item(BackupButton(label, backup))
        if self.page > 0:
            self.add_item(PrevPageButton())
        if end < len(self.backups):
            self.add_item(NextPageButton())

class BackupButton(discord.ui.Button):
    def __init__(self, label, backup_file):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.backup_file = backup_file
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("❌ Not allowed", ephemeral=True)
            return
        try:
            shutil.copy2(self.backup_file, database_file)
            await interaction.response.send_message(
                f"✅ Restored from:\n```{os.path.basename(self.backup_file)}```", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

class PrevPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
    async def callback(self, interaction: discord.Interaction):
        view: BackupListView = self.view
        view.page -= 1
        view.refresh_buttons()
        await interaction.response.edit_message(view=view)

class NextPageButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡️ Next", style=discord.ButtonStyle.secondary)
    async def callback(self, interaction: discord.Interaction):
        view: BackupListView = self.view
        view.page += 1
        view.refresh_buttons()
        await interaction.response.edit_message(view=view)

@bot.tree.command(name="list-backups", description="📂 Admin: List all database backups with restore options")
async def list_backups(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ Access Denied", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    backup_files = sorted(glob.glob(f"{database_file}.backup_*"), reverse=True)
    if not backup_files:
        await interaction.followup.send("⚠️ No backups found.", ephemeral=True)
        return
    embed = discord.Embed(
        title="📂 Database Backups",
        description="Click a button to restore. Use ⬅️ / ➡️ to scroll pages.",
        color=0x2400ff
    )
    view = BackupListView(backup_files)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
# ==================================================
# OTHER BOT COMMANDS (your originals stay intact)
# ==================================================

@bot.tree.command(name="regen-ssh", description="🔄 Regenerate SSH session for your instance")
@discord.app_commands.describe(container_name="The name of your container")
async def regen_ssh(interaction: discord.Interaction, container_name: str):
    await regen_ssh_command(interaction, container_name)

@bot.tree.command(name="start", description="▶️ Start your VPS instance")
@discord.app_commands.describe(container_name="The name of your container")
async def start(interaction: discord.Interaction, container_name: str):
    await start_server(interaction, container_name)

@bot.tree.command(name="stop", description="⏹️ Stop your VPS instance")
@discord.app_commands.describe(container_name="The name of your container")
async def stop(interaction: discord.Interaction, container_name: str):
    await stop_server(interaction, container_name)

@bot.tree.command(name="restart", description="🔄 Restart your VPS instance")
@discord.app_commands.describe(container_name="The name of your container")
async def restart(interaction: discord.Interaction, container_name: str):
    await restart_server(interaction, container_name)

@bot.tree.command(name="delete", description="🗑️ Delete your VPS instance")
@discord.app_commands.describe(container_name="The name of your container")
async def delete(interaction: discord.Interaction, container_name: str):
    await delete_server(interaction, container_name)

# ==================================================
# PLACEHOLDER FUNCTIONS FOR OTHER VPS MGMT COMMANDS
# ==================================================

async def start_server(interaction, container_name):
    await interaction.response.send_message(
        f"▶️ Starting VPS `{container_name}`... (not implemented in this snippet)"
    )

async def stop_server(interaction, container_name):
    await interaction.response.send_message(
        f"⏹️ Stopping VPS `{container_name}`... (not implemented in this snippet)"
    )

async def restart_server(interaction, container_name):
    await interaction.response.send_message(
        f"🔄 Restarting VPS `{container_name}`... (not implemented in this snippet)"
    )

async def delete_server(interaction, container_name):
    await interaction.response.send_message(
        f"🗑️ Deleting VPS `{container_name}`... (not implemented in this snippet)"
    )

# ==================================================
# (Your other commands would still be here unchanged)
# ==================================================

# Example stub command to show the pattern
@bot.tree.command(name="ping", description="🏓 Test command")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! 🏓")

# ==================================================
# ERROR HANDLER
# ==================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don’t have permission to do that.")
    else:
        await ctx.send(f"⚠️ Error: {error}")
       # ==================================================
# BOT ENTRYPOINT
# ==================================================

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}") 
        

