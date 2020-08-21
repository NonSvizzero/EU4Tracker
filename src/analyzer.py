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
        with open(f"{ASSETS_DIR}/province_coordinates.json") as f:
            self.province_coordinates = json.load(f)
        self.map_img = Image.open(f"{ASSETS_DIR}/provinces_bordered.png")
        self.map_img_pixels = self.map_img.getdata()

    @timing
    def draw_conquest_heat_map(self, country=None, crop_offset=50):
        country = self.player if country is None else country
        conquests = self.get_conquest_history(country=country)
        max_month_diff = max(calculate_months_diff(p.last_conquest, self.start_date) for p in conquests)
        country_color = tuple(map(lambda x: x / 255, self.countries[country]['colors']['map_color'].values()))
        a = Color(rgb=country_color, luminance=0.1, saturation=0.9)  # fixme find proper hsl values here
        b = Color(rgb=a.rgb, luminance=0.9, saturation=0.1)
        gradient = a.range_to(b, max_month_diff + 1)
        gradient = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in gradient]
        dates_to_color = {date: c for date, c in zip(range(max_month_diff + 1), gradient)}
        id_to_color = {str(p.id): dates_to_color[calculate_months_diff(p.last_conquest, self.start_date)]
                       for p in conquests}
        width, height = self.map_img.size
        ls = list(self.map_img_pixels)
        e, n, w, s = 0, height, width, 0
        for province_id, color in id_to_color.items():
            for x, bands in self.province_coordinates[province_id].items():
                x = int(x)
                for y1, y2 in bands:
                    band_length = y2 - y1
                    band_start = x * width + y1
                    for i in range(band_start, band_start + band_length):
                        ls[i] = color
                e = max(e, min(y2 + crop_offset, width))
                n = min(n, max(x - crop_offset, 0))
                w = min(w, max(y2 - crop_offset, 0))
                s = max(s, min(x + crop_offset, height))
        out = Image.new(self.map_img.mode, self.map_img.size)
        out.putdata(ls)
        if crop_offset >= 0:
            out = out.crop((w, n, e, s))
        # todo resize options
        # todo draw legend
        # todo provide timeframe options
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
