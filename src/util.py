import datetime
from collections import defaultdict
from functools import wraps
from time import time

func_times = defaultdict(float)


def get_date(s):
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return datetime.datetime.strptime(s, "%Y.%m.%d")


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


def yield_info(d, f=lambda x: True, reverse=False):
    """Yields items in the dictionary sorting by keys and expanding items grouped in the same keys."""
    items = sorted(((standardize_date(k), v) for k, v in d.items() if f(k)), reverse=reverse)
    for k, v in items:
        if k[-1] == 's' and isinstance(v, dict) and all(key.isnumeric() for key in v):
            for inner in v.values():
                yield k[:-1], inner
        else:
            yield k, v


def standardize_date(s):
    try:
        date = datetime.datetime.strptime(s, "%Y.%m.%d")
        return date.isoformat()
    except ValueError:
        return s
