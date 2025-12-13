from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 1. 제어 파라미터
# ============================================================
# [주행 - 가변 룩어헤드]
LOOKAHEAD_MIN = 5.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0          
SPEED_LOOKAHEAD_DIST = 25.0     

# [도착 판정 & 정밀 제어]
GOAL_THRESHOLD = 7.0            
FINAL_GOAL_THRESHOLD = 15.0     
PARKING_THRESHOLD = 3.0         
LIMIT = 0.35                    

# [!!! 핵심 수정: 목표 속도 설정 !!!]
# 이제 Weight(가중치)가 아니라 '목표 속도(km/h)'를 직접 설정합니다.
TARGET_SPEED_STRAIGHT_KMH = 40.0  # 직선 구간 목표 속도
TARGET_SPEED_CORNER_KMH = 15.0    # 코너 구간 목표 속도 (감속)

# [속도 제어 P-Gain]
# 목표 속도와 현재 속도의 차이에 비례해 엑셀을 얼마나 밟을지 결정
KP_SPEED = 0.5  

# [조향 PD 게인]
KP_STEER = 0.05   
KD_STEER = 0.005  

# 제어 임계값
STRAIGHT_ANGLE_THRESHOLD = 2.0  
APPROACH_DISTANCE = 25.0        

# ============================================================
# 2. 전역 변수 (상태 저장)
# ============================================================
prev_angle_error = 0.0   
prev_time = None         
prev_dt = 0.033          

current_active_waypoints = [] 


# ============================================================
# (0) 유틸리티 함수들 (기존 유지)
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    if isinstance(wp, dict):
        return {"x": wp.get("x", 0.0), "y": wp.get("y", default_y), "z": wp.get("z", 0.0)}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        return {"x": wp[0], "y": wp[1], "z": wp[2]}
    return {"x": 0.0, "y": default_y, "z": 0.0}

def normalize_waypoints_list(raw_list, default_y=0.0):
    if not isinstance(raw_list, list): return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]

def calculate_dt(time_now):
    global prev_time, prev_dt
    if prev_time is None:
        raw_dt = 0.033
    else:
        raw_dt = time_now - prev_time
    
    if raw_dt <= 1e-4 or raw_dt > 0.1:
        dt = 0.033 
    else:
        dt = 0.7 * raw_dt + 0.3 * prev_dt
    prev_time = time_now
    prev_dt = dt
    return dt

# ============================================================
# (3) 룩어헤드 및 곡률 (기존 유지)
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    return LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio

def compute_lookahead_point(player_x, player_z, waypoints, speed_mps):
    if not waypoints: return None
    L = compute_dynamic_lookahead(speed_mps)
    remain = L
    prev_x, prev_z = player_x, player_z
    for wp in waypoints:
        wx, wz = wp["x"], wp["z"]
        seg_len = math.sqrt((wx - prev_x)**2 + (wz - prev_z)**2)
        if seg_len < 1e-6: continue
        if seg_len >= remain:
            t = remain / seg_len
            return {"x": prev_x + (wx-prev_x)*t, "z": prev_z + (wz-prev_z)*t}
        remain -= seg_len
        prev_x, prev_z = wx, wz
    return {"x": waypoints[-1]["x"], "z": waypoints[-1]["z"]}

def compute_curvature_factor(player_x, player_z, waypoints):
    if len(waypoints) < 2: return 0.0
    dx1, dz1 = waypoints[0]["x"] - player_x, waypoints[0]["z"] - player_z
    dx2, dz2 = waypoints[1]["x"] - waypoints[0]["x"], waypoints[1]["z"] - waypoints[0]["z"]
    ang1 = math.atan2(dz1, dx1)
    ang2 = math.atan2(dz2, dx2)
    diff = abs(ang1 - ang2)
    while diff > math.pi: diff -= 2*math.pi
    while diff < -math.pi: diff += 2*math.pi
    return abs(diff)

# ============================================================
# (4) 웨이포인트 관리
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints: return None, []
    current = waypoints[0]
    dist = math.sqrt((current["x"] - player_x)**2 + (current["z"] - player_z)**2)
    if len(waypoints) == 1: return current, waypoints
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints: return None, []
        return waypoints[0], waypoints
    return current, waypoints

# ============================================================
# (5) 조향 및 속도 제어 (!!! 핵심 수정됨 !!!)
# ============================================================
def steering_pd(angle_error, dt):
    global prev_angle_error
    if dt <= 0.0001: dt = 0.033
    P = KP_STEER * angle_error
    D = KD_STEER * ((angle_error - prev_angle_error) / dt)
    prev_angle_error = angle_error
    return max(-1.0, min(1.0, P + D))

def speed_pid_control(current_speed_mps, target_speed_kmh):
    """
    목표 속도(km/h)와 현재 속도(m/s)를 비교하여 적절한 throttle(0.0 ~ 1.0)을 반환
    """
    target_speed_mps = target_speed_kmh / 3.6
    
    # Error: 목표 속도까지 얼마나 남았는가?
    error = target_speed_mps - current_speed_mps
    
    # P-Control: 속도가 많이 남았으면 1.0(풀악셀), 가까워지면 서서히 줄임
    throttle = error * KP_SPEED
    
    # Clamp: 0.0 ~ 1.0 사이로 제한
    return max(0.0, min(1.0, throttle))

# ============================================================
# (7) ADCS 메인 제어함수
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, current_speed_mps, dt):
    
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    # --- 1. 조향 제어 (기존 동일) ---
    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    dist = math.sqrt(dx*dx + dz*dz)
    
    # 곡률 기반 룩어헤드 조정 (코너에서는 짧게, 직선에서는 길게)
    curve_factor = compute_curvature_factor(px, pz, waypoints)
    lookahead_speed_ref = current_speed_mps if curve_factor <= 0.5 else 0.0
    
    lookahead = compute_lookahead_point(px, pz, waypoints, lookahead_speed_ref)
    if lookahead is None: lookahead = head_wp
    
    target_angle = math.degrees(math.atan2(lookahead["x"] - px, lookahead["z"] - pz)) % 360
    angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
    steer_cmd = steering_pd(angle_error, dt)

    # --- 2. 속도 제어 (완전히 새로 작성됨) ---
    
    # (A) 목표 속도 설정 (Geometry 기반)
    # 곡률이 심하면(0.5 이상) 목표 속도를 15km/h로 낮춤, 아니면 40km/h
    # steer_cmd 절댓값이 크다는 건 현재 핸들을 많이 꺾고 있다는 뜻 -> 감속 필요
    if curve_factor > 0.5 or abs(steer_cmd) > 0.3:
        target_speed = TARGET_SPEED_CORNER_KMH
    else:
        target_speed = TARGET_SPEED_STRAIGHT_KMH

    # (B) 도착 임박 시 감속 (Override)
    is_final_leg = (len(waypoints) <= 1)
    if is_final_leg:
        final_wp = waypoints[-1]
        dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
        
        if dist_to_final <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        elif dist_to_final <= FINAL_GOAL_THRESHOLD:
            # 거리에 비례해서 목표 속도를 0으로 수렴시킴
            target_speed = min(target_speed, dist_to_final * 2.0) # 예: 5m 남았으면 10km/h 목표

    # (C) PID 제어기로 실제 페달 밟는 양(Weight) 계산
    # 목표가 40km/h이고 현재가 0km/h면 -> 1.0 (풀악셀) 나옴
    # 목표가 40km/h이고 현재가 39km/h면 -> 조금만 밟음
    # 목표가 40km/h이고 현재가 45km/h면 -> 0.0 (악셀 뗌)
    WS_weight = speed_pid_control(current_speed_mps, target_speed)
    
    # (D) 최종 명령 결정
    if current_speed_mps > (target_speed/3.6) + 2.0: 
        # 목표보다 7km/h 이상 빠르면 브레이크
        WS_command = "S"
        WS_weight = 0.5 
    else:
        WS_command = "W"

    # 조향 명령 문자열 변환
    if steer_cmd > 0: AD_command = "D"
    elif steer_cmd < 0: AD_command = "A"
    else: AD_command = ""
    
    return WS_command, WS_weight, AD_command, abs(steer_cmd), head_wp

# ============================================================
# Flask Endpoint
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    global current_active_waypoints

    data = request.get_json(force=True)
    
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = float(data.get("time", 0.0))

    px = float(ally_pos.get("x", 0.0))
    py = float(ally_pos.get("y", 0.0))
    pz = float(ally_pos.get("z", 0.0))
    yaw = float(ally_angle.get("x", 0.0)) 

    # [Ground Truth Speed 사용]
    raw_speed = data.get("player_speed") or data.get("ally_speed") or 0.0
    player_speed_mps = float(raw_speed)

    dt = calculate_dt(time_now)

    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
    
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, current_active_waypoints, player_speed_mps, dt
    )
    
    if head_wp is None:
        head_wp = {"x": px, "y": py, "z": pz}

    response = {
        "WS_command": WS_cmd,
        "WS_weight": WS_w,
        "AD_command": AD_cmd,
        "AD_weight": AD_w,
        "head_waypoint": {
            "x": head_wp["x"],
            "y": head_wp.get("y", py),
            "z": head_wp["z"],
        }
    }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)