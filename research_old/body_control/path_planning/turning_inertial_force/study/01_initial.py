# -*- coding: utf-8 -*-
"""
turning_speed_profile_v2.py
- weight 1~10 × each 5회 → 총 50회 자동 실험
- 결과 CSV 저장
- 종료 시:
   Weight별 |Extra| 평균/최대/최소 출력
   Overshoot 평균 bar plot 저장
   Overshoot vs ω scatter + 회귀추세선
"""

from flask import Flask, request, jsonify
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import csv
import os
from datetime import datetime

app = Flask(__name__)

################################################
# Experiment Configuration
################################################
WEIGHTS = list(range(1, 11))
REPEAT_PER_WEIGHT = 5
TOTAL = len(WEIGHTS) * REPEAT_PER_WEIGHT

OMEGA_STABLE = 6.0
STABLE_REQ = 2
MIN_SETTLE = 0.2
MAX_SETTLE = 3.0

# 저장 경로 지정
SAVE_DIR = os.path.join(
    "source", "research", "body_control", "path_planning", "turning_inertial_force"
)
os.makedirs(SAVE_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
csv_path = os.path.join(SAVE_DIR, f"speed_profile_{timestamp}.csv")

################################################
# Runtime State
################################################
yaw = None
sim_time = None
last_yaw = None
last_time = None
omega = 0.0
stable_ticks = 0

state = "spinup"
current_weight_idx = 0
current_repeat = 0
release_yaw = None
stop_time = None
max_omega = 0.0

results = []

print("turning_speed_profile v2 started!")
print(f"🔹 Weights = {WEIGHTS} / Repeats = {REPEAT_PER_WEIGHT} → Total={TOTAL}")
print(f"🔹 Results saved to: {SAVE_DIR}")

################################################
# Utility Functions
################################################
def norm360(a): return a % 360.0
def signed_diff(a,b):
    d=(a-b)%360.0
    if d>180: d-=360
    return d

def save_csv():
    with open(csv_path,"w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["weight","peak_omega","raw_extra","abs_extra"])
        w.writerows(results)
    print(f"\nCSV saved: {csv_path}")

def print_statistics():
    print("\n========================")
    print("Overshoot Statistics")
    print("========================")
    
    for w in WEIGHTS:
        data=[r[3] for r in results if r[0]==w]
        if data:
            print(f"Weight {w}: mean={np.mean(data):.2f}°, "
                  f"max={np.max(data):.2f}°, min={np.min(data):.2f}°")

def make_plots():
    weights=[r[0] for r in results]
    peaks=[r[1] for r in results]
    extras=[r[3] for r in results]

    # Weight별 평균 Overshoot Bar Plot
    means=[]
    for w in WEIGHTS:
        w_vals=[r[3] for r in results if r[0]==w]
        means.append(np.mean(w_vals))

    plt.figure()
    plt.bar(WEIGHTS,means)
    plt.title("Average Overshoot Δθ per Weight")
    plt.xlabel("Weight")
    plt.ylabel("Average Δθ (deg)")
    plt.grid(axis='y',alpha=0.4)
    avg_plot_path = os.path.join(SAVE_DIR, "overshoot_avg_by_weight.png")
    plt.savefig(avg_plot_path)
    plt.close()
    print(f"Saved: {avg_plot_path}")

    # Δθ vs ω Scatter + Linear Fit
    peaks_np=np.array(peaks)
    extras_np=np.array(extras)

    m,b=np.polyfit(peaks_np,extras_np,1) # 추세선

    plt.figure()
    plt.scatter(peaks_np,extras_np,label="Data")
    plt.plot(peaks_np,m*peaks_np+b,'r--',label=f"Fit: y={m:.2f}x+{b:.2f}")
    plt.title("Overshoot Δθ vs Peak ω")
    plt.xlabel("Peak ω (deg/s)")
    plt.ylabel("Δθ (deg)")
    plt.grid()
    plt.legend()
    scatter_path = os.path.join(SAVE_DIR, "overshoot_vs_peakomega_fit.png")
    plt.savefig(scatter_path)
    plt.close()
    print(f"Saved: {scatter_path}")


################################################
# Experiment Finish
################################################
def finish():
    save_csv()
    print_statistics()
    make_plots()
    print("\nALL DONE! Check CSV + PNG files!\n")

################################################
# Flask Endpoints
################################################
@app.route("/info", methods=["POST"])
def info():
    global yaw, sim_time, last_yaw, last_time, omega, stable_ticks
    data=request.get_json(force=True)

    if "playerBodyX" in data:
        yaw=norm360(float(data["playerBodyX"]))
    if "time" in data:
        sim_time=float(data["time"])

    if yaw and sim_time and last_yaw:
        dt=max(1e-3,sim_time-last_time)
        diff=signed_diff(yaw,last_yaw)
        omega=diff/dt
        stable_ticks=stable_ticks+1 if abs(omega)<OMEGA_STABLE else 0

    last_yaw=yaw
    last_time=sim_time
    return jsonify({"status":"ok"})


@app.route("/get_action", methods=["POST"])
def get_action():
    global state,current_weight_idx,current_repeat
    global release_yaw,stop_time,max_omega,stable_ticks

    cmd={"moveWS":{"command":"","weight":0.0},
         "moveAD":{"command":"","weight":0.0},
         "turretQE":{"command":"","weight":0.0},
         "turretRF":{"command":"","weight":0.0},
         "fire":False}

    if len(results)>=TOTAL:
        finish()
        return jsonify(cmd)

    if yaw is None: return jsonify(cmd)

    weight=WEIGHTS[current_weight_idx]

    # FSM ------------------------------------
    if state=="spinup":
        cmd["moveAD"]={"command":"D","weight":weight}
        if abs(omega)>max_omega: max_omega=abs(omega)
        if max_omega-abs(omega)>0.5: # peak reached
            release_yaw=yaw
            stop_time=sim_time
            stable_ticks=0
            state="settle"
            print(f"RELEASE w={weight} peakω={max_omega:.2f}")

    elif state=="settle":
        elapsed=sim_time-stop_time if stop_time else 0.0
        if (elapsed>=MIN_SETTLE and stable_ticks>=STABLE_REQ) or elapsed>=MAX_SETTLE:
            raw_extra=signed_diff(yaw,release_yaw)
            abs_extra=abs(raw_extra)
            results.append([weight,max_omega,raw_extra,abs_extra])
            print(f"{len(results)}/{TOTAL}: w={weight}, peakω={max_omega:.2f}, extra={abs_extra:.2f}")

            current_repeat+=1
            if current_repeat>=REPEAT_PER_WEIGHT:
                current_repeat=0
                current_weight_idx+=1

            max_omega=0.0
            state="spinup"

    return jsonify(cmd)

################################################

if __name__=="__main__":
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    print("Server Running on 0.0.0.0:5000 …")
    app.run(host="0.0.0.0", port=5000)
