import datetime
import itertools
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from colour import Color

from models import Ruler, Province
from src import ASSETS_DIR
from util import get_date, yield_info, calculate_months_diff, timing


class Analyzer:
    start_date = datetime.datetime(year=1444, month=11, day=11)
    # https://eu4.paradoxwikis.com/Template:Revolutionary_flag
    rev_colors = [(255, 255, 255), (20, 20, 20), (131, 0, 146), (121, 0, 41), (103, 0, 5), (185, 0, 0),
                  (195, 83, 0), (66, 40, 20), (245, 193, 0), (0, 59, 9), (0, 124, 52), (0, 194, 111),
                  (0, 175, 194), (53, 0, 131), (110, 194, 243), (26, 50, 134), (211, 0, 27)]

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
    def draw_conquest_heat_map(self, country=None, crop_margin=50, resize_ratio=1.0, start_date=None, end_date=None):
        country = self.player if country is None else country
        start_date = get_date(start_date) if start_date else self.start_date
        end_date = (get_date(end_date) if end_date else self.current_date) + datetime.timedelta(days=1)
        provinces = self.get_conquest_history(country=country, end_date=end_date)
        months_diff = [max(calculate_months_diff(p.last_conquest, start_date), 0) for p in provinces]
        colors = [self.rev_colors[i] for i in self.countries[country]["colors"]["revolutionary_colors"].values()]
        spectrum = self.calculate_spectrum(colors=colors, parts=end_date.year - start_date.year + 1)
        id_to_color = {str(p.id): spectrum[max(p.last_conquest.year - start_date.year, 0)]
                       for p, months in zip(provinces, months_diff)}
        width, height = self.map_img.size
        pixels = self.map_img_pixels.copy()
        e, n, w, s = 0, height, width, 0
        for province_id, color in id_to_color.items():
            for x, bands in self.province_coordinates[province_id].items():
                x = int(x)
                for y1, y2 in bands:
                    pixels[x, y1:y2] = color
                    e = max(e, min(y2 + crop_margin, width))
                    w = min(w, max(y1 - crop_margin, 0))
                n = min(n, max(x - crop_margin, 0))
                s = max(s, min(x + crop_margin, height))
        out = Image.fromarray(pixels)
        if out.size[0] > 50 and crop_margin >= 0:
            out = out.crop((w, n, e, s))
            self.draw_legend(out, colors, start_date, end_date)
        out = out.resize(np.array(out.size) * resize_ratio, Image.BILINEAR)
        out.save(f"{ASSETS_DIR}/heatmap.png")

    def draw_legend(self, im, colors, start_date, end_date):
        font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 15, encoding='unic')
        draw = ImageDraw.Draw(im)
        draw.fontmode = '1'
        margin, height = 10, 30
        w, h = im.size
        box_width = (w - 2 * margin)
        if start_date.year != end_date.year:
            spectrum = self.calculate_spectrum(colors, parts=box_width)
            for i, c in enumerate(spectrum):
                draw.rectangle([(margin + i, h - margin - height), (margin + i + 1, h - margin)], fill=c)
            draw.rectangle([(margin, h - margin - height), (w - margin, h - margin)], outline="black", width=1)
        else:
            draw.rectangle([(margin, h - margin - height), (w - margin, h - margin)],
                           outline="black", width=1, fill=colors[0])
        font_margin = 8
        draw.text((margin + font_margin, h - margin - height + font_margin),
                  str(start_date.year), font=font, fill='white')
        draw.text((w - margin - 42, h - margin - height + font_margin),
                  str(end_date.year), font=font, fill='white')

    @staticmethod
    def calculate_spectrum(colors, parts):
        """Calculate the color spectrum. Some countries (like sweden) have the first color equal to the last, in that
        case the spectrum is just a range between the two colors to avoid confusion."""
        c1, c2, c3 = (Color(rgb=map(lambda x: x / 255, color)) for color in colors)
        if c1 == c3:
            it = c1.range_to(c2, parts)
        else:
            steps = parts // 2 + 1
            it = itertools.chain(c1.range_to(c2, steps), c2.range_to(c3, steps))
        spectrum = [tuple(map(lambda x: round(x * 255), c.rgb)) for c in it]
        return spectrum[:-(len(spectrum) - parts + 1)] + [spectrum[-1]]

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
    analyzer.draw_conquest_heat_map(resize_ratio=2)
