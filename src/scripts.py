import csv
import json
from collections import defaultdict

import geojson
import numpy as np
from PIL import Image
from rasterio.features import shapes

from src import ASSETS_DIR


def process_map():
    black = (0, 0, 0)
    gray = (128, 128, 128)
    new_sea_color = (166, 255, 255)
    sea_colors = set()
    sea_ids = {4224, 4225, 4226, 4233, 4234, 4333, 4346, 4347, 4357, 4358, 3004, 3005, 3006, 3007, 3008, 3009, 3010,
               3011, 3012, 3013, 3014, 3015, 3016, 3017, 3018, 3019, 3020, 3021, 3022, 3023, 3024, 3025, 3026, 3027,
               3028, 3029, 3030, 3031, 3032, 3033, 3034, 3035, 3036, 3037, 3038, 3039, 3040, 3041, 3042, 3043, 3044,
               3045, 3046, 3047, 3048, 3049, 3050, 3051, 3052, 3053, 3054, 3055, 3056, 3057, 3058, 3059, 3060, 3061,
               3062, 3063, 3064, 3065, 3066, 3067, 3068, 3069, 3070, 3071, 3072, 3073, 3074, 3075, 3076, 3077, 3078,
               3079, 3080, 3081, 3082, 3083, 3084, 3085, 3086, 3087, 3088, 3089, 3090, 3091, 3092, 3093, 3094, 3095,
               3096, 3097, 3098, 3099, 3100, 3101, 3102, 3103, 3104, 3105, 3106, 3107, 3108, 3109, 3110, 3111, 3112,
               3113, 3114, 3115, 3116, 3117, 3118, 3119, 3120, 3121, 3122, 3123, 3124, 3125, 3126, 3127, 3128, 3129,
               3130, 3131, 3132, 3133, 3134, 3135, 3136, 3137, 3138, 3139, 3140, 3141, 3142, 3143, 3144, 3145, 3146,
               3147, 3148, 3149, 3150, 3151, 3152, 3153, 3154, 3155, 3156, 3157, 3158, 3159, 3160, 3161, 3162, 3163,
               3164, 3165, 3166, 3167, 3168, 3169, 3170, 3171, 3172, 3173, 3174, 3175, 3176, 3177, 3178, 3179, 3180,
               3181, 3182, 3183, 3184, 3185, 3186, 3187, 3188, 3189, 1252, 1253, 1254, 1255, 1256, 1257, 1258, 1259,
               1263, 1264, 1265, 1266, 1267, 1268, 1269, 1270, 1271, 1272, 1274, 1275, 1276, 1277, 1278, 1279, 1280,
               1281, 1282, 1283, 1284, 1285, 1286, 1287, 1288, 1289, 1290, 1291, 1292, 1293, 1294, 1295, 1296, 1297,
               1298, 1299, 1300, 1301, 1302, 1303, 1304, 1305, 1307, 1308, 1309, 1310, 1311, 1312, 1313, 1314, 1315,
               1316, 1317, 1319, 1320, 1321, 1322, 1323, 1324, 1328, 1329, 1330, 1331, 1332, 1333, 1334, 1335, 1336,
               1337, 1338, 1339, 1340, 1341, 1342, 1343, 1344, 1345, 1346, 1347, 1348, 1349, 1350, 1351, 1352, 1353,
               1354, 1355, 1356, 1357, 1358, 1359, 1360, 1361, 1362, 1363, 1364, 1365, 1366, 1367, 1368, 1369, 1370,
               1371, 1372, 1373, 1374, 1375, 1376, 1377, 1378, 1379, 1380, 1381, 1382, 1383, 1384, 1385, 1386, 1387,
               1388, 1389, 1390, 1391, 1392, 1393, 1394, 1395, 1396, 1397, 1398, 1399, 1400, 1401, 1402, 1403, 1404,
               1405, 1406, 1407, 1408, 1409, 1410, 1411, 1412, 1413, 1414, 1415, 1416, 1417, 1418, 1419, 1420, 1421,
               1422, 1423, 1424, 1425, 1426, 1427, 1428, 1429, 1430, 1431, 1432, 1433, 1434, 1435, 1436, 1437, 1438,
               1439, 1440, 1441, 1442, 1443, 1444, 1445, 1446, 1447, 1448, 1449, 1450, 1451, 1452, 1453, 1454, 1455,
               1456, 1457, 1458, 1459, 1460, 1461, 1462, 1463, 1464, 1465, 1466, 1467, 1468, 1469, 1470, 1471, 1472,
               1473, 1474, 1475, 1476, 1477, 1478, 1479, 1480, 1481, 1482, 1483, 1484, 1485, 1486, 1487, 1488, 1489,
               1490, 1491, 1492, 1493, 1494, 1495, 1496, 1497, 1498, 1499, 1500, 1501, 1502, 1503, 1504, 1505, 1506,
               1507, 1508, 1509, 1510, 1511, 1512, 1513, 1514, 1515, 1516, 1517, 1518, 1519, 1520, 1521, 1522, 1523,
               1524, 1525, 1526, 1527, 1528, 1529, 1530, 1531, 1532, 1533, 1534, 1535, 1536, 1537, 1538, 1539, 1540,
               1541, 1542, 1543, 1544, 1545, 1546, 1547, 1548, 1549, 1550, 1551, 1552, 1553, 1554, 1555, 1556, 1557,
               1558, 1559, 1560, 1561, 1562, 1563, 1564, 1565, 1566, 1567, 1568, 1569, 1570, 1571, 1572, 1573, 1574,
               1575, 1576, 1577, 1578, 1579, 1580, 1581, 1582, 1583, 1584, 1585, 1586, 1587, 1588, 1589, 1590, 1591,
               1592, 1593, 1594, 1595, 1596, 1597, 1598, 1599, 1600, 1601, 1602, 1603, 1604, 1605, 1606, 1607, 1608,
               1609, 1610, 1611, 1612, 1613, 1614, 1615, 1616, 1617, 1618, 1619, 1620, 1621, 1622, 1623, 1624, 1625,
               1626, 1627, 1628, 1629, 1630, 1631, 1632, 1633, 1634, 1635, 1636, 1637, 1638, 1639, 1640, 1641, 1642,
               1643, 1644, 1645, 1646, 1647, 1652, 1666, 1667, 1668, 1669, 1670, 1671, 1672, 1673, 1674, 1675, 1676,
               1677, 1678, 1679, 1680, 1681, 1682, 1683, 1684, 1685, 1686, 1687, 1688, 1689, 1690, 1691, 1692, 1693,
               1694, 1695, 1696, 1697, 1698, 1699, 1700, 1701, 1702, 1703, 1704, 1705, 1706, 1707, 1708, 1709, 1710,
               1711, 1712, 1713, 1714, 1715, 1716, 1717, 1718, 1719, 1720, 1721, 1722, 1723, 1724, 1725, 1726, 1727,
               1728, 1729, 1730, 1731, 1732, 1733, 1734, 1735, 1736, 1737, 1738, 1739, 1740, 1741, 1924, 1926, 1927,
               1928, 1929, 1932, 1975, 1980}  # stored in default.map game file
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
            if previous != pixel or (i - w > 0 and pixel != pixels[i - w]):
                new_pixels[i] = black
                province_id = rgb_to_id[previous]
                id_to_pixels[province_id][y].append([start, x])
                start = x + 1
            else:
                new_pixels[i] = new_sea_color if pixel in sea_colors else gray
            previous = pixel
        province_id = rgb_to_id[previous]
        id_to_pixels[province_id][y].append([start, x])
    out = Image.new(im.mode, im.size)
    out.putdata(new_pixels)
    out.save(f"{ASSETS_DIR}/provinces_bordered.png")
    with open(f"{ASSETS_DIR}/province_coordinates.json", 'w') as f:
        json.dump(id_to_pixels, f)


def find_polygons():
    rgb_to_province = {}
    with open(f"{ASSETS_DIR}/definition.csv", encoding='windows-1252') as f:
        reader = csv.DictReader(f, delimiter=';')
        for line in reader:
            rgb = tuple(int(line[x]) for x in ('red', 'green', 'blue'))
            province_id = int(line['province'])
            rgb_to_province[rgb] = (province_id, line['name'])
    im = Image.open(f"{ASSETS_DIR}/provinces.png")
    arr = np.array(im)
    out = np.vectorize(rgb_to_int32, otypes=[np.int32])(*np.rollaxis(arr, 2, 0))
    out = out[::-1]
    features = []
    for i, (s, v) in enumerate(shapes(out)):
        rgb = int32_to_rgb(v)
        province_id, name = rgb_to_province[rgb]
        feature = {"geometry": s, "id": province_id, "properties": {"color": rgb, "name": name}, "type": "Feature"}
        features.append(feature)

    feature_collection = geojson.FeatureCollection(sorted(features, key=lambda x: x["id"]))
    with open(f'{ASSETS_DIR}/provinces.geojson', 'w') as f:
        geojson.dump(feature_collection, f)
        print(f"{len(features)} polygons found! GeoJSON dumped.")


def rgb_to_int32(r, g, b):
    return (r << 16) + (g << 8) + b


def int32_to_rgb(n):
    n = int(n)
    return n >> 16 & 0xFF, n >> 8 & 0xFF, n & 0xFF


if __name__ == '__main__':
    find_polygons()
