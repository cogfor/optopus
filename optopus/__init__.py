import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from optopus.settings import DATA_DIR

LOG_FILE = 'optopus.log'
file_name = Path.cwd() / DATA_DIR / LOG_FILE
# Create the Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create the Handler for logging data to a file
file_handler = TimedRotatingFileHandler(file_name, when='W4')
file_handler.setLevel(logging.DEBUG)

# Create the handler for logging data to console
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Create a Formatter for formatting the log messages
file_formatter = logging.Formatter("%(asctime)s — %(name)s — %(levelname)s — %(message)s")
console_formatter = logging.Formatter("%(asctime)s — %(name)s — %(levelname)s — %(message)s")
# Add the Formatter to the Handlers
file_handler.setFormatter(file_formatter)
console_handler.setFormatter(console_formatter)

# Add the Handlers to the Logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.info('Completed configuring the logger')
