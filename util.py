from collections import defaultdict
from functools import wraps
from time import time

func_times = defaultdict(float)


def timing(f):
    @wraps(f)
    def wrap(*args, **kw):
        ts = time()
        result = f(*args, **kw)
        te = time()
        func_times[f.__name__] += te - ts
        print(f"{f.__name__} took {te-ts:2.4f}s")
        return result

    return wrap
