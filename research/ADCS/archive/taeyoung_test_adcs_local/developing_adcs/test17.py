# 메인1.py파일로부터 웨이포인트 저장 방식을 처음 바꾸고 실험하는 코드야 11/21 13:00


from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# [설정] 제어 파라미터 (main1.py 기반 + 안정화/3D 튜닝)
# ============================================================
# 1. Lookahead 관련 (main1.py의 동적 로직 유지)
LOOKAHEAD_MIN = 6.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0   # 약 65km/h ≈ 18 m/s

# 2. Waypoint 관리
# [수정] 3D 거리 및 고속 주행 고려하여 3.0m로 설정 (너무 작으면 놓침)
GOAL_THRESHOLD = 3.0 

# 3. 속도 제어 제한값
# [수정] main1.py의 1.0 같은 상대값 대신 물리적 속도 제한 명시
MAX_PHYSICAL_SPEED_KMH = 65.0       
TARGET_CRUISE_SPEED_KMH = 60.0      # 목표 순항 속도
MIN_SPEED_WEIGHT = 0.0              # 정지

# 4. 조향(Steering) PD Gains
KP_STEER = 0.025
KD_STEER = 0.08          # dt 반영 시 값이 너무 커지지 않도록 조정

# ============================================================
# [전역 상태]
# ============================================================
prev_angle_error = 0.0   
prev_time = None         
prev_x = None            
prev_y = None            # [추가] 고도 반영
prev_z = None            
prev_filtered_speed = 0.0 # [추가] LPF용

# [핵심 추가] 웨이포인트 캐싱용 변수
prev_waypoints = [] 

# ============================================================
# 유틸리티 함수
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    """
    dict / list 모두 지원하며 3D 좌표(x, y, z)를 정규화
    """
    if isinstance(wp, dict):
        return {
            "x": float(wp.get("x", 0.0)), 
            "y": float(wp.get("y", default_y)), 
            "z": float(wp.get("z", 0.0))
        }
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": float(wp[0]), "y": float(wp[1]), "z": float(wp[2])}
    else:
        return {"x": 0.0, "y": default_y, "z": 0.0}

def normalize_waypoints_list(raw_list, default_y=0.0):
    if not isinstance(raw_list, list):
        return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]

# ============================================================
# (1) Waypoint Pop 로직 (3D 거리 적용)
# ============================================================
def select_waypoint(player_x, player_y, player_z, waypoints):
    """
    3차원 유클리드 거리 사용하여 언덕 위 웨이포인트도 정확히 판정.
    """
    if not waypoints:
        return None, waypoints

    current = waypoints[0]

    dx = current["x"] - player_x
    dy = current["y"] - player_y # 고도 차이 반영
    dz = current["z"] - player_z
    
    # 3D 거리 계산
    dist = math.sqrt(dx*dx + dy*dy + dz*dz)

    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:     
            return None, waypoints
        current = waypoints[0]

    return current, waypoints

# ============================================================
# (2) 속도 계산 (LPF + 3D 거리 + dt)
# ============================================================
def estimate_speed_with_filter(time_now, x_now, y_now, z_now):
    """
    3D 이동 거리와 LPF를 사용하여 안정적인 속도 계산.
    """
    global prev_time, prev_x, prev_y, prev_z, prev_filtered_speed

    if prev_time is None:
        prev_time = time_now
        prev_x = x_now
        prev_y = y_now
        prev_z = z_now
        return 0.0, 0.0

    dt = time_now - prev_time
    
    if dt <= 1e-6:
        return prev_filtered_speed, 0.0

    # 3D 이동 거리
    dx = x_now - prev_x
    dy = y_now - prev_y
    dz = z_now - prev_z
    distance = math.sqrt(dx*dx + dy*dy + dz*dz)

    raw_speed = distance / dt

    # LPF 적용 (노이즈 제거)
    alpha = 0.3
    filtered_speed = alpha * raw_speed + (1 - alpha) * prev_filtered_speed

    # 상태 업데이트
    prev_time = time_now
    prev_x = x_now
    prev_y = y_now
    prev_z = z_now
    prev_filtered_speed = filtered_speed

    return filtered_speed, dt

# ============================================================
# (3) Lookahead 거리 계산 (main1.py 로직 유지)
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    ratio = 0.0
    if SPEED_FOR_MAX_L > 1e-6:
        ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))

    L = LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio
    return L

# ============================================================
# (4) Lookahead Point 계산 (3D Polyline 보간)
# ============================================================
def compute_lookahead_point(player_x, player_y, player_z, waypoints, speed_mps):
    """
    3차원 좌표계를 사용하여 Lookahead Point를 계산.
    """
    if not waypoints:
        return None

    L = compute_dynamic_lookahead(speed_mps)
    remain = L

    prev_x_local = player_x
    prev_y_local = player_y
    prev_z_local = player_z

    for wp in waypoints:
        wx, wy, wz = wp["x"], wp["y"], wp["z"]

        seg_dx = wx - prev_x_local
        seg_dy = wy - prev_y_local 
        seg_dz = wz - prev_z_local
        
        seg_len = math.sqrt(seg_dx*seg_dx + seg_dy*seg_dy + seg_dz*seg_dz)

        if seg_len < 1e-6:
            prev_x_local, prev_y_local, prev_z_local = wx, wy, wz
            continue

        if seg_len >= remain:
            t = remain / seg_len
            lx = prev_x_local + seg_dx * t
            ly = prev_y_local + seg_dy * t 
            lz = prev_z_local + seg_dz * t
            return {"x": lx, "y": ly, "z": lz}

        remain -= seg_len
        prev_x_local, prev_y_local, prev_z_local = wx, wy, wz

    last = waypoints[-1]
    return {"x": last["x"], "y": last["y"], "z": last["z"]}

# ============================================================
# [보조] 경로 굴곡도 계산 (main1.py 로직 유지)
# ============================================================
def compute_curvature_factor(player_x, player_z, waypoints):
    if len(waypoints) < 2:
        return 0.0
    
    dx1 = waypoints[0]["x"] - player_x
    dz1 = waypoints[0]["z"] - player_z
    
    dx2 = waypoints[1]["x"] - waypoints[0]["x"]
    dz2 = waypoints[1]["z"] - waypoints[0]["z"]
    
    angle1 = math.atan2(dz1, dx1)
    angle2 = math.atan2(dz2, dx2)
    
    diff = abs(angle1 - angle2)
    while diff > math.pi: diff -= 2*math.pi
    while diff < -math.pi: diff += 2*math.pi
    
    return abs(diff)

# ============================================================
# (5) Steering PD Control (Robust Time-step)
# ============================================================
def steering_pd(angle_error, dt):
    """
    dt를 반영하여 불규칙한 프레임 간격에도 안정적인 D 제어 수행.
    """
    global prev_angle_error

    P = KP_STEER * angle_error

    safe_dt = max(dt, 0.001) 
    
    error_diff = angle_error - prev_angle_error
    
    if error_diff > 180: error_diff -= 360
    elif error_diff < -180: error_diff += 360

    D = KD_STEER * (error_diff / safe_dt)

    steer_cmd = P + D
    prev_angle_error = angle_error

    return max(-1.0, min(steer_cmd, 1.0))

# ============================================================
# (6) Smooth Speed Control (with FEEDBACK)
# ============================================================
def calculate_speed_command(steer_cmd, current_speed_mps):
    """
    [핵심 보완] 현재 속도 피드백을 통해 무한 가속 방지 (Governor).
    """
    curvature = abs(steer_cmd)
    k = 1.8
    safe_speed_ratio = 1.0 / (1.0 + k * curvature)

    target_speed_kmh = TARGET_CRUISE_SPEED_KMH * safe_speed_ratio
    target_speed_kmh = max(target_speed_kmh, 10.0) 

    current_speed_kmh = current_speed_mps * 3.6
    
    # [Feedback Governor] 목표 속도 초과 시 가속 중단
    if current_speed_kmh > target_speed_kmh:
        return "W", 0.0
    
    throttle_weight = target_speed_kmh / MAX_PHYSICAL_SPEED_KMH
    throttle_weight = max(throttle_weight, 0.1) 

    return "W", throttle_weight

# ============================================================
# (7) Main Path Tracking Logic
# ============================================================
def path_tracking(px, py, pz, yaw, waypoints, speed_mps, dt):
    # 1. Waypoint Pop (3D 거리 기반)
    head_wp, waypoints = select_waypoint(px, py, pz, waypoints)

    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    # 2. 급커브 감지 및 Lookahead 조정
    curve_factor = compute_curvature_factor(px, pz, waypoints)
    effective_speed = speed_mps
    if curve_factor > 0.5:
        effective_speed = 0.0 

    # 3. Lookahead Point 계산 (3D)
    lookahead = compute_lookahead_point(px, py, pz, waypoints, effective_speed)
    
    if lookahead is None:
        lookahead = head_wp

    # 4. 조향 각도 계산 (X-Z 평면 Yaw)
    dx = lookahead["x"] - px
    dz = lookahead["z"] - pz
    
    target_angle = (math.degrees(math.atan2(dx, dz))) % 360
    
    angle_error = (target_angle - yaw + 540.0) % 540.0 - 180.0

    # 5. PD 조향 제어
    steer_cmd = steering_pd(angle_error, dt)

    AD_command = "D" if steer_cmd > 0 else "A"
    if abs(steer_cmd) < 0.01: AD_command = "" 
    AD_weight = abs(steer_cmd)

    # 6. 속도 제어 (피드백 적용)
    WS_command, WS_weight = calculate_speed_command(steer_cmd, speed_mps)

    return WS_command, WS_weight, AD_command, AD_weight, head_wp

# ============================================================
# Flask Endpoint
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    global prev_waypoints # 전역 변수 사용

    try:
        data = request.get_json(force=True)
        
        print("\n@@@@@@ ADCS가 IBSM으로부터 제공받은 데이터 \n", data)

        ally_pos = data.get("ally_body_pos", {})
        ally_angle = data.get("ally_body_angle", {})
        waypoints_raw = data.get("waypoints", [])
        time_now = float(data.get("time", 0.0))

        px = float(ally_pos.get("x", 0.0))
        py = float(ally_pos.get("y", 0.0))
        pz = float(ally_pos.get("z", 0.0))
        yaw = float(ally_angle.get("x", 0.0)) 

        # 1. 속도 계산 (LPF + 3D + dt)
        speed_mps, dt = estimate_speed_with_filter(time_now, px, py, pz)

        # 2. [핵심] Waypoint 갱신 및 캐싱 로직
        if waypoints_raw: 
            # IBSM이 새로운 웨이포인트를 보냈으면 갱신
            # print(f"@@@ 새로운 경로 수신! ({len(waypoints_raw)} 개) @@@")
            prev_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
        
        # 현재 사용할 웨이포인트는 저장된 것 사용
        # (만약 IBSM이 빈 리스트를 보내면 prev_waypoints가 그대로 유지됨)
        current_waypoints = prev_waypoints 

        # 3. 주행 제어
        WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
            px, py, pz, yaw, current_waypoints, speed_mps, dt
        )

        # [중요] path_tracking 내부에서 pop된 결과를 다시 전역 변수에 저장해야 함
        # (그래야 다음 프레임에서 pop된 상태로 이어서 주행 가능)
        # path_tracking 함수가 (명령들..., head_wp) 만 리턴하고 waypoints 리스트 자체를 리턴하지 않는 구조라면 수정 필요.
        # 여기서는 select_waypoint가 리스트를 직접 수정(pop)하므로, 
        # current_waypoints 객체 자체가 변경되었음. 따라서 별도 재할당 불필요.
        # 다만, 안전을 위해 명시적으로 관리하고 싶다면 path_tracking 리턴값에 waypoints를 포함시키는 게 좋음.
        # * 현재 select_waypoint는 mutable list를 받아 pop하므로 prev_waypoints도 같이 변경됨. (OK)

        if head_wp is None:
            # 목적지 도달 시 정지 및 웨이포인트 초기화
            prev_waypoints = [] 
            return jsonify({"WS_command": "STOP", "WS_weight": 1.0, "AD_command": "", "AD_weight": 0.0})

        response = {
            "WS_command": WS_cmd,
            "WS_weight": WS_w,
            "AD_command": AD_cmd,
            "AD_weight": AD_w,
            "head_waypoint": {
                "x": head_wp["x"],
                "y": head_wp.get("y", py),
                "z": head_wp["z"],
            },
        }
        
        print('기존에 전달받앗던 웨이포인트 : \n', prev_waypoints)

        print("\n@@@@ ADCS 가 IBSM 에게 주는 데이터")
        print(response)
        
        return jsonify(response)

    except Exception as e:
        print(f"Error in ADCS: {e}")
        return jsonify({"WS_command": "W", "WS_weight": 0.0, "AD_command": "", "AD_weight": 0.0})

if __name__ == '__main__':
    print("🚀 ADCS Server Started on Port 5000")
    app.run(host="0.0.0.0", port=5000)