from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ============================================================
# 제어 파라미터
# ============================================================
LOOKAHEAD_DIST = 10.0   # Pure-Pursuit Lookahead 거리
GOAL_THRESHOLD = 8.0    # waypoint 도달 기준
MAX_SPEED_WEIGHT = 65.0 / 65.0  # 65km/h
MIN_SPEED_WEIGHT = 10.0 / 65.0  # 거의 정지 수준

# 전차 최소 회전 반경 (근사값, 곡률 계산의 안정성 위해)
MIN_TURN_RADIUS = 6.0   # meter     현재는 코드에서 쓰이지 않고 있는 파라미터


# ============================================================
# Waypoint pop 방식 (A 스타일)
# ============================================================
def select_waypoint(player_x, player_z, waypoints):
    if not waypoints:
        return None, waypoints

    current = waypoints[0]

    dx = current["x"] - player_x
    dz = current["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 도달 판정
    if dist <= GOAL_THRESHOLD:
        waypoints.pop(0)
        if not waypoints:     # 목적지 도착
            return None, waypoints
        current = waypoints[0]

    return current, waypoints


# ============================================================
# Pure-Pursuit Lookahead Target 계산
# (waypoint가 짧을 때 선분 상에서 보간)
# ============================================================
def compute_lookahead_point(player_x, player_z, waypoints):
    if not waypoints:
        return None

    # 1) 가장 가까운 선분 찾기
    #    (여기서는 간단히 waypoint[0] 기준 → 이후 필요시 확장 가능)
    wp0 = waypoints[0]

    dx = wp0["x"] - player_x
    dz = wp0["z"] - player_z
    dist = math.sqrt(dx*dx + dz*dz)

    # 가까우면 다음 waypoint 사용 (부드러운 lookahead)
    if dist < LOOKAHEAD_DIST and len(waypoints) >= 2:
        wp1 = waypoints[1]
    else:
        wp1 = wp0

    # 2) 선분 방향 벡터
    vx = wp1["x"] - player_x
    vz = wp1["z"] - player_z
    v_len = math.sqrt(vx*vx + vz*vz)

    if v_len < 1e-6:
        return wp1  # 변화 거의 없음

    # 3) lookahead 거리만큼 전진한 점 계산
    scale = LOOKAHEAD_DIST / v_len
    lx = player_x + vx * scale
    lz = player_z + vz * scale

    return {"x": lx, "z": lz}


# ============================================================
# 곡률 기반 속도 제어 (핵심: 조향 ↔ 속도 연동)
# ============================================================
def curvature_speed_control(steering_angle_deg):
    """
    steering_angle_deg: 조향 요구량 (degree)
    크면 클수록 감속해야 함
    """

    abs_ang = abs(steering_angle_deg)

    # 곡률 기반 감속 모델
    # steering 0° → 1.0
    # steering > 45° → 강한 감속
    # steering > 80° → 거의 정지
    factor = max(0.0, 1.0 - abs_ang / 80.0)

    # 전진 weight 하한 설정
    factor = max(factor, MIN_SPEED_WEIGHT)

    return factor * MAX_SPEED_WEIGHT


# ============================================================
# ADCS 메인 제어함수
# ============================================================
def path_tracking(player_x, player_y, player_z, body_yaw_deg, waypoints):

    # ---------- waypoint pop ----------
    head_wp, waypoints = select_waypoint(player_x, player_z, waypoints)

    # ---------- 목적지 도달 ----------
    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # ---------- Pure-Pursuit Lookahead 계산 ----------
    lookahead = compute_lookahead_point(player_x, player_z, waypoints)

    # ---------- lookahead → 목표 각도 ----------
    dx = lookahead["x"] - player_x
    dz = lookahead["z"] - player_z

    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    # ---------- 차량 yaw 기준 각도 차 ----------
    angle_diff = (target_angle - body_yaw_deg + 540.0) % 360.0 - 180.0
    abs_angle_diff = abs(angle_diff)

    # ========================================================
    # 회전 명령
    # ========================================================
    AD_command = ""
    AD_weight = 0.0

    if abs_angle_diff > 10:
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command = "D"
        else:
            AD_command = "A"
        AD_weight = turn_weight

    # ========================================================
    # 전진 명령 (곡률 기반 자동 감속)
    # ========================================================
    WS_command = ""
    WS_weight = 0.0

    # Pure-Pursuit steering ↔ speed 연동
    forward_weight = curvature_speed_control(angle_diff)

    if forward_weight > MIN_SPEED_WEIGHT:
        WS_command = "W"
        WS_weight = forward_weight

    return WS_command, WS_weight, AD_command, AD_weight, head_wp


# ============================================================
# Flask Endpoint
# ============================================================
@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)

    print('\n@@@@@@@@@@@@@@@@@@@@@@@@@ IBSM에서 제공받은 데이터 \n', data)

    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints = data.get("waypoints", [])

    px = ally_pos.get("x", 0.0)
    py = ally_pos.get("y", 0.0)
    pz = ally_pos.get("z", 0.0)

    # yaw = y축
    yaw = ally_angle.get("y", 0.0)

    WS_cmd, WS_w, AD_cmd, AD_w, head_wp = path_tracking(
        px, py, pz, yaw, waypoints
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

    print("\n@@@@@@@@@@@@@@@@@@@@@@@@@ ADCS가 주는 응답 → IBSM")
    print(response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)


# 받아오는 데이터
# time                  # 속력 계산하는데 필수
# ally_body_pos         # 나의 좌표. 속력 계산하는데 필수
# ally_body_angle       # 쓰진 않는것같애
# ally_speed            # 근데 이건 안써 정확하지가 않아
# waypoints             # 가장중요해 ibsm에서 생성된 장애물 주변에 생성된 노드 좌표야. 이 노드와 노드 사이를 "스무스하게" 주행하는게 목표야
# @@@@@@ IBSM에서 제공받은 데이터
#  {'time': 34.61923599243164, 'ally_body_pos': {'x': 23.199731826782227, 'y': 7.967824935913086, 'z': 27.666059494018555}, 'ally_body_angle': {'x': 141.78524780273438, 'y': -1.1652911098281038e-06, 'z': 9.781058906810358e-06}, 'ally_speed': 6.962269306182861, 'waypoints': [{'x': 149.99990844726562, 'y': 8.599993705749512, 'z': 150.0001678466797}]}

# @@@@ ADCS Response → IBSM
# {'WS_command': 'W', 'WS_weight': 0.42466255832174515, 'AD_command': 'D', 'AD_weight': 0.7671165889043399, 'head_waypoint': {'x': 149.99990844726562, 'y': 8.599993705749512, 'z': 150.0001678466797}}
# 192.168.0.142 - - [19/Nov/2025 09:47:36] "POST /get_adcs HTTP/1.1" 200 -
