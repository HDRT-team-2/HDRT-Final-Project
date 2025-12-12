from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ==============================================================================
# [CONFIG] 통합 튜닝 파라미터
# ==============================================================================

# 1. [속도 및 룩어헤드 설정] (Mode별 가변 설정)
# ------------------------------------------------------------------------------
# 0.3초 딜레이 환경이므로 고속일수록 더 멀리 봐야(Lookahead High) 진동하지 않습니다.

# [Mode 1] 저속/정밀 주행
MODE_1_SPEED_STRAIGHT_KMH = 20.0
MODE_1_SPEED_CORNER_KMH   = 12.0
MODE_1_LOOKAHEAD_MAX      = 15.0  # 짧게 봐서 경로를 정밀하게 추종

# [Mode 2] 일반 주행
MODE_2_SPEED_STRAIGHT_KMH = 40.0
MODE_2_SPEED_CORNER_KMH   = 24.0
MODE_2_LOOKAHEAD_MAX      = 28.0  # 속도에 비례하여 시야 확장

# [Mode 3] 고속 주행
MODE_3_SPEED_STRAIGHT_KMH = 70.0
MODE_3_SPEED_CORNER_KMH   = 30.0
MODE_3_LOOKAHEAD_MAX      = 45.0  # 멀리 보지 않으면 차가 좌우로 흔들림 (Oscillation 방지)

# 공통 속도 제어 게인
KP_SPEED = 0.4  # 전진 가속력 P게인 (0.1 ~ 1.0)
KP_BRAKE = 0.2  # 브레이크 감속력 P게인 (0.1 ~ 1.0)


# 2. [조향 제어] (PD-Control)
# ------------------------------------------------------------------------------
# 딜레이가 크므로(0.3s) P게인을 낮추고 D게인을 높여 안정성 확보
KP_STEER = 0.02   # P게인
KD_STEER = 0.015  # D게인

# 3. [주행 시야 공통 설정]
# ------------------------------------------------------------------------------
LOOKAHEAD_MIN        = 12.0  # 어떤 모드든 최소 12m는 봐야 함 (너무 짧으면 뱀처럼 움직임)
SPEED_FOR_MAX_L      = 15.0  # 이 속도(m/s) 이상일 때 MAX 거리를 적용 (약 54km/h)
# 70km/h(약 19m/s)인 Mode 3에서는 항상 MAX 거리(45m)를 보게 됨

# [FIX] 기존: 곡률 예측 스캔 거리 (고정값 30.0) -> 수정: 임시 고정값 사용 (2단계에서 동적 변경 예정)
# SPEED_LOOKAHEAD_DIST = 30.0  # (삭제됨)
SCAN_DISTANCE_FIXED = 30.0 # [STEP 1] 로직 검증용 임시 고정 거리

# 4. [주차 및 도착 판정]
# ------------------------------------------------------------------------------
GOAL_THRESHOLD        = 8.0   # 경유지 통과 판정
FINAL_GOAL_THRESHOLD  = 20.0  # 도착 감속 시작 거리
PARKING_THRESHOLD     = 3.0   # 완전 정지 판정

# 5. [제어 임계값]
# ------------------------------------------------------------------------------
CURVE_FACTOR_LIMIT = 0.5   # 곡률이 이 값보다 크면 '코너'로 인식
STEER_CMD_LIMIT    = 0.3   # 조향 명령이 이 값보다 크면 '급커브'로 인식

# ==============================================================================
# 전역 변수 (상태 저장)
# ==============================================================================
prev_angle_error = 0.0
prev_time = None
prev_dt = 0.033 
current_active_waypoints = []
dt_buffer = []
MAX_DT_BUFFER_SIZE = 10 

# ==============================================================================
# (0) 유틸리티 함수
# ==============================================================================
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
    global prev_time, prev_dt, dt_buffer
    if prev_time is None:
        prev_time = time_now
        return 0.1
    raw_dt = time_now - prev_time
    if raw_dt < 0.001: return prev_dt 
    if raw_dt > 1.0: raw_dt = 1.0
    dt_buffer.append(raw_dt)
    if len(dt_buffer) > MAX_DT_BUFFER_SIZE: dt_buffer.pop(0)
    avg_dt = sum(dt_buffer) / len(dt_buffer)
    prev_time = time_now
    prev_dt = avg_dt
    return avg_dt

def get_target_params(mode_int):
    """
    Mode에 따라 [직선속도, 코너속도, 최대룩어헤드] 3가지를 반환
    """
    if mode_int == 1:
        return MODE_1_SPEED_STRAIGHT_KMH, MODE_1_SPEED_CORNER_KMH, MODE_1_LOOKAHEAD_MAX
    elif mode_int == 2:
        return MODE_2_SPEED_STRAIGHT_KMH, MODE_2_SPEED_CORNER_KMH, MODE_2_LOOKAHEAD_MAX
    elif mode_int == 3:
        return MODE_3_SPEED_STRAIGHT_KMH, MODE_3_SPEED_CORNER_KMH, MODE_3_LOOKAHEAD_MAX
    else:
        # 기본값 (Mode 1)
        return MODE_1_SPEED_STRAIGHT_KMH, MODE_1_SPEED_CORNER_KMH, MODE_1_LOOKAHEAD_MAX

# ==============================================================================
# (1) 룩어헤드 및 곡률 계산
# ==============================================================================
def compute_dynamic_lookahead(speed_mps, max_dist):
    # 속도가 빠를수록 ratio가 1.0에 가까워짐
    ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))
    # 모드별로 설정된 max_dist까지 늘어나도록 함
    return LOOKAHEAD_MIN + (max_dist - LOOKAHEAD_MIN) * ratio

def compute_lookahead_point(player_x, player_z, waypoints, speed_mps, max_dist):
    if not waypoints: return None
    
    # [핵심] 가변 룩어헤드 적용
    L = compute_dynamic_lookahead(speed_mps, max_dist)
    
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

# [STEP 1 수정] 3점 벡터 계산 및 루프 적용
def compute_curvature_factor(player_x, player_z, waypoints):
    # [FIX] 기존: len < 2 -> 수정: 3점 계산을 위해 최소 3개 필요
    if len(waypoints) < 3: return 0.0

    max_curvature = 0.0
    accumulated_dist = 0.0
    
    # 시작점(차량) ~ 첫 웨이포인트 거리 계산
    dx = waypoints[0]["x"] - player_x
    dz = waypoints[0]["z"] - player_z
    accumulated_dist += math.sqrt(dx**2 + dz**2)

    # [FIX] 기존: 무조건 앞의 두 점만 비교 -> 수정: 스캔 거리(30m) 내의 모든 점 순회
    for i in range(len(waypoints) - 2):
        if accumulated_dist > SCAN_DISTANCE_FIXED:
            break
            
        p1 = waypoints[i]
        p2 = waypoints[i+1]
        p3 = waypoints[i+2]
        
        # 거리 누적
        seg_len = math.sqrt((p2["x"] - p1["x"])**2 + (p2["z"] - p1["z"])**2)
        accumulated_dist += seg_len
        
        # [FIX] 기존: dx1, dx2 단순 차이 -> 수정: 3점(Vector 1, Vector 2) 각도 차이 계산
        vec1_x, vec1_z = p2["x"] - p1["x"], p2["z"] - p1["z"]
        vec2_x, vec2_z = p3["x"] - p2["x"], p3["z"] - p2["z"]
        
        angle1 = math.atan2(vec1_z, vec1_x)
        angle2 = math.atan2(vec2_z, vec2_x)
        
        diff = abs(angle1 - angle2)
        while diff > math.pi: diff -= 2*math.pi
        while diff < -math.pi: diff += 2*math.pi
        
        if abs(diff) > max_curvature:
            max_curvature = abs(diff)
            
    return max_curvature

# ==============================================================================
# (2) 웨이포인트 관리
# ==============================================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints: return None, []
    current = waypoints[0]
    dist = math.sqrt((current["x"] - player_x)**2 + (current["z"] - player_z)**2)
    
    if len(waypoints) == 1:
        return current, waypoints

    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints: return None, []
        return waypoints[0], waypoints
    return current, waypoints

# ==============================================================================
# (3) 제어기
# ==============================================================================
def steering_pd(angle_error, dt):
    global prev_angle_error
    if dt <= 0.001: dt = 0.033
    P = KP_STEER * angle_error
    D = KD_STEER * ((angle_error - prev_angle_error) / dt)
    prev_angle_error = angle_error
    return max(-1.0, min(1.0, P + D))

def speed_pid_control(current_speed_mps, target_speed_kmh):
    target_speed_mps = target_speed_kmh / 3.6
    error = target_speed_mps - current_speed_mps
    throttle = error * KP_SPEED
    return max(0.0, min(1.0, throttle))

def brake_p_control(current_speed_mps, target_speed_kmh):
    target_speed_mps = target_speed_kmh / 3.6
    speed_diff = current_speed_mps - target_speed_mps

    # [Deadband] 목표보다 1.0m/s (약 3.6km/h) 이상 빠를 때만 브레이크 작동
    # 엑셀과 브레이크가 동시에 간섭하는 것을 방지
    if speed_diff > 1.0:
        # P-Control : 초과한 속도에 비례해서 브레이크 밟기
        # speed_diff가 5.0(18km/h 초과)이면 5.0 * 0.2 = 1.0 (풀 브레이킹)
        brake_val = (speed_diff - 1.0) * KP_BRAKE

        # 0.0 ~ 1.0 사이로 클램핑(Clamping)
        return max(0.0, min(1.0, brake_val))
    return 0.0

# ==============================================================================
# (4) ADCS 메인 주행 로직
# ==============================================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, current_speed_mps, dt,
                  target_spd_str, target_spd_cnr, lookahead_max):
    
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    if head_wp is None: return "STOP", 1.0, "", 0.0, None

    # --- Steering Control ---
    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    
    # [STEP 1] 곡률 계산 함수 호출 (3점 벡터 방식 적용됨)
    curve_factor = compute_curvature_factor(px, pz, waypoints)
    
    # 코너에서는 룩어헤드를 최소값(12m)으로 줄여 안쪽을 파고들게 함
    lookahead_speed_ref = current_speed_mps if curve_factor <= CURVE_FACTOR_LIMIT else 0.0
    
    # [핵심] lookahead_max 인자 전달
    lookahead = compute_lookahead_point(px, pz, waypoints, lookahead_speed_ref, lookahead_max)
    if lookahead is None: lookahead = head_wp
    
    target_angle = math.degrees(math.atan2(lookahead["x"] - px, lookahead["z"] - pz)) % 360
    angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
    steer_cmd = steering_pd(angle_error, dt)

    # --- Speed Control ---
    if curve_factor > CURVE_FACTOR_LIMIT or abs(steer_cmd) > STEER_CMD_LIMIT:
        target_speed = target_spd_cnr
    else:
        target_speed = target_spd_str

    # --- Parking Logic ---
    is_final_leg = (len(waypoints) <= 1)
    if is_final_leg:
        final_wp = waypoints[-1]
        dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
        if dist_to_final <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        elif dist_to_final <= FINAL_GOAL_THRESHOLD:
            target_speed = min(target_speed, dist_to_final * 2.0)

    # --- Actuation ---
    
    # 1. 엑셀량 계산
    throttle_val = speed_pid_control(current_speed_mps, target_speed)

    # 2. 브레이크량 계산 (P제어)
    brake_val = brake_p_control(current_speed_mps, target_speed)

    # 3. 우선순위 결정 (브레이크가 필요하면 엑셀 무시)
    if brake_val > 0.0:
        WS_command = "S"
        WS_weight = brake_val
    else:
        WS_command = "W"
        WS_weight = throttle_val

    if steer_cmd > 0: 
        AD_command = "D"
    elif steer_cmd < 0: 
        AD_command = "A"
    else: 
        AD_command = ""
    
    return WS_command, WS_weight, AD_command, abs(steer_cmd), head_wp

# ==============================================================================
# Flask Endpoint
# ==============================================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    global current_active_waypoints

    # 1. 데이터 수신
    data = request.get_json(force=True)
    print('@@@@@ IBSM -> ADCS :', data)
    
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = float(data.get("time", 0.0))

    # 2. Mode에 따른 파라미터 추출 (속도 + 룩어헤드)
    mode = int(data.get("mode", 0)) 
    TARGET_STR, TARGET_CNR, LOOK_MAX = get_target_params(mode)

    px = float(ally_pos.get("x", 0.0))
    py = float(ally_pos.get("y", 0.0))
    pz = float(ally_pos.get("z", 0.0))
    yaw = float(ally_angle.get("x", 0.0)) 

    # 3. 속도 및 시간 계산
    raw_speed = data.get("player_speed") or data.get("ally_speed") or 0.0
    player_speed_mps = float(raw_speed)
    dt = calculate_dt(time_now)

    # 4. 경로 갱신
    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
    
    # 5. 주행 로직 실행 (모드별 룩어헤드 전달)
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, current_active_waypoints, player_speed_mps, dt,
        TARGET_STR, TARGET_CNR, LOOK_MAX
    )
    
    # 6. 응답 생성
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
    print('@@ ADCS -> IBSM : ', response)
    return jsonify(response)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)