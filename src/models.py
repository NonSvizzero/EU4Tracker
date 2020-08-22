from datetime import datetime

import numpy as np

from util import yield_info, get_date


class Province:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.last_conquest = datetime(year=1444, month=11, day=11)
        try:
            for k, v in yield_info(self.history, f=lambda k: k[0] == '1'):
                inner, tag = v.popitem()
                if inner == 'owner':
                    self.last_conquest = get_date(k)
        except AttributeError:  # no history -> uncolonized?
            pass

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return str(self)


class Ruler:
    stats = ('ADM', 'DIP', 'MIL')

    def __init__(self, **kwargs):
        self.value = np.array([kwargs[x] for x in self.stats])
        self.is_regency_council = kwargs['name'] == "(Regency Council)"
        self.months = None

    def __str__(self):
        return f"value={self.value}, months={self.months}"

    def mana_generated(self):
        return self.value * self.months
