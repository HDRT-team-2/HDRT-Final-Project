# adcs_service.py
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

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

    ally_pos = data.get('ally_body_pos') or data.get('ally_body_pos'.lower()) or {}
    ally_angle = data.get('ally_body_angle') or data.get('ally_body_angle'.lower()) or {}
    ally_speed = data.get('ally_speed') if 'ally_speed' in data else data.get('allySpeed', 0.0)

    waypoints = data.get('waypoints') or data.get('waypoints_list') or data.get('Waypoints_list') or []

    ax = read_coord(ally_pos, 'x', 'X')
    ay = read_coord(ally_pos, 'y', 'Y')
    az = read_coord(ally_pos, 'z', 'Z')

    # assume ally_body_angle.x is yaw in degrees
    body_yaw = read_coord(ally_angle, 'x', 'X')  # degrees

    print("ADCS: time=", time_val, "ally_pos=", (ax, ay, az), "body_yaw(deg)=", body_yaw, "speed=", ally_speed)
    print("ADCS: received waypoints (count)=", len(waypoints))

    WS_command = ""
    WS_weight = 0.0
    AD_command = ""
    AD_weight = 0.0
    Head_waypoint = [0.0, 0.0, 0.0]

    # --- Robust selection of head waypoint: skip waypoints that are effectively at current pos ---
    head_wp = None
    MIN_DIST_FOR_TARGET = 1.0  # cells: require waypoint to be this far to be meaningful
    if isinstance(waypoints, list) and len(waypoints) > 0:
        # iterate and pick first waypoint sufficiently far from current pos
        for entry in waypoints:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    hx = float(entry[0])
                    hz = float(entry[1])  # TPP returns [X, Z, altitude]
                    halt = float(entry[2]) if len(entry) > 2 else 0.0
                except Exception:
                    continue
                dist = math.hypot(hx - ax, hz - az)
                if dist >= MIN_DIST_FOR_TARGET:
                    head_wp = (hx, hz, halt)
                    break
                else:
                    # skip near-equal waypoint (likely start)
                    continue
            elif isinstance(entry, dict):
                hx = read_coord(entry, 'x', 'X')
                hy = read_coord(entry, 'y', 'Y')
                hz = read_coord(entry, 'z', 'Z')
                dist = math.hypot(hx - ax, hz - az)
                if dist >= MIN_DIST_FOR_TARGET:
                    head_wp = (hx, hz, hy)
                    break
                else:
                    continue

    # If no valid head waypoint found, fallback to last waypoint if present
    if head_wp is None and isinstance(waypoints, list) and len(waypoints) > 0:
        last = waypoints[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            try:
                hx = float(last[0]); hz = float(last[1]); halt = float(last[2]) if len(last) > 2 else 0.0
                head_wp = (hx, hz, halt)
            except Exception:
                head_wp = None
        elif isinstance(last, dict):
            hx = read_coord(last, 'x', 'X'); hy = read_coord(last, 'y', 'Y'); hz = read_coord(last, 'z', 'Z')
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

    hx, hz, _hz_extra = head_wp
    Head_waypoint = [float(hx), float(hz), float(_hz_extra)]

    dx = hx - ax
    dz = hz - az
    dist = math.hypot(dx, dz)

    if dist < 1e-3:
        WS_command = ""
        WS_weight = 0.0
        AD_command = ""
        AD_weight = 0.0
        print("ADCS: close to head waypoint (dist ~ 0) -> stop")
    else:
        target_angle = math.degrees(math.atan2(dx, dz)) % 360.0
        angle_diff = normalize_angle_deg(target_angle - body_yaw)
        abs_diff = abs(angle_diff)

        turn_deadband = 8.0
        if abs_diff > turn_deadband:
            AD_weight = min(abs_diff / 90.0, 1.0)
            AD_command = "D" if angle_diff > 0 else "A"
        else:
            AD_command = ""
            AD_weight = 0.0

        max_forward_weight = 0.6
        forward_weight = max(0.0, (1.0 - (abs_diff / 180.0))) * max_forward_weight
        if dist < 2.0:
            forward_weight = min(forward_weight, 0.25)
        if forward_weight > 0.05:
            WS_command = "W"
            WS_weight = round(float(forward_weight), 3)
        else:
            WS_command = ""
            WS_weight = 0.0

    print(f"ADCS: head_wp=({hx:.2f},{hz:.2f}), dist={dist:.2f}, target_angle={target_angle:.2f}, body_yaw={body_yaw:.2f}, angle_diff={angle_diff:.2f}")
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
