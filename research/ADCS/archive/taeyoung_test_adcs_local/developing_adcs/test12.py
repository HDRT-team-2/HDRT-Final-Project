from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 제어 파라미터
# ============================================================
# [원래] LOOKAHEAD_DIST = 10.0 (고정)
# [변경] 속도 기반 동적 Lookahead: L = L_min + k * speed (m/s)
LOOKAHEAD_MIN = 7.0      # 저속에서도 최소 7m 앞을 본다
LOOKAHEAD_MAX = 20.0     # 고속에서도 20m 이상은 안 본다 (안정성)
LOOKAHEAD_K   = 0.7      # 속도(m/s)에 따른 L 증가량 계수
SPEED_FOR_MAX_L = 18.0   # 약 65km/h ≈ 18 m/s 부근에서 L이 거의 MAX 근처

GOAL_THRESHOLD = 5.0     # waypoint 도달 기준
MAX_SPEED_WEIGHT = 1.0   # 65km/h
MIN_SPEED_WEIGHT = 0.05  # 거의 정지 수준

# [새로 추가] PD Steering Gains
KP_STEER = 0.03          # 각도 오차 비례 조향 (P)
KD_STEER = 0.12          # 오차 변화율 기반 감쇠 (D)

# ============================================================
# 전역 상태 — 속도 계산 / D항 계산용 이전 상태 저장
# ============================================================
prev_angle_error = 0.0   # 이전 프레임의 각도 에러 (D항)
prev_time = None         # 이전 프레임 시간
prev_x = None            # 이전 x
prev_z = None            # 이전 z


# ============================================================
# (0) Waypoint 형태 정규화 유틸
#      - dict {'x','y','z'} 또는 list/tuple [x,y,z] 모두 지원
# ============================================================
def normalize_waypoint(wp, default_y=0.0):
    """
    [원래] IBSM -> ADCS는 dict 리스트만 온다고 가정하고 current["x"] 형태로 바로 접근.
    [변경] TPP 보정 로직 등에서 [x,y,z] list 형태가 올 수 있어서,
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
    [원래] 방식과 동일한 pop 로직 유지:
      - 맨 앞 waypoint까지의 거리가 GOAL_THRESHOLD 이하면 pop.
      - 남은 waypoint가 없으면 None 반환.
    """
    if not waypoints:
        return None, waypoints

    current = waypoints[0]

    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 도달 판정 - Robust 하게 웨이포인트 도달 판정을 내리지 않고, 
    # '근처(웨이포인트로부터 GOAL_THRESHOLD 거리 이내)에 도달만 하면' 헤드 웨이포인트 도착 판정
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:     # 목적지 도착
            return None, waypoints
        current = waypoints[0]

    return current, waypoints


# ============================================================
# (2) 속도 계산: ally_speed 컬럼은 무시하고,
#      이전 위치/시간과의 차이로 실제 속도(m/s) 추정
# ============================================================
def estimate_speed_from_pos(time_now, x_now, z_now):
    """
    시뮬레이터의 ally_speed는 믿지 않기로 했으므로,
          (d거리 / d시간)으로 속도(m/s)를 직접 계산.

    - 첫 프레임이거나 dt <= 0 이면 speed = 0.0
    - 거리 단위는 시뮬레이션 상에서 1 = 1 m 라고 가정.
    """
    global prev_time, prev_x, prev_z

    if prev_time is None:
        # 첫 호출: 참고 이력 없음 → 속도 0으로 시작
        prev_time = time_now
        prev_x = x_now
        prev_z = z_now
        return 0.0

    dt = time_now - prev_time
    if dt <= 1e-6:
        # 시간 변화가 거의 없으면 0으로 처리. 하지만 이런 일은 일어나지 않을 듯.
        return 0.0

    dx = x_now - prev_x
    dz = z_now - prev_z
    dist = math.sqrt(dx*dx + dz*dz)

    speed = dist / dt  # 속력 단위 -> m/s

    # 상태 업데이트
    prev_time = time_now
    prev_x = x_now
    prev_z = z_now

    return speed


# ============================================================
# (3) Lookahead 거리 계산 (속도 기반 동적 L)
# ============================================================
def compute_dynamic_lookahead(speed_mps):
    """
    [원래] LOOKAHEAD_DIST = 10.0 고정.
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
    [원래] 첫 waypoint(wp0) 기준으로만 방향을 잡고,
          L보다 가깝고 다음 waypoint가 있으면 wp1까지의 선분으로만 처리.

    [변경] 전체 waypoint polyline을 따라
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
# (5) Steering PD Control
#      - 각도 오차 + 오차 변화율 기반으로 부드러운 조향
# ============================================================
def steering_pd(angle_error):
    """
    [원래] if abs(angle_error) > 10:
              turn_weight = abs(angle_error)/60
              D/A + turn_weight
           → 10° 임계값에서 갑자기 조향 시작하는 Step Function.

    [변경] 연속적인 PD 제어:
         steer_cmd = Kp * angle_error + Kd * d(angle_error)/dt
         → [-1, 1] 범위로 clamp 해서 AD_weight로 사용.
    """
    global prev_angle_error

    # P 항
    P = KP_STEER * angle_error

    # D 항 (단순 프레임 기반, dt 계산은 여기선 생략)
    D = KD_STEER * (angle_error - prev_angle_error)

    steer_cmd = P + D

    prev_angle_error = angle_error

    # [-1, 1] 범위로 제한
    if steer_cmd > 1.0:
        steer_cmd = 1.0
    elif steer_cmd < -1.0:
        steer_cmd = -1.0

    return steer_cmd


# ============================================================
# (6) Smooth Speed Control
# ============================================================
def smooth_speed_control(steer_cmd):
    """
    [원래] factor = 1 - |angle_error| / 80  (선형, 계단식 변화)
    [변경] steering_cmd(조향 강도)에 따라
          1 / (1 + k * curvature) 형태로 부드럽게 감속.
    """
    curvature = abs(steer_cmd)  # 0 ~ 1

    k = 1.8  # 감속 민감도
    weight = 1.0 / (1.0 + k * curvature)

    # 최소/최대 속도 weight 제한
    if weight < MIN_SPEED_WEIGHT:
        weight = MIN_SPEED_WEIGHT
    if weight > MAX_SPEED_WEIGHT:
        weight = MAX_SPEED_WEIGHT

    return weight


# ============================================================
# (7) ADCS 메인 제어함수
# ============================================================
def path_tracking(px, py, pz, yaw_deg, waypoints, speed_mps):
    """
    전체 흐름:
      1) waypoint pop으로 head_wp 갱신
      2) polyline 기반 lookahead point 계산
      3) lookahead 방향을 기준으로 목표 각도 계산
      4) yaw와의 각도 오차 -> PD -> 조향 명령(A/D, weight)
      5) steering 기반 smooth speed control -> W, weight
    """

    # ---------- waypoint pop ----------
    head_wp, waypoints = select_waypoint(px, pz, waypoints)

    # ---------- 목적지 도달 ----------
    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # ---------- Lookahead 계산 ----------
    lookahead = compute_lookahead_point(px, pz, waypoints, speed_mps)
    if lookahead is None:
        # 안전장치 : lookahead 실패 시 head_wp를 사용
        lookahead = {"x": head_wp["x"], "z": head_wp["z"]}

    # ---------- lookahead → 목표 각도 ----------
    dx = lookahead["x"] - px
    dz = lookahead["z"] - pz

    target_angle = math.degrees(math.atan2(dx, dz)) % 360.0

    # ---------- 차량 yaw 기준 각도 차 ----------
    angle_error = (target_angle - yaw_deg + 540.0) % 360.0 - 180.0

    # ---------- PD Steering 적용 ----------
    steer_cmd = steering_pd(angle_error)

    # ---------- A/D 방향 결정 ----------
    if steer_cmd > 0.0:
        AD_command = "D"
    elif steer_cmd < 0.0:
        AD_command = "A"
    else:
        AD_command = ""

    AD_weight = abs(steer_cmd)

    # ---------- Smooth Speed Control ----------
    WS_command = "W"
    WS_weight = smooth_speed_control(steer_cmd)

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

    # yaw = y축
    yaw = ally_angle.get("x", 0.0)

    # [원래] ally_speed = data.get("ally_speed", 0.0) 를 사용할 여지가 있었음.
    # [변경] ally_speed는 완전히 무시, 좌표/시간으로 직접 계산.
    speed_mps = estimate_speed_from_pos(float(time_now), float(px), float(pz))

    # waypoints 형태 정규화 (dict/list 섞여 있어도 dict 리스트로 변환)
    waypoints = normalize_waypoints_list(waypoints_raw, default_y=py)

    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, waypoints, speed_mps
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

    print("\n@@@@ ADCS 가 IBSM 에게 주는 데이터")
    print(response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
