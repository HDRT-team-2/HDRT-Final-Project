from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 1. 제어 파라미터
# ============================================================
# [주행 - 가변 룩어헤드]
LOOKAHEAD_MIN = 5.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0          # 이 속도(m/s) 이상일 때 MAX 거리를 봅니다
SPEED_LOOKAHEAD_DIST = 25.0     # 곡률 예측 스캔 거리

# [도착 판정 & 정밀 제어]
GOAL_THRESHOLD = 7.0            
FINAL_GOAL_THRESHOLD = 15.0     # 넉넉한 감속 거리
PARKING_THRESHOLD = 3.0         # 주차 판정
LIMIT = 0.35                    # 감속 비율

# [속도 제한 (엑셀 강도)]
MAX_SPEED_WEIGHT = 40.0 / 70.0   
MIN_SPEED_WEIGHT = 8.0 / 70.0    

# [절대 속도 제한 (Governor)]
# 시뮬레이터가 주는 player_speed가 이 값을 넘으면 강제로 제어
MAX_SPEED_LIMIT_KMH = 40.0
MAX_SPEED_LIMIT_MPS = MAX_SPEED_LIMIT_KMH / 3.6  # 약 11.11 m/s

# [조향 PD 게인]
KP_STEER = 0.05   
KD_STEER = 0.005  

# 제어 임계값
STRAIGHT_ANGLE_THRESHOLD = 2.0  
APPROACH_DISTANCE = 25.0        

# ============================================================
# 2. 전역 변수 (상태 저장)
# ============================================================
# 좌표 미분용 변수(prev_x, prev_z)는 모두 삭제했습니다.
prev_angle_error = 0.0   
prev_time = None         
prev_dt = 0.033          

# 현재 주행 중인 경로 저장
current_active_waypoints = [] 


# ============================================================
# (0) 유틸리티: 데이터 포맷 정규화
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


# ============================================================
# (1) 웨이포인트 관리 로직
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints:
        return None, []

    current = waypoints[0]
    is_final_waypoint = (len(waypoints) == 1)

    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 마지막 점은 절대 삭제하지 않음
    if is_final_waypoint:
        return current, waypoints

    # 도착 판정 시 다음 점으로
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, []
        return waypoints[0], waypoints

    return current, waypoints


# ============================================================
# (2) 시간 변화량(DT) 계산 (속도 계산 로직 완전 삭제됨)
# ============================================================
def calculate_dt(time_now):
    """
    오직 조향 PD 제어의 D항(미분) 계산을 위해 시간 차이(dt)만 관리합니다.
    위치(x, z)를 이용한 속도 계산 코드는 완전히 제거되었습니다.
    """
    global prev_time, prev_dt

    if prev_time is None:
        raw_dt = 0.033
    else:
        raw_dt = time_now - prev_time
    
    # 시간 데이터가 튀는 현상(Jitter) 방어
    # 0.0001초 이하는 중복 패킷, 0.1초 이상은 렉으로 간주하여 기본값 사용
    if raw_dt <= 1e-4 or raw_dt > 0.1:
        dt = 0.033 
    else:
        # LPF를 적용하여 부드러운 dt 생성
        dt = 0.7 * raw_dt + 0.3 * prev_dt

    prev_time = time_now
    prev_dt = dt
    
    return dt


# ============================================================
# (3) 룩어헤드 및 곡률 계산 (Player Speed 기반)
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    # 입력받은 player_speed를 기준으로 룩어헤드 거리 결정
    ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    return LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio

def compute_lookahead_point(player_x, player_z, waypoints, speed_mps):
    if not waypoints: return None
    
    # 여기서 사용하는 speed_mps는 무조건 player_speed입니다.
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
    # 곡률은 기하학적 정보이므로 속도와 무관하게 계산
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
# (4) 예측 속도 제어
# ============================================================
def calculate_predictive_speed_weight(waypoints):
    # 경로의 휨 정도만 판단 (속도 무관)
    if len(waypoints) < 3: return 1.0
    scan_dist = 0.0
    max_curve = 0.0
    
    for i in range(len(waypoints) - 2):
        wp1, wp2, wp3 = waypoints[i], waypoints[i+1], waypoints[i+2]
        scan_dist += math.sqrt((wp2['x']-wp1['x'])**2 + (wp2['z']-wp1['z'])**2)
        if scan_dist > SPEED_LOOKAHEAD_DIST: break
        
        ang1 = math.atan2(wp2['z']-wp1['z'], wp2['x']-wp1['x'])
        ang2 = math.atan2(wp3['z']-wp2['z'], wp3['x']-wp2['x'])
        diff = abs(ang1 - ang2)
        while diff > math.pi: diff -= 2*math.pi
        while diff < -math.pi: diff += 2*math.pi
        if abs(diff) > max_curve: max_curve = abs(diff)

    if max_curve < 0.2: return 1.0
    elif max_curve > 1.0: return 0.3
    else: return 1.0 - (0.7 * (max_curve - 0.2) / 0.8)


# ============================================================
# (5) 조향 제어 (PD Control)
# ============================================================
def steering_pd(angle_error, dt):
    global prev_angle_error
    if dt <= 0.0001: dt = 0.033

    P = KP_STEER * angle_error
    derivative = (angle_error - prev_angle_error) / dt
    D = KD_STEER * derivative

    prev_angle_error = angle_error
    
    return max(-1.0, min(1.0, P + D))

def smooth_speed_control(steer_cmd, predictive_weight=1.0, angle_error=0.0):
    curvature = abs(steer_cmd)
    reactive_weight = 1.0 / (1.0 + 1.8 * curvature)
    
    weight = min(reactive_weight, predictive_weight)
    
    if weight < MIN_SPEED_WEIGHT: weight = MIN_SPEED_WEIGHT
    if weight > MAX_SPEED_WEIGHT: weight = MAX_SPEED_WEIGHT
    return weight


# ============================================================
# (7) ADCS 메인 제어함수 (Player Speed 완전 의존)
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, current_speed_mps, dt):
    """
    Args:
        current_speed_mps: IBSM에서 받아온 'player_speed' (Ground Truth)
    """
    
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    
    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    dist = math.sqrt(dx*dx + dz*dz)
    is_final_leg = (len(waypoints) <= 1)
    
    # --------------------------------------------------------
    # [MODE 1] 정밀 진입 모드
    # --------------------------------------------------------
    if is_final_leg and dist <= FINAL_GOAL_THRESHOLD:
        
        if dist <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        
        look_x, look_z = head_wp["x"], head_wp["z"]
        
        # 목표 속도 설정
        desired_speed = dist * 0.8 
        
        # [속도 제어] 외부 데이터(current_speed_mps)를 기준으로 판단
        if current_speed_mps > (desired_speed + 0.5):
             WS_command = "S"
             WS_weight = 0.4 
        elif current_speed_mps > desired_speed:
             WS_command = "W"
             WS_weight = 0.0 
        else:
             WS_command = "W"
             target_weight = max(0.15, min(0.6, dist * 0.1))
             WS_weight = target_weight
             
        target_angle = math.degrees(math.atan2(look_x - px, look_z - pz)) % 360
        angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
        steer_cmd = steering_pd(angle_error, dt)

    # --------------------------------------------------------
    # [MODE 2] 일반 주행 모드
    # --------------------------------------------------------
    else:
        curve_factor = compute_curvature_factor(px, pz, waypoints)
        
        # 코너링 시 속도(player_speed)가 빠르면 룩어헤드를 줄이기 위한 변수
        eff_speed = current_speed_mps if curve_factor <= 0.5 else 0.0 
        
        lookahead = compute_lookahead_point(px, pz, waypoints, eff_speed)
        if lookahead is None: lookahead = head_wp
        look_x, look_z = lookahead["x"], lookahead["z"]
        
        target_angle = math.degrees(math.atan2(look_x - px, look_z - pz)) % 360
        angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
        steer_cmd = steering_pd(angle_error, dt)
        
        pred_w = calculate_predictive_speed_weight(waypoints)
        
        WS_command = "W"
        WS_weight = smooth_speed_control(steer_cmd, pred_w, angle_error)

        # ================================================================
        # [절대 속도 제한 (Governor)]
        # ================================================================
        # 여기서 사용하는 current_speed_mps는 정확한 'player_speed'입니다.
        # 시속 40km(약 11.1m/s)를 넘으면 강제로 제어합니다.
        if current_speed_mps >= MAX_SPEED_LIMIT_MPS:
            WS_weight = 0.0  # 가속 중단
            
            # 내리막 등에서 가속이 계속 붙는 경우 브레이크 개입
            if current_speed_mps > (MAX_SPEED_LIMIT_MPS + 2.0):
                WS_command = "S"
                WS_weight = 0.5
        # ================================================================

        if is_final_leg:
            final_wp = waypoints[-1]
            dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
            
            if dist_to_final <= APPROACH_DISTANCE:
                limit = LIMIT
                if WS_weight > limit:
                    WS_weight = limit

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

    # 1. 속도 데이터 추출 (Ground Truth)
    # IBSM이 보내주는 'player_speed' (또는 'ally_speed')를 직접 사용
    # 단위: m/s (만약 km/h로 들어온다면 /3.6 처리가 필요하나, 보통 m/s임)
    raw_speed = data.get("player_speed") or data.get("ally_speed") or 0.0
    player_speed_mps = float(raw_speed)

    # 2. 시간 계산 (오직 PD 제어용 DT만 산출)
    dt = calculate_dt(time_now)

    # 3. 경로 갱신
    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
    
    # 4. 주행 로직 실행
    # 좌표 미분 속도가 아닌, player_speed_mps를 직접 전달
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