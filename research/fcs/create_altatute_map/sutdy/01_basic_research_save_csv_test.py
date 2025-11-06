"""
주행 로그 데이터를 이용해 [map name]altatude_map.csv로 변환시키는 프로그램.


참고사항 : 
지도 전체 넓이는 300 * 300.
지도 top view 기준 좌 상단이 x:0,z:300.
Player_Pos_X : 지도 top view 기준 가로 축
Player_Pos_Y : 고도
Player_Pos_Z : 지도 top view 기준 세로 축

메서드1 : 시뮬레이터에서 출력한 원본 주행 로그를 Player_Pos_X,Player_Pos_Y,Player_Pos_Z
값만 남기고, 모두 0으로 저장된 'occupancy_status' 열을 추가 후, 다른 csv로 저장, 
csv 파일 상 소숫점 이하의 숫자를 버리고, 겹치는 좌표는 제거.

메서드2 : y결측치를 자동으로 채우는 매서드 (보간법 활용)

메서드3 : csv 파일로 된 altatude_map을 시각화.

메서드4 : 기존 300 * 300 지도를 가정하고 만들어진 고도값 csv를 3000 * 3000으로 확장.

메서드5 : (Forest_and_river용) 강 구역의 y 값을 모두 -5로, occupancy_status는 1(장애물, 통행불가)로 채우는 코드
"""

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import pandas as pd
import numpy as np
from pathlib import Path
import os
from matplotlib.tri import Triangulation

drive_log_path = "/original_drive_log/" 
# ▲ 주행로그 txt 파일들이 모여있는 폴더로 지정할것.

map_0_csv_name = "00_Forest and River_Map_Info_Scan_Log.csv"
map_1_csv_name = "01_Country Road_Map_Info_Scan_Log.csv"
map_2_csv_name = "02_Wildness Dry_Map_Info_Scan_Log.csv"
map_3_csv_name = "03_Simple Flat_Map_Info_Scan_Log.csv"
#map_4_csv_name = "04_Fist and Hills_Map_Info_Scan_Log.csv"     #주행로그 미사용으로 결정.


altatude_map_path = drive_log_path + "/altatute_map_" + map_2_csv_name
expended_altatude_map_path = drive_log_path + "/exp_altatute_map_" + map_2_csv_name

####################
#    메서드 1번     #
####################
def drive_log_to_xyz_csv(input_csv_path, out_path):
    """
    - 0..300 (포함) 전체 격자(301x301)를 NaN으로 초기화
    - 주행 로그에서 X,Y,Z만 사용(소수점 버림), X-Z 중복은 첫 값 유지
    - occupancy_status=0 추가 후 저장
    """
    # 1) 301x301 격자 생성 (Y는 NaN)
    xs = np.arange(0, 300, dtype=int)
    zs = np.arange(0, 300, dtype=int)
    grid = np.array(np.meshgrid(xs, zs, indexing="ij"))
    grid = grid.reshape(2, -1).T
    df_grid = pd.DataFrame(grid, columns=["Player_Pos_X", "Player_Pos_Z"])
    df_grid["Player_Pos_Y"] = np.nan

    # 2) 로그 로드 & 필요한 컬럼만
    df = pd.read_csv(input_csv_path)
    df = df[["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]].copy()

    # 3) 소수점 버림(=정수화). 안전하게 to_numeric 후 astype
    for c in ["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Player_Pos_X", "Player_Pos_Z"])
    df[["Player_Pos_X", "Player_Pos_Z"]] = df[["Player_Pos_X", "Player_Pos_Z"]].astype(int)
    # Y도 정수로 버림 (원한다면 반올림/유지로 바꿔도 됨)
    if df["Player_Pos_Y"].notna().any():
        df["Player_Pos_Y"] = df["Player_Pos_Y"].astype(int)

    # 4) X-Z 중복 제거(첫 값 유지)
    df = df.drop_duplicates(subset=["Player_Pos_X", "Player_Pos_Z"], keep="first")

    # 5) 격자와 병합 → 격자 우선, 로그값으로 덮기
    df_merged = df_grid.merge(
        df,
        on=["Player_Pos_X", "Player_Pos_Z"],
        how="left",
        suffixes=("", "_log")
    )
    # 로그 Y가 있으면 덮어쓰기
    df_merged["Player_Pos_Y"] = df_merged["Player_Pos_Y_log"].combine_first(df_merged["Player_Pos_Y"])
    df_merged = df_merged.drop(columns=["Player_Pos_Y_log"])

    # 6) occupancy_status 추가(0)
    df_merged["occupancy_status"] = 0

    # 7) 정렬 & 저장
    df_merged = df_merged.sort_values(["Player_Pos_X"]).reset_index(drop=True)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df_merged.to_csv(out_path, index=False)
    print(f"[메서드1] saved -> {out_path}")

####################
#    메서드 2번     #
####################
def impute_y_two_pass(df: pd.DataFrame,
                      method_z: str = "linear",
                      method_x: str = "linear",
                      fill_edges: bool = True,
                      col_x: str = "Player_Pos_X",
                      col_y: str = "Player_Pos_Y",
                      col_z: str = "Player_Pos_Z") -> pd.DataFrame:
    """
    1) 같은 X 내에서 Z축 정렬 후 Y 선형 보간
    2) 같은 Z 라인에서 X축 방향으로 한 번 더 보간
       (피벗 -> 가로보간 -> 역피벗)
    """
    df = df.copy()
    for c in [col_x, col_y, col_z]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["_orig_idx__"] = np.arange(len(df))

    # 1단계: X 그룹 내 Z-방향 보간
    def _interp_along_z(g):
        g = g.sort_values(col_z)
        if fill_edges:
            g[col_y] = g[col_y].interpolate(method=method_z, limit_direction="both")
        else:
            g[col_y] = g[col_y].interpolate(method=method_z)
        return g

    df1 = (
        df.sort_values([col_x, col_z])
          .groupby(col_x, group_keys=False)
          .apply(_interp_along_z)
    )

    # 2단계: Z 라인별 X-방향 보간
    pivot = (
        df1.pivot(index=col_z, columns=col_x, values=col_y)
           .sort_index(axis=0)  # Z 오름차순
           .sort_index(axis=1)  # X 오름차순
    )
    if fill_edges:
        pivot2 = pivot.interpolate(axis=1, method=method_x, limit_direction="both")
    else:
        pivot2 = pivot.interpolate(axis=1, method=method_x)

    filled_long = pivot2.stack().rename(col_y).reset_index()

    out = (
        df1.drop(columns=[col_y])
           .merge(filled_long, on=[col_z, col_x], how="left")
           .sort_values("_orig_idx__")
           .drop(columns=["_orig_idx__"])
           .reset_index(drop=True)
    )
    return out

def checking_missing_values(in_path: str,
                            out_path: str = None,
                            overwrite: bool = False,
                            method_z: str = "linear",
                            method_x: str = "linear",
                            fill_edges: bool = True):
    """
    - 파일 로드 → 2단계 보간 → 저장
    - 기본은 원본을 보존하고 *_IMPUTED.csv로 저장.
      overwrite=True면 in_path에 덮어씀.
    """
    df = pd.read_csv(in_path)
    df.columns = [c.strip() for c in df.columns]

    before_na = df["Player_Pos_Y"].isna().sum()
    df_out = impute_y_two_pass(df, method_z=method_z, method_x=method_x, fill_edges=fill_edges)
    after_na = df_out["Player_Pos_Y"].isna().sum()

    if overwrite or not out_path:
        save_path = in_path if overwrite else _append_suffix(in_path, "_IMPUTED")
    else:
        save_path = out_path

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(save_path, index=False)

    print("[메서드2] Imputation Summary")
    print(f" - rows_total        : {len(df)}")
    print(f" - y_missing_before  : {before_na}")
    print(f" - y_missing_after   : {after_na}")
    print(f" - saved -> {save_path}")
    return save_path

def _append_suffix(path_str: str, suffix: str) -> str:
    p = Path(path_str)
    return str(p.with_name(p.stem + suffix + p.suffix))


####################
#    메서드 3번     #
####################
def visualization_altatute_map(csv_path):
    df = pd.read_csv(csv_path)
    for c in ["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df_vis = df.dropna(subset=["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"])
    x = df_vis["Player_Pos_X"].to_numpy()
    y = df_vis["Player_Pos_Y"].to_numpy()
    z = df_vis["Player_Pos_Z"].to_numpy()

    tri = Triangulation(x, z)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_trisurf(x, z, y, triangles=tri.triangles, cmap="viridis")

    ax.set_xlabel("Player_Pos_X")
    ax.set_ylabel("Player_Pos_Z")
    ax.set_zlabel("Player_Pos_Y")
    plt.title("3D Terrain-like Surface (Triangulated)")
    plt.colorbar(surf, label="Player_Pos_Y")

    ax.set_xlim(0, 300)
    ax.set_ylim(0, 300)
    ax.set_zlim(0, 50)

    ax.view_init(elev=30, azim=45)
    plt.tight_layout()
    plt.show()
    plt.close()

    print(f"{csv_path} has been visualized.")


####################
#    메서드 4번     #
####################
def expend_altatute_map(input_csv_path, out_path):
    df = pd.read_csv(input_csv_path)

    grid_size = 300
    height_map = df['Player_Pos_Y'].to_numpy().reshape(grid_size, grid_size)
    occupancy_map = df['occupancy_status'].to_numpy().reshape(grid_size, grid_size)

    scale = 10
    expanded_height = np.repeat(np.repeat(height_map, scale, axis=0), scale, axis=1)
    expanded_occupancy = np.repeat(np.repeat(occupancy_map, scale, axis=0), scale, axis=1)

    x_coords, z_coords = np.meshgrid(np.arange(expanded_height.shape[1]),
                                 np.arange(expanded_height.shape[0]))

    # 새 DataFrame으로 결합
    expanded_df = pd.DataFrame({
        "Player_Pos_X": x_coords.ravel(),
        "Player_Pos_Z": z_coords.ravel(),
        "Player_Pos_Y": expanded_height.ravel(),
        "occupancy_status": expanded_occupancy.ravel()
    })

    expanded_df.to_csv(out_path, index=False)

    print("expend_altatute_map has been complete")


####################
#    메서드 5번     #
####################


####################
#    메인 메서드    #
####################
if __name__ == "__main__":
    
    # 1) 로그를 300x300 격자형 CSV로 변환
    drive_log_to_xyz_csv(drive_log_path + map_0_csv_name, altatude_map_path)

    """
    # 2) 결측치 보간(기본: 선형/선형, 양방향 엣지 채움). 원본 보존 + *_IMPUTED.csv 생성
    imputed_path = checking_missing_values(
        altatude_map_path,
        overwrite=False,      # True로 바꾸면 원본 파일에 덮어씀
        method_z="linear",    # X별 Z-축 보간 방식
        method_x="linear",    # Z별 X-축 보간 방식
        fill_edges=True       # 엣지도 채움
    )
    """

    # 3) 시각화
    visualization_altatute_map(altatude_map_path)


    # 4) 3000 * 3000으로 확장
    expend_altatute_map(altatude_map_path, expended_altatude_map_path)
    visualization_altatute_map(expended_altatude_map_path)

    # 5) Forest_and_river용 후처리
