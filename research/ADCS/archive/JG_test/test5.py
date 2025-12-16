# adcs_service.py  (modified)
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

# ---- Tunable parameters ----
TURN_DEADBAND = 3.0       # degrees (was 8.0) -> be more sensitive to heading error
AD_SCALE_DIVISOR = 60.0   # divide abs angle diff by this to get AD_weight (smaller => stronger)
MAX_FORWARD_WEIGHT = 0.6  # max forward weight scale
MIN_FORWARD_ENABLE = 0.05 # forward deadband
SLOW_NEAR_DIST = 2.0      # if closer than this, reduce forward speed
FLIP_AD_SIDE = False      # if True, flips AD left/right command mapping

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

def parse_waypoint(entry):
    """
    Accept several waypoint formats and return tuple (x,y,z) if possible.
    - list/tuple: [x,y,z] or [x,y]
    - dict: {'x':..., 'y':..., 'z':...}
    - if invalid -> None
    """
    if isinstance(entry, (list, tuple)):
        if len(entry) >= 2:
            try:
                x = float(entry[0])
                y = float(entry[1])
                z = float(entry[2]) if len(entry) > 2 else 0.0
                return (x, y, z)
            except Exception:
                return None
        else:
            return None
    elif isinstance(entry, dict):
        x = read_coord(entry, 'x', 'X')
        y = read_coord(entry, 'y', 'Y')
        z = read_coord(entry, 'z', 'Z')
        return (x, y, z)
    else:
        return None

@app.route('/get_adcs', methods=['POST'])
def get_adcs():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    # --- read inputs (be lenient with key names) ---
    time_val = data.get('time', data.get('Time', 0.0))

    ally_pos = data.get('ally_body_pos') or data.get('ally') or {}
    ally_angle = data.get('ally_body_angle') or data.get('ally_body_angle'.lower()) or {}
    ally_speed = data.get('ally_speed') if 'ally_speed' in data else data.get('allySpeed', 0.0)

    waypoints = data.get('waypoints') or data.get('waypoints_list') or data.get('Waypoints_list') or []

    # read coordinates (allow 'x' or 'X', 'y'/'Y', 'z'/'Z')
    ax = read_coord(ally_pos, 'x', 'X')
    ay = read_coord(ally_pos, 'y', 'Y')
    az = read_coord(ally_pos, 'z', 'Z')

    # assume ally_body_angle.x is yaw in degrees (0 = +X). If your system uses different convention,
    # set FLIP_AD_SIDE or adjust outside.
    body_yaw = read_coord(ally_angle, 'x', 'X')  # degrees

    # debug print
    print("ADCS: time=", time_val, "ally_pos=(x,y,z)=", (ax, ay, az), "body_yaw(deg)=", body_yaw, "speed=", ally_speed)
    print("ADCS: received raw waypoints count=", len(waypoints))

    # default response values
    WS_command = ""   # "W" forward, "S" backward, "" stop
    WS_weight = 0.0
    AD_command = ""   # "D" right, "A" left, "" none
    AD_weight = 0.0
    Head_waypoint = [0.0, 0.0, 0.0]

    # pick head waypoint: robustly parse first valid waypoint
    head_wp = None
    if isinstance(waypoints, list) and len(waypoints) > 0:
        for first in waypoints:
            parsed = parse_waypoint(first)
            if parsed is not None:
                head_wp = parsed
                break

    if head_wp is None:
        # No valid waypoint -> return default (stop)
        print("ADCS: no valid head waypoint -> returning stop")
        resp = {
            "WS_command": WS_command,
            "WS_weight": WS_weight,
            "AD_command": AD_command,
            "AD_weight": AD_weight,
            "Head_waypoint": Head_waypoint
        }
        return jsonify(resp)

    hx, hy, hz = head_wp
    Head_waypoint = [float(hx), float(hy), float(hz)]

    # --- compute control on XY plane (treat world plane as X,Y) ---
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
        # target angle: use atan2(dy, dx) so that 0 deg = +X, 90 deg = +Y
        target_angle = math.degrees(math.atan2(dy, dx)) % 360.0
        angle_diff = normalize_angle_deg(target_angle - body_yaw)
        abs_diff = abs(angle_diff)

        # debug before decision
        print("DBG: head_wp=(hx,hy,hz)=", hx, hy, hz)
        print("DBG: computed: dx,dy,dist=", round(dx,3), round(dy,3), round(dist,3))
        print("DBG: target_angle, body_yaw, angle_diff=", round(target_angle,3), round(body_yaw,3), round(angle_diff,3))

        # AD (turn) decision
        if abs_diff > TURN_DEADBAND:
            AD_weight = min(abs_diff / AD_SCALE_DIVISOR, 1.0)  # scale to 0..1
            # sign: positive angle_diff => rotate positive (right) assuming body yaw increases CCW; if mapping differs, flip
            if FLIP_AD_SIDE:
                AD_command = "D" if angle_diff < 0 else "A"
            else:
                AD_command = "D" if angle_diff > 0 else "A"
        else:
            AD_command = ""
            AD_weight = 0.0

        # WS (forward) decision
        # forward_weight decreases as heading error increases
        forward_weight = max(0.0, (1.0 - (abs_diff / 180.0))) * MAX_FORWARD_WEIGHT
        # slow near waypoint
        if dist < SLOW_NEAR_DIST:
            forward_weight = min(forward_weight, 0.25)
        if forward_weight > MIN_FORWARD_ENABLE:
            WS_command = "W"
            WS_weight = round(float(forward_weight), 3)
        else:
            WS_command = ""
            WS_weight = 0.0

    # debug prints: final decisions
    print(f"ADCS: head_wp=({hx:.2f},{hy:.2f}), dist={dist:.2f}, target_angle={target_angle:.2f}, body_yaw={body_yaw:.2f}, angle_diff={angle_diff:.2f}")
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
