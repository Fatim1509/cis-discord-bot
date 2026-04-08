#!/usr/bin/env python3
"""
CIS Discord Bot - Mobile Command & Control Interface

Provides mobile access to CIS intelligence data with approval/reject functionality.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
import discord
from discord.ext import commands, tasks
from discord.ui import View, Button

logger = logging.getLogger(__name__)

class CISBot(commands.Bot):
    """CIS Discord Bot for mobile C2 interface"""
    
    def __init__(self, config: Dict):
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix=config.get('prefix', '!'),
            intents=intents,
            help_command=None
        )
        
        self.config = config
        self.pat_token = config.get('pat_token', '')
        self.repo_owner = config.get('repo_owner', '')
        self.repo_name = config.get('repo_name', 'cis-operational-center')
        self.poll_interval = config.get('poll_interval', 120)  # seconds
        self.approval_timeout = config.get('approval_timeout', 300)  # seconds
        
        self.last_check = None
        self.pending_approvals = {}  # message_id -> approval_data
        self.intelligence_cache = None
        self.cache_timestamp = None
        
    async def setup_hook(self):
        """Setup bot components"""
        logger.info("🤖 Setting up CIS Discord Bot...")
        
        # Start background tasks
        self.poll_intelligence.start()
        self.cleanup_approvals.start()
        
        logger.info("✅ Bot setup completed")
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f"✅ {self.user} has connected to Discord!")
        logger.info(f"   Bot ID: {self.user.id}")
        logger.info(f"   Connected to {len(self.guilds)} guilds")
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="financial markets | !help"
        )
        await self.change_presence(activity=activity)
    
    def get_intelligence_data(self) -> Optional[Dict]:
        """Fetch latest intelligence data from GitHub repository"""
        try:
            # Check cache first
            if (self.cache_timestamp and 
                datetime.utcnow() - self.cache_timestamp < timedelta(seconds=30)):
                return self.intelligence_cache
            
            # Construct raw file URL
            url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/main/data/master_intel.json"
            
            headers = {
                'Authorization': f'token {self.pat_token}',
                'Accept': 'application/vnd.github.v3.raw'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.intelligence_cache = data
                self.cache_timestamp = datetime.utcnow()
                logger.info(f"📊 Fetched intelligence data: {data.get('status', 'unknown')}")
                return data
            else:
                logger.warning(f"⚠️ Failed to fetch intelligence data: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error fetching intelligence data: {e}")
            return None
    
    def create_intelligence_embed(self, data: Dict) -> discord.Embed:
        """Create Discord embed for intelligence data"""
        consensus = data.get('consensus', {})
        summary = data.get('summary', {})
        
        # Determine embed color based on sentiment
        sentiment = consensus.get('dominant_sentiment', 'neutral')
        if sentiment == 'positive':
            color = discord.Color.green()
        elif sentiment == 'negative':
            color = discord.Color.red()
        else:
            color = discord.Color.gold()
        
        embed = discord.Embed(
            title="🎯 CIS Intelligence Update",
            description="New financial intelligence signals detected",
            color=color,
            timestamp=datetime.utcnow()
        )
        
        # Add consensus information
        recommendation = consensus.get('recommendation', 'NEUTRAL')
        confidence = consensus.get('confidence', 0)
        
        embed.add_field(
            name="Recommendation",
            value=f"**{recommendation}**",
            inline=True
        )
        
        embed.add_field(
            name="Confidence",
            value=f"{confidence:.1%}",
            inline=True
        )
        
        embed.add_field(
            name="Sentiment",
            value=f"{sentiment.title()}",
            inline=True
        )
        
        # Add summary
        total_signals = summary.get('total_signals', 0)
        sources_active = summary.get('sources_active', 0)
        
        embed.add_field(
            name="Signals",
            value=f"{total_signals} total",
            inline=True
        )
        
        embed.add_field(
            name="Sources Active",
            value=f"{sources_active}/5",
            inline=True
        )
        
        # Add timestamp
        last_update = summary.get('last_update', 'Unknown')
        embed.add_field(
            name="Last Update",
            value=last_update,
            inline=True
        )
        
        # Set footer
        embed.set_footer(text="CIS - Center Intelligence System")
        
        return embed
    
    def create_approval_view(self, intelligence_data: Dict) -> View:
        """Create approval/reject buttons"""
        view = View(timeout=self.approval_timeout)
        
        async def approve_callback(interaction: discord.Interaction):
            await self.handle_approval(interaction, intelligence_data, "APPROVED")
        
        async def reject_callback(interaction: discord.Interaction):
            await self.handle_approval(interaction, intelligence_data, "REJECTED")
        
        approve_button = Button(
            style=discord.ButtonStyle.success,
            label="✅ Approve",
            emoji="✅"
        )
        approve_button.callback = approve_callback
        
        reject_button = Button(
            style=discord.ButtonStyle.danger,
            label="❌ Reject",
            emoji="❌"
        )
        reject_button.callback = reject_callback
        
        view.add_item(approve_button)
        view.add_item(reject_button)
        
        return view
    
    async def handle_approval(self, interaction: discord.Interaction, intelligence_data: Dict, decision: str):
        """Handle approval/reject decision"""
        try:
            # Update embed to show decision
            embed = interaction.message.embeds[0]
            embed.title = f"🎯 CIS Intelligence - {decision}"
            embed.description = f"Decision: **{decision}** by {interaction.user.mention}"
            embed.color = discord.Color.green() if decision == "APPROVED" else discord.Color.red()
            
            # Add decision timestamp
            embed.add_field(
                name="Decision Time",
                value=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                inline=False
            )
            
            # Disable buttons
            view = View()
            for item in interaction.message.components[0].children:
                if hasattr(item, 'disabled'):
                    item.disabled = True
                view.add_item(item)
            
            await interaction.response.edit_message(embed=embed, view=view)
            
            # Log decision
            logger.info(f"📝 Intelligence {decision} by {interaction.user}")
            
            # Store decision for analytics
            decision_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'user': str(interaction.user),
                'user_id': interaction.user.id,
                'decision': decision,
                'intelligence_id': intelligence_data.get('timestamp', 'unknown')
            }
            
            self.save_decision(decision_data)
            
        except Exception as e:
            logger.error(f"❌ Error handling approval: {e}")
            await interaction.response.send_message(
                "❌ Error processing decision. Please try again.",
                ephemeral=True
            )
    
    def save_decision(self, decision_data: Dict):
        """Save decision to file for analytics"""
        try:
            decisions_file = Path("data/decisions.json")
            decisions_file.parent.mkdir(exist_ok=True)
            
            decisions = []
            if decisions_file.exists():
                with open(decisions_file, 'r') as f:
                    decisions = json.load(f)
            
            decisions.append(decision_data)
            
            # Keep only last 1000 decisions
            if len(decisions) > 1000:
                decisions = decisions[-1000:]
            
            with open(decisions_file, 'w') as f:
                json.dump(decisions, f, indent=2)
                
        except Exception as e:
            logger.error(f"❌ Error saving decision: {e}")
    
    @tasks.loop(seconds=120)  # Poll every 2 minutes
    async def poll_intelligence(self):
        """Background task to poll for new intelligence"""
        try:
            logger.debug("🔍 Polling for new intelligence...")
            
            intelligence_data = self.get_intelligence_data()
            
            if intelligence_data:
                # Check if this is new data
                data_timestamp = intelligence_data.get('timestamp')
                
                if data_timestamp and data_timestamp != self.last_check:
                    logger.info(f"🎯 New intelligence detected: {data_timestamp}")
                    self.last_check = data_timestamp
                    
                    # Send to configured channels
                    await self.broadcast_intelligence(intelligence_data)
                    
        except Exception as e:
            logger.error(f"❌ Error in intelligence polling: {e}")
    
    async def broadcast_intelligence(self, intelligence_data: Dict):
        """Broadcast intelligence to configured Discord channels"""
        try:
            # Get configured channels
            channels = self.config.get('channels', [])
            
            if not channels:
                # Use bot's home guild if no channels configured
                if self.guilds:
                    guild = self.guilds[0]
                    # Find or create intelligence channel
                    channel = discord.utils.get(guild.text_channels, name="cis-intelligence")
                    if not channel:
                        # Try to create channel (requires permissions)
                        try:
                            channel = await guild.create_text_channel("cis-intelligence")
                        except:
                            logger.warning("❌ Could not create intelligence channel")
                            return
                    
                    if channel:
                        channels = [channel.id]
            
            # Send to each channel
            for channel_id in channels:
                channel = self.get_channel(channel_id)
                if channel:
                    embed = self.create_intelligence_embed(intelligence_data)
                    view = self.create_approval_view(intelligence_data)
                    
                    message = await channel.send(embed=embed, view=view)
                    
                    # Store for approval tracking
                    self.pending_approvals[message.id] = {
                        'intelligence_data': intelligence_data,
                        'timestamp': datetime.utcnow(),
                        'channel_id': channel_id
                    }
                    
                    logger.info(f"📤 Intelligence broadcasted to {channel.name}")
                    
        except Exception as e:
            logger.error(f"❌ Error broadcasting intelligence: {e}")
    
    @tasks.loop(minutes=5)  # Cleanup every 5 minutes
    async def cleanup_approvals(self):
        """Clean up expired approval requests"""
        try:
            now = datetime.utcnow()
            expired_ids = []
            
            for message_id, approval_data in self.pending_approvals.items():
                timestamp = approval_data['timestamp']
                if now - timestamp > timedelta(seconds=self.approval_timeout):
                    expired_ids.append(message_id)
            
            # Remove expired approvals
            for message_id in expired_ids:
                del self.pending_approvals[message_id]
                logger.info(f"🧹 Cleaned up expired approval: {message_id}")
                
        except Exception as e:
            logger.error(f"❌ Error in cleanup: {e}")
    
    @poll_intelligence.before_loop
    async def before_poll_intelligence(self):
        """Wait for bot to be ready"""
        await self.wait_until_ready()
        logger.info("🔄 Intelligence polling starting...")
    
    @cleanup_approvals.before_loop
    async def before_cleanup_approvals(self):
        """Wait for bot to be ready"""
        await self.wait_until_ready()
        logger.info("🧹 Approval cleanup starting...")

# Command definitions
@commands.command(name='help')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="🤖 CIS Bot Help",
        description="Center Intelligence System Discord Bot",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Commands",
        value="""
        `!help` - Show this help message
        `!status` - Show bot status
        `!intelligence` - Get latest intelligence
        `!poll` - Manually poll for intelligence
        """,
        inline=False
    )
    
    embed.add_field(
        name="Features",
        value="""
        • Automatic intelligence polling
        • Approval/reject buttons
        • Mobile-friendly interface
        • Termux integration ready
        """,
        inline=False
    )
    
    await ctx.send(embed=embed)

@commands.command(name='status')
async def status_command(ctx):
    """Show bot status"""
    bot = ctx.bot
    
    embed = discord.Embed(
        title="📊 CIS Bot Status",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="Uptime",
        value=f"{discord.utils.utcnow() - bot.start_time}",
        inline=True
    )
    
    embed.add_field(
        name="Poll Interval",
        value=f"{bot.poll_interval}s",
        inline=True
    )
    
    embed.add_field(
        name="Pending Approvals",
        value=str(len(bot.pending_approvals)),
        inline=True
    )
    
    await ctx.send(embed=embed)

@commands.command(name='intelligence')
async def intelligence_command(ctx):
    """Get latest intelligence manually"""
    bot = ctx.bot
    
    data = bot.get_intelligence_data()
    if data:
        embed = bot.create_intelligence_embed(data)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No intelligence data available")

@commands.command(name='poll')
async def poll_command(ctx):
    """Manually poll for intelligence"""
    bot = ctx.bot
    
    await ctx.send("🔄 Manually polling for intelligence...")
    
    # Force refresh
    bot.intelligence_cache = None
    bot.cache_timestamp = None
    
    data = bot.get_intelligence_data()
    if data:
        await bot.broadcast_intelligence(data)
        await ctx.send("✅ Intelligence polling completed")
    else:
        await ctx.send("❌ No intelligence data found")

# Load bot configuration
def load_config() -> Dict:
    """Load bot configuration"""
    config_file = Path("config.json")
    
    default_config = {
        'prefix': '!',
        'poll_interval': 120,
        'approval_timeout': 300,
        'repo_owner': '',
        'repo_name': 'cis-operational-center',
        'pat_token': '',
        'channels': [],
        'discord_token': ''
    }
    
    try:
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = json.load(f)
            # Merge with defaults
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            return config
    except Exception as e:
        logging.error(f"Error loading config: {e}")
    
    return default_config

def main():
    """Main function"""
    # Load configuration
    config = load_config()
    
    # Check required configuration
    if not config.get('discord_token'):
        logging.error("❌ Discord token not configured")
        return
    
    if not config.get('pat_token'):
        logging.error("❌ GitHub PAT token not configured")
        return
    
    # Create bot instance
    bot = CISBot(config)
    
    # Add commands
    bot.add_command(help_command)
    bot.add_command(status_command)
    bot.add_command(intelligence_command)
    bot.add_command(poll_command)
    
    # Add start time for uptime tracking
    bot.start_time = datetime.utcnow()
    
    # Run bot
    try:
        bot.run(config['discord_token'])
    except KeyboardInterrupt:
        logging.info("🛑 Bot stopped by user")
    except Exception as e:
        logging.error(f"❌ Bot error: {e}")

if __name__ == "__main__":
    main()