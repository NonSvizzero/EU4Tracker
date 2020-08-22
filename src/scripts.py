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
    id_to_pixels = defaultdict(lambda: defaultdict(list))  # {id: {y: [[x1, x2], ...[]]}} list of bands for each row
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
    for y in range(h):
        previous = pixels[y * w]
        start = 0
        for x in range(w):
            i = y * w + x
            pixel = pixels[i]
            if pixel in sea_colors:
                new_pixels[i] = new_sea_color
            elif previous != pixel or (i - w > 0 and pixel != pixels[i - w]):
                new_pixels[i] = black
                province_id = rgb_to_id[previous]
                id_to_pixels[province_id][y].append([start, x])
                start = x + 1
            else:
                new_pixels[i] = gray
            previous = pixel
        province_id = rgb_to_id[previous]
        id_to_pixels[province_id][y].append([start, x])
    out = Image.new(im.mode, im.size)
    out.putdata(new_pixels)
    out.save(f"{ASSETS_DIR}/provinces_bordered.png")
    with open(f"{ASSETS_DIR}/province_coordinates.json", 'w') as f:
        json.dump(id_to_pixels, f)


if __name__ == '__main__':
    process_map()
