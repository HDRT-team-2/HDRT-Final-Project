# ADCS main.py (modified)
from flask import Flask, request, jsonify
import math
import time

app = Flask(__name__)

# ------- Parameters / Tunables -------
DIST_ARRIVAL = 8.0               # 도착(soft) 거리 기준 (meters / cells)
MIN_FORWARD_WHEN_TURNING = 0.12  # 회전중에도 최소 전진 유지 (0~1)
MAX_FORWARD_WEIGHT = 40.0 / 65.0 # 기존 코드에서 사용하던 max forward scale
MAX_AD_WEIGHT = 0.95             # 회전 명령 상한
TURN_ANGLE_THRESHOLD = 10.0      # 이 각도 이하이면 회전 입력 제거 (deg)
# -------------------------------------

def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)

def read_coord(obj, *keys, default=0.0):
    if not obj:
        return float(default)
    for k in keys:
        if k in obj:
            try:
                return float(obj[k])
            except Exception:
                return float(default)
    return float(default)

def normalize_angle_deg(angle):
    """Normalize to -180..180"""
    a = (angle + 180.0) % 360.0 - 180.0
    return a

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    """
    Expected request JSON (from IBSM / info):
    {
      "time": <float>,
      "ally_body_pos": {"x":..., "y":..., "z":...}  # use x,z for ground plane
      "ally_body_angle": {"x": yaw_deg, "y":..., "z":...}  # yaw stored in x per IBSM
      "ally_speed": <float>,
      "waypoints": [[x,y,z], ...]  # IB S M sends list (we treat index0 = head waypoint)
    }
    Response:
    {
      "WS_command": "W"/"S"/"STOP"/"",
      "WS_weight": float,
      "AD_command": "A"/"D"/"",
      "AD_weight": float,
      "Head_waypoint": [x,y,z] or None
    }
    """
    req = request.get_json(force=True)
    if not req:
        return jsonify({"error":"empty request"}), 400

    t = safe_float(req.get('time', 0.0))
    # read ally pos (IBSM uses x,z plane; they sometimes use lowercase keys)
    # ally_body_pos may be {"x":..., "y":..., "z":...} where y is altitude
    ally_pos = req.get('ally_body_pos') or req.get('ally_body_position') or {}
    ally_x = read_coord(ally_pos, 'x', 'X', default=0.0)
    ally_y = read_coord(ally_pos, 'y', 'Y', default=0.0)
    ally_z = read_coord(ally_pos, 'z', 'Z', default=0.0)

    # body yaw (IBSM stores yaw in body angle X field in some code)
    body_angle = req.get('ally_body_angle') or {}
    body_yaw = read_coord(body_angle, 'x', 'X', default=0.0)

    ally_speed = safe_float(req.get('ally_speed', 0.0))

    # waypoints: expect list-of-lists e.g. [[x,y,z],...]
    wps = req.get('waypoints') or req.get('waypoints_list') or []
    if not isinstance(wps, list):
        wps = []

    wp_count = len(wps)
    print(f"ADCS: time={t} ally_pos=({ally_x:.6f},{ally_z:.6f}) body_yaw={body_yaw:.3f} received waypoints (count)= {wp_count}")

    # default response (stop)
    ws_cmd, ws_w = "STOP", 0.0
    ad_cmd, ad_w = "", 0.0
    head_waypoint_out = None

    if wp_count == 0:
        # no waypoints: keep stop
        print("ADCS: no waypoints -> STOP")
    else:
        # take head waypoint (first element). IBSM convention: [x,y,z] -> use x & y as x & z
        head = wps[0]
        # defensive: ensure length >=2
        try:
            hx = float(head[0])
            hz = float(head[1])
            hz_z = float(head[2]) if len(head) > 2 else 0.0
        except Exception as e:
            hx = safe_float(head[0] if len(head)>0 else 0.0)
            hz = safe_float(head[1] if len(head)>1 else 0.0)
            hz_z = safe_float(head[2] if len(head)>2 else 0.0)

        head_waypoint_out = [hx, hz, hz_z]

        # compute planar distance in XZ
        dx = hx - ally_x
        dz = hz - ally_z
        dist = math.hypot(dx, dz)

        # arrival (soft)
        if dist <= DIST_ARRIVAL:
            # reached -> stop (optionally could pop but IB S M controls pop)
            ws_cmd, ws_w = "STOP", 0.0
            ad_cmd, ad_w = "", 0.0
            print(f"ADCS: close to head waypoint (dist={dist:.2f}) -> STOP (arrival threshold {DIST_ARRIVAL})")
        else:
            # compute target_angle on XZ plane: atan2(dx, dz) matches other code (x offset, z offset)
            target_angle = math.degrees(math.atan2(dx, dz)) % 360.0
            # normalize angle diff to -180..180
            angle_diff = normalize_angle_deg(target_angle - body_yaw)
            abs_angle_diff = abs(angle_diff)

            # AD (turn) calculation
            if abs_angle_diff > TURN_ANGLE_THRESHOLD:
                turn_weight = min(abs_angle_diff / 60.0, 1.0)
                # clamp max
                turn_weight = min(turn_weight, MAX_AD_WEIGHT)
                ad_cmd = "D" if angle_diff > 0 else "A"
                ad_w = turn_weight
            else:
                ad_cmd, ad_w = "", 0.0

            # WS (forward) calculation: reduce when angle is large, but keep a small forward if desired
            angle_norm = min(abs_angle_diff / 90.0, 1.0)
            forward_weight = 0.6 * (1.0 - angle_norm)  # base mapping
            forward_weight = min(forward_weight, MAX_FORWARD_WEIGHT)

            # Ensure minimal forward if angle not extreme OR allow small forward while turning
            if forward_weight > 0:
                # if turning strongly, allow a small minimum forward movement (so it doesn't lock)
                if abs_angle_diff > 45.0:
                    forward_weight = max(forward_weight, MIN_FORWARD_WHEN_TURNING)
                # small threshold to avoid tiny jitter
                if forward_weight > 0.05:
                    ws_cmd, ws_w = "W", round(forward_weight, 3)
                else:
                    ws_cmd, ws_w = "STOP", 0.0
            else:
                ws_cmd, ws_w = "STOP", 0.0

            # DEBUG print
            print(f"ADCS: head_wp=({hx:.2f},{hz:.2f}), dist={dist:.2f}, target_angle={target_angle:.2f}, body_yaw={body_yaw:.2f}, angle_diff={angle_diff:.2f}")
            print(f"ADCS: => WS={ws_cmd}({ws_w:.3f}), AD={ad_cmd}({ad_w:.3f}), Head_waypoint={head_waypoint_out}")

    resp = {
        "WS_command": ws_cmd,
        "WS_weight": ws_w,
        "AD_command": ad_cmd,
        "AD_weight": ad_w,
        "Head_waypoint": head_waypoint_out
    }
    return jsonify(resp), 200

if __name__ == '__main__':
    # dev server
    app.run(host='0.0.0.0', port=5000, debug=True)
