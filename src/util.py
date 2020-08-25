import datetime
from collections import defaultdict
from functools import wraps
from time import time

from flask import render_template

func_times = defaultdict(float)


def get_date(s):
    try:
        return datetime.datetime.fromisoformat(s)
    except ValueError:
        return datetime.datetime.strptime(s, "%Y.%m.%d")


def calculate_months_diff(d1, d2):
    return (d1.year - d2.year) * 12 + d1.month - d2.month


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


def yield_info(pairs, reverse=False):
    """Yields items in the dictionary sorting by keys and expanding items grouped in the same keys."""
    items = sorted(((standardize_date(k), v) for k, v in pairs), reverse=reverse)
    for k, v in items:
        if k[-1] == 's' and isinstance(v, dict) and all(key.isnumeric() for key in v):
            for inner in v.values():
                yield_info({k[:-1]: inner}, reverse=reverse)
        else:
            yield k, v


def standardize_date(s):
    try:
        date = datetime.datetime.strptime(s, "%Y.%m.%d")
        return date.isoformat()
    except ValueError:
        return s


def render_template_wrapper(page, **kwargs):
    return render_template(page, **kwargs), "HTTP/1.1 200 OK", {"Content-Type": "text/html"}
