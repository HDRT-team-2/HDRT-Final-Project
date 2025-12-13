# look-ahead steering Control
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ===============================
# 전역 저장값 (IBSM ↔ ADCS)
# ===============================
global_WS_command = ""
global_WS_weight = 0.0
global_AD_command = ""
global_AD_weight = 0.0


# ============================================================
# Waypoint Selection
# ============================================================

def select_waypoint(player_x, player_z, waypoints):
    """
    A 스타일 도달 판정:
    - waypoints[0]까지 8m 이하 → pop(0)
    - pop 후 리스트가 비면 목적지 도달
    """
    if not waypoints:
        return None, waypoints

    current = waypoints[0]
    dx = current["x"] - player_x
    dz = current["z"] - player_z
    distance = math.sqrt(dx * dx + dz * dz)

    # 노드 근처 (n)m 근처 도달시, 해당 노드 도착 판정
    THRESHOLD = 8.0

    # ---- 도달 판정 ----
    if distance <= THRESHOLD:
        waypoints.pop(0)

        # 목적지 도달
        if not waypoints:
            return None, waypoints

        current = waypoints[0]

    return current, waypoints


# ============================================================
# Lookahead Steering Target 계산
# ============================================================

def get_lookahead_wp(waypoints, lookahead_step=1):
    """
    lookahead_step = 1 → 다음 waypoint
    lookahead_step = 2 → 다다음 waypoint
    """
    if not waypoints:
        return None

    idx = min(lookahead_step, len(waypoints) - 1)
    return waypoints[idx]


# ============================================================
# ADCS 메인 제어 로직 (룩어헤드 + 커브감속 적용)
# ============================================================

def path_tracking(player_x, player_y, player_z, body_yaw_deg, waypoints):

    # 1) Waypoint 선택 (A스타 방식)
    head_wp, waypoints = select_waypoint(player_x, player_z, waypoints)

    # 목적지 도달
    if head_wp is None:
        return ("STOP", 1.0, "", 0.0, None)

    # 2) 룩어헤드 waypoint 가져오기
    lookahead_wp = get_lookahead_wp(waypoints, lookahead_step=1)
    target_wp = lookahead_wp if lookahead_wp is not None else head_wp

    # ------------------------------
    # 3. 목표각 계산
    # ------------------------------
    dx = target_wp["x"] - player_x
    dz = target_wp["z"] - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360

    # ------------------------------
    # 4. 차량 yaw 기준 각도차 계산
    # ------------------------------
    angle_diff = (target_angle - body_yaw_deg + 540.0) % 360.0 - 180.0
    abs_angle_diff = abs(angle_diff)

    # ------------------------------
    # NEW: 룩어헤드 기반 steering intensity (0~1)
    # ------------------------------
    steering_intensity = min(abs_angle_diff / 90.0, 1.0)

    # ------------------------------
    # 5. 커브 감속 모델 (핵심)
    # ------------------------------
    # forward_weight = 1 - steering_intensity^p
    p = 2.5
    forward_weight = 1.0 - (steering_intensity ** p)
    forward_weight = max(0.0, forward_weight)  # 음수 방지

    # ------------------------------
    # 6. 회전 명령
    # ------------------------------
    AD_command = ""
    AD_weight = 0.0

    if abs_angle_diff > 10:
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        AD_command = "D" if angle_diff > 0 else "A"
        AD_weight = turn_weight

    # ------------------------------
    # 조향과 속도 커플링(선택적)
    # 고속일수록 조향 제한 → 안전한 곡선 주행
    # ------------------------------
    AD_weight = AD_weight * (0.7 + 0.3 * (1.0 - forward_weight))

    # ------------------------------
    # 7. 전진 명령
    # ------------------------------
    WS_command = ""
    WS_weight = 0.0

    if forward_weight > 0.02:
        WS_command = "W"
        WS_weight = forward_weight

    return WS_command, WS_weight, AD_command, AD_weight, head_wp


# ============================================================
# /get_adcs API
# ============================================================

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)
    print('@@@@@@@IBSM에서 제공받은 데이터 : ', data)


    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints = data.get("waypoints", [])

    player_x = ally_pos.get("x", 0.0)
    player_y = ally_pos.get("y", 0.0)
    player_z = ally_pos.get("z", 0.0)

    # yaw = y축
    body_yaw_deg = ally_angle.get("y", 0.0)

    WS_command, WS_weight, AD_command, AD_weight, head_wp = path_tracking(
        player_x, player_y, player_z, body_yaw_deg, waypoints
    )

    # Head_waypoint dict 구성
    if head_wp is not None:
        head_waypoint_dict = {
            "x": head_wp["x"],
            "y": head_wp["y"],
            "z": head_wp["z"]
        }
    else:
        head_waypoint_dict = {
            "x": player_x,
            "y": player_y,
            "z": player_z
        }

    response = {
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "head_waypoint": head_waypoint_dict
    }

    print('@@@ IBSM에 주는 ADCS 응답:', response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
