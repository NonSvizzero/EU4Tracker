import csv
import json
from collections import defaultdict

from PIL import Image

from src import ASSETS_DIR


def process_map():
    black = (0, 0, 0)
    gray = (128, 128, 128)
    new_sea_color = (39, 199, 255)
    sea_colors = set()
    sea_ids = set()  # todo load here ids of sea tiles stored in default.map
    rgb_to_id = {}
    id_to_pixels = defaultdict(lambda: defaultdict(list))  # {id: {x: [[y1, y2], ...[]]}} list of bands for each row
    with open(f"{ASSETS_DIR}/definition.csv", encoding='windows-1252') as f:
        reader = csv.DictReader(f, delimiter=';')
        for line in reader:
            rgb = tuple(int(line[x]) for x in ('red', 'green', 'blue'))
            province_id = int(line['province'])
            rgb_to_id[rgb] = province_id
            if province_id in sea_ids:
                sea_colors.add(rgb)
    # draw black borders and gray out all land
    im = Image.open(f"{ASSETS_DIR}/provinces.png")
    w, h = im.size
    pixels = list(im.getdata())
    new_pixels = pixels.copy()
    for x in range(h):
        previous = pixels[x * w]
        for y in range(w):
            i = x * w + y
            pixel = pixels[i]
            if i - w > 0 and pixel != pixels[i - w]:
                new_pixels[i - w] = black
                new_pixels[i] = black
            elif previous == pixel:
                new_pixels[i] = pixel
            elif pixel in sea_colors:
                new_pixels[i] = new_sea_color
            else:
                new_pixels[i] = black
            previous = pixel
    out = Image.new(im.mode, im.size)
    out.putdata([p if (p == black or p == new_sea_color) else gray for p in new_pixels])
    out.save(f"{ASSETS_DIR}/provinces_bordered.png")
    # store coordinates for each tile
    for x in range(h):
        previous = black
        for y in range(w):
            i = x * w + y
            pixel = new_pixels[i]
            if pixel == new_sea_color or previous == new_sea_color:
                continue
            if previous == black and pixel != black:
                province_id = rgb_to_id[pixel]
                id_to_pixels[province_id][x].append([y, w])
            elif pixel == black and previous != black:
                province_id = rgb_to_id[previous]
                id_to_pixels[province_id][x][-1][1] = y
            previous = pixel
    with open(f"{ASSETS_DIR}/province_coordinates.json", 'w') as f:
        json.dump(id_to_pixels, f)


if __name__ == '__main__':
    process_map()
