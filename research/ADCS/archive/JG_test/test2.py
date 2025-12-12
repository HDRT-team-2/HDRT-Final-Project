# adcs.py
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# arrival threshold (cells / units) — 변경 원하면 값 바꿔주세요
ARRIVAL_THRESH = 1.0

def read_coord(obj, *keys, default=0.0):
    if not isinstance(obj, dict):
        return float(default)
    for k in keys:
        if k in obj:
            try:
                return float(obj[k])
            except Exception:
                return float(default)
    return float(default)

def normalize_angle_deg(a):
    a = (a + 180.0) % 360.0 - 180.0
    return a

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    time_val = data.get('time', data.get('Time', 0.0))

    ally_pos = data.get('ally_body_pos') or data.get('ally') or {}
    ally_angle = data.get('ally_body_angle') or data.get('ally_body_angle'.lower()) or {}
    ally_speed = data.get('ally_speed') if 'ally_speed' in data else data.get('allySpeed', 0.0)

    # waypoints: accept various names and formats
    waypoints = data.get('waypoints') or data.get('waypoints_list') or data.get('Waypoints_list') or []

    ax = read_coord(ally_pos, 'x', 'X')
    ay = read_coord(ally_pos, 'y', 'Y')
    az = read_coord(ally_pos, 'z', 'Z')

    # ally_body_angle.x treated as yaw degrees
    body_yaw = read_coord(ally_angle, 'x', 'X')

    print("ADCS: time=", time_val, "ally_pos=", (ax, ay, az), "body_yaw(deg)=", body_yaw, "speed=", ally_speed)
    print("ADCS: received waypoints (count)=", len(waypoints))

    # defaults
    WS_command = ""
    WS_weight = 0.0
    AD_command = ""
    AD_weight = 0.0
    Head_waypoint = [0.0, 0.0, 0.0]

    # pick head waypoint (first valid)
    head_wp = None
    if isinstance(waypoints, list) and len(waypoints) > 0:
        first = waypoints[0]
        if isinstance(first, (list, tuple)):
            # Expectation: TPP returns [x, z, altitude]
            try:
                hx = float(first[0])
                hz = float(first[1]) if len(first) > 1 else 0.0
                extra = float(first[2]) if len(first) > 2 else 0.0
                head_wp = (hx, hz, extra)
            except Exception:
                head_wp = None
        elif isinstance(first, dict):
            # if dict, try keys; map to (x,z,alt)
            hx = read_coord(first, 'x', 'X')
            hy = read_coord(first, 'y', 'Y')
            hz = read_coord(first, 'z', 'Z')
            # assume dict might be x,y,z where y is altitude — choose conservative mapping:
            head_wp = (hx, hz, hy)

    if head_wp is None:
        print("ADCS: no valid head waypoint -> returning stop")
        resp = {
            "WS_command": WS_command,
            "WS_weight": WS_weight,
            "AD_command": AD_command,
            "AD_weight": AD_weight,
            "Head_waypoint": Head_waypoint
        }
        return jsonify(resp)

    hx, hz, extra = head_wp
    Head_waypoint = [float(hx), float(hz), float(extra)]

    # compute vector on XZ plane
    dx = hx - ax
    dz = hz - az
    dist = math.hypot(dx, dz)

    # initialize locals for safe logging later
    target_angle = None
    angle_diff = None

    if dist <= ARRIVAL_THRESH:
        # arrived / close -> stop
        WS_command = ""
        WS_weight = 0.0
        AD_command = ""
        AD_weight = 0.0
        print(f"ADCS: close to head waypoint (dist={dist:.3f} <= {ARRIVAL_THRESH}) -> stop")
    else:
        # target angle: use atan2(dx, dz) so that 0 deg = +Z direction (consistent with project)
        target_angle = math.degrees(math.atan2(dx, dz)) % 360.0
        angle_diff = normalize_angle_deg(target_angle - body_yaw)
        abs_diff = abs(angle_diff)

        # AD (turn) decision
        turn_deadband = 8.0  # degrees tolerance
        if abs_diff > turn_deadband:
            AD_weight = min(abs_diff / 90.0, 1.0)
            AD_command = "D" if angle_diff > 0 else "A"
        else:
            AD_command = ""
            AD_weight = 0.0

        # WS (forward) decision
        max_forward_weight = 0.6
        forward_weight = max(0.0, (1.0 - (abs_diff / 180.0))) * max_forward_weight
        # slow down when near
        if dist < 2.0:
            forward_weight = min(forward_weight, 0.25)
        if forward_weight > 0.05:
            WS_command = "W"
            WS_weight = round(float(forward_weight), 3)
        else:
            WS_command = ""
            WS_weight = 0.0

    # safe logging: if target_angle/angle_diff None, print N/A
    ta_str = f"{target_angle:.2f}" if target_angle is not None else "N/A"
    adiff_str = f"{angle_diff:.2f}" if angle_diff is not None else "N/A"

    print(f"ADCS: head_wp=({hx:.2f},{hz:.2f}), dist={dist:.2f}, target_angle={ta_str}, body_yaw={body_yaw:.2f}, angle_diff={adiff_str}")
    print(f"ADCS: -> WS=({WS_command},{WS_weight}), AD=({AD_command},{AD_weight})")

    resp = {
        "WS_command": WS_command,
        "WS_weight": WS_weight,
        "AD_command": AD_command,
        "AD_weight": AD_weight,
        "Head_waypoint": Head_waypoint
    }
    return jsonify(resp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
