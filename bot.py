#!/usr/bin/env python3
"""
CIS Discord Bot - Mobile Command & Control Interface

Provides mobile control interface for the CIS system via Discord bot commands.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests
import discord
from discord.ext import commands, tasks
import schedule

logger = logging.getLogger(__name__)

class CISDiscordBot(commands.Bot):
    """CIS Discord Bot for mobile command and control"""
    
    def __init__(self, config: dict):
        self.config = config
        self.raw_json_url = config.get('raw_json_url', '')
        self.pat_token = config.get('pat_token', '')
        self.poll_interval = config.get('poll_interval', 120)  # 2 minutes
        self.approval_timeout = config.get('approval_timeout', 300)  # 5 minutes
        
        # Bot configuration
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            description='CIS - Center Intelligence System Bot'
        )
        
        self.pending_approvals = {}  # message_id -> approval_data
        self.last_poll = None
        self.recent_signals = set()  # Track recent signals to avoid duplicates
        
    async def setup_hook(self):
        """Setup bot tasks"""
        self.poll_intel.start()
        self.cleanup_approvals.start()
    
    async def on_ready(self):
        """Bot is ready"""
        logger.info(f"✅ {self.user} has connected to Discord!")
        logger.info(f"📊 Connected to {len(self.guilds)} guilds")
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="financial markets | !help"
        )
        await self.change_presence(activity=activity)
    
    async def get_intelligence_data(self) -> Optional[Dict]:
        """Fetch intelligence data from GitHub"""
        try:
            if not self.raw_json_url:
                logger.error("No raw JSON URL configured")
                return None
            
            headers = {}
            if self.pat_token:
                headers['Authorization'] = f'token {self.pat_token}'
            
            response = requests.get(self.raw_json_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch intelligence data: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching intelligence data: {e}")
            return None
    
    @tasks.loop(seconds=120)  # Poll every 2 minutes
    async def poll_intel(self):
        """Poll for new intelligence data"""
        try:
            logger.info("🔍 Polling for new intelligence...")
            
            intel_data = await self.get_intelligence_data()
            if not intel_data:
                logger.warning("No intelligence data available")
                return
            
            signals = intel_data.get('signals', [])
            summary = intel_data.get('summary', {})
            
            if not signals:
                logger.info("No signals to process")
                return
            
            # Process new signals
            new_signals = []
            for signal in signals:
                signal_id = signal.get('id', '')
                
                # Skip if already processed
                if signal_id in self.recent_signals:
                    continue
                
                # Add to recent signals (keep last 100)
                self.recent_signals.add(signal_id)
                if len(self.recent_signals) > 100:
                    # Remove oldest
                    oldest = min(self.recent_signals)
                    self.recent_signals.remove(oldest)
                
                new_signals.append(signal)
            
            if new_signals:
                logger.info(f"🎯 Found {len(new_signals)} new signals")
                await self.notify_new_signals(new_signals, summary)
            
            self.last_poll = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"❌ Error in poll loop: {e}")
    
    @poll_intel.before_loop
    async def before_poll_intel(self):
        """Wait before starting poll loop"""
        await self.wait_until_ready()
        logger.info("🔄 Starting intelligence polling...")
    
    async def notify_new_signals(self, signals: List[Dict], summary: Dict):
        """Notify about new signals"""
        try:
            # Find the first text channel
            channel = None
            for guild in self.guilds:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break
                if channel:
                    break
            
            if not channel:
                logger.error("No channel available to send notifications")
                return
            
            # Create notification embed
            embed = discord.Embed(
                title="🎯 New Intelligence Signals",
                description=f"{len(signals)} new signals detected",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            # Add signal summary
            for i, signal in enumerate(signals[:5]):  # Show first 5
                title = signal.get('title', 'Unknown')
                sentiment = signal.get('sentiment', 'neutral')
                confidence = signal.get('confidence', 0.5)
                source = signal.get('source', 'unknown')
                
                # Truncate title if too long
                if len(title) > 50:
                    title = title[:47] + "..."
                
                # Sentiment emoji
                sentiment_emoji = {
                    'positive': '📈',
                    'negative': '📉',
                    'neutral': '➡️'
                }.get(sentiment, '❓')
                
                embed.add_field(
                    name=f"{sentiment_emoji} Signal {i+1}",
                    value=f"**{title}**\n"
                          f"Sentiment: `{sentiment}`\n"
                          f"Confidence: `{confidence:.1%}`\n"
                          f"Source: `{source}`",
                    inline=False
                )
            
            if len(signals) > 5:
                embed.add_field(
                    name="📊 More signals",
                    value=f"...and {len(signals) - 5} more signals",
                    inline=False
                )
            
            # Add summary
            if summary:
                breakdown = summary.get('sentiment_breakdown', {})
                avg_confidence = summary.get('avg_confidence', 0)
                
                embed.add_field(
                    name="📈 Summary",
                    value=f"Total: `{summary.get('total_signals', 0)}`\n"
                          f"Positive: `{breakdown.get('positive', 0)}`\n"
                          f"Negative: `{breakdown.get('negative', 0)}`\n"
                          f"Neutral: `{breakdown.get('neutral', 0)}`\n"
                          f"Avg Confidence: `{avg_confidence:.1%}`",
                    inline=True
                )
            
            # Send notification
            message = "🚨 New intelligence signals available for review!"
            
            # Add approve/reject buttons
            view = SignalApprovalView(signals[:3])  # Only approve first 3 for simplicity
            
            await channel.send(message, embed=embed, view=view)
            logger.info(f"📤 Sent notification about {len(signals)} signals")
            
        except Exception as e:
            logger.error(f"❌ Error notifying about signals: {e}")
    
    @tasks.loop(minutes=5)
    async def cleanup_approvals(self):
        """Clean up expired approval requests"""
        try:
            current_time = datetime.utcnow()
            expired = []
            
            for message_id, approval_data in self.pending_approvals.items():
                created_at = approval_data.get('created_at')
                if created_at:
                    age = current_time - created_at
                    if age > timedelta(seconds=self.approval_timeout):
                        expired.append(message_id)
            
            # Remove expired approvals
            for message_id in expired:
                del self.pending_approvals[message_id]
                logger.info(f"🧹 Cleaned up expired approval: {message_id}")
            
            if expired:
                logger.info(f"🧹 Cleaned up {len(expired)} expired approvals")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up approvals: {e}")
    
    # Discord Commands
    @commands.command(name='status')
    async def status_command(self, ctx):
        """Show bot status"""
        embed = discord.Embed(
            title="🤖 CIS Bot Status",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Get intelligence data
        intel_data = await self.get_intelligence_data()
        
        if intel_data:
            signals = intel_data.get('signals', [])
            summary = intel_data.get('summary', {})
            
            embed.add_field(
                name="📊 Intelligence",
                value=f"Signals: `{len(signals)}`\n"
                      f"Last Update: `{intel_data.get('last_updated', 'Unknown')[:19]}`",
                inline=True
            )
            
            if summary:
                breakdown = summary.get('sentiment_breakdown', {})
                embed.add_field(
                    name="📈 Sentiment",
                    value=f"📈 Positive: `{breakdown.get('positive', 0)}`\n"
                          f"📉 Negative: `{breakdown.get('negative', 0)}`\n"
                          f"➡️ Neutral: `{breakdown.get('neutral', 0)}`",
                    inline=True
                )
        else:
            embed.add_field(
                name="⚠️ Intelligence",
                value="No data available",
                inline=True
            )
        
        embed.add_field(
            name="🔄 Polling",
            value=f"Interval: `{self.poll_interval}s`\n"
                  f"Last Poll: `{self.last_poll.strftime('%H:%M:%S UTC') if self.last_poll else 'Never'}`",
            inline=True
        )
        
        embed.add_field(
            name="📱 Mobile",
            value=f"Pending Approvals: `{len(self.pending_approvals)}`\n"
                  f"Recent Signals: `{len(self.recent_signals)}`",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='help')
    async def help_command(self, ctx):
        """Show help information"""
        embed = discord.Embed(
            title="🤖 CIS Bot Commands",
            description="Center Intelligence System - Mobile Command Interface",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="📊 `!status`",
            value="Show bot and intelligence status",
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ `!help`",
            value="Show this help message",
            inline=False
        )
        
        embed.add_field(
            name="🔄 Automatic Features",
            value=f"• Polls every {self.poll_interval}s for new intelligence\n"
                  f"• Auto-cleans expired approvals after {self.approval_timeout}s\n"
                  "• Tracks recent signals to avoid duplicates",
            inline=False
        )
        
        await ctx.send(embed=embed)

class SignalApprovalView(discord.ui.View):
    """View for signal approval buttons"""
    
    def __init__(self, signals: list):
        super().__init__(timeout=None)
        self.signals = signals
    
    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green, custom_id="approve_signals")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle approve button click"""
        try:
            # Add approval logic here
            await interaction.response.send_message(
                "✅ Signals approved! Executing trades...",
                ephemeral=True
            )
            logger.info(f"Signals approved by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Approval error: {e}")
            await interaction.response.send_message(
                "❌ Approval failed. Please try again.",
                ephemeral=True
            )
    
    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red, custom_id="reject_signals")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle reject button click"""
        try:
            await interaction.response.send_message(
                "❌ Signals rejected. No action taken.",
                ephemeral=True
            )
            logger.info(f"Signals rejected by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Rejection error: {e}")
            await interaction.response.send_message(
                "❌ Rejection failed. Please try again.",
                ephemeral=True
            )

def load_config(config_path: str = 'config.json') -> dict:
    """Load bot configuration"""
    default_config = {
        'raw_json_url': '',
        'pat_token': '',
        'poll_interval': 120,
        'approval_timeout': 300,
        'discord_token': ''
    }
    
    try:
        if Path(config_path).exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Merge with defaults
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        else:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return default_config
            
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return default_config

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='CIS Discord Bot')
    parser.add_argument('--config', default='config.json', help='Configuration file')
    parser.add_argument('--token', help='Discord bot token (overrides config)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Load configuration
    config = load_config(args.config)
    
    # Override token if provided
    if args.token:
        config['discord_token'] = args.token
    
    if not config.get('discord_token'):
        logger.error("No Discord token provided")
        return 1
    
    # Create and run bot
    bot = CISDiscordBot(config)
    
    try:
        bot.run(config['discord_token'])
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())