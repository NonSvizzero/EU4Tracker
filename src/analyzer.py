import datetime
import itertools
import json

import numpy as np
from PIL import Image
from colour import Color

from models import Ruler, Province
from src import ASSETS_DIR
from util import get_date, yield_info, calculate_months_diff, timing


class Analyzer:
    start_date = datetime.datetime(year=1444, month=11, day=11)
    # https://eu4.paradoxwikis.com/Template:Revolutionary_flag
    rev_colors = [Color(rgb=map(lambda x: x / 255, t)) for t in
                  ((255, 255, 255), (20, 20, 20), (131, 0, 146), (121, 0, 41), (103, 0, 5), (185, 0, 0),
                   (195, 83, 0), (66, 40, 20), (245, 193, 0), (0, 59, 9), (0, 124, 52), (0, 194, 111),
                   (0, 175, 194), (53, 0, 131), (110, 194, 243), (26, 50, 134), (211, 0, 27))]

    def __init__(self, gameinfo):
        self.gameinfo = gameinfo
        self.player = gameinfo["meta"]["player"]
        self.current_date = get_date(gameinfo["meta"]["date"])
        self.countries = gameinfo["gamestate"]["countries"]
        self.provinces = [Province(id=int(i[1:]), **p) for i, p in gameinfo["gamestate"]["provinces"].items()]
        with open(f"{ASSETS_DIR}/province_coordinates.json") as f:
            self.province_coordinates = json.load(f)
        self.map_img = Image.open(f"{ASSETS_DIR}/provinces_bordered.png")
        self.map_img_pixels = np.array(self.map_img)

    @timing
    def draw_conquest_heat_map(self, country=None, crop_offset=50, resize_ratio=1.0, start_date=None, end_date=None):
        country = self.player if country is None else country
        start_date = get_date(start_date) if start_date else self.start_date
        end_date = get_date(end_date) if end_date else self.current_date
        provinces = self.get_conquest_history(country=country, end_date=end_date)
        months_diff = [max(calculate_months_diff(p.last_conquest, start_date), 0) for p in provinces]
        max_month_diff = max(months_diff) + 1
        c1, c2, c3 = [self.rev_colors[i] for i in self.countries[country]["colors"]["revolutionary_colors"].values()]
        steps = max_month_diff // 2 + 1
        spectrum = itertools.chain(c1.range_to(c2, steps), c2.range_to(c3, steps))
        months_to_color = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in spectrum]
        id_to_color = {str(p.id): months_to_color[months] for p, months in zip(provinces, months_diff)}
        width, height = self.map_img.size
        pixels = self.map_img_pixels.copy()
        e, n, w, s = 0, height, width, 0
        for province_id, color in id_to_color.items():
            for x, bands in self.province_coordinates[province_id].items():
                x = int(x)
                for y1, y2 in bands:
                    pixels[x, y1:y2] = color
                    e = max(e, min(y2 + crop_offset, width))
                    w = min(w, max(y1 - crop_offset, 0))
                n = min(n, max(x - crop_offset, 0))
                s = max(s, min(x + crop_offset, height))
        out = Image.fromarray(pixels)
        if crop_offset >= 0:
            out = out.crop((w, n, e, s))
        out = out.resize(np.array(out.size) * resize_ratio, Image.BILINEAR)
        # todo draw legend
        out.save(f"{ASSETS_DIR}/heatmap.png")

    def get_conquest_history(self, country=None, end_date=None):
        country = self.player if country is None else country
        end_date = end_date if end_date else self.current_date
        conquests = list(sorted((p for p in self.provinces if getattr(p, "owner", None) == country and
                                 p.last_conquest <= end_date),
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
    analyzer.draw_conquest_heat_map(resize_ratio=3)
