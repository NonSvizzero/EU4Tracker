import itertools
import json
from datetime import datetime

import numpy as np
from colour import Color

from util import yield_info, get_date, calculate_months_diff

START_DATE = datetime(year=1444, month=11, day=11)


class Campaign:
    def __init__(self, gameinfo):
        self.gameinfo = gameinfo
        self.player = gameinfo["meta"]["player"]
        self.current_date = get_date(gameinfo["meta"]["date"])
        self.provinces = [Province(id=int(i[1:]), **p) for i, p in gameinfo["gamestate"]["provinces"].items()]
        self.countries = {tag: Country(self, tag=tag, **c) for tag, c in gameinfo["gamestate"]["countries"].items()}

    def get_country(self, country=None):
        return self.countries[country if country else self.player]

    @classmethod
    def from_file(cls, filename):
        with open(filename) as f:
            d = json.load(f)
            return cls(gameinfo=d)


class Country:
    # https://eu4.paradoxwikis.com/Template:Revolutionary_flag
    REV_COLORS = [(255, 255, 255), (20, 20, 20), (131, 0, 146), (121, 0, 41), (103, 0, 5), (185, 0, 0),
                  (195, 83, 0), (66, 40, 20), (245, 193, 0), (0, 59, 9), (0, 124, 52), (0, 194, 111),
                  (0, 175, 194), (53, 0, 131), (110, 194, 243), (26, 50, 134), (211, 0, 27)]

    def __init__(self, campaign, **kwargs):
        self.__dict__.update(**kwargs)
        for k in ('owned_provinces', 'controlled_provinces', 'core_provinces'):
            setattr(self, k, list(sorted((campaign.provinces[i - 1] for i in kwargs[k].values()),
                                         key=lambda p: p.last_conquest)))
        # todo find meanings of 'adm_spent_indexed' with the "powerspend" command in-game
        for k in ('capital', 'trade_port'):
            setattr(self, k, campaign.provinces[kwargs[k]])
        self.rulers = []
        self.avg_ruler_stats = None
        self.avg_ruler_life = None
        self.get_ruler_history(campaign.current_date)
        self.colors = [self.REV_COLORS[i] for i in kwargs["colors"]["revolutionary_colors"].values()]

    def get_ruler_history(self, current_date):
        total_months = calculate_months_diff(current_date, START_DATE)
        last_crowning = last_ruler = None
        for date, history in yield_info(self.history, f=lambda x: x[0] == '1'):
            if any(x in history for x in ('monarch', 'monarch_heir')):
                new_crowing = get_date(date)
                if new_crowing > START_DATE:
                    self.add_ruler(last_ruler, new_crowing, last_crowning)
                last_crowning, last_ruler = new_crowing, Ruler(**history.popitem()[1])
        self.add_ruler(last_ruler, current_date, last_crowning)
        # rulers stats
        self.avg_ruler_life = np.average([r.months for r in self.rulers if not r.is_regency_council])
        self.avg_ruler_stats = sum([r.mana_generated for r in self.rulers]) / total_months

    def add_ruler(self, ruler, d1, d2):
        months_diff = calculate_months_diff(d1, d2)
        ruler.set_lifespan(months_diff)
        self.rulers.append(ruler)

    def calculate_color_spectrum(self, n):
        """Calculate the color spectrum. Some countries (like sweden) have the first color equal to the last, in that
        case the spectrum is just a range between the two colors to avoid confusion."""
        c1, c2, c3 = (Color(rgb=map(lambda x: x / 255, color)) for color in self.colors)
        if c1 == c3:
            it = c1.range_to(c2, n)
        else:
            steps = n // 2 + 1
            it = itertools.chain(c1.range_to(c2, steps), c2.range_to(c3, steps))
        spectrum = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in it]
        return spectrum[:-(len(spectrum) - n + 1)] + [spectrum[-1]]


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
        self.mana_generated = None

    def __str__(self):
        return f"value={self.value}, months={self.months}"

    def set_lifespan(self, months):
        self.months = months
        self.mana_generated = self.value * self.months
