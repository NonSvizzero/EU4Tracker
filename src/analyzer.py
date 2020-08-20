import csv
import datetime
import json

import numpy as np
from PIL import Image
from colour import Color

from models import Ruler, Province
from src import ASSETS_DIR
from util import get_date, yield_info, calculate_months_diff, timing


class Analyzer:
    start_date = datetime.datetime(year=1444, month=11, day=11)

    def __init__(self, gameinfo):
        self.gameinfo = gameinfo
        self.player = gameinfo["meta"]["player"]
        self.current_date = get_date(gameinfo["meta"]["date"])
        self.countries = gameinfo["gamestate"]["countries"]
        self.provinces = [Province(id=int(i[1:]), **p) for i, p in gameinfo["gamestate"]["provinces"].items()]

    @timing
    def draw_conquest_heat_map(self, country=None):
        conquests = self.get_conquest_history(country=country)
        starting = [p for p in conquests if calculate_months_diff(self.start_date, p.last_conquest) == 0]
        s = len(starting)
        a, b = Color('green'), Color('red')  # todo find good colors for the heatmap
        gradient = [a] * s + list(a.range_to(b, len(conquests) - s))
        gradient = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in gradient]
        id_to_gradient = {p.id: c for p, c in zip(conquests, gradient)}
        color_to_id = {}
        with open(f"{ASSETS_DIR}/definition.csv", encoding='windows-1252') as f:
            reader = csv.DictReader(f, delimiter=';')
            for line in reader:
                color_to_id[tuple(int(line[x]) for x in ('red', 'green', 'blue'))] = int(line['province'])
        im = Image.open(f"{ASSETS_DIR}/provinces.bmp")
        w, h = im.size
        maxw, maxh = 1920, 1080  # fixme find a good aaspect ratio that keeps performance high
        ratio = min(maxw / w, maxh / h)
        new_size = tuple(map(lambda x: round(x * ratio), im.size))
        im.thumbnail(new_size, resample=Image.NEAREST)
        out = im.copy()
        w, h = im.size
        for x in range(w):
            for y in range(h):
                px = im.getpixel((x, y))
                province_id = color_to_id.get(px, -1)
                out_color = id_to_gradient.get(province_id, (128, 128, 128))
                out.putpixel((x, y), out_color)
                # todo put another color for water
        out.save(f"{ASSETS_DIR}/heatmap.png")

    def get_conquest_history(self, country=None):
        country = self.player if country is None else country
        conquests = list(sorted((p for p in self.provinces if getattr(p, "owner", None) == country),
                                key=lambda p: p.last_conquest))
        return conquests

    def get_ruler_history(self, country=None):
        country = self.player if country is None else country
        rulers = []
        results = {}
        total_months = 0
        last_crowning = last_ruler = None
        for date, history in yield_info(self.countries[country]["history"], f=lambda x: x[0] == '1'):
            if any(x in history for x in ('monarch', 'monarch_heir')):
                new_crowing = get_date(date)
                if new_crowing > self.start_date:
                    months_diff = calculate_months_diff(new_crowing, last_crowning)
                    last_ruler.months = months_diff
                    total_months += months_diff
                    rulers.append(last_ruler)
                last_crowning, last_ruler = new_crowing, Ruler(**history.popitem()[1])
        months_diff = calculate_months_diff(self.current_date, last_crowning)
        last_ruler.months = months_diff
        total_months += months_diff
        rulers.append(last_ruler)
        # rulers stats
        results["avg_months_active"] = np.average([r.months for r in rulers if not r.is_regency_council])
        results["avg_mana"] = sum([r.mana_generated() for r in rulers]) / total_months
        return results

    @classmethod
    def from_file(cls, filename):
        with open(filename) as f:
            d = json.load(f)
            return cls(gameinfo=d)


if __name__ == '__main__':
    analyzer = Analyzer.from_file(f"{ASSETS_DIR}/emperor.json")
    analyzer.draw_conquest_heat_map()
