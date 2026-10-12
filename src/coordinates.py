"""Display-only WGS84 / GCJ-02 conversion; stored routes always remain WGS84.

The inverse is a numerical approximation, not an official surveying service.
Never reinterpret existing WGS84 values as GCJ-02 when changing providers.
"""
import math


def wgs84_to_gcj02(latitude, longitude):
    if not (72.004 <= longitude <= 137.8347 and 0.8293 <= latitude <= 55.8271):
        return latitude, longitude
    x, y = longitude - 105, latitude - 35
    dlat = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
    dlon = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
    wave = (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    dlat += wave + (20*math.sin(y*math.pi) + 40*math.sin(y*math.pi/3))*2/3
    dlat += (160*math.sin(y*math.pi/12) + 320*math.sin(y*math.pi/30))*2/3
    dlon += wave + (20*math.sin(x*math.pi) + 40*math.sin(x*math.pi/3))*2/3
    dlon += (150*math.sin(x*math.pi/12) + 300*math.sin(x*math.pi/30))*2/3
    rad = math.radians(latitude)
    magic = 1 - .00669342162296594323 * math.sin(rad)**2
    dlat = dlat*180 / ((6378245*(1-.00669342162296594323))/(magic*math.sqrt(magic))*math.pi)
    dlon = dlon*180 / (6378245/math.sqrt(magic)*math.cos(rad)*math.pi)
    return latitude+dlat, longitude+dlon


def gcj02_to_wgs84(latitude, longitude):
    lat, lon = latitude, longitude
    for _ in range(8):
        mapped_lat, mapped_lon = wgs84_to_gcj02(lat, lon)
        a, b = mapped_lat-latitude, mapped_lon-longitude
        lat, lon = lat-a, lon-b
        if max(abs(a), abs(b)) < 1e-9:
            break
    return lat, lon


def to_amap(points):
    return [list(reversed(wgs84_to_gcj02(p['latitude'], p['longitude']))) for p in points]


def from_amap(points):
    from src.route import normalize_route
    from utils.auxiliary_util import SportsUploaderError
    if not isinstance(points, list) or len(points) > 5000:
        raise SportsUploaderError('路线点数超过上限。')
    converted = []
    for p in points:
        if not isinstance(p, list) or len(p) != 2:
            raise SportsUploaderError('地图坐标格式错误。')
        lon, lat = map(float, p)
        if not math.isfinite(lat) or not math.isfinite(lon) or not (-85 <= lat <= 85 and -180 <= lon <= 180):
            raise SportsUploaderError('地图坐标超出范围。')
        lat, lon = gcj02_to_wgs84(lat, lon)
        converted.append({'latitude':lat, 'longitude':lon})
    return normalize_route(converted)


def service_coordinate(config, latitude, longitude):
    """Custom editor routes are WGS84; the running map consumes GCJ-02.

    Legacy coordinate-only callers retain their original API coordinate contract.
    Conversion belongs at the API boundary, independent of the displayed basemap.
    """
    if (config.get('APP_CONFIG') or {}).get('使用自定义路线', False):
        return wgs84_to_gcj02(latitude, longitude)
    return latitude, longitude


def service_payload(config, running_data):
    from copy import deepcopy
    converted = deepcopy(running_data)
    if not (config.get('APP_CONFIG') or {}).get('使用自定义路线', False):
        return converted
    for record in converted:
        for track in record.get('tracks', []):
            for point in track.get('points', []):
                value = point['latLng']
                lat, lon = service_coordinate(config, value['latitude'], value['longitude'])
                point['latLng'] = {'latitude': round(lat, 7), 'longitude': round(lon, 7)}
                point['location'] = f'{lon:.7f},{lat:.7f}'
    return converted
