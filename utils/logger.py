import logging

# Colors
RED = "\033[91m"
PURPLE = "\033[95m"
YELLOW = "\033[93m"
RESET = "\033[0m"


class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.levelname == "ERROR":
            color = RED
        elif record.levelname == "WARNING":
            color = PURPLE
        elif record.levelname in ["INFO", "DEBUG"]:
            color = YELLOW
        else:
            color = RESET
            
        record.levelname = f"{color}{record.levelname}{RESET}"

        if record.args:
            record.msg = self.highlight_args(record.msg, record.args, color)
            record.args = ()
            
        return super().format(record)

    def highlight_args(self, message, args, color):
        highlighted_args = tuple(f"{color}{arg}{RESET}" for arg in args)
        return message % highlighted_args
