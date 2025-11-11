"""
시뮬레이터에서 추출한 주행 로그를 1단계 가공하는 코드

credit by : oixxta

300*300이며, 원본 주행로그에 대한 왜곡이 가장 적음.

반드시, 시작하기 전에 원본 주행로그의 확장자만 txt에서 csv로 바꾸고,
file_to_read_name에 주행 로그 원본파일의 이름을,
input_csv_path에 주행 로그 원본파일의 경로를,
out_path에 가공된 csv 파일이 저장될 경로를 지정할 것.
"""

import numpy as np
import pandas as pd
from pathlib import Path

file_to_read_name = "03_simple_flat_map_Info_scan_log" + ".csv"
input_csv_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/" + file_to_read_name
out_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/jobed_" + file_to_read_name

def drive_log_to_xyz_csv(input_csv_path, out_path):
    """
    - 0..300 (포함) 전체 격자(300x300)를 NaN으로 초기화
    - 주행 로그에서 X,Y,Z만 사용(소수점 버림), X-Z 중복은 첫 값 유지
    - occupancy_status=0 추가 후 저장
    """
    # 1) 300x300 격자 생성 (Y는 NaN)
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


drive_log_to_xyz_csv(input_csv_path, out_path)