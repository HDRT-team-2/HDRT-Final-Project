from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ==============================================================================
# [CONFIG] 통합 튜닝 파라미터 (0.3초 딜레이 대응 버전)
# ==============================================================================

# 1. [속도 제어] (P-Control)
# ------------------------------------------------------------------------------
# 0.3초 딜레이 환경이므로 P게인을 낮춰 부드럽게 가속/감속하도록 유도
TARGET_SPEED_STRAIGHT_KMH = 20.0  # 직선 주행 시 목표 속도 (km/h)
TARGET_SPEED_CORNER_KMH   = 12.0  # 코너링/조향 시 목표 속도 (km/h)
KP_SPEED                  = 0.4   # 속도 P게인 (0.1~1.0)

# 2. [조향 제어] (PD-Control)
# ------------------------------------------------------------------------------
# 딜레이가 크므로(0.3s) P게인을 대폭 낮춰 오버슈트(흔들림)를 막고,
# D게인을 높여 진동을 억제합니다.
KP_STEER = 0.02   # 조향 P게인 (기존 0.05 -> 0.02 하향)
KD_STEER = 0.015  # 조향 D게인 (기존 0.005 -> 0.015 상향)

# 3. [주행 시야] (가변 룩어헤드)
# ------------------------------------------------------------------------------
# 데이터가 듬성듬성 들어오므로(약 3~4m 이동), 너무 가까이 보면 진동합니다.
# 멀리 봐서 경로를 평균적으로 추종하게 합니다.
LOOKAHEAD_MIN        = 12.0  # 저속 룩어헤드 (기존 5.0 -> 12.0 상향)
LOOKAHEAD_MAX        = 25.0  # 고속 룩어헤드 (기존 15.0 -> 25.0 상향)
SPEED_FOR_MAX_L      = 10.0  # 이 속도(m/s)일 때 MAX 거리를 봄
SPEED_LOOKAHEAD_DIST = 30.0  # 곡률 예측 스캔 거리

# 4. [주차 및 도착 판정]
# ------------------------------------------------------------------------------
# 통신 딜레이로 제동 타이밍이 밀릴 수 있어 감속 시작 거리를 늘림
GOAL_THRESHOLD       = 8.0   # 경유지 통과 판정
FINAL_GOAL_THRESHOLD = 20.0  # 도착 감속 시작 거리 (기존 15.0 -> 20.0)
PARKING_THRESHOLD    = 3.0   # 완전 정지 판정

# 5. [제어 임계값]
# ------------------------------------------------------------------------------
CURVE_FACTOR_LIMIT = 0.5   # 곡률이 이 값보다 크면 '코너'로 인식
STEER_CMD_LIMIT    = 0.3   # 조향 명령이 이 값보다 크면 '급커브'로 인식

# ==============================================================================
# 전역 변수 (상태 저장)
# ==============================================================================
prev_angle_error = 0.0
prev_time = None
prev_dt = 0.033 # 초기값
current_active_waypoints = []

# [DT 필터용 버퍼]
dt_buffer = []
MAX_DT_BUFFER_SIZE = 10 # 최근 10개 프레임 평균 사용 (진동 방지)

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
    """
    이동 평균 필터(Moving Average Filter)를 적용하여
    들쭉날쭉한 프레임 시간(Jitter)을 부드럽게 만듭니다.
    이는 D제어의 발산(Derivative Kick)을 막는 핵심 로직입니다.
    """
    global prev_time, prev_dt, dt_buffer
    
    if prev_time is None:
        prev_time = time_now
        return 0.1 # 첫 진입 시(에피소드 최초 시작시) 안전값

    raw_dt = time_now - prev_time
    
    # 이상치 제거 (중복 패킷 or 심각한 렉)
    if raw_dt < 0.001: 
        return prev_dt 
    if raw_dt > 1.0:
        raw_dt = 1.0

    # 이동 평균 계산
    dt_buffer.append(raw_dt)
    if len(dt_buffer) > MAX_DT_BUFFER_SIZE:
        dt_buffer.pop(0)
    
    avg_dt = sum(dt_buffer) / len(dt_buffer)

    prev_time = time_now
    prev_dt = avg_dt
    
    return avg_dt

# ==============================================================================
# (1) 룩어헤드 및 곡률 계산
# ==============================================================================
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

# ==============================================================================
# (2) 웨이포인트 관리
# ==============================================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints: return None, []
    
    current = waypoints[0]
    # 단순히 첫 번째 점과의 거리만 보지 않고, 룩어헤드 로직에서 처리하므로
    # 여기서는 "지나쳤는지"만 판별하여 리스트에서 제거함
    dist = math.sqrt((current["x"] - player_x)**2 + (current["z"] - player_z)**2)
    
    # 마지막 점은 삭제 금지
    if len(waypoints) == 1:
        return current, waypoints

    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:
            return None, []
        return waypoints[0], waypoints

    return current, waypoints

# ==============================================================================
# (3) 제어기 (Steering PD & Speed P-Control)
# ==============================================================================
def steering_pd(angle_error, dt):
    global prev_angle_error
    
    # dt가 너무 작으면 미분항 폭주 방지
    if dt <= 0.001: 
        dt = 0.033

    P = KP_STEER * angle_error
    D = KD_STEER * ((angle_error - prev_angle_error) / dt)
    
    prev_angle_error = angle_error
    
    # 조향값 -1.0 ~ 1.0 제한
    return max(-1.0, min(1.0, P + D))

def speed_pid_control(current_speed_mps, target_speed_kmh):
    """
    목표 속도 추종을 위한 P-제어기
    """
    target_speed_mps = target_speed_kmh / 3.6
    
    # 오차 계산
    error = target_speed_mps - current_speed_mps
    
    # P-Control (목표보다 느리면 밟고, 빠르면 뗀다)
    throttle = error * KP_SPEED
    
    # 출력 제한 (0.0 ~ 1.0)
    return max(0.0, min(1.0, throttle))

# ==============================================================================
# (4) ADCS 메인 주행 로직
# ==============================================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, current_speed_mps, dt):
    
    head_wp, waypoints = select_waypoint(px, pz, waypoints)
    
    if head_wp is None:
        return "STOP", 1.0, "", 0.0, None

    # --- [1] Steering Control (PD) ---
    dx = head_wp["x"] - px
    dz = head_wp["z"] - pz
    
    curve_factor = compute_curvature_factor(px, pz, waypoints)
    
    # 코너링 중이면 룩어헤드를 짧게 가져가기 위해 '속도가 0인 것처럼' 속여서 계산
    # (LOOKAHEAD_MIN 값을 사용하게 됨)
    lookahead_speed_ref = current_speed_mps if curve_factor <= CURVE_FACTOR_LIMIT else 0.0
    
    lookahead = compute_lookahead_point(px, pz, waypoints, lookahead_speed_ref)
    if lookahead is None: lookahead = head_wp
    
    # 목표 각도 및 오차 계산
    target_angle = math.degrees(math.atan2(lookahead["x"] - px, lookahead["z"] - pz)) % 360
    angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0
    
    steer_cmd = steering_pd(angle_error, dt)

    # --- [2] Speed Control (Logic + P-Control) ---
    
    # (A) 목표 속도 설정 (Planning)
    # 곡률이 심하거나, 조향각이 크면(급커브) 목표 속도를 낮춤
    if curve_factor > CURVE_FACTOR_LIMIT or abs(steer_cmd) > STEER_CMD_LIMIT:
        target_speed = TARGET_SPEED_CORNER_KMH
    else:
        target_speed = TARGET_SPEED_STRAIGHT_KMH

    # (B) 주차 모드 (Override)
    is_final_leg = (len(waypoints) <= 1)
    if is_final_leg:
        final_wp = waypoints[-1]
        dist_to_final = math.sqrt((final_wp["x"] - px)**2 + (final_wp["z"] - pz)**2)
        
        if dist_to_final <= PARKING_THRESHOLD:
            return "STOP", 1.0, "", 0.0, head_wp
        elif dist_to_final <= FINAL_GOAL_THRESHOLD:
            # 거리에 비례해 목표 속도를 0으로 수렴시킴 (부드러운 정차)
            target_speed = min(target_speed, dist_to_final * 2.0)

    # (C) 실제 페달 조작량 계산 (Control)
    WS_weight = speed_pid_control(current_speed_mps, target_speed)
    
    # (D) 브레이크 로직 (Safety)
    # 목표 속도보다 2m/s (약 7km/h) 이상 빠르면 브레이크 개입
    if current_speed_mps > (target_speed/3.6) + 2.0: 
        WS_command = "S"
        WS_weight = 0.5 
    else:
        WS_command = "W"

    # 조향 명령 문자열 변환
    if steer_cmd > 0: AD_command = "D"
    elif steer_cmd < 0: AD_command = "A"
    else: AD_command = ""
    
    return WS_command, WS_weight, AD_command, abs(steer_cmd), head_wp

# ==============================================================================
# Flask Endpoint
# ==============================================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    global current_active_waypoints

    # 1. 데이터 수신
    data = request.get_json(force=True)
    print('@@@@ IBSM으로부터 제공받은 데이터값들 : \n', data)
    
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = float(data.get("time", 0.0))

    px = float(ally_pos.get("x", 0.0))
    py = float(ally_pos.get("y", 0.0))
    pz = float(ally_pos.get("z", 0.0))
    yaw = float(ally_angle.get("x", 0.0)) 

    # 2. 속도 데이터 추출 (Ground Truth)
    # player_speed가 없으면 ally_speed를 찾고, 없으면 0.0
    raw_speed = data.get("player_speed") or data.get("ally_speed") or 0.0
    player_speed_mps = float(raw_speed)

    # 3. 시간 간격(dt) 계산 (이동 평균 필터 적용)
    dt = calculate_dt(time_now)

    # 4. 경로 갱신
    if waypoints_raw:
        current_active_waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)
    
    # 5. 주행 로직 실행
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, current_active_waypoints, player_speed_mps, dt
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
    print('@@@ ADCS의 리턴값 : \n', response)
    return jsonify(response)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)