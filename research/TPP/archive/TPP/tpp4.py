# tpp_main_fixed.py
# 최종 TPP 핸들러 (ally 기반 좌표 보정 포함)
# 기존 main.py 의 /get_tpp 핸들러를 대체하거나, 필요한 부분만 옮겨 사용하세요.

from flask import Flask, request, jsonify
import copy
import math
import traceback

app = Flask(__name__)

# -----------------------
# 보정 유틸리티
# -----------------------
def fix_point_with_ally(px, ally_y, y_delta=4.0):
    """
    px: list-like [x, y, z]
    ally_y: float or None - 신뢰 가능한 지면/몸체 y 좌표
    y_delta: tolerance (meters) - ally_y에서 얼마나 벗어나면 '비정상'으로 판단할지
    Returns: (fixed_point_list, swapped_flag, reason_str)
    """
    reason = ""
    swapped = False

    if px is None:
        return px, False, "none_point"

    # ensure length
    try:
        if len(px) < 3:
            return px, False, "short_len"
    except Exception:
        return px, False, "not_iterable"

    # try to coerce floats
    try:
        x = float(px[0])
        y = float(px[1])
        z = float(px[2])
    except Exception:
        return px, False, "not_numbers"

    if ally_y is None or (not isinstance(ally_y, (int, float))) or math.isnan(ally_y):
        return [x, y, z], False, "no_ally"

    dy = abs(y - ally_y)
    dz = abs(z - ally_y)

    # Swap heuristic:
    # - 현재 y가 ally_y로부터 크게 벗어나고(dy > y_delta)
    # - 반면 z가 ally_y에 가깝거나(y_delta보다 작거나 dy보다 더 가깝다)
    # -> y와 z를 바꾼다.
    if (dy > y_delta) and ((dz <= y_delta) or (dz < dy)):
        y, z = z, y
        swapped = True
        reason = f"swap_due_to_ally(dy={dy:.2f},dz={dz:.2f},y_delta={y_delta})"
    else:
        reason = f"no_swap(dy={dy:.2f},dz={dz:.2f},y_delta={y_delta})"

    return [x, y, z], swapped, reason


def fix_tpp_payload_using_ally(payload, ally_body_pos, y_delta=4.0):
    """
    payload: dict 형식의 TPP 입력 (target_pos, waypoints_list 등)
    ally_body_pos: dict-like with 'y' key (float)
    y_delta: float - 감지 민감도
    Returns: fixed_payload (deep copy) with _debug.swap_info 추가
    """
    out = copy.deepcopy(payload)
    ally_y = None
    try:
        if isinstance(ally_body_pos, dict):
            ally_y = ally_body_pos.get('y', None)
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

    # target_pos 처리
    tgt = out.get("target_pos", None)
    if tgt is not None:
        fixed_tgt, swapped, reason = fix_point_with_ally(tgt, ally_y, y_delta=y_delta)
        out["target_pos"] = fixed_tgt
        swap_info["target_swapped"] = swapped
        swap_info["target_reason"] = reason

    # waypoints_list 처리
    wps = out.get("waypoints_list", []) or []
    fixed_wps = []
    ws_count = 0
    for p in wps:
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

    # _debug 확장
    debug = out.get("_debug", {}) or {}
    debug["swap_info"] = swap_info
    out["_debug"] = debug

    # 콘솔 로그 (원본 로그 스타일에 맞춤)
    try:
        print("TPP_FIX(ally): original target_pos:", repr(tgt))
        print("TPP_FIX(ally): fixed  target_pos:", out.get("target_pos"),
              "| swapped:", swap_info["target_swapped"], "| reason:", swap_info["target_reason"])
        if ws_count:
            print("TPP_FIX(ally): waypoint swaps:", ws_count)
            for w in swap_info["waypoint_details"][:10]:
                print("  wp orig:", w["orig"], "-> fixed:", w["fixed"], " reason:", w["reason"])
    except Exception:
        # 보호용: 로그 실패해도 동작 계속
        traceback.print_exc()

    return out


# -----------------------
# 기존 TPP 경로계산 함수(있다면 사용) - 없으면 더미 반환
# -----------------------
def compute_tpp_response(fixed_payload):
    """
    실제 프로젝트에서는 여기에 기존의 path planner 호출 코드를 넣으세요.
    예: result = existing_tpp.compute(fixed_payload)
    현재는 테스트/대체용 더미 응답(요약) 생성.
    """
    # 만약 외부에 실제 함수가 있으면 import 시도
    try:
        # 예시: from tpp_module import compute_tpp  # <-- 프로젝트에 맞게 수정
        # result = compute_tpp(fixed_payload)
        # return result
        pass
    except Exception:
        pass

    # 더미 요약: path_len은 waypoints 수 * 10(임의)
    wps = fixed_payload.get("waypoints_list", []) or []
    path_len = max(1, len(wps) * 10)
    simp_len = 2
    turns = 2
    status = "OK"
    summary = {
        "status": status,
        "message": f"path_len={path_len}, simp_len={simp_len}, turns={turns}",
        "target_pos": fixed_payload.get("target_pos"),
        "_debug": fixed_payload.get("_debug", {})
    }
    return summary


# -----------------------
# Flask 핸들러
# -----------------------
@app.route("/get_tpp", methods=["POST"])
def get_tpp():
    """
    원본 핸들러 자리에서 이 함수를 사용하세요.
    - 요청 JSON에서 ally_body_pos 를 찾아 보정 적용
    - 이후 기존 계산 루틴에 전달 (여기서는 compute_tpp_response로 추상화)
    """
    try:
        payload = request.get_json(force=True)
    except Exception:
        # 잘못된 JSON 요청 처리
        return jsonify({"status": "ERR", "message": "invalid json"}), 400

    # 원본 로그 스타일 출력 (간단)
    try:
        t = payload.get("time", None)
        ally = payload.get("ally_body_pos", payload.get("ally_body_pos_dict", None))
        target = payload.get("target_pos", None)
        map_keys = list(payload.get("map_info", {}).keys()) if isinstance(payload.get("map_info", {}), dict) else []
        print("TPP /get_tpp request received:")
        print("  time:", t)
        print("  ally_body_pos:", ally)
        print("  target_pos:", target)
        print("  map_info keys:", map_keys)
    except Exception:
        pass

    # 1) ally 기반 보정 적용 (보수적 y_delta 기본값 4.0m)
    fixed_payload = fix_tpp_payload_using_ally(payload, ally, y_delta=4.0)

    # 2) 실제 경로계산 호출 (프로젝트에 맞게 compute_tpp_response를 교체하세요)
    result_summary = compute_tpp_response(fixed_payload)

    # 3) TPP 응답 로그 (원본 형식에 맞게 출력)
    try:
        status = result_summary.get("status", "OK")
        message = result_summary.get("message", "")
        print("TPP response being sent (summary): status =", status, "| message =", message)
    except Exception:
        pass

    # 4) 반환 - 실제 프로젝트 응답 스키마에 맞춰 수정 가능
    return jsonify(result_summary), 200


# -----------------------
# 실행용
# -----------------------
if __name__ == "__main__":
    # 디버그/개발용 실행 옵션: 기존 main.py 와 유사하게
    app.run(host="0.0.0.0", port=5000, debug=True)

