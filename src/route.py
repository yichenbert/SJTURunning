"""WGS84 route validation and distance-based sampling, independent of the GUI."""
import bisect
import math
from utils.auxiliary_util import haversine_distance, SportsUploaderError

MAX_ROUTE_POINTS = 5000


def normalize_route(points):
    if not isinstance(points, list) or len(points) > MAX_ROUTE_POINTS:
        raise SportsUploaderError('路线格式错误或点数超过 5000。')
    result = []
    for point in points:
        try:
            lat, lon = float(point['latitude']), float(point['longitude'])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise SportsUploaderError('路线坐标格式错误。')
        if not (math.isfinite(lat) and math.isfinite(lon) and -85 <= lat <= 85 and -180 <= lon <= 180):
            raise SportsUploaderError('路线坐标超出有效范围。')
        value = {'latitude': lat, 'longitude': lon}
        if not result or haversine_distance(result[-1]['latitude'], result[-1]['longitude'], lat, lon) >= 0.1:
            result.append(value)
    return result


def cumulative_distances(points):
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine_distance(a['latitude'], a['longitude'], b['latitude'], b['longitude']))
    return cumulative


def route_distance(points):
    points = normalize_route(points)
    return cumulative_distances(points)[-1] if points else 0.0


def validate_route(points):
    points = normalize_route(points)
    distance = route_distance(points)
    if len(points) < 2 or distance < 5:
        raise SportsUploaderError('请绘制至少两个不同的点，路线长度至少 5 米。')
    if distance > 100000:
        raise SportsUploaderError('路线长度不能超过 100 公里。')
    return points, distance


def sample_route(points, pace_min_per_km, interval_seconds, start_time_ms, stop_check_cb=None):
    """Retain every turn plus regular samples; timestamps follow cumulative distance."""
    points, distance = validate_route(points)
    if not math.isfinite(pace_min_per_km) or pace_min_per_km <= 0 or interval_seconds <= 0:
        raise SportsUploaderError('配速和采样间隔必须为正数。')
    speed = 1000 / (pace_min_per_km * 60)
    duration = distance / speed
    if math.ceil(duration / interval_seconds) + len(points) > 100000:
        raise SportsUploaderError('采样点过多，请缩短路线或增大采样间隔。')
    cumulative = cumulative_distances(points)
    # Merge distance samples with vertices so turns are never cut across.
    stations = sorted(set(cumulative + [min(i * interval_seconds * speed, distance)
                      for i in range(math.ceil(duration / interval_seconds) + 1)]))
    samples = []
    for station in stations:
        if stop_check_cb and stop_check_cb():
            raise SportsUploaderError('任务已停止。')
        idx = min(bisect.bisect_right(cumulative, station) - 1, len(points) - 2)
        a, b = points[idx:idx + 2]
        fraction = (station - cumulative[idx]) / (cumulative[idx + 1] - cumulative[idx])
        lat = round(a['latitude'] + fraction * (b['latitude'] - a['latitude']), 7)
        lon = round(a['longitude'] + fraction * (b['longitude'] - a['longitude']), 7)
        timestamp = int(start_time_ms) + round(station / speed * 1000)
        # Nearby vertices can round to the same ms. Keep coordinates without reversing time.
        samples.append({'latLng': {'latitude': lat, 'longitude': lon},
                        'location': f'{lon:.7f},{lat:.7f}', 'step': 0, 'locatetime': timestamp})
    return samples, distance, duration
