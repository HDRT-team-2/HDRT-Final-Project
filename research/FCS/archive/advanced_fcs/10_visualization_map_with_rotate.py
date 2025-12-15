import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  # 3D 플롯 활성화용


############################
# 1. 고도맵 로드 (기존 함수 재사용)
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

    grid = np.zeros((z_arr.max() + 1, x_arr.max() + 1))
    grid[z_arr, x_arr] = y_arr
    return grid


############################
# 2. 맵 전체 지형 시각화 + 자동 회전 옵션
############################
def visualize_map_3d(
    map_type: int,
    map_csv_dir: str,
    show: bool = True,
    save_path: str | None = None,
    max_height: float | None = None,
    title: str | None = None,
    # ▼ 새로 추가된 옵션들
    auto_rotate: bool = False,
    rotate_speed_deg: int = 1,      # 프레임당 회전 각도
    rotate_revolutions: int = 1,    # 몇 바퀴 돌지
    elev: float = 60.0,             # 카메라 고도
    start_azim: float = -35.0,      # 시작 방위각
    pause_sec: float = 0.03,        # 프레임 간 지연 (속도 조절)
):
    """
    map_type과 map_csv_dir를 바탕으로
    고도맵 전체를 3D surface로 시각화하고,
    옵션에 따라 창 위에서 자동 회전시킬 수 있음.
    """

    altitude_grid = load_altitude_grid(map_type, map_csv_dir)
    max_z, max_x = altitude_grid.shape

    # X, Z 격자 생성
    X = np.arange(0, max_x)
    Z = np.arange(0, max_z)
    Xg, Zg = np.meshgrid(X, Z)
    Yg = altitude_grid

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    # 1) 지형 surface
    surf = ax.plot_surface(
        Xg, Zg, Yg,
        cmap="terrain",
        linewidth=0,
        antialiased=True,
        alpha=0.95,
    )

    # 2) 컬러바
    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, label="Height (m)")

    # 3) 제목/라벨
    if title is None:
        title = f"Map Height Field (map_type={map_type})"
    ax.set_title(title, fontsize=14)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Z (m)")
    ax.set_zlabel("Height (m)")

    # 4) 범위 세팅
    ax.set_xlim(0, max_x)
    ax.set_ylim(0, max_z)

    if max_height is None:
        z_min = Yg.min() - 2
        z_max = Yg.max() + 2
    else:
        z_min = 0
        z_max = max_height
    ax.set_zlim(z_min, z_max)

    # 초기 시점
    ax.view_init(elev=elev, azim=start_azim)

    # 5) 저장 (원하면 그대로 유지)
    if save_path is not None:
        fig.savefig(save_path, dpi=160)
        print(f"[INFO] 맵 3D 이미지 저장: {save_path}")

    if show:
        # 블로킹 없이 창 띄우기
        plt.show(block=False)

        # 자동 회전 모드
        if auto_rotate:
            total_deg = 360 * rotate_revolutions
            for azim in range(0, total_deg, rotate_speed_deg):
                ax.view_init(elev=elev, azim=start_azim + azim)
                plt.draw()
                plt.pause(pause_sec)

        # 사용자가 창을 닫을 때까지 유지
        plt.show()
    else:
        plt.close(fig)


############################
# 3. 직접 실행 예시
############################
if __name__ == "__main__":
    # 이 파일이 있는 폴더 기준으로 map_csvs 폴더 찾기
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")

    # 보고 싶은 맵 타입 선택 (0~3)
    MAP_TYPE = 0  # 0: forest, 1: road, 2: dry, 3: flat

    visualize_map_3d(
        map_type=MAP_TYPE,
        map_csv_dir=altitude_map_csv_path,
        show=True,
        max_height=110,
        auto_rotate=True,       # ← 이거만 True로 켜주면 됨
        rotate_revolutions=2,   # 2바퀴 돌기
        rotate_speed_deg=2,     # 프레임당 2도씩 회전
        pause_sec=0.03,         # 0.03초 간격 → 부드러운 회전
    )