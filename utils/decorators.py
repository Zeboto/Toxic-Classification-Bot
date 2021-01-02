from functools import wraps
from time import time
from typing import Callable


def timing(log=None):
    if log is None:
        prt = print
    else:
        prt = log.debug

    def inner_function(function: Callable):
        @wraps(function)
        def wrapper(*args, **kwargs):
            prt(f"starting {function.__name__}..")
            ts = time.time()
            result = function(*args, **kwargs)
            te = time.time()
            prt(f"{function.__name__} completed, took {te - ts} seconds")
            return result
        return wrapper
    return inner_function
