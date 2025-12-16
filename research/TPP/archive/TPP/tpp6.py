# main.py  — 최종 (TPP 보정 + waypoints_list 보장 + 옵션 설정)
from flask import Flask, request, jsonify
import copy
import math
import os
import logging
import traceback

app = Flask(__name__)

# ---------- 설정 ----------
# 환경변수로 y_delta 조정 가능 (기본 4.0)
try:
    Y_DELTA = float(os.environ.get("Y_DELTA", "4.0"))
except Exception:
    Y_DELTA = 4.0

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tpp")

# -----------------------
# 포인트 정규화/복원 유틸
# -----------------------
def normalize_point(px):
    """
    Accepts px: dict {'x','y','z'} or list/tuple [x,y,z]
    Returns: (kind, x, y, z) where kind in {'dict','list'} or (None,None,None,None) on failure
    """
    if px is None:
        return None, None, None, None
    if isinstance(px, dict):
        try:
            x = float(px.get("x", px.get(0)))
            y = float(px.get("y", px.get(1)))
            z = float(px.get("z", px.get(2)))
            return "dict", x, y, z
        except Exception:
            return "dict", None, None, None
    # list/tuple-like
    try:
        x = float(px[0])
        y = float(px[1])
        z = float(px[2])
        return "list", x, y, z
    except Exception:
        return "list", None, None, None

def restore_point(kind, x, y, z, orig_px):
    """
    Restore same structure as input (dict or list)
    """
    if kind == "dict":
        if isinstance(orig_px, dict):
            out = dict(orig_px)
            out["x"] = x
            out["y"] = y
            out["z"] = z
            return out
        else:
            return {"x": x, "y": y, "z": z}
    else:
        return [x, y, z]

# -----------------------
# 보정 로직
# -----------------------
def fix_point_with_ally(px, ally_y, y_delta=Y_DELTA):
    """
    px: dict or list/tuple representing point. ally_y float.
    If y is far from ally_y but z is closer, swap y<->z.
    Returns: (fixed_point_same_type, swapped_flag, reason)
    """
    kind, x, y, z = normalize_point(px)
    if kind is None:
        return px, False, "none_point"
    if x is None or y is None or z is None:
        return px, False, "not_numbers"

    if ally_y is None or (not isinstance(ally_y, (int, float))) or math.isnan(ally_y):
        return restore_point(kind, x, y, z, px), False, "no_ally"

    dy = abs(y - ally_y)
    dz = abs(z - ally_y)

    swapped = False
    reason = ""

    # 보수적 휴리스틱: y와 ally_y의 차이가 y_delta보다 크고 z가 더 가까우면 swap
    if (dy > y_delta) and ((dz <= y_delta) or (dz < dy)):
        y, z = z, y
        swapped = True
        reason = f"swap_due_to_ally(dy={dy:.2f},dz={dz:.2f},y_delta={y_delta})"
    else:
        reason = f"no_swap(dy={dy:.2f},dz={dz:.2f},y_delta={y_delta})"

    fixed = restore_point(kind, x, y, z, px)
    return fixed, swapped, reason

# -----------------------
# payload 보정 및 waypoints 추출
# -----------------------
def extract_waypoints_candidates(payload):
    """
    다양한 키명에서 웨이포인트 리스트를 찾아 반환
    우선순위: waypoints_list -> waypoints -> path -> route -> points
    """
    candidates = payload.get("waypoints_list")
    if candidates is not None:
        return candidates
    for k in ("waypoints", "path", "route", "points"):
        v = payload.get(k)
        if isinstance(v, list):
            return v
    return []

def fix_tpp_payload_using_ally(payload, ally_body_pos, y_delta=Y_DELTA):
    """
    Deep-copy payload, fix target_pos and waypoints, ensure waypoints_list exists,
    attach _debug.swap_info
    """
    out = copy.deepcopy(payload) if payload is not None else {}
    ally_y = None
    try:
        if isinstance(ally_body_pos, dict):
            ally_y = ally_body_pos.get("y", None)
            if ally_y is not None:
                ally_y = float(ally_y)
    except Exception:
        ally_y = None

    swap_info = {
        "target_swapped": False,
        "target_reason": "",
        "waypoint_swaps": 0,
        "waypoint_details": []
    }

    # target_pos 보정
    tgt = out.get("target_pos", None)
    fixed_tgt, swapped, reason = fix_point_with_ally(tgt, ally_y, y_delta=y_delta)
    out["target_pos"] = fixed_tgt
    swap_info["target_swapped"] = bool(swapped)
    swap_info["target_reason"] = reason

    # waypoints_list 확보 (다양한 키에서 추출)
    wps_in = extract_waypoints_candidates(out) or []
    if not isinstance(wps_in, list):
        wps_in = []

    fixed_wps = []
    ws_count = 0
    for p in wps_in:
        p_fixed, swapped_p, reason_p = fix_point_with_ally(p, ally_y, y_delta=y_delta)
        fixed_wps.append(p_fixed)
        if swapped_p:
            ws_count += 1
            swap_info["waypoint_details"].append({
                "orig": p,
                "fixed": p_fixed,
                "reason": reason_p
            })

    out["waypoints_list"] = fixed_wps
    swap_info["waypoint_swaps"] = ws_count

    # attach debug
    debug = out.get("_debug", {}) or {}
    debug["swap_info"] = swap_info
    out["_debug"] = debug

    # 로그
    try:
        logger.info("TPP_FIX(ally): original target_pos: %s", repr(tgt))
        logger.info("TPP_FIX(ally): fixed  target_pos: %s | swapped: %s | reason: %s",
                    out.get("target_pos"), swap_info["target_swapped"], swap_info["target_reason"])
        if ws_count:
            logger.info("TPP_FIX(ally): waypoint swaps: %d", ws_count)
            for w in swap_info["waypoint_details"][:10]:
                logger.info("  wp orig: %s -> fixed: %s reason: %s", w["orig"], w["fixed"], w["reason"])
    except Exception:
        logger.exception("Error logging swap_info")

    return out

# -----------------------
# compute_tpp_response (플러그인 연결지점)
# -----------------------
def compute_tpp_response(fixed_payload):
    """
    실제 프로젝트의 경로계산기를 이곳에 연결하세요.
    반환값은 dict여야 하고 'waypoints_list' 키를 반드시 포함해야 합니다.
    현재는 데모 요약을 반환합니다.
    """
    # 예: from planner import plan_path
    # try:
    #     plan_result = plan_path(fixed_payload)
    #     # plan_result must include waypoints_list
    #     return plan_result
    # except Exception:
    #     logger.exception("planner failed, falling back to demo result")

    # Demo: summary
    wps = fixed_payload.get("waypoints_list", []) or []
    path_len = max(1, len(wps) * 10)
    simp_len = 2
    turns = 2
    summary = {
        "status": "OK",
        "message": f"path_len={path_len}, simp_len={simp_len}, turns={turns}",
        "target_pos": fixed_payload.get("target_pos"),
        "waypoints_list": wps,
        "_debug": fixed_payload.get("_debug", {})
    }
    return summary

# -----------------------
# Flask 핸들러
# -----------------------
@app.route("/get_tpp", methods=["POST"])
def get_tpp():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "ERR", "message": "invalid json"}), 400

    try:
        t = payload.get("time", None)
        ally = payload.get("ally_body_pos", payload.get("ally_body_pos_dict", None))
        target = payload.get("target_pos", None)
        map_info = payload.get("map_info", {})
        map_keys = list(map_info.keys()) if isinstance(map_info, dict) else []
        logger.info("TPP /get_tpp request received: time=%s ally_body_pos=%s target_pos=%s map_keys=%s",
                    t, ally, target, map_keys)
    except Exception:
        logger.exception("Error reading incoming payload")

    fixed_payload = fix_tpp_payload_using_ally(payload, ally, y_delta=Y_DELTA)
    result_summary = compute_tpp_response(fixed_payload)

    try:
        status = result_summary.get("status", "OK")
        message = result_summary.get("message", "")
        logger.info("TPP response being sent (summary): status=%s message=%s", status, message)
    except Exception:
        logger.exception("Error logging result_summary")

    return jsonify(result_summary), 200

# 간단한 헬스체크
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "Y_DELTA": Y_DELTA}), 200

if __name__ == "__main__":
    # dev server
    app.run(host="0.0.0.0", port=5000, debug=True)
