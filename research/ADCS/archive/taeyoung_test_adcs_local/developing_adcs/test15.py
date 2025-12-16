from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# [설정] 제어 파라미터 (안정화 튜닝)
# ============================================================
# 1. Lookahead 관련
# [수정] 3.5 -> 4.5 (저속에서 너무 민감하게 반응하지 않도록 거리를 늘림)
LOOKAHEAD_MIN = 4.5      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0   

# 2. Waypoint 관리 - GOAL_THRESHOLD (m) 이내에 웨이포인트에 도달하면 도착 판정
GOAL_THRESHOLD = 3.0     

# 3. 속도 제어 제한값
MAX_SPEED_KMH = 65.0 / 65.0    
MIN_SPEED_WEIGHT = 0.0   

# 4. 조향(Steering) PID Gains
# [수정] D게인 대폭 감소 (0.05 -> 0.01)
# IBSM 데이터가 튈 때 핸들이 좌우로 요동치는 현상(Oscillation)을 잡기 위함
KP_STEER = 0.04          
KD_STEER = 0.01          

# ============================================================
# [전역 상태]
# ============================================================
prev_angle_error = 0.0   
prev_time = None         
prev_x = None            
prev_z = None
prev_filtered_speed = 0.0 

# ============================================================
# 유틸리티 함수
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    if isinstance(wp, dict):
        return {"x": float(wp.get("x", 0.0)), "y": float(wp.get("y", default_y)), "z": float(wp.get("z", 0.0))}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": float(wp[0]), "y": float(wp[1]), "z": float(wp[2])}
    else:
        return {"x": 0.0, "y": default_y, "z": 0.0}

def normalize_waypoints_list(raw_list, default_y=0.0):
    if not isinstance(raw_list, list):
        return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]

# ============================================================
# (1) Waypoint Pop 로직
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints:
        return None, waypoints

    current = waypoints[0]
    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 종료 조건(도착판정)
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, waypoints
        else:
            current = waypoints[0]

    return current, waypoints

# ============================================================
# (2) 속도 계산 (LPF + dt)
# ============================================================
def estimate_speed_with_filter(time_now, x_now, z_now):
    global prev_time, prev_x, prev_z, prev_filtered_speed

    if prev_time is None:
        prev_time = time_now
        prev_x = x_now
        prev_z = z_now
        return 0.0, 0.0

    dt = time_now - prev_time
    
    # 시간이 역전되거나 너무 짧으면 무시
    if dt <= 1e-6:
        return prev_filtered_speed, 0.0

    dx = x_now - prev_x
    dz = z_now - prev_z
    dist = math.sqrt(dx*dx + dz*dz)

    raw_speed = dist / dt 

    # LPF 적용 (알파값 0.3)
    alpha = 0.3
    filtered_speed = alpha * raw_speed + (1 - alpha) * prev_filtered_speed

    prev_time = time_now
    prev_x = x_now
    prev_z = z_now
    prev_filtered_speed = filtered_speed

    return filtered_speed, dt

# ============================================================
# (3) 미래 곡률 예측
# ============================================================
def get_forward_curvature(waypoints, check_count=3):
    max_diff = 0.0
    count = min(len(waypoints) - 2, check_count)
    
    if count < 1:
        return 0.0

    for i in range(count):
        wp1 = waypoints[i]
        wp2 = waypoints[i+1]
        wp3 = waypoints[i+2]

        dx1, dz1 = wp2["x"] - wp1["x"], wp2["z"] - wp1["z"]
        dx2, dz2 = wp3["x"] - wp2["x"], wp3["z"] - wp2["z"]

        diff = abs(math.atan2(dz1, dx1) - math.atan2(dz2, dx2))
        
        while diff > math.pi: diff -= 2*math.pi
        while diff < -math.pi: diff += 2*math.pi
        
        max_diff = max(max_diff, abs(diff))

    return max_diff

# ============================================================
# (4) Lookahead Point 계산
# ============================================================
def compute_lookahead_point(player_x, player_z, waypoints, speed_mps, future_curvature):
    
    ratio = 0.0
    if SPEED_FOR_MAX_L > 1e-6:
        ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    
    target_L = LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio

    # 코너 진입 시 Lookahead 단축
    if future_curvature > 0.2: 
        factor = 1.0 - min(future_curvature * 0.8, 0.8) 
        target_L *= factor
    
    target_L = max(target_L, LOOKAHEAD_MIN)

    remain = target_L
    prev_x_local = player_x
    prev_z_local = player_z

    if not waypoints:
        return None, target_L

    for wp in waypoints:
        wx, wz = wp["x"], wp["z"]
        seg_dx = wx - prev_x_local
        seg_dz = wz - prev_z_local
        seg_len = math.sqrt(seg_dx*seg_dx + seg_dz*seg_dz)

        if seg_len < 1e-6:
            continue

        if seg_len >= remain:
            t = remain / seg_len
            lx = prev_x_local + seg_dx * t
            lz = prev_z_local + seg_dz * t
            return {"x": lx, "z": lz}, target_L

        remain -= seg_len
        prev_x_local = wx
        prev_z_local = wz

    last = waypoints[-1]
    return {"x": last["x"], "z": last["z"]}, target_L

# ============================================================
# (5) Steering PD Control (Wrap handling 추가)
# ============================================================
def steering_pd(angle_error, dt):
    global prev_angle_error

    P = KP_STEER * angle_error

    safe_dt = max(dt, 0.001) 
    
    # [수정] 각도 차이가 180도를 넘어가면(예: -179 -> +179) 보정
    # 이게 없으면 순간적으로 반대 방향 미분값이 튀어서 핸들이 요동침
    diff = angle_error - prev_angle_error
    if diff > 180.0: diff -= 360.0
    elif diff < -180.0: diff += 360.0
    
    D = KD_STEER * (diff / safe_dt)

    steer_cmd = P + D
    prev_angle_error = angle_error

    return max(-1.0, min(steer_cmd, 1.0))

# ============================================================
# (6) Speed Control
# ============================================================
def calculate_speed_command(speed_mps, future_curvature):
    safe_speed_ratio = 1.0 / (1.0 + 3.0 * future_curvature)
    target_speed_kmh = MAX_SPEED_KMH * safe_speed_ratio
    target_speed_kmh = max(target_speed_kmh, 15.0)

    target_speed_mps = target_speed_kmh / 3.6
    
    # 과속 방지 (Feedback)
    if speed_mps > target_speed_mps:
        return "W", 0.0
    
    # 비율 제어 (Open-loop)
    throttle_weight = target_speed_kmh / MAX_SPEED_KMH
    throttle_weight = max(throttle_weight, 0.1)
    
    return "W", throttle_weight

# ============================================================
# 메인 로직
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    try:
        data = request.get_json(force=True)
        
        print('\n@@@@@@ IBSM 수신 데이터:', data)
        print('test : ')
        print('-' * 100)
        ally_pos = data.get("ally_body_pos", {})
        ally_angle = data.get("ally_body_angle", {})
        waypoints_raw = data.get("waypoints", [])
        time_now = float(data.get("time", 0.0))

        px = float(ally_pos.get("x", 0.0))
        py = float(ally_pos.get("y", 0.0))
        pz = float(ally_pos.get("z", 0.0))
        yaw = float(ally_angle.get("x", 0.0))

        speed_mps, dt = estimate_speed_with_filter(time_now, px, pz)

        waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
        head_wp, waypoints = select_waypoint(px, pz, waypoints)

        if head_wp is None:
            stop_response = {"WS_command": "STOP", "WS_weight": 1.0, "AD_command": "", "AD_weight": 0.0}
            print('@@@@@@ [ADCS] 목적지 도달 -> 정지')
            return jsonify(stop_response)

        future_curvature = get_forward_curvature(waypoints, check_count=3)

        lookahead, L_dist = compute_lookahead_point(px, pz, waypoints, speed_mps, future_curvature)
        if lookahead is None:
            lookahead = head_wp

        dx = lookahead["x"] - px
        dz = lookahead["z"] - pz
        target_angle = (math.degrees(math.atan2(dx, dz))) % 360
        angle_error = (target_angle - yaw + 540.0) % 360.0 - 180.0
        
        steer_cmd = steering_pd(angle_error, dt)

        WS_cmd, WS_weight = calculate_speed_command(speed_mps, future_curvature)

        AD_cmd = "D" if steer_cmd > 0 else "A"
        AD_weight = abs(steer_cmd)
        if AD_weight < 0.05: AD_cmd = ""

        response = {
            "WS_command": WS_cmd,
            "WS_weight": WS_weight,
            "AD_command": AD_cmd,
            "AD_weight": AD_weight,
            "head_waypoint": {
                "x": head_wp["x"],
                "y": head_wp.get("y", py),
                "z": head_wp["z"],
            },
            # 디버깅 필요시 주석 해제
            # "debug": { ... }
        }
        
        print('@@@@@@@@@@@@@@@ ADCS 출력:', response)

        return jsonify(response)

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"WS_command": "W", "WS_weight": 0.0, "AD_command": "", "AD_weight": 0.0})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)