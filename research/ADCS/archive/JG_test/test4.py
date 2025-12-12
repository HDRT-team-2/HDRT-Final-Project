# adcs_service.py
from flask import Flask, request, jsonify
import math
import traceback

app = Flask(__name__)

def read_coord(obj, *keys, default=0.0):
    """utility: try several key names in obj (e.g. 'x' or 'X')"""
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
    """normalize to [-180, 180]"""
    a = (a + 180.0) % 360.0 - 180.0
    return a

def to_float_safe(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON received"}), 400

        # --- read inputs (be lenient with key names) ---
        time_val = data.get('time', data.get('Time', 0.0))

        ally_pos = data.get('ally_body_pos') or data.get('ally') or {}
        ally_angle = data.get('ally_body_angle') or data.get('ally_body_angle'.lower()) or {}
        # ally_speed: accept ally_speed or allySpeed
        ally_speed = data.get('ally_speed') if 'ally_speed' in data else data.get('allySpeed', 0.0)

        # waypoints: accept several possible names/formats
        waypoints = data.get('waypoints') or data.get('waypoints_list') or data.get('Waypoints_list') or data.get('waypoint') or []

        # read coordinates (allow 'x' or 'X', 'y'/'Y', 'z'/'Z')
        ax = read_coord(ally_pos, 'x', 'X')
        ay = read_coord(ally_pos, 'y', 'Y')
        az = read_coord(ally_pos, 'z', 'Z')

        # assume ally_body_angle.x is yaw in degrees
        body_yaw = read_coord(ally_angle, 'x', 'X')  # degrees

        # debug print
        print("ADCS: time=", time_val, "ally_pos=", (ax, ay, az), "body_yaw(deg)=", body_yaw, "speed=", ally_speed)
        print("ADCS: raw waypoints (type/count)=", type(waypoints), (len(waypoints) if isinstance(waypoints, (list,tuple)) else 'N/A'))

        # default response values
        WS_command = ""   # "W" forward, "S" backward, "" stop
        WS_weight = 0.0
        AD_command = ""   # "D" right, "A" left, "" none
        AD_weight = 0.0
        Head_waypoint = [0.0, 0.0, 0.0]

        # Normalize single waypoint (some send a single [x,y,z] not nested)
        norm_waypoints = []
        if isinstance(waypoints, (list, tuple)) and waypoints and not isinstance(waypoints[0], (list, tuple, dict)):
            # It's likely a single waypoint list e.g. [x,y,z]
            # Wrap it so first element becomes that list
            norm_waypoints = [waypoints]
        elif isinstance(waypoints, (list, tuple)):
            norm_waypoints = list(waypoints)
        else:
            # maybe it's a single dict
            if isinstance(waypoints, dict):
                norm_waypoints = [waypoints]
            else:
                norm_waypoints = []

        # pick head waypoint: first in list if present
        head_wp = None
        if len(norm_waypoints) > 0:
            first = norm_waypoints[0]

            # 1) list / tuple 형식: 일반적으로 TPP는 [x, y, z]
            if isinstance(first, (list, tuple)):
                if len(first) >= 3:
                    hx = to_float_safe(first[0])
                    hy = to_float_safe(first[1])
                    hz = to_float_safe(first[2])
                    head_wp = (hx, hy, hz)
                elif len(first) == 2:
                    hx = to_float_safe(first[0])
                    hy = to_float_safe(first[1])
                    head_wp = (hx, hy, 0.0)
                else:
                    # unexpected short list
                    head_wp = None

            # 2) dict 형식: {'x':..,'y':..,'z':..}
            elif isinstance(first, dict):
                hx = read_coord(first, 'x', 'X')
                hy = read_coord(first, 'y', 'Y')
                hz = read_coord(first, 'z', 'Z')
                head_wp = (hx, hy, hz)

            else:
                head_wp = None

        # if no head waypoint, return default (stop)
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

        # Unpack: ADCS uses planar coordinates as X (hx) and Y (hy)
        hx, hy, hz = head_wp
        Head_waypoint = [float(hx), float(hy), float(hz)]

        # --- compute control on XY plane (use ay as Y) ---
        dx = hx - ax
        dy = hy - ay
        dist = math.hypot(dx, dy)

        # if distance very small -> stop
        if dist < 1e-3:
            WS_command = ""
            WS_weight = 0.0
            AD_command = ""
            AD_weight = 0.0
            print("ADCS: close to head waypoint (dist ~ 0) -> stop")
        else:
            # target angle: use atan2(dx, dy) so that 0 deg means facing +Y (consistent)
            # Explanation: atan2(dx, dy) returns angle relative to +Y axis (north) with +X to the right.
            target_angle = math.degrees(math.atan2(dx, dy)) % 360.0
            # body_yaw expected in degrees; normalize difference to [-180,180]
            angle_diff = normalize_angle_deg(target_angle - body_yaw)
            abs_diff = abs(angle_diff)

            # AD (turn) decision
            # threshold for "no-turn" zone
            turn_deadband = 8.0  # degrees
            if abs_diff > turn_deadband:
                # turn strength proportional to angle difference (clamped)
                AD_weight = min(abs_diff / 90.0, 1.0)  # 0..1
                AD_command = "D" if angle_diff > 0 else "A"
            else:
                AD_command = ""
                AD_weight = 0.0

            # WS (forward) decision
            # forward_weight decreases as heading error increases
            # base max forward weight (tuned): e.g. map to 0..0.6
            max_forward_weight = 0.6
            forward_weight = max(0.0, (1.0 - (abs_diff / 180.0))) * max_forward_weight
            # if very close, slow down
            if dist < 2.0:
                forward_weight = min(forward_weight, 0.25)  # slow near waypoint
            # minor deadband
            if forward_weight > 0.05:
                WS_command = "W"
                WS_weight = round(float(forward_weight), 3)
            else:
                WS_command = ""
                WS_weight = 0.0

        # debug prints
        print(f"ADCS: head_wp=({hx:.2f},{hy:.2f},{hz:.2f}), dist={dist:.2f}, target_angle={target_angle:.2f}, body_yaw={body_yaw:.2f}, angle_diff={angle_diff:.2f}")
        print(f"ADCS: -> WS=({WS_command},{WS_weight}), AD=({AD_command},{AD_weight})")

        resp = {
            "WS_command": WS_command,
            "WS_weight": WS_weight,
            "AD_command": AD_command,
            "AD_weight": AD_weight,
            "Head_waypoint": Head_waypoint
        }
        return jsonify(resp)

    except Exception as e:
        # Return a safe default and log traceback
        print("ADCS exception:", e)
        traceback.print_exc()
        resp = {
            "WS_command": "",
            "WS_weight": 0.0,
            "AD_command": "",
            "AD_weight": 0.0,
            "Head_waypoint": [0.0, 0.0, 0.0],
            "error": str(e)
        }
        return jsonify(resp), 500

if __name__ == '__main__':
    # run on port 5000 by default; change if needed to avoid conflicts
    app.run(host='0.0.0.0', port=5000, debug=True)
