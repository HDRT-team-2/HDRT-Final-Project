# ============================================================
# ADCS (Automatic Driving Control Server)
# - mid_light_complete 기반 제어 로직 100% 유지
# - IBSM2와 데이터 포맷 완전 호환
# - Head_waypoint를 dict로 통일
# - fire 제거
# ============================================================

from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ------------------------------------------------------------
# 가장 가까운 waypoint를 찾고 그 다음 waypoint를 반환
# ------------------------------------------------------------
def select_target_waypoint(player_x, player_y, player_z, waypoints):
    if not waypoints:
        return None, None

    min_idx = 0
    min_dist2 = float('inf')

    for i, wp in enumerate(waypoints): 
        wx = float(wp.get("x", 0.0))
        wy = float(wp.get("y", 0.0))
        wz = float(wp.get("z", 0.0))

        dx = wx - player_x
        dz = wz - player_z
        d2 = dx * dx + dz * dz

        if d2 < min_dist2:
            min_dist2 = d2
            min_idx = i

    # min_idx + 1 사용 (앞을 향하게)
    target_idx = min_idx + 1 if min_idx + 1 < len(waypoints) else min_idx

    return waypoints[target_idx], target_idx


# ------------------------------------------------------------
# mid_light_complete 기반 path_tracking
# ------------------------------------------------------------
def path_tracking(player_x, player_y, player_z, body_yaw_deg, waypoints):

    WS_command, WS_weight = "", 0.0
    AD_command, AD_weight = "", 0.0

    if not waypoints:
        return "S", 1.0, "", 0.0, None

    target_wp, idx = select_target_waypoint(player_x, player_y, player_z, waypoints)

    print('@@@@@ 타겟_wp ',target_wp)

    if target_wp is None:
        return "S", 1.0, "", 0.0, None

    target_x = float(target_wp.get("x", 0.0))
    target_z = float(target_wp.get("z", 0.0))
    print(f'@@@@@@타겟 좌표 : ({target_x}, {target_z})')

    # -------- mid_light 원본 로직 --------
    dx = target_x - player_x
    dz = target_z - player_z

    # atan2(dx, dz)는 mid_light 원본 그대로 유지
    target_angle = math.degrees(math.atan2(dx, dz)) % 360.0

    angle_diff = (target_angle - body_yaw_deg + 540.0) % 360.0 - 180.0
    abs_angle_diff = abs(angle_diff)

    # 각도 기반 속도 조절
    angle_norm = min(abs_angle_diff / 90.0, 1.0)
    forward_weight = 0.6 * (1.0 - angle_norm)

    max_forward_weight = 65.0 / 65.0
    forward_weight = min(forward_weight, max_forward_weight)

    # 회전 명령
    if abs_angle_diff > 10.0:
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command, AD_weight = "D", turn_weight
        else:
            AD_command, AD_weight = "A", turn_weight
    else:
        AD_command, AD_weight = "", 0.0

    # 전진 명령
    if forward_weight > 0.05:
        WS_command, WS_weight = "W", forward_weight
    else:
        WS_command, WS_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight, target_wp

# ------------------------------------------------------------
# Flask 엔드포인트 (/get_adcs)
# ------------------------------------------------------------
@app.route('/get_adcs', methods=['POST'])
def get_adcs():

    data = request.get_json(force=True)
    print("ADCS /get_adcs request_data:", data)

    # ------- 입력 파싱 -------
    ally_pos = data.get("ally_body_pos", {})
    ally_angle = data.get("ally_body_angle", {})
    waypoints = data.get("waypoints", [])

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    # yaw 축은 IBSM2가 준 y축 그대로 사용
    body_yaw_deg = float(ally_angle.get("y", 0.0))

    # ------- 제어 연산 -------
    WS_command, WS_weight, AD_command, AD_weight, head_wp = path_tracking(
        player_x, player_y, player_z, body_yaw_deg, waypoints
    )

    # ------- dict 기반 Head_waypoint -------
    if head_wp is not None:
        head_waypoint_dict = {
            "x": float(head_wp.get("x", 0.0)),
            "y": float(head_wp.get("y", 0.0)),
            "z": float(head_wp.get("z", 0.0))
        }
    else:
        head_waypoint_dict = {
            "x": float(player_x),
            "y": float(player_y),
            "z": float(player_z)
        }

    # ------- 응답 -------
    response = {
        "WS_command": WS_command,
        "WS_weight": float(WS_weight),
        "AD_command": AD_command,
        "AD_weight": float(AD_weight),
        "Head_waypoint": head_waypoint_dict
    }

    # print(f"전진 가속력 커맨드 : {response['WS_command']}")
    return jsonify(response)


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
