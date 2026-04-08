#!/usr/bin/env python3
"""
Termux Integration Module

Handles Android-specific functionality for persistent background operation.
"""

import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TermuxIntegration:
    """Handles Termux-specific functionality for CIS bot"""
    
    def __init__(self):
        self.is_termux = self.detect_termux()
        self.wakelock_active = False
        
    def detect_termux(self) -> bool:
        """Detect if running in Termux environment"""
        return (
            os.environ.get('TERMUX_VERSION') is not None or
            os.path.exists('/data/data/com.termux') or
            'termux' in os.environ.get('PREFIX', '').lower()
        )
    
    def enable_wake_lock(self) -> bool:
        """Enable wake lock to keep device awake"""
        if not self.is_termux:
            logger.warning("⚠️ Not running in Termux, wake lock not available")
            return False
        
        try:
            # Check if termux-wake-lock is available
            result = subprocess.run(['which', 'termux-wake-lock'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error("❌ termux-wake-lock not found. Install with: pkg install termux-api")
                return False
            
            # Enable wake lock
            subprocess.run(['termux-wake-lock'], check=True)
            self.wakelock_active = True
            
            logger.info("✅ Wake lock enabled - device will stay awake")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to enable wake lock: {e}")
            return False
    
    def disable_wake_lock(self) -> bool:
        """Disable wake lock"""
        if not self.is_termux or not self.wakelock_active:
            return False
        
        try:
            subprocess.run(['termux-wake-unlock'], check=True)
            self.wakelock_active = False
            logger.info("✅ Wake lock disabled")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to disable wake lock: {e}")
            return False
    
    def create_termux_service(self, script_path: str, service_name: str = "cis-bot") -> bool:
        """Create Termux service for auto-start"""
        if not self.is_termux:
            logger.warning("⚠️ Not running in Termux, service creation not available")
            return False
        
        try:
            # Create service directory
            service_dir = Path.home() / ".termux" / "boot"
            service_dir.mkdir(parents=True, exist_ok=True)
            
            # Create service script
            service_script = service_dir / f"{service_name}.sh"
            
            service_content = f'''#!/bin/bash
# CIS Bot Termux Service
# Auto-starts on device boot

# Enable wake lock
tmux new-session -d -s cis-session 'termux-wake-lock && cd {os.path.dirname(script_path)} && python3 {script_path}'

# Log startup
echo "$(date): CIS Bot service started" >> ~/cis-boot.log
'''
            
            with open(service_script, 'w') as f:
                f.write(service_content)
            
            # Make executable
            service_script.chmod(0o755)
            
            logger.info(f"✅ Termux service created: {service_script}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create Termux service: {e}")
            return False
    
    def setup_termux_notifications(self) -> bool:
        """Setup Termux notifications"""
        if not self.is_termux:
            return False
        
        try:
            # Check if termux-notification is available
            result = subprocess.run(['which', 'termux-notification'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.warning("⚠️ termux-notification not found")
                return False
            
            logger.info("✅ Termux notifications available")
            return True
            
        except Exception as e:
            logger.error(f"❌ Termux notification setup failed: {e}")
            return False
    
    def send_notification(self, title: str, content: str, priority: str = "normal") -> bool:
        """Send Termux notification"""
        if not self.is_termux:
            return False
        
        try:
            cmd = [
                'termux-notification',
                '--title', title,
                '--content', content,
                '--priority', priority
            ]
            
            subprocess.run(cmd, check=True)
            logger.info(f"📱 Notification sent: {title}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to send notification: {e}")
            return False
    
    def get_battery_info(self) -> dict:
        """Get battery information"""
        if not self.is_termux:
            return {}
        
        try:
            result = subprocess.run(['termux-battery-status'], 
                                  capture_output=True, text=True, check=True)
            
            import json
            battery_info = json.loads(result.stdout)
            return battery_info
            
        except Exception as e:
            logger.error(f"❌ Failed to get battery info: {e}")
            return {}
    
    def create_startup_script(self, bot_script: str) -> str:
        """Create Termux startup script"""
        script_content = f'''#!/bin/bash
# CIS Bot Termux Startup Script

# Enable wake lock
termux-wake-lock

# Change to bot directory
cd {os.path.dirname(bot_script)}

# Start bot with logging
nohup python3 {os.path.basename(bot_script)} > cis-bot.log 2>&1 &

# Store PID
echo $! > cis-bot.pid

echo "$(date): CIS Bot started with PID $(cat cis-bot.pid)"
'''
        return script_content

def main():
    """Test Termux integration"""
    termux = TermuxIntegration()
    
    print(f"Running in Termux: {termux.is_termux}")
    
    if termux.is_termux:
        print("Testing Termux features...")
        
        # Test battery info
        battery = termux.get_battery_info()
        if battery:
            print(f"Battery: {battery.get('percentage', 'unknown')}%")
        
        # Test wake lock
        if termux.enable_wake_lock():
            print("✅ Wake lock enabled")
            # Don't disable for testing
            # termux.disable_wake_lock()
        
        # Test notification
        termux.send_notification("CIS Bot Test", "Termux integration working!")
    else:
        print("Not running in Termux environment")        print("Not running in Termux environment")

if __name__ == "__main__":
    main()