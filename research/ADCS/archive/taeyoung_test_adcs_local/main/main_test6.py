from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 1. 제어 파라미터 (기존 튜닝 유지 + 속도 제한 추가)
# ============================================================
# [주행 - 가변 룩어헤드]
LOOKAHEAD_MIN = 5.0      
LOOKAHEAD_MAX = 15.0     
SPEED_FOR_MAX_L = 18.0          # 이 속도(m/s) 이상일 때 MAX 거리를 봅니다
SPEED_LOOKAHEAD_DIST = 25.0     # 곡률 예측을 위해 미리 스캔하는 거리

# [도착 판정 & 정밀 제어] (앞서 논의된 대로 주차 판정 완화 적용)
GOAL_THRESHOLD = 7.0            
FINAL_GOAL_THRESHOLD = 15.0     # (수정됨) 3.0 -> 15.0 (안전한 감속 거리 확보)
PARKING_THRESHOLD = 3.0         # (수정됨) 2.0 -> 3.0 (주차 판정 완화)
LIMIT = 0.35                    # 도착 임박 감속력 비율

# [속도 제한]
MAX_SPEED_WEIGHT = 40.0 / 70.0   # 최대 가속 페달 깊이
MIN_SPEED_WEIGHT = 8.0 / 70.0    # 최소 가속 페달 깊이

# [!!! 추가된 파라미터 !!!] 절대 속도 제한
# 시뮬레이터 물리 특성과 관계없이 이 속도를 넘으면 무조건 악셀 OFF
MAX_SPEED_LIMIT_KMH = 40.0
MAX_SPEED_LIMIT_MPS = MAX_SPEED_LIMIT_KMH / 3.6  # m/s 변환 (약 11.11 m/s)

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
prev_x = None            
prev_z = None            
prev_dt = 0.033          

# 현재 주행 중인 경로를 기억하기 위한 전역 변수
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

    # 마지막 점은 거리가 가까워져도 절대 삭제(pop)하지 않음
    if is_final_waypoint:
        return current, waypoints

    # 일반 경유지는 {GOAL_THRESHOLD}m 이내로 접근하면 '통과'로 간주하고 삭제
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, []
        return waypoints[0], waypoints

    return current, waypoints


# ============================================================
# (2) 속도 및 DT 계산 (변경됨: 외부 속도 사용)
# ============================================================
def estimate_speed_from_pos(time_now, x_now, z_now, external_speed_mps=None):
    global prev_time, prev_x, prev_z, prev_dt

    # 1. DT 계산 (조향 PD 제어를 위해 시간 차이는 여전히 필요함)
    if prev_time is None:
        raw_dt = 0.033
    else:
        raw_dt = time_now - prev_time
    
    # 시간 데이터 진동(Jitter) 방어: 너무 작거나 크면 기본값 사용
    if raw_dt <= 1e-4 or raw_dt > 0.1:
        dt = 0.033 
    else:
        # LPF 적용하여 dt 부드럽게 (PD 제어 안정화 용도)
        dt = 0.7 * raw_dt + 0.3 * prev_dt

    # 상태 업데이트
    prev_time, prev_x, prev_z = time_now, x_now, z_now
    prev_dt = dt

    # 2. 속도 반환 로직 변경
    # [변경됨] 직접 계산하지 않고, 신뢰할 수 있는 외부 데이터(external_speed_mps)를 우선 사용
    if external_speed_mps is not None:
        # 외부 데이터는 이미 정확하다고 가정
        return float(external_speed_mps), dt

    # --- [기존 로직 주석 처리: 시간 진동으로 인해 부정확함] ---
    # dx = x_now - prev_x
    # dz = z_now - prev_z
    # calc_speed = math.sqrt(dx*dx + dz*dz) / dt
    # return calc_speed, dt
    # --------------------------------------------------------

    return 0.0, dt


# ============================================================
# (3) 룩어헤드 및 곡률 계산
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
# (4) 예측 속도 제어
# ============================================================
def calculate_predictive_speed_weight(waypoints):
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
    # (앞선 수정사항 유지) 직진이라고 무조건 가속하는 로직 제거 -> 예측값 존중
    curvature = abs(steer_cmd)
    reactive_weight = 1.0 / (1.0 + 1.8 * curvature)
    
    # 예측 제어값과 반응형 제어값 중 더 안전한(작은) 쪽 선택
    weight = min(reactive_weight, predictive_weight)
    
    if weight < MIN_SPEED_WEIGHT: weight = MIN_SPEED_WEIGHT
    if weight > MAX_SPEED_WEIGHT: weight = MAX_SPEED_WEIGHT
    return weight


# ============================================================
# (7) ADCS 메인 제어함수 (하이브리드 로직)
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, speed_mps, dt):
    
    # 전역 변수(리스트)를 직접 수정하게 됨 (pop 등)
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
        
        # A. 목표 달성 -> 완전 정지
        if dist <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        
        # B. 정밀 제어
        look_x, look_z = head_wp["x"], head_wp["z"]
        desired_speed = dist * 0.8 
        
        # 정밀 진입 시에도 실제 속도 확인 후 제어
        if speed_mps > (desired_speed + 0.5):
             WS_command = "S"
             WS_weight = 0.4 
        elif speed_mps > desired_speed:
             WS_command = "W"
             WS_weight = 0.0 
        else:
             WS_command = "W"
             # (수정됨) 거리가 늘어난 만큼 감속 비율을 부드럽게 조정
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
        eff_speed = speed_mps if curve_factor <= 0.5 else 0.0 
        
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
        # [!!! 핵심 추가 로직 !!!] 절대 속도 제한 (Governor)
        # ================================================================
        # speed_mps는 이제 외부에서 들어온 정확한 속도값입니다.
        # 시속 40km(약 11.1m/s)를 넘으면 강제로 가속 페달을 뗍니다.
        if speed_mps >= MAX_SPEED_LIMIT_MPS:
            WS_weight = 0.0  # 과속 시 악셀 OFF
            
            # (옵션) 내리막 등에서 속도가 계속 붙으면 브레이크 사용
            # 설정한 제한속도보다 2m/s (약 7km/h) 더 빠르면 브레이크
            if speed_mps > (MAX_SPEED_LIMIT_MPS + 2.0):
                WS_command = "S"
                WS_weight = 0.5
        # ================================================================

        # [접근 감속]
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
    global current_active_waypoints # 전역 변수 유지

    data = request.get_json(force=True)
    # print('@@@@IBSM이 ADCS에 주는 데이터 : \n', data) # 디버깅용 출력
    
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = float(data.get("time", 0.0))

    px = float(ally_pos.get("x", 0.0))
    py = float(ally_pos.get("y", 0.0))
    pz = float(ally_pos.get("z", 0.0))
    yaw = float(ally_angle.get("x", 0.0)) 

    # ===============================================================
    # [수정됨] 속도 데이터 추출 (Player_Speed 사용)
    # ===============================================================
    # IBSM이 보내주는 JSON 키 이름을 확인해야 합니다.
    # 로그 데이터의 'Player_Speed'에 해당하는 값을 가져옵니다.
    # (일반적으로 'ally_speed' 혹은 'player_speed' 등의 키를 사용합니다)
    input_speed = data.get("player_speed") or data.get("ally_speed") or 0.0
    input_speed = float(input_speed)

    # estimate_speed_from_pos에 외부 속도(input_speed)를 전달합니다.
    # 이제 내부 미분 연산은 무시되고, 이 input_speed가 speed_mps가 됩니다.
    speed_mps, dt = estimate_speed_from_pos(time_now, px, pz, external_speed_mps=input_speed)

    # 웨이포인트 갱신 로직
    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
        # print(f"경로 갱신됨 ({len(current_active_waypoints)} points)")
    
    # 추적 함수 호출 (speed_mps는 이제 정확한 Player_Speed 값임)
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, current_active_waypoints, speed_mps, dt
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