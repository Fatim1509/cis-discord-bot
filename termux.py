#!/usr/bin/env python3
"""
Termux Integration Script

Handles Android Termux integration for persistent background operation.
"""

import os
import subprocess
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TermuxManager:
    """Manages Termux operations"""
    
    def __init__(self):
        self.wake_lock_active = False
    
    def acquire_wake_lock(self):
        """Acquire wake lock to keep device awake"""
        try:
            subprocess.run(['termux-wake-lock'], check=True)
            self.wake_lock_active = True
            logger.info("✅ Wake lock acquired")
            return True
        except subprocess.CalledProcessError:
            logger.error("❌ Failed to acquire wake lock")
            return False
    
    def release_wake_lock(self):
        """Release wake lock"""
        try:
            subprocess.run(['termux-wake-unlock'], check=True)
            self.wake_lock_active = False
            logger.info("✅ Wake lock released")
            return True
        except subprocess.CalledProcessError:
            logger.error("❌ Failed to release wake lock")
            return False
    
    def setup_termux(self):
        """Setup Termux environment"""
        commands = [
            'pkg update && pkg upgrade -y',
            'pkg install python git nodejs -y',
            'pip install --upgrade pip'
        ]
        
        for cmd in commands:
            logger.info(f"Running: {cmd}")
            os.system(cmd)
    
    def create_systemd_service(self):
        """Create systemd service for auto-start (if available)"""
        service_content = """[Unit]
Description=CIS Discord Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/cis-discord-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        
        service_path = Path.home() / '.config' / 'systemd' / 'user' / 'cis-bot.service'
        service_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(service_path, 'w') as f:
            f.write(service_content)
        
        logger.info(f"Created systemd service at {service_path}")
        logger.info("Enable with: systemctl --user enable cis-bot.service")
        logger.info("Start with: systemctl --user start cis-bot.service")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    manager = TermuxManager()
    
    # Setup Termux
    manager.setup_termux()
    
    # Acquire wake lock
    manager.acquire_wake_lock()
    
    # Create systemd service
    manager.create_systemd_service()
    
    print("✅ Termux setup completed!")
    print("📱 Run 'termux-wake-lock' to keep device awake")
    print("🤖 Bot will run automatically on boot if systemd service is enabled")