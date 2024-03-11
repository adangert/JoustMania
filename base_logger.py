import logging
from logging import RotatingFileHandler

#TODO - Read logging level from file)

# Configure logging
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_file = 'piparty.log'

# Create a rotating file handler with a maximum file size of 1 MB and keep 3 backup copies
rotating_handler = RotatingFileHandler(log_file, maxBytes=1e6, backupCount=3)
rotating_handler.setFormatter(log_formatter)

logging.basicConfig(
    level=logging.DEBUG,  # Set the global logging level
    format='%(asctime)s - %(levelname)s - %(message)s',  # Specify the log message format
    handlers=[
        logging.StreamHandler(),  # Output logs to the console
        rotating_handler  # Output logs to a rotating log file
    ]
)

logger = logging