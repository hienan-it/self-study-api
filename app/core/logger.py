import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

class ANSIConsoleFormatter(logging.Formatter):
    COLORS = {
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[1;91m',
        'INFO': '\033[92m',
        'DEBUG': '\033[94m'
    }
    RESET = '\033[0m'

    def format(self, record):
        if not hasattr(record, "action_code"):
            record.action_code = "SYSTEM"
        
        log_fmt = f"{self.COLORS.get(record.levelname, self.RESET)}[%(asctime)s] [%(levelname)s] [%(action_code)s]: %(message)s{self.RESET}"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class FileFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("[%(asctime)s] [%(levelname)s] [%(action_code)s]: %(message)s")

    def format(self, record):
        if not hasattr(record, "action_code"):
            record.action_code = "SYSTEM"
        return super().format(record)

def _get_namer(default_name: str) -> str:
    # default_name is something like error_log.log.15-10-2023
    # We want error_log-15-10-2023.log
    parts = default_name.split('.')
    if len(parts) >= 3:
        # e.g., error -> log -> 15-10-2023
        # parts[0]: error_log, parts[1]: log, parts[2]: DD-MM-YYYY
        return f"{parts[0]}-{parts[-1]}.log"
    return default_name

def setup_logger(name: str, log_file_prefix: str, level: int) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ANSIConsoleFormatter())
    
    # File Handler
    file_path = os.path.join(LOGS_DIR, f"{log_file_prefix}.log")
    file_handler = TimedRotatingFileHandler(
        filename=file_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.suffix = "%d-%m-%Y"
    file_handler.namer = lambda name: name.replace(".log.", "-") + ".log"
    file_handler.setFormatter(FileFormatter())

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

error_logger = setup_logger("error_logger", "error_log", logging.DEBUG)
access_logger = setup_logger("access_logger", "access_log", logging.DEBUG)
