import math
import uuid
import time
import random
from src.config import load_config
from src.route import sample_route, validate_route
from utils.auxiliary_util import haversine_distance, log_output, TRACK_POINT_DECIMAL_PLACES, get_current_epoch_ms, SportsUploaderError

def interpolate_points(start_lat, start_lon, end_lat, end_lon, speed_mps, interval_seconds):
    """
    在起点和终点之间以给定速度和采样间隔插值生成轨迹点。
    返回一个包含轨迹点字典的列表，以及这段的距离和时长。
    注意：这里生成的点不包含locatetime，由generate_running_data统一分配。
    """
    points = []

    start_lat_calc = float(f"{start_lat:.14f}")
    start_lon_calc = float(f"{start_lon:.14f}")
    end_lat_calc = float(f"{end_lat:.14f}")
    end_lon_calc = float(f"{end_lon:.14f}")

    start_lat_rad = math.radians(start_lat_calc)
    start_lon_rad = math.radians(start_lon_calc)
    end_lat_rad = math.radians(end_lat_calc)
    end_lon_rad = math.radians(end_lon_calc)

    segment_distance = haversine_distance(start_lat_calc, start_lon_calc, end_lat_calc, end_lon_calc)
    segment_duration_seconds = segment_distance / speed_mps

    num_steps = math.ceil(segment_duration_seconds / interval_seconds)
    if num_steps <= 1 and segment_distance > 0:
        num_steps = 1
    elif segment_distance == 0:
        num_steps = 0

    if num_steps == 0:
        formatted_lat = f"{start_lat_calc:.{TRACK_POINT_DECIMAL_PLACES}f}"
        formatted_lon = f"{start_lon_calc:.{TRACK_POINT_DECIMAL_PLACES}f}"
        points.append({
            "latLng": {"latitude": float(formatted_lat), "longitude": float(formatted_lon)},
            "location": f"{formatted_lon},{formatted_lat}",
            "step": 0
        })
        return points, segment_distance, math.ceil(segment_duration_seconds)

    for i in range(num_steps + 1):
        fraction = i / num_steps

        interp_lat_rad = start_lat_rad + fraction * (end_lat_rad - start_lat_rad)
        interp_lon_rad = start_lon_rad + fraction * (end_lon_rad - start_lon_rad)

        interp_lat = math.degrees(interp_lat_rad)
        interp_lon = math.degrees(interp_lon_rad)

        formatted_lat = f"{interp_lat:.{TRACK_POINT_DECIMAL_PLACES}f}"
        formatted_lon = f"{interp_lon:.{TRACK_POINT_DECIMAL_PLACES}f}"

        points.append({
            "latLng": {"latitude": float(formatted_lat), "longitude": float(formatted_lon)},
            "location": f"{formatted_lon},{formatted_lat}",
            "step": 0
        })

    final_end_lat_formatted = float(f"{end_lat_calc:.{TRACK_POINT_DECIMAL_PLACES}f}")
    final_end_lon_formatted = float(f"{end_lon_calc:.{TRACK_POINT_DECIMAL_PLACES}f}")

    if abs(points[-1]['latLng']['latitude'] - final_end_lat_formatted) > 1e-10 or \
            abs(points[-1]['latLng']['longitude'] - final_end_lon_formatted) > 1e-10:
        points[-1] = {
            "latLng": {"latitude": final_end_lat_formatted, "longitude": final_end_lon_formatted},
            "location": f"{final_end_lon_formatted},{final_end_lat_formatted}",
            "step": 0
        }

    return points, segment_distance, math.ceil(segment_duration_seconds)


def split_track_into_segments(all_points_with_time, total_duration_sec, min_segment_points=5, stop_check_cb=None):
    """Share boundary points so splitting never drops distance or time."""
    tracks = []
    start = 0
    while start < len(all_points_with_time) - 1:
        if stop_check_cb and stop_check_cb():
            raise SportsUploaderError("任务已停止。")
        points = all_points_with_time[start:start + 250]
        distance = sum(haversine_distance(a['latLng']['latitude'], a['latLng']['longitude'],
                                         b['latLng']['latitude'], b['latLng']['longitude'])
                       for a, b in zip(points, points[1:]))
        stime = points[0]['locatetime'] // 1000
        etime = points[-1]['locatetime'] // 1000
        tracks.append({"counts": len(points), "distance": distance, "duration": etime - stime,
                       "points": points, "status": "normal", "trid": str(uuid.uuid4()),
                       "tstate": "0", "stime": stime, "etime": etime})
        start += len(points) - 1
    return tracks


def generate_running_data_payload(config, required_signpoints, point_rules_data, log_cb=None, stop_check_cb=None):
    """
    生成符合POST请求体格式的跑步数据，并整合打卡点。
    """
    # Use the frozen UI settings throughout a batch; fallback supports callers without a UI.
    app_config = config.get("APP_CONFIG")
    if app_config is None:
        app_config = load_config()
    use_random_params = app_config.get("参数随机", False)
    if use_random_params:
        pace_min = float(app_config.get("配速最小_分钟每公里", 3.5))
        pace_max = float(app_config.get("配速最大_分钟每公里", 5.0))
        if pace_min > pace_max:
            raise SportsUploaderError("配速范围的最小值不能大于最大值。")
        pace_min_per_km = round(random.uniform(pace_min, pace_max), 1)
    else:
        pace_min_per_km = float(app_config.get("配速_分钟每公里", 3.5))
    interval_seconds = int(app_config.get("GPS采样间隔_秒", config.get('INTERVAL_SECONDS', 3)))
    if interval_seconds <= 0:
        raise SportsUploaderError("GPS 采样间隔必须大于 0。")
    start_time_ms = config.get('START_TIME_EPOCH_MS')
    if start_time_ms is None:
        start_time_ms = get_current_epoch_ms()

    if app_config.get("使用自定义路线", False):
        route, route_length = validate_route(app_config.get("自定义路线", []))
        log_output(f"使用地图路线：{app_config.get('路线名称', '我的路线')}，长度 {route_length:.1f} 米", callback=log_cb)
    else:
        if use_random_params:
            dist_min = int(app_config.get("距离最小_米", 4000))
            dist_max = int(app_config.get("距离最大_米", 6000))
            if dist_min > dist_max:
                raise SportsUploaderError("距离范围的最小值不能大于最大值。")
            target_distance_m = random.randint(dist_min, dist_max)
        else:
            target_distance_m = float(app_config.get("每日距离_米", 5000))
        start_lat = float(app_config.get("起点纬度", config.get('START_LATITUDE', 31.031599)))
        start_lon = float(app_config.get("起点经度", config.get('START_LONGITUDE', 121.442938)))
        lon_delta = target_distance_m / (111111 * math.cos(math.radians(start_lat)))
        route = [{"latitude": start_lat, "longitude": start_lon},
                 {"latitude": start_lat, "longitude": start_lon + lon_delta}]

    full_interpolated_points_with_time, _, _ = sample_route(
        route, pace_min_per_km, interval_seconds, start_time_ms, stop_check_cb)
    actual_total_duration_sec = (full_interpolated_points_with_time[-1]['locatetime'] // 1000
                                 - full_interpolated_points_with_time[0]['locatetime'] // 1000)
    tracks_list = split_track_into_segments(full_interpolated_points_with_time, actual_total_duration_sec,
                                           stop_check_cb=stop_check_cb)
    actual_total_distance = sum(t['distance'] for t in tracks_list)

    run_id = point_rules_data.get('rules', {}).get('id', 6)
    if run_id == 6:
        run_id = 9

    sp_avg = 0
    if actual_total_distance > 0 and actual_total_duration_sec > 0:
        sp_avg = actual_total_duration_sec / (actual_total_distance / 1000) / 60
        sp_avg = round(sp_avg)

    rules_meta = point_rules_data.get('rules', {})
    min_sp_s_per_km = rules_meta.get('spmin', 180)
    max_sp_s_per_km = rules_meta.get('spmax', 540)

    sp_avg_s_per_km = sp_avg * 60 if sp_avg > 0 else 0

    if actual_total_distance > 0:
        if sp_avg_s_per_km < min_sp_s_per_km:
            log_output(f"Warning: Calculated pace {sp_avg} min/km ({sp_avg_s_per_km:.0f} s/km) is faster than {min_sp_s_per_km / 60:.0f} min/km ({min_sp_s_per_km:.0f} s/km). Adjusting to minimum allowed pace.", "warning", log_cb)
            sp_avg = math.ceil(min_sp_s_per_km / 60)
        elif sp_avg_s_per_km > max_sp_s_per_km:
            log_output(f"Warning: Calculated pace {sp_avg} min/km ({sp_avg_s_per_km:.0f} s/km) is slower than {max_sp_s_per_km / 60:.0f} min/km ({max_sp_s_per_km:.0f} s/km). Adjusting to maximum allowed pace.", "warning", log_cb)
            sp_avg = math.floor(max_sp_s_per_km / 60)

    request_body = [
        {
            "fravg": 0,
            "id": run_id,
            "sid": str(uuid.uuid4()),
            "signpoints": [],
            "spavg": sp_avg,
            "state": "0",
            "tracks": tracks_list,
            "userId": config['USER_ID']
        }
    ]
    return request_body, actual_total_distance, actual_total_duration_sec