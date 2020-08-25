import itertools
import json
from datetime import datetime

import numpy as np
from colour import Color

from util import yield_info, get_date, calculate_months_diff, timing

START_DATE = datetime(year=1444, month=11, day=11)

MANA_EXPENSES = ['buy_idea', 'advance_tech', 'boost_stab', 'buy_general', 'buy_admiral', 'buy_conq', 'buy_explorer',
                 'develop_prov', 'force_march', 'assault', 'seize_colony', 'burn_colony', 'attack_natives',
                 'scorch_earth', 'demand_non_wargoal_prov', 'reduce_inflation', 'move_capital', 'make_province_core',
                 'replace_rival', 'change_gov', 'change_culture', 'harsh_treatment', 'reduce_we', 'boost_faction',
                 'raise_war_taxes', 'buy_native_advancement', 'increase_tariffs', 'promote_merc', 'decrease_tariffs',
                 'move_trade_port', 'create_trade_post', 'siege_sorties', 'buy_religious_reform', 'set_primary_culture',
                 'add_accepted_culture', 'remove_accepted_culture', 'strengthen_government', 'boost_millitarization',
                 'unknown', 'artillery_barrage', 'establish_siberian_frontier', 'government_interaction', 'unknown',
                 'naval_barrage', 'unknown', 'force_march', 'create_leader', 'enforce_culture', 'effect',
                 'minority_expulsion', 'unknown']

MANA = ('ADM', 'DIP', 'MIL')


class DummyCountryException(Exception):
    pass


class Campaign:
    def __init__(self, gameinfo, player_only=False):
        self.gameinfo = gameinfo
        self.player = gameinfo["meta"]["player"]
        self.current_date = get_date(gameinfo["meta"]["date"])
        self.countries = {}
        for tag, c in gameinfo["gamestate"]["countries"].items():
            try:
                self.countries[tag] = Country(tag=tag, **c)
            except DummyCountryException:  # fixme some real countries don't have revolutionary colors, find another key
                pass
        self.provinces = [Province(id=int(i[1:]), **p) for i, p in gameinfo["gamestate"]["provinces"].items()]
        if player_only:
            player_country = self.countries[self.player]
            player_country.analyze(self)
        else:
            for country in self.countries.values():
                country.analyze(self)

    def __str__(self):
        return str(self.gameinfo["meta"])

    def get_country(self, country=None):
        return self.countries[country if country else self.player]

    @classmethod
    @timing
    def from_file(cls, filename, player_only=False):
        with open(filename) as f:
            d = json.load(f)
            return cls(gameinfo=d, player_only=player_only)


class Country:
    # https://eu4.paradoxwikis.com/Template:Revolutionary_flag
    REV_COLORS = [(255, 255, 255), (20, 20, 20), (131, 0, 146), (121, 0, 41), (103, 0, 5), (185, 0, 0),
                  (195, 83, 0), (66, 40, 20), (245, 193, 0), (0, 59, 9), (0, 124, 52), (0, 194, 111),
                  (0, 175, 194), (53, 0, 131), (110, 194, 243), (26, 50, 134), (211, 0, 27)]

    def __init__(self, **kwargs):
        self.__dict__.update(**kwargs)
        try:
            self.colors = [self.REV_COLORS[i] for i in kwargs["colors"]["revolutionary_colors"].values()]
        except KeyError:
            raise DummyCountryException
        self.rulers = []
        self.avg_ruler_stats = None
        self.avg_ruler_life = None

    def __str__(self):
        return self.tag

    def __repr__(self):
        return str(self)

    def analyze(self, campaign):
        self.categorize_mana_expenses()
        self.get_ruler_history(campaign.current_date)
        self.calculate_provinces(campaign.provinces)

    def calculate_provinces(self, provinces):
        for k in ('owned_provinces', 'controlled_provinces', 'core_provinces'):
            setattr(self, k, list(sorted((provinces[i - 1] for i in getattr(self, k).values()),
                                         key=lambda p: p.last_conquest)))
        for k in ('capital', 'trade_port'):
            setattr(self, k, provinces[getattr(self, k)])
        # fixme add subject provinces

    def get_ruler_history(self, current_date):
        total_months = calculate_months_diff(current_date, START_DATE)
        last_crowning = last_ruler = None
        for date, history in yield_info(((k, v) for k, v in self.history.items() if k[0].isnumeric())):
            if any(x in history for x in ('monarch', 'monarch_heir')):
                new_crowing = get_date(date)
                try:
                    last_ruler = Ruler(**history['monarch'])
                except KeyError:
                    last_ruler = Ruler(**history['monarch_heir'])
                if new_crowing > START_DATE:
                    self.add_ruler(last_ruler, new_crowing, last_crowning)
                    last_crowning = new_crowing
                else:
                    last_crowning = START_DATE
        self.add_ruler(last_ruler, current_date, last_crowning)
        # rulers stats
        self.avg_ruler_life = np.average([r.months for r in self.rulers if not r.is_regency_council])
        self.avg_ruler_stats = sum([r.mana_generated for r in self.rulers]) / total_months

    def categorize_mana_expenses(self):
        for k in (f"{x.lower()}_spent_indexed" for x in MANA):
            d = getattr(self, k)
            setattr(self, k, {MANA_EXPENSES[int(kw)]: v for kw, v in d.items()})

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
            for k, v in yield_info(((k, v) for k, v in self.history.items() if k[0].isnumeric())):
                inner, tag = v.popitem()
                # fixme this probably breaks with tag-switching countries, see occupations as well
                if inner == 'owner':
                    self.last_conquest = get_date(k)
        except AttributeError:  # no history -> uncolonized?
            pass

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return str(self)


class Ruler:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.value = np.array([kwargs[x] for x in MANA])
        self.is_regency_council = kwargs['name'] == "(Regency Council)"
        self.months = None
        self.mana_generated = None

    def __str__(self):
        return f"name={self.name}, value={self.value}, months={self.months}"

    def __repr__(self):
        return str(self)

    def set_lifespan(self, months):
        self.months = months
        self.mana_generated = self.value * self.months
