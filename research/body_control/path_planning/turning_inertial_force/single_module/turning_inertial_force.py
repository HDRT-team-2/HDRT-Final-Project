# -*- coding: utf-8 -*-
"""
turning_inertial_force_v3.py
- 포탑 비활성화, 차체 회전만 제어
- 회전속도 n: 1.0~5.0 (0.5 step) → n=65×(1~5)
- weight = n/65, command = 'D' on/off
- 각 속도별 10회 반복
- 릴리즈 직전 ω 기록 + 감속률 α 추정 + yaw unwrap 적용
"""

import os, math
from datetime import datetime
from collections import defaultdict, deque
from flask import Flask, request, jsonify
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import logging
import numpy as np

# ------------------------
# 저장 경로 설정
# ------------------------
SAVE_DIR = os.path.join(
    "source", "research", "body_control", "path_planning", "turning_inertial_force"
)
os.makedirs(SAVE_DIR, exist_ok=True)

# ------------------------
# Flask & Access log 억제
# ------------------------
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)

# ------------------------
# 실험 파라미터
# ------------------------
SPEED_LEVELS = [65 * (1.0 + 0.5 * i) for i in range(9)]  # n = 65~325
REPEATS_PER_SPEED = 20
HOLD_SEC = 2.0
STABLE_TICKS_REQ = 3
MIN_SETTLE_TIME = 0.4
DECAY_RECORD_SEC = 1.0  # 감속 구간 샘플링 시간

# ------------------------
# 전역 상태
# ------------------------
yaw, time_s = None, None
_last_yaw, _last_time = None, None
omega, ema_dt = 0.0, None
state = "idle"
curr_speed_idx, curr_repeat = 0, 0
hold_end_time, release_yaw, release_time = None, None, None
stable_ticks = 0
peak_omega_this_trial = 0.0
omega_release = 0.0

overshoot_by_speed = defaultdict(list)
peakomega_by_speed = defaultdict(list)
alpha_by_speed = defaultdict(list)
all_trials = []

yaw_buffer = deque(maxlen=500)
omega_buffer = deque(maxlen=500)

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
CSV_PATH = os.path.join(SAVE_DIR, f"turning_inertia_results.csv")

# ------------------------
# 유틸 함수
# ------------------------
def norm360(a): return a % 360.0
def cw_diff(tgt, cur): return (tgt - cur) % 360.0
def unwrap_yaw(yaw_list):
    if not yaw_list:
        return []
    yaws = np.array(yaw_list)
    return np.rad2deg(np.unwrap(np.deg2rad(yaws)))

def current_speed():
    if curr_speed_idx >= len(SPEED_LEVELS):
        return SPEED_LEVELS[-1]   # 안전 처리: 마지막 속도로 고정 반환
    return SPEED_LEVELS[curr_speed_idx]
def current_weight(): return current_speed() / 65.0
def is_done_all(): return curr_speed_idx >= len(SPEED_LEVELS)

def summarize_and_save():
    print("\n============================")
    print("실험 종료 (속도별 추가 회전각 통계)")
    lines = []
    for n in SPEED_LEVELS:
        vals = overshoot_by_speed.get(n, [])
        if not vals:
            continue
        avg, mn, mx = np.mean(vals), np.min(vals), np.max(vals)
        print(f" n={n/65:.1f}× (n={n:.1f}) → avg={avg:.2f}°, min={mn:.2f}°, max={mx:.2f}° (N={len(vals)})")
        lines.append((n, avg, mn, mx))

    # CSV 저장
    with open(CSV_PATH, "w", encoding="utf-8") as f:
        f.write("speed_ratio,n_value,repeat,peak_omega,omega_release,release_yaw,final_yaw,overshoot_deg,alpha_est\n")
        for tr in all_trials:
            f.write(f"{tr['speed']/65.0:.2f},{tr['speed']:.2f},{tr['repeat']},{tr['peak_omega']:.3f},"
                    f"{tr['omega_release']:.3f},{tr['release_yaw']:.2f},{tr['final_yaw']:.2f},"
                    f"{tr['extra']:.3f},{tr['alpha_est']:.4f}\n")
    print(f"CSV saved: {CSV_PATH}")

    # 그래프 1: 속도별 평균 오버슈트
    xs = [f"{n/65:.1f}" for (n, _, _, _) in lines]
    avgs = [v for (_, v, _, _) in lines]
    plt.figure(figsize=(10,5))
    plt.bar(range(len(xs)), avgs)
    plt.xticks(range(len(xs)), xs)
    plt.ylabel("Mean Overshoot (deg)")
    plt.xlabel("Speed Ratio (×)")
    plt.title("Overshoot — Mean by Speed Level")
    plt.grid(axis='y', alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(SAVE_DIR, "turning_inertial_force_degree_avg_by_speed.png"), dpi=120)
    plt.close()

    # 그래프 2: Overshoot vs Peak ω
    xs = [t['peak_omega'] for t in all_trials]
    ys = [t['extra'] for t in all_trials]
    plt.figure(figsize=(7,6))
    plt.scatter(xs, ys, s=24)
    plt.xlabel("Peak |omega| (deg/s)")
    plt.ylabel("Overshoot (deg)")
    plt.title("Overshoot vs Peak Angular Speed")
    plt.grid(alpha=0.4)
    plt.tight_layout()
    plt.savefig(os.path.join(SAVE_DIR, "turning_inertial_force_degree_by_speed.png"), dpi=120)
    plt.close()

# ------------------------
# Flask Routes
# ------------------------
@app.route("/info", methods=["POST"])
def info():
    global yaw, time_s, _last_yaw, _last_time, omega, ema_dt, stable_ticks
    data = request.get_json(force=True)
    try:
        yaw = norm360(float(data.get("playerBodyX", yaw)))
        time_s = float(data.get("time", time_s))
    except:
        return jsonify({"status": "invalid"})

    if yaw is not None and time_s is not None and _last_yaw is not None and _last_time is not None:
        dt = max(1e-3, time_s - _last_time)
        ema_dt = dt if ema_dt is None else (0.6 * ema_dt + 0.4 * dt)
        d = cw_diff(yaw, _last_yaw)
        if d > 180: d -= 360
        omega = d / dt
        stable_ticks = stable_ticks + 1 if abs(omega) < (5.0 * (current_speed()/65.0)) else 0
        yaw_buffer.append(yaw)
        omega_buffer.append(omega)
    _last_yaw, _last_time = yaw, time_s
    return jsonify({"status": "ok"})

@app.route("/get_action", methods=["POST"])
def get_action():
    global state, curr_speed_idx, curr_repeat
    global hold_end_time, release_yaw, release_time, stable_ticks
    global peak_omega_this_trial, omega_release

    cmd = {
        "moveWS": {"command": "STOP", "weight": 1.0},
        "moveAD": {"command": "", "weight": 0.0},
        "turretQE": {"command": "", "weight": 0.0},
        "turretRF": {"command": "", "weight": 0.0},
        "fire": False
    }

    if yaw is None or time_s is None or is_done_all():
        return jsonify(cmd)

    n = current_speed()
    w = current_weight()

    if state == "idle":
        yaw_buffer.clear()
        omega_buffer.clear()
        peak_omega_this_trial = 0.0
        hold_end_time = time_s + HOLD_SEC
        release_yaw = None
        release_time = None
        stable_ticks = 0
        state = "hold"
        print(f"\n=== Speed {n/65:.1f}× (n={n:.1f}, weight={w:.3f}) | Trial {curr_repeat+1}/{REPEATS_PER_SPEED} ===")

    if state == "hold":
        cmd["moveAD"] = {"command": "D", "weight": w}
        if omega is not None:
            peak_omega_this_trial = max(peak_omega_this_trial, abs(omega))
        if time_s >= hold_end_time:
            cmd["moveAD"] = {"command": "", "weight": 0.0}
            release_yaw, release_time = yaw, time_s
            omega_release = abs(omega)
            stable_ticks = 0
            state = "settle"
            print(f"RELEASE @ yaw={yaw:.2f}, ω={omega_release:.2f}, t={time_s:.2f}")

    elif state == "settle":
        elapsed = 0.0 if release_time is None else max(0.0, time_s - release_time)
        if elapsed >= MIN_SETTLE_TIME and stable_ticks >= STABLE_TICKS_REQ:
            # 감속률 α 추정
            yaw_unwrapped = unwrap_yaw(list(yaw_buffer))
            t_decay, omega_decay = np.array(range(len(omega_buffer))), np.array(list(omega_buffer))
            alpha_est = 0.0
            if len(omega_decay) > 5:
                dt_mean = ema_dt or 0.02
                t_axis = np.arange(len(omega_decay)) * dt_mean
                coefs = np.polyfit(t_axis, omega_decay, 1)
                alpha_est = -coefs[0]

            final_yaw = yaw
            extra_cw = cw_diff(final_yaw, release_yaw)
            if extra_cw > 180: extra_cw = 360.0 - extra_cw
            extra = abs(extra_cw)

            overshoot_by_speed[n].append(extra)
            peakomega_by_speed[n].append(peak_omega_this_trial)
            alpha_by_speed[n].append(alpha_est)
            all_trials.append({
                "speed": n, "repeat": curr_repeat + 1,
                "peak_omega": peak_omega_this_trial,
                "omega_release": omega_release,
                "release_yaw": release_yaw,
                "final_yaw": final_yaw,
                "extra": extra,
                "alpha_est": alpha_est
            })
            print(f"extra={extra:.2f}°, α≈{alpha_est:.3f}")

            curr_repeat += 1
            if curr_repeat >= REPEATS_PER_SPEED:
                curr_repeat = 0
                curr_speed_idx += 1
                if curr_speed_idx < len(SPEED_LEVELS):
                    print(f"➡️ Next speed {current_speed()/65:.1f}×")
            if is_done_all():
                summarize_and_save()
                state = "done"
            else:
                state = "idle"
    return jsonify(cmd)

# ------------------------
# main
# ------------------------
if __name__ == "__main__":
    print("starting turning_inertial_force_v3 server ...")
    app.run(host="0.0.0.0", port=5000)
