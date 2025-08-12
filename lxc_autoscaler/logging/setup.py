"""Logging configuration and setup for LXC Autoscaler."""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

from ..config.models import GlobalConfig


class ColoredFormatter(logging.Formatter):
    """Colored log formatter for console output."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors.
        
        Args:
            record: Log record to format.
            
        Returns:
            Formatted log message with colors.
        """
        # Apply color to level name
        level_name = record.levelname
        if level_name in self.COLORS:
            colored_level = f"{self.COLORS[level_name]}{level_name}{self.RESET}"
            record.levelname = colored_level
        
        # Format the message
        formatted = super().format(record)
        
        # Reset level name for other formatters
        record.levelname = level_name
        
        return formatted


class StructuredFormatter(logging.Formatter):
    """Structured JSON-like formatter for log files."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record in structured format.
        
        Args:
            record: Log record to format.
            
        Returns:
            Structured log message.
        """
        # Basic structured fields
        log_data = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add process and thread info
        if hasattr(record, 'process') and record.process:
            log_data['process_id'] = record.process
        
        if hasattr(record, 'thread') and record.thread:
            log_data['thread_id'] = record.thread
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add custom fields from extra parameter
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                          'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process', 'message']:
                log_data[key] = value
        
        # Format as key=value pairs for easier parsing
        parts = []
        for key, value in log_data.items():
            if isinstance(value, str) and (' ' in value or '=' in value):
                parts.append(f'{key}="{value}"')
            else:
                parts.append(f'{key}={value}')
        
        return ' '.join(parts)


def _is_running_in_container() -> bool:
    """Detect if running inside a container.
    
    Returns:
        True if running in a container environment.
    """
    # Check for container environment indicators
    container_indicators = [
        # Docker
        os.path.exists('/.dockerenv'),
        # Kubernetes
        bool(os.getenv('KUBERNETES_SERVICE_HOST')),
        # General container environment variable
        bool(os.getenv('CONTAINER')),
        # LXC Autoscaler specific variable
        bool(os.getenv('LXC_AUTOSCALER_CONTAINER')),
    ]
    
    return any(container_indicators)


def setup_logging(config: GlobalConfig, service_name: str = "lxc-autoscaler") -> None:
    """Setup logging configuration.
    
    Args:
        config: Global configuration.
        service_name: Name of the service for logging context.
    """
    # Get log level
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    
    # Detect container environment
    is_container = _is_running_in_container()
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Use simpler format in containers for better log aggregation
    if is_container:
        console_formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        console_formatter = ColoredFormatter(
            fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler if log file is specified
    if config.log_file:
        try:
            # Ensure log directory exists
            log_path = Path(config.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Rotating file handler to prevent log files from growing too large
            file_handler = logging.handlers.RotatingFileHandler(
                config.log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setLevel(log_level)
            
            # Use structured formatter for file output
            file_formatter = StructuredFormatter(
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
            
            logging.info(f"File logging enabled: {config.log_file}")
            
        except (OSError, PermissionError) as e:
            logging.warning(f"Failed to setup file logging: {e}")
    
    # Set up specific logger levels for noisy libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('proxmoxer').setLevel(logging.INFO)
    
    # Log initial setup information
    logging.info(f"{service_name} logging initialized")
    logging.info(f"Log level: {config.log_level}")
    if is_container:
        logging.info("Container environment detected - using plain console formatting")
    if config.log_file:
        logging.info(f"File logging enabled: {config.log_file}")
    logging.debug("Debug logging enabled")


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name.
    
    Args:
        name: Logger name, typically __name__.
        
    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str, exc_info: Optional[Exception] = None) -> None:
    """Log exception with full traceback.
    
    Args:
        logger: Logger instance.
        message: Log message.
        exc_info: Exception info, uses sys.exc_info() if None.
    """
    logger.error(message, exc_info=exc_info or True)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **context
) -> None:
    """Log message with additional context fields.
    
    Args:
        logger: Logger instance.
        level: Log level (logging.INFO, etc.).
        message: Log message.
        **context: Additional context fields.
    """
    logger.log(level, message, extra=context)


class LogContextManager:
    """Context manager for adding context to all log messages within a block."""
    
    def __init__(self, logger: logging.Logger, **context):
        """Initialize log context manager.
        
        Args:
            logger: Logger instance.
            **context: Context fields to add to all log messages.
        """
        self.logger = logger
        self.context = context
        self.original_factory = None
    
    def __enter__(self):
        """Enter context manager."""
        self.original_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = self.original_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        logging.setLogRecordFactory(self.original_factory)


def with_log_context(logger: logging.Logger, **context):
    """Create a log context manager.
    
    Args:
        logger: Logger instance.
        **context: Context fields.
        
    Returns:
        Log context manager.
    """
    return LogContextManager(logger, **context)