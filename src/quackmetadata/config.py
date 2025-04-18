# src/quackmetadata/config.py
"""
Configuration management for QuackMetadata.

This module uses QuackCore's configuration system to manage settings
for the QuackMetadata application.
"""

import atexit
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from quackcore.config import load_config
from quackcore.config.models import QuackConfig

# Keep track of open file handlers to ensure they get closed
# Use a module-level variable instead of ClassVar since we're not in a class
_file_handlers: list[logging.FileHandler] = []


@atexit.register
def _close_file_handlers() -> None:
    """
    Close all file handlers when the program exits.

    This helps avoid resource warnings during test runs.
    """
    for handler in _file_handlers:
        if handler:
            handler.close()
    _file_handlers.clear()


class QuackMetadataConfig(BaseModel):
    """
    QuackMetadata-specific configuration model.

    This model defines the configuration structure specific to QuackMetadata,
    which will be stored in the 'custom' section of the QuackCore config.
    """

    default_prompt_template: str = Field(
        default="generic",
        description="Default prompt template for metadata extraction",
    )

    max_retries: int = Field(
        default=3,
        description="Maximum retries for LLM calls",
        ge=1,
        le=10,
    )

    output_format: str = Field(
        default="json",
        description="Default output format for metadata",
    )

    temp_dir: str = Field(
        default="./temp",
        description="Directory for temporary files",
    )

    output_dir: str = Field(
        default="./output",
        description="Default directory for output files",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level for QuackMetadata",
    )


def initialize_config(config_path: str | None = None) -> QuackConfig:
    """
    Initialize configuration from a file and set up defaults.

    Args:
        config_path: Optional path to configuration file

    Returns:
        QuackConfig object with QuackMetadata-specific configuration
    """
    # Reset global config to ensure a fresh load
    global _config
    _config = None

    # Load configuration from file or defaults
    quack_config = load_config(config_path)

    # Initialize QuackMetadata-specific configuration if not present
    # Handle both dictionary and attribute access for custom
    if hasattr(quack_config.custom, "get"):
        # Dictionary-like access
        if "quackmetadata" not in quack_config.custom:
            quack_config.custom["quackmetadata"] = QuackMetadataConfig().model_dump()
        metadata_config = quack_config.custom.get("quackmetadata", {})
    else:
        # Attribute-based access
        if not hasattr(quack_config.custom, "quackmetadata"):
            setattr(quack_config.custom, "quackmetadata", QuackMetadataConfig().model_dump())
        metadata_config = getattr(quack_config.custom, "quackmetadata", {})

    # Get the log level from metadata_config
    log_level_name = (
        metadata_config.get("log_level", "INFO")
        if isinstance(metadata_config, dict)
        else getattr(metadata_config, "log_level", "INFO")
    )
    log_level = getattr(logging, log_level_name, logging.INFO)

    # When running tests, use minimal logging configuration to avoid file handle issues
    if "PYTEST_CURRENT_TEST" in os.environ:
        # Just set the log level without file handlers during tests
        logging.basicConfig(level=log_level, force=True)

        # Get logs directory - correct approach for PathsConfig
        logs_dir = "./logs"  # Default value

        # Create directory for tests
        Path(logs_dir).mkdir(parents=True, exist_ok=True)

        return quack_config

    # In normal operation, use full logging configuration
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Add console handler if none exists
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root_logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    # Remove existing file handlers to avoid duplicates and resource leaks
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            handler.close()

    # Get log file path from config or use default
    global _file_handlers

    # Access the logs_dir properly - PathsConfig doesn't have a get method
    # Use direct attribute access with a default fallback
    logs_dir = "./logs"  # Default fallback

    # If we have a 'logs_dir' attribute directly in paths, use it
    if hasattr(quack_config.paths, "logs_dir"):
        logs_dir = quack_config.paths.logs_dir

    # Always ensure the directory exists
    Path(logs_dir).mkdir(parents=True, exist_ok=True)

    try:
        log_file = Path(logs_dir) / "quackmetadata.log"

        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
        _file_handlers.append(file_handler)  # Track for cleanup
    except (OSError, PermissionError):
        # If we can't create the log file (e.g., in a read-only filesystem),
        # just skip adding the file handler
        pass

    return quack_config


# Create a global config object - lazy initialization to avoid
# resource issues during testing
_config = None


def get_config() -> QuackConfig:
    """
    Get the QuackMetadata configuration.

    Uses lazy initialization to avoid resource issues during testing.

    Returns:
        QuackConfig instance
    """
    global _config
    if _config is None:
        _config = initialize_config()
    return _config


def get_tool_config() -> dict[str, Any]:
    """
    Get the QuackMetadata-specific configuration.

    Returns:
        Dictionary containing QuackMetadata configuration
    """
    config = get_config()
    # Access custom directly, and provide an empty dict as default if quackmetadata is not found
    if hasattr(config.custom, "get"):
        metadata_config = config.custom.get("quackmetadata", {})
    else:
        # Try attribute access
        metadata_config = getattr(config.custom, "quackmetadata", {})
    return metadata_config


def update_tool_config(new_config: dict[str, Any]) -> None:
    """
    Update the QuackMetadata-specific configuration.

    Args:
        new_config: Dictionary containing new configuration values
    """
    config = get_config()
    tool_config = get_tool_config()

    # Make a copy of the current config to avoid modifying a dict while iterating
    if isinstance(tool_config, dict):
        updated_config = dict(tool_config)
        updated_config.update(new_config)
    else:
        updated_config = new_config

    # Handle both dictionary-based and attribute-based access
    if hasattr(config.custom, "get"):
        # Dictionary-like access
        config.custom["quackmetadata"] = updated_config
    else:
        # Attribute-based access
        setattr(config.custom, "quackmetadata", updated_config)


def get_logger() -> logging.Logger:
    """
    Get the QuackMetadata logger.

    Returns:
        Logger instance for QuackMetadata
    """
    return logging.getLogger("quackmetadata")