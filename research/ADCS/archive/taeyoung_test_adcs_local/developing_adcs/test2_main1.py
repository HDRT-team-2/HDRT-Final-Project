from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 제어 파라미터 (수정됨)
# ============================================================
# 장애물 회피 및 코너링 정밀도 향상을 위해 값 조정
LOOKAHEAD_MIN = 5.0      # [추천값] 5.0 (장애물 바로 앞에서 피하기 위해 더 가깝게 봄)
LOOKAHEAD_MAX = 15.0     # [수정] 20.0 -> 15.0 (최대 거리도 살짝 줄임)
LOOKAHEAD_K   = 0.5      # [수정] 0.7 -> 0.5 (속도에 따른 증가폭 감소)
SPEED_FOR_MAX_L = 18.0   # 약 65km/h ≈ 18 m/s 부근에서 L이 거의 MAX 근처

# 속도 제어용 미래 예측 거리 (m) - 조향보다 더 멀리 보고 감속
SPEED_LOOKAHEAD_DIST = 25.0

# [도착 판정] 경유지 노드 근접 도착 판정, 목적지 도착 판정
# (매우 중요: GOAL_THRESHOLD(m) 이내까지 접근해야만 다음 노드로 넘어감. 미리 삭제되는 현상 방지)
GOAL_THRESHOLD = 7
FINAL_GOAL_THRESHOLD = 3.0
MAX_SPEED_WEIGHT = 65.0 / 65.0                      # 40km/h
MIN_SPEED_WEIGHT = MAX_SPEED_WEIGHT * (20 / 100)    # 거의 정지 수준

# PD Steering Gains (수정됨)
KP_STEER = 0.05          # [수정] 0.04 -> 0.05 (P항 소폭 상향)
KD_STEER = 0.005         # [수정] 0.12 -> 0.005 (진동 해결을 위해 D항 대폭 축소)

# ============================================================
# 전역 상태 — 속도 계산 / D항 계산용 이전 상태 저장
# ============================================================
prev_angle_error = 0.0   # 이전 프레임의 각도 에러 (D항)
prev_time = None         # 이전 프레임 시간
prev_x = None            # 이전 x
prev_z = None            # 이전 z
prev_dt = 0.033          # [추가] dt 필터링을 위한 이전 dt 값 (초기값 약 30fps 기준)


# ============================================================
# (0) Waypoint 형태 정규화 유틸
#      - dict {'x','y','z'} 또는 list/tuple [x,y,z] 모두 지원
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    """
    TPP 보정 로직 등에서 [x,y,z] list 형태가 올 수 있어서,
          dict / list 모두 안전하게 처리하도록 정규화.
    """
    if isinstance(wp, dict):
        x = float(wp.get("x", 0.0))
        y = float(wp.get("y", default_y))
        z = float(wp.get("z", 0.0))
        return {"x": x, "y": y, "z": z}
    elif isinstance(wp, (list, tuple)) and len(wp) >= 3:
        x = float(wp[0])
        y = float(wp[1])
        z = float(wp[2])
        return {"x": x, "y": y, "z": z}
    else:
        # 형식이 이상하면 일단 플레이어 위치 근처로 보정
        return {"x": 0.0, "y": default_y, "z": 0.0}

# 만약, ibsm에서 리스트 형태의 웨이포인트 데이터를 줬을때, 리스트 -> 딕트 타입으로 변경해주는 함수
def normalize_waypoints_list(raw_list, default_y=0.0):
    """
    리스트 전체를 dict 형태로 정규화.
    """
    if not isinstance(raw_list, list):
        return []
    return [normalize_waypoint(wp, default_y) for wp in raw_list]


# ============================================================
# (1) waypoint pop
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    """
    마지막 웨이포인트인지 확인하여 Threshold(헤딩 노드에 대한 도착판정)를 다르게 적용
    """
    if not waypoints:
        return None, waypoints

    current = waypoints[0]
    is_final_waypoint = (len(waypoints) == 1) # 남은 게 1개면 그게 마지막 점

    dx = current["x"] - player_x
    # dy = current["y"] - player_y
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx  + dz*dz)

    # 임계값 결정 로직
    # 마지막 점이면 1.0m, 아니면 7.0m 적용
    current_threshold = FINAL_GOAL_THRESHOLD if is_final_waypoint else GOAL_THRESHOLD

    # 도달 판정
    if dist <= current_threshold:
        waypoints.pop(0)
        if not waypoints:                # 진짜 최종 목적지 도착
            return None, waypoints
        current = waypoints[0]

    return current, waypoints


# ============================================================
# (2) 속도 계산 및 DT 필터링 (수정됨)
#      - 노이즈 방지 LPF 적용
# ============================================================
def estimate_speed_from_pos(time_now, x_now, z_now):
    """
    time_now를 인자로 받아 dt를 정확히 계산하고,
    (속도, dt) 튜플을 반환하도록 변경함.
    [추가] dt 값에 Low Pass Filter를 적용하여 D항 폭주 방지.
    """
    global prev_time, prev_x, prev_z, prev_dt

    if prev_time is None:
        # 첫 호출: 참고 이력 없음 → 속도 0으로 시작
        prev_time = time_now
        prev_x = x_now
        prev_z = z_now
        return 0.0, 0.033 # [수정] 초기 dt 0.033(30fps) 반환

    # IBSM 시간 기반 Raw dt 계산
    raw_dt = time_now - prev_time
    
    # 0 나누기 방지 및 리셋 대응 (너무 작거나 음수면 기본값 사용)
    if raw_dt <= 1e-4:
        raw_dt = 0.033

    # [추가] DT Low Pass Filter (노이즈 완화)
    # 현재 값 비중 0.7, 이전 값 비중 0.3
    dt = 0.7 * raw_dt + 0.3 * prev_dt
    prev_dt = dt # 다음 프레임을 위해 저장

    dx = x_now - prev_x
    dz = z_now - prev_z
    dist = math.sqrt(dx*dx + dz*dz)

    speed = dist / dt  # 속력 단위 -> m/s

    # 상태 업데이트
    prev_time = time_now
    prev_x = x_now
    prev_z = z_now

    return speed, dt                 # 필터링된 dt 반환


# ============================================================
# (3) Lookahead 거리 계산 (속도 기반 동적 L)
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    """
    [변경] 속도에 따라 L을 조정:
      - 느릴 때: L ≈ LOOKAHEAD_MIN
      - 빠를 때: L -> LOOKAHEAD_MAX 가까이
    """
    # 속도 비율 (0~1로 clamp)
    ratio = 0.0
    if SPEED_FOR_MAX_L > 1e-6:
        ratio = max(0.0, min(speed_mps / SPEED_FOR_MAX_L, 1.0))

    L = LOOKAHEAD_MIN + (LOOKAHEAD_MAX - LOOKAHEAD_MIN) * ratio
    return L


# ============================================================
# (4) Lookahead point 계산 (polyline 기반 보간)
#      - Z자 / 꺾인 경로에서도 "L m 앞 포인트"를 찾도록
# ============================================================
def compute_lookahead_point(player_x, player_z, waypoints, speed_mps):
    """
    전체 waypoint polyline을 따라
          "현재 위치에서 L m 앞"의 점을 찾아 보간.
          → 급커브에서도 미리 코너를 보고 조향할 수 있음.
    """

    if not waypoints:
        return None

    L = compute_dynamic_lookahead(speed_mps)
    remain = L

    # 현재 위치에서 시작해서 각 segment를 따라가며 L 앞 지점을 찾는다.
    prev_x = player_x
    prev_z = player_z

    for wp in waypoints:
        wx = wp["x"]
        wz = wp["z"]

        seg_dx = wx - prev_x
        seg_dz = wz - prev_z
        seg_len = math.sqrt(seg_dx*seg_dx + seg_dz*seg_dz)

        if seg_len < 1e-6:
            # 거의 움직임이 없는 segment -> 다음으로
            prev_x = wx
            prev_z = wz
            continue

        if seg_len >= remain:
            # 이 segment 안에서 L 위치를 찾을 수 있음 → 보간
            t = remain / seg_len
            lx = prev_x + seg_dx * t
            lz = prev_z + seg_dz * t
            return {"x": lx, "z": lz}

        # 아직 L에 못 미치면 남은 거리에서 seg_len만큼 빼고 다음 segment로
        remain -= seg_len
        prev_x = wx
        prev_z = wz

    # 모든 segment를 지나도 remain > 0 이면, 마지막 waypoint를 lookahead로 사용
    last_wp = waypoints[-1]
    return {"x": last_wp["x"], "z": last_wp["z"]}


# ============================================================
# 경로 굴곡도(Curvature) 계산 함수
# ============================================================
def compute_curvature_factor(player_x, player_z, waypoints):
    """
    현재 위치에서 다음 웨이포인트들의 꺾임 정도를 계산합니다.
    급커브(장애물 회피) 구간인지 판단하기 위함입니다.
    """
    if len(waypoints) < 2:
        return 0.0
    
    # 현재 진행해야 할 벡터 (내 위치 -> 첫번째 웨이포인트)
    dx1 = waypoints[0]["x"] - player_x
    dz1 = waypoints[0]["z"] - player_z
    
    # 그 다음 경로 벡터 (첫번째 -> 두번째 웨이포인트)
    dx2 = waypoints[1]["x"] - waypoints[0]["x"]
    dz2 = waypoints[1]["z"] - waypoints[0]["z"]
    
    # 두 벡터의 각도
    angle1 = math.atan2(dz1, dx1)
    angle2 = math.atan2(dz2, dx2)
    
    # 각도 차이 (절대값)
    diff = abs(angle1 - angle2)
    
    # -pi ~ pi 정규화
    while diff > math.pi: diff -= 2*math.pi
    while diff < -math.pi: diff += 2*math.pi
    
    return abs(diff) # 값이 클수록 급커브


# ============================================================
# (5) Steering PD Control
#      - 각도 오차 + 오차 변화율 기반으로 부드러운 조향
# ============================================================
def steering_pd(angle_error, dt): # dt 인자 추가
    """
    연속적인 PD 제어:
          steer_cmd = Kp * angle_error + Kd * d(angle_error)/dt
          → [-1, 1] 범위로 clamp 해서 AD_weight로 사용.
    """
    global prev_angle_error

    # P 항
    P = KP_STEER * angle_error

    # D 항 [수정] dt로 나누어 변화율 반영 (오실레이션 방지)
    # dt가 너무 작아지는 경우 방어 ( estimate_speed_from_pos에서 이미 처리하지만 2중 안전장치)
    if dt <= 0.001: dt = 0.033
        
    derivative = (angle_error - prev_angle_error) / dt
    D = KD_STEER * derivative

    steer_cmd = P + D

    prev_angle_error = angle_error

    # [-1, 1] 범위로 제한
    if steer_cmd > 1.0:
        steer_cmd = 1.0
    elif steer_cmd < -1.0:
        steer_cmd = -1.0

    return steer_cmd


# ============================================================
# 미래 경로 기반 예측 감속 (Predictive Speed Control)
# ============================================================
def calculate_predictive_speed_weight(waypoints):
    """
    미래 경로(약 {SPEED_LOOKAHEAD_DIST}m)를 스캔하여 최대 곡률을 찾고 목표 속도 Weight를 반환
    """
    if len(waypoints) < 3:
        return 1.0

    scan_dist = 0.0
    max_curvature_deg = 0.0
    
    for i in range(len(waypoints) - 2):
        wp1, wp2, wp3 = waypoints[i], waypoints[i+1], waypoints[i+2]

        # 거리 누적
        seg_dist = math.sqrt((wp2['x']-wp1['x'])**2 + (wp2['z']-wp1['z'])**2)
        scan_dist += seg_dist
        if scan_dist > SPEED_LOOKAHEAD_DIST:
            break

        # 꺾임 각도 계산
        dx1, dz1 = wp2['x'] - wp1['x'], wp2['z'] - wp1['z']
        dx2, dz2 = wp3['x'] - wp2['x'], wp3['z'] - wp2['z']
        ang1 = math.atan2(dz1, dx1)
        ang2 = math.atan2(dz2, dx2)
        
        diff = abs(ang1 - ang2)
        while diff > math.pi: diff -= 2*math.pi
        while diff < -math.pi: diff += 2*math.pi
        
        deg = math.degrees(abs(diff))
        if deg > max_curvature_deg:
            max_curvature_deg = deg
            
    # 곡률에 따른 감속 매핑 (10도~60도 사이 선형 보간)
    if max_curvature_deg <= 10.0:
        return 1.0
    elif max_curvature_deg >= 60.0:
        return 0.3 # 급커브 시 최소 속도 유지 비율
    else:
        ratio = (max_curvature_deg - 10.0) / (60.0 - 10.0)
        return 1.0 - (0.7 * ratio)


# ============================================================
# (6) Smooth Speed Control
# ============================================================
def smooth_speed_control(steer_cmd, predictive_weight=1.0): # [수정] 인자 추가
    """
    steering_cmd(조향 강도)와 predictive_weight(미래 예측) 중
    더 안전한(낮은) 값을 선택하여 감속.
    """
    curvature = abs(steer_cmd)  # 0 ~ 1

    k = 1.8  # 감속 민감도
    reactive_weight = 1.0 / (1.0 + k * curvature)

    # 예측값과 반응값 중 더 작은 값 선택 (미리 감속)
    weight = min(reactive_weight, predictive_weight)

    # 최소/최대 속도 weight 제한
    if weight < MIN_SPEED_WEIGHT:
        weight = MIN_SPEED_WEIGHT
    if weight > MAX_SPEED_WEIGHT:
        weight = MAX_SPEED_WEIGHT

    return weight


# ============================================================
# (7) ADCS 메인 제어함수
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, speed_mps, dt): # [수정] dt 추가
    """
    전체 흐름:
      1) waypoint pop으로 head_wp 갱신
      2) polyline 기반 lookahead point 계산
      3) lookahead 방향을 기준으로 목표 각도 계산
      4) yaw와의 각도 오차 -> PD -> 조향 명령(A/D, weight)
      5) steering 기반 smooth speed control -> W, weight
    """

    # ---------- waypoint pop ----------
    # GOAL_THRESHOLD가 1.5로 줄어서 더 가까이 가야 pop 됨
    head_wp, waypoints = select_waypoint(px, pz, waypoints)

    # ---------- 목적지 도달 ----------
    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # ---------- 급커브 감지 및 Lookahead 조정 ----------
    # 경로가 꺾여있다면(장애물 회피 등) 멀리 보지 말고,
    # 강제로 최저 거리(LOOKAHEAD_MIN)를 보게 하여 코너를 파고들도록 함
    curve_factor = compute_curvature_factor(px, pz, waypoints)
    
    effective_speed = speed_mps
    # 약 30도(0.5 rad) 이상 꺾인 경로라면
    if curve_factor > 0.5:
        # 속도가 빠르더라도 Lookahead 계산 시 0으로 간주하여 
        # LOOKAHEAD_MIN(3.5m)을 강제로 사용하게 함
        effective_speed = 0.0 

    # ---------- Lookahead 계산 ----------
    # speed_mps 대신 effective_speed 사용
    lookahead = compute_lookahead_point(px, pz, waypoints, effective_speed)
    
    if lookahead is None:
        # 안전장치 : lookahead 실패 시 head_wp를 사용
        lookahead = {"x": head_wp["x"], "z": head_wp["z"]}

    # ---------- lookahead -> 목표 각도 ----------
    dx = lookahead["x"] - px
    dz = lookahead["z"] - pz

    target_angle = (math.degrees(math.atan2(dx, dz))) % 360   # 반대 방향 보정

    # ---------- 차량 yaw 기준 각도 차 ----------
    angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0

    # ---------- PD Steering 적용 ----------
    steer_cmd = steering_pd(angle_error, dt)        # dt 전달

    # ---------- A/D 방향 결정 ----------
    if steer_cmd > 0.0:
        AD_command = "D"
    elif steer_cmd < 0.0:
        AD_command = "A"
    else:
        AD_command = ""

    AD_weight = abs(steer_cmd)

    # ---------- Smooth Speed Control ----------
    # 미래 경로 예측 감속 적용
    predictive_w = calculate_predictive_speed_weight(waypoints)
    
    WS_command = "W"
    WS_weight = smooth_speed_control(steer_cmd, predictive_w) # 예측값 전달

    return WS_command, WS_weight, AD_command, AD_weight, head_wp


# ============================================================
# Flask Endpoint — IBSM In/Out 형식 유지
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)

    print("\n@@@@@@ ADCS가 IBSM으로부터 제공받은 데이터 \n", data)

    # ---- 위치 / 각도 / 웨이포인트 / 시간 추출 ----
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints_raw = data.get("waypoints", [])
    time_now = data.get("time", 0.0)

    px = ally_pos.get("x", 0.0)
    py = ally_pos.get("y", 0.0)
    pz = ally_pos.get("z", 0.0)

    # yaw = x축, 즉 2차원 평면에서의 좌우 바라보는 각도값
    yaw = ally_angle.get("x", 0.0)   # 실제 heading 값

    # dt 반환 받음 (LPF 적용됨)
    speed_mps, dt = estimate_speed_from_pos(float(time_now), float(px), float(pz))

    # waypoints 형태 정규화 (dict/list 섞여 있어도 dict 리스트로 변환)
    waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)

    
    # path_tracking에 dt 전달
    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, waypoints, speed_mps, dt
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
    print('@@@@@@@@@@웨이포인트 좌표 : \n', waypoints)
    print("\n@@@@ ADCS 가 IBSM 에게 주는 데이터")
    print(response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)