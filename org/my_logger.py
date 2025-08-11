import os
import datetime
from typing import NoReturn

log_path = os.path.join(os.getcwd(), "log.log")
debug_flag = False

def log(level: str, message: str) -> None:
    """
    Just my personal log function
    """

    # exit if debug flag not on and level is debug
    if not debug_flag and level == "debug":
        return

    # get basic variables
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    valid_levels = {"debug", "info", "warning", "error", "critical"}
    level = level.lower()

    # check if level in valid levels
    if level not in valid_levels:
        full_msg = f"[{current_time}][{script_name}][ERROR]: Invalid log level: {level}"
        with open(log_path, "a") as f:
            f.write(full_msg + "\n")
        raise Exception(full_msg)

    # prepare and write the message
    full_msg = f"[{current_time}][{script_name}][{level.upper()}]: {message}"
    with open(log_path, "a") as f:
        f.write(full_msg + "\n")

    # raise exception if level is serious
    serious_levels = {"error", "critical"}
    if level in serious_levels:
        raise Exception(full_msg)
