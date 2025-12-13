import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# ============================================================
# 설정
# ============================================================

WAYPOINT_FILE = "waypoints.json"      # 모놀리식 코드에서 저장한 웨이포인트
LOG_FILE      = "C:/Users/acorn/OneDrive/문서/Tank Challenge/log_data/tank_info_log.txt"   # 실제 주행 로그 파일
SAVE_VIDEO    = False                 # True면 mp4 저장

# ============================================================
# 1) 이론 경로(웨이포인트) 로드
# ============================================================
with open(WAYPOINT_FILE, "r", encoding="utf-8") as f:
    wps = json.load(f)["waypoints"]

wp_x = [wp["x"] for wp in wps]
wp_z = [wp["z"] for wp in wps]

print(f"[INFO] 로드된 웨이포인트 개수 = {len(wp_x)}")


# ============================================================
# 2) 실제 로그 로드
# ============================================================
df = pd.read_csv(LOG_FILE)

required = ["Time", "Player_Pos_X", "Player_Pos_Z"]
for col in required:
    if col not in df.columns:
        raise ValueError(f"로그에 '{col}' 컬럼이 없습니다!")

time = df["Time"].values
real_x = df["Player_Pos_X"].values
real_z = df["Player_Pos_Z"].values

print(f"[INFO] 실제 경로 프레임 수 = {len(real_x)}")


# ============================================================
# 3) 정적 비교 그래프 (Static)
# ============================================================
plt.figure(figsize=(10, 10))
plt.title("Theoretical Path (Waypoint) vs Real Tank Path")
plt.xlabel("X")
plt.ylabel("Z")
plt.grid(True, linestyle="--", alpha=0.4)

# 이론 경로
plt.plot(wp_x, wp_z, "bo-", label="Theoretical Path (Waypoints)")

# 실제 경로
plt.plot(real_x, real_z, "r-", alpha=0.7, label="Real Path")

# 시작/도착 표시
if len(wp_x) > 0:
    plt.scatter(wp_x[0], wp_z[0], s=200, c="green", marker="o", label="Start")
    plt.scatter(wp_x[-1], wp_z[-1], s=200, c="black", marker="X", label="Goal")

plt.legend()
plt.tight_layout()
plt.show()


# ============================================================
# 4) 애니메이션 (Optional)
# ============================================================
fig, ax = plt.subplots(figsize=(10, 10))
ax.set_title("Real Tank Movement Animation")
ax.set_xlabel("X")
ax.set_ylabel("Z")
ax.grid(True, linestyle="--", alpha=0.4)

# 이론 경로 표시
ax.plot(wp_x, wp_z, "bo-", label="Waypoints")

# 실제 경로 라인
real_line, = ax.plot([], [], "r-", linewidth=2, label="Real Path")
current_point, = ax.plot([], [], "ro")

ax.legend()

def init():
    real_line.set_data([], [])
    current_point.set_data([], [])
    return real_line, current_point

def update(frame):
    real_line.set_data(real_x[:frame], real_z[:frame])
    current_point.set_data(real_x[frame], real_z[frame])
    return real_line, current_point

ani = FuncAnimation(fig, update, frames=len(real_x), init_func=init, interval=20, blit=True)

if SAVE_VIDEO:
    ani.save("tank_path_comparison.mp4", fps=60)
else:
    plt.show()
