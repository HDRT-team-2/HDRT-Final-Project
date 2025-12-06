import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  # 3D 플롯 활성화용


############################
# 1. 사격 로그 파싱
############################
def parse_shooting_record(record_path: str) -> dict:
    data = {}
    with open(record_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()

    # 타입 처리
    data["map_type"] = int(data["map_type"])
    float_keys = ["ally_x","ally_y","ally_z","target_x","target_y","target_z","elevation_angle_deg"]
    for k in float_keys:
        data[k] = float(data[k])
    return data



############################
# 2. 고도맵 로드
############################
def load_altitude_grid(map_type: int, base_dir: str) -> np.ndarray:
    csv_file_names = {
        0: "00_forest_and_river_300x300.csv",
        1: "01_country_road_300x300.csv",
        2: "02_wildness_dry_300x300.csv",
        3: "03_simple_flat_300x300.csv",
    }

    path = os.path.join(base_dir, csv_file_names[map_type])
    df = pd.read_csv(path)

    x_arr = df["x"].to_numpy(int)
    y_arr = df["y"].to_numpy(float)
    z_arr = df["z"].to_numpy(int)

    grid = np.zeros((z_arr.max()+1, x_arr.max()+1))
    grid[z_arr, x_arr] = y_arr
    return grid



############################
# 3. 궤적 계산
############################
def compute_trajectory(ally, target, angle_deg, muzzle_velocity=61.0):
    G = 9.81

    ax, ay, az = ally["x"], ally["y"], ally["z"]
    tx, ty, tz = target["x"], target["y"], target["z"]

    dx, dz = tx - ax, tz - az
    d = math.sqrt(dx*dx + dz*dz)

    if d <= 0.1:
        return np.array([ax,tx]), np.array([ay,ty]), np.array([az,tz])

    ux, uz = dx/d, dz/d
    θ = math.radians(angle_deg)

    cos2 = math.cos(θ)**2
    tanθ = math.tan(θ)

    muzzle_height = ay + 0.2
    s = np.linspace(0, d, 150)

    xs = ax + ux * s
    zs = az + uz * s
    ys = muzzle_height + s * tanθ - (G * s**2) / (2 * muzzle_velocity**2 * cos2)

    return xs, ys, zs

############################
# 4. 전체 지형 + 궤적 시각화
############################
def visualize_shot(record_path, map_csv_dir, show=True, save_path=None, max_height=None):

    # 지형에서 살짝 띄워서 완전히 분리
    TRAJ_OFFSET  = 1.0   # 궤적용
    POINT_OFFSET = 1.0   # 아군/적 포인트용

    rec = parse_shooting_record(record_path)
    altitude_grid = load_altitude_grid(rec["map_type"], map_csv_dir)
    max_z, max_x = altitude_grid.shape

    traj_x, traj_y, traj_z = compute_trajectory(
        {"x":rec["ally_x"],"y":rec["ally_y"],"z":rec["ally_z"]},
        {"x":rec["target_x"],"y":rec["target_y"],"z":rec["target_z"]},
        rec["elevation_angle_deg"]
    )

    # ---- 표시용 높이 보정 ----
    vis_traj_y   = traj_y + TRAJ_OFFSET
    vis_ally_y   = rec["ally_y"]   + POINT_OFFSET
    vis_target_y = rec["target_y"] + POINT_OFFSET

    X = np.arange(0, max_x)
    Z = np.arange(0, max_z)
    Xg, Zg = np.meshgrid(X, Z)
    Yg = altitude_grid

    fig = plt.figure(figsize=(12,10))
    ax = fig.add_subplot(111, projection="3d")

    # 1) 지형: 더 투명하게 + zorder 낮게
    ax.plot_surface(
        Xg, Zg, Yg,
        cmap="terrain",
        linewidth=0,
        antialiased=True,
        alpha=0.6,      # 0.85 → 0.6
        zorder=1
    )

    # 2) 궤적: 두껍게 + zorder 높게
    ax.plot(
        traj_x, traj_z, vis_traj_y,
        color="red",
        linewidth=3,
        label="Trajectory",
        zorder=10
    )

    # 3) 아군/적: 더 크게, 테두리, depthshade 끄기 + zorder 더 높게
    ax.scatter(
        [rec["ally_x"]], [rec["ally_z"]], [vis_ally_y],
        marker="^", s=200, color="blue",
        edgecolor="k",
        depthshade=False,
        label="Ally",
        zorder=11
    )
    ax.scatter(
        [rec["target_x"]], [rec["target_z"]], [vis_target_y],
        marker="o", s=200, color="orange",
        edgecolor="k",
        depthshade=False,
        label="Enemy",
        zorder=12
    )

    # 9) 제목/라벨
    title_ts = rec.get("timestamp", os.path.basename(record_path))
    ax.set_title(
        f"3D Ballistic Visualization | map={rec['map_type']} | {title_ts}",
        fontsize=15
    )
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_zlabel("Height (m)")

    # 10) 전장 전체 범위
    ax.set_xlim(0, max_x)
    ax.set_ylim(0, max_z)

    # 11) 높이 스케일 (자동 vs 수동)
    if max_height is None:
        z_min = min(Yg.min(), vis_traj_y.min(), vis_ally_y, vis_target_y) - 2
        z_max = max(Yg.max(), vis_traj_y.max(), vis_ally_y, vis_target_y) + 2
    else:
        z_min = 0
        z_max = max_height
    ax.set_zlim(z_min, z_max)

    # 12) 카메라 시점 & 범례
    ax.view_init(elev=60, azim=-35)
    ax.legend()

    # 13) 저장/표시
    if save_path is not None:
        fig.savefig(save_path, dpi=160)
        print(f"[INFO] 이미지 저장: {save_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


#######################################
# 5. 직접 실행 예시
#######################################
if __name__ == "__main__":
    # 예시 경로들 – 필요에 맞게 수정해서 사용
    record_file = "shooting_record_20251206_154823.txt"  # 실제 파일명으로 교체

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))                  # 현재 파이썬 파일이 있는 폴더 경로를 BASE_DIR에 저장
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")

    visualize_shot(
        record_path=record_file,
        map_csv_dir=altitude_map_csv_path,
        show=True,
        max_height=110,
        # save_path="shot_3d.png",  # 파일로 저장하고 싶으면 주석 해제
    )