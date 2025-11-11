import pandas as pd
import numpy as np
from pathlib import Path

file_to_read_name = "jobed_00_forest_and_river_map_info_scan_log_fixed" + ".csv"
input_csv_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/" + file_to_read_name
out_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/filled_" + file_to_read_name


def impute_y_two_pass(df) -> pd.DataFrame:
    """
    1) 같은 X 내에서 Z축 정렬 후 Y 선형 보간
    2) 같은 Z 라인에서 X축 방향으로 한 번 더 보간
       (피벗 -> 가로보간 -> 역피벗)
    """
    df = df.copy()
    for c in ["Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["_orig_idx__"] = np.arange(len(df))

    # 1단계: X 그룹 내 Z-방향 보간
    def _interp_along_z(g):
        g = g.sort_values("Player_Pos_Z")
        g["Player_Pos_Y"] = g["Player_Pos_Y"].interpolate(method="linear", limit_direction="both")

        return g

    df1 = (
        df.sort_values(["Player_Pos_X", "Player_Pos_Z"])
          .groupby("Player_Pos_X", group_keys=False)
          .apply(_interp_along_z)
    )

    # 2단계: Z 라인별 X-방향 보간
    pivot = (
        df1.pivot(index="Player_Pos_Z", columns="Player_Pos_X", values="Player_Pos_Y")
           .sort_index(axis=0)  # Z 오름차순
           .sort_index(axis=1)  # X 오름차순
    )

    pivot2 = pivot.interpolate(axis=1, method="linear", limit_direction="both")


    filled_long = pivot2.stack().rename("Player_Pos_Y").reset_index()

    out = (
        df1.drop(columns=["Player_Pos_Y"])
           .merge(filled_long, on=["Player_Pos_Z", "Player_Pos_X"], how="left")
           .sort_values("_orig_idx__")
           .drop(columns=["_orig_idx__"])
           .reset_index(drop=True)
    )
    return out

def checking_missing_values(in_path, out_path):
    """
    - 파일 로드 → 2단계 보간 → 저장
    """
    df = pd.read_csv(in_path)
    df.columns = [c.strip() for c in df.columns]

    before_na = df["Player_Pos_Y"].isna().sum()
    df_out = impute_y_two_pass(df)
    after_na = df_out["Player_Pos_Y"].isna().sum()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # 기존 데이터 프레임의 x와 z좌표가 같은 것들을 덮어씌우기
    df_out = df_out.drop_duplicates(subset=["Player_Pos_X", "Player_Pos_Z"], keep="last")


    df_out.to_csv(out_path, index=False)


    print("[메서드2] Imputation Summary")
    print(f" - rows_total        : {len(df)}")
    print(f" - y_missing_before  : {before_na}")
    print(f" - y_missing_after   : {after_na}")
    print(f" - saved -> {out_path}")
    return out_path


imputed_path = checking_missing_values(input_csv_path, out_path)