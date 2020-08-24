import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from models import Campaign, START_DATE
from src import ASSETS_DIR
from util import get_date, timing


class Analyzer:
    def __init__(self):
        with open(f"{ASSETS_DIR}/province_coordinates.json") as f:
            self.province_coordinates = json.load(f)
        self.map_img = Image.open(f"{ASSETS_DIR}/provinces_bordered.png")
        self.map_img_pixels = np.array(self.map_img)
        self.font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 15, encoding='unic')
        # todo load config here for drawing, etc
        self.campaign = None

    def analyze(self, campaign):
        self.campaign = campaign
        self.draw_conquest_heat_map()

    @timing
    def draw_conquest_heat_map(self, country=None, crop_margin=50, resize_ratio=1.0, start_date=None, end_date=None):
        # todo add support for multiplayer by drawing multiple countries in a single map
        # fixme some provinces in the bharat file don't work properly, find why
        country = self.campaign.get_country(country)
        start_date = get_date(start_date) if start_date else START_DATE
        end_date = get_date(end_date) if end_date else self.campaign.current_date  # todo raise exception wrong date
        provinces = [p for p in country.owned_provinces if p.last_conquest <= end_date]
        spectrum = country.calculate_color_spectrum(n=end_date.year - start_date.year + 1)
        id_to_color = {str(p.id): spectrum[max(p.last_conquest.year - start_date.year, 0)] for p in provinces}
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
            w, h = out.size
            # draw legend
            draw = ImageDraw.Draw(out)
            draw.fontmode = '1'
            margin, height = 10, 30
            box_width = (w - 2 * margin)
            # fixme test functioning for conquest after a single year on 3-color countries
            if start_date.year != end_date.year:
                spectrum = country.calculate_color_spectrum(n=box_width)
                for i, c in enumerate(spectrum):
                    draw.rectangle([(margin + i, h - margin - height), (margin + i + 1, h - margin)], fill=c)
                draw.rectangle([(margin, h - margin - height), (w - margin, h - margin)], outline="black", width=1)
            else:
                draw.rectangle([(margin, h - margin - height), (w - margin, h - margin)],
                               outline="black", width=1, fill=country.colors[0])
            font_margin = 8
            draw.text((margin + font_margin, h - margin - height + font_margin),
                      str(start_date.year), font=self.font, fill='white')
            draw.text((w - margin - 42, h - margin - height + font_margin),
                      str(end_date.year), font=self.font, fill='white')
        out = out.resize(np.array(out.size) * resize_ratio, Image.BILINEAR)
        out.save(f"{ASSETS_DIR}/heatmap.png")


if __name__ == '__main__':
    analyzer = Analyzer()
    campaign = Campaign.from_file(f"{ASSETS_DIR}/Bharat.json", player_only=True)
    analyzer.analyze(campaign)
