import csv
import datetime
import json
from collections import defaultdict

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
        country = self.player if country is None else country
        conquests = self.get_conquest_history(country=country)
        dates = {p.last_conquest for p in conquests}
        country_color = tuple(map(lambda x: x / 255, self.countries[country]['colors']['map_color'].values()))
        a = Color(rgb=country_color, luminance=0.2)
        b = Color(rgb=a.rgb, luminance=0.8)
        gradient = a.range_to(b, len(dates))
        gradient = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in gradient]
        dates_to_color = {date: c for date, c in zip(sorted(dates), gradient)}
        id_to_color = defaultdict(lambda: (128, 128, 128), {p.id: dates_to_color[p.last_conquest] for p in conquests})
        color_conversions = {}
        with open(f"{ASSETS_DIR}/definition.csv", encoding='windows-1252') as f:
            reader = csv.DictReader(f, delimiter=';')
            for line in reader:
                rgb = tuple(int(line[x]) for x in ('red', 'green', 'blue'))
                province_id = int(line['province'])
                color_conversions[rgb] = id_to_color[province_id]
                # todo create map with borders and unique colors for sea tiles
        im = Image.open(f"{ASSETS_DIR}/provinces.png")
        ls = [color_conversions[px_value] for px_value in im.getdata()]
        # todo autocrop image
        out = Image.new(im.mode, im.size)
        out.putdata(ls)
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
