# adcs.py  -------------------------------------------------------------
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ------------------ mid_light 기반 path tracking -------------------

def select_target_waypoint(player_x, player_y, player_z, waypoints):
    """
    waypoints: [ {"x":..,"y":..,"z":..}, ... ]
    플레이어와 가장 가까운 waypoint를 찾고,
    그 다음 인덱스(있으면)를 Head waypoint로 사용.
    """
    if not waypoints:
        return None

    # 가장 가까운 waypoint 인덱스 찾기
    min_idx = 0
    min_dist2 = float('inf')
    for i, wp in enumerate(waypoints):
        wx = float(wp.get("x", 0.0))
        wz = float(wp.get("z", 0.0))
        dx = wx - player_x
        dz = wz - player_z
        d2 = dx*dx + dz*dz
        if d2 < min_dist2:
            min_dist2 = d2
            min_idx = i

    # 한 칸 앞을 보도록: min_idx+1 사용, 없으면 min_idx
    target_idx = min_idx + 1 if min_idx + 1 < len(waypoints) else min_idx
    return waypoints[target_idx], target_idx

def path_tracking_mid_light(player_x, player_y, player_z, body_yaw_deg, waypoints):
    """
    mid_light_complete.py 의 path_tracking 수식(각도/weight 계산) 그대로 사용.
    차이점: waypoints를 외부에서 dict 리스트로 받아서 사용.
    """

    WS_command, WS_weight = "", 0.0
    AD_command, AD_weight = "", 0.0

    if not waypoints:
        # 경로 없으면 정지
        return "S", 1.0, "", 0.0, None

    target_wp, idx = select_target_waypoint(player_x, player_y, player_z, waypoints)
    target_x = float(target_wp.get("x", 0.0))
    target_z = float(target_wp.get("z", 0.0))

    # ----- mid_light 원본 로직: 각도/weight 계산 -----
    dx = target_x - player_x
    dz = target_z - player_z

    # 목표 각도 (deg)
    target_angle = math.degrees(math.atan2(dx, dz)) % 360.0

    # 현재 차체 yaw
    angle_diff = (target_angle - body_yaw_deg + 540.0) % 360.0 - 180.0
    abs_angle_diff = abs(angle_diff)

    # 각도 차이 기반 속도 조절
    angle_norm = min(abs_angle_diff / 90.0, 1.0)  # 0~1
    forward_weight = 0.6 * (1.0 - angle_norm)    # 0.0 ~ 0.6

    # 최대 전진 속도 제한 (40km/h → weight ≈ 40/65)
    max_forward_weight = 40.0 / 65.0
    forward_weight = min(forward_weight, max_forward_weight)

    # 회전 명령 (AD)
    if abs_angle_diff > 10.0:
        turn_weight = min(abs_angle_diff / 60.0, 1.0)
        if angle_diff > 0:
            AD_command, AD_weight = "D", turn_weight
        else:
            AD_command, AD_weight = "A", turn_weight
    else:
        AD_command, AD_weight = "", 0.0

    # 전진 명령 (WS)
    if forward_weight > 0.05:
        WS_command, WS_weight = "W", forward_weight
    else:
        WS_command, WS_weight = "", 0.0

    return WS_command, WS_weight, AD_command, AD_weight, target_wp


# ------------------ Flask 엔드포인트 -------------------

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    """
    IBSM2.send_adcs 에서 보내는 포맷을 그대로 받는다.
    입력:
      {
        "time": float,
        "ally_body_pos": {"x":..,"y":..,"z":..},
        "ally_body_angle": {"x":..,"y":..,"z":..},
        "ally_speed": float,
        "waypoints": [ {"x":..,"y":..,"z":..}, ... ]
      }
    출력:
      {
        "WS_command": "...",
        "WS_weight": float,
        "AD_command": "...",
        "AD_weight": float,
        "Head_waypoint": [x, y, z]
      }
    """
    data = request.get_json(force=True)
    print("ADCS /get_adcs request_data:", data)

    ally_pos = data.get("ally_body_pos", {"x":0.0, "y":0.0, "z":0.0})
    ally_angle = data.get("ally_body_angle", {"x":0.0, "y":0.0, "z":0.0})
    waypoints = data.get("waypoints", [])

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    body_yaw_deg = float(ally_angle.get("x", 0.0))  # 기존 mid_light는 body_x(yaw)를 사용

    WS_command, WS_weight, AD_command, AD_weight, head_wp = path_tracking_mid_light(
        player_x, player_y, player_z, body_yaw_deg, waypoints
    )

    if head_wp is not None:
        head_waypoint_list = [
            float(head_wp.get("x", 0.0)),
            float(head_wp.get("y", 0.0)),
            float(head_wp.get("z", 0.0))
        ]
    else:
        head_waypoint_list = [player_x, player_y, player_z]

    response = {
        "WS_command": WS_command,
        "WS_weight": float(WS_weight),
        "AD_command": AD_command,
        "AD_weight": float(AD_weight),
        "Head_waypoint": head_waypoint_list
    }
    print("ADCS /get_adcs response:", response)
    return jsonify(response)

if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000)
