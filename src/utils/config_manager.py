"""
Helper for loading and saving the config.json file.
Ensures the application settings are persisted across sessions.
"""
import json
import os
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    DEFAULT_CONFIG_PATH = "config.json"

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self) -> dict:
        """Loads configuration from JSON file. Returns default if not found."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file {self.config_path} not found. Using defaults.")
            return {}
        
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def save_config(self, config_data: dict = None):
        """Saves current configuration to JSON file."""
        if config_data:
            self.config = config_data
            
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info("Configuration saved successfully.")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get(self, key: str, default=None):
        """Retrieves a nested configuration value using dot notation (e.g. 'plc.host')."""
        parts = key.split('.')
        val = self.config
        try:
            for part in parts:
                val = val[part]
            return val
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value):
        """Sets a nested configuration value using dot notation."""
        parts = key.split('.')
        val = self.config
        for part in parts[:-1]:
            if part not in val:
                val[part] = {}
            val = val[part]
        val[parts[-1]] = value
        self.save_config()
