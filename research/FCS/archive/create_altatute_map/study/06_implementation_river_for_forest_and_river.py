"""
forest and river의 원본 주행기록 (00_forest_and_river_map_info_scan_log)의 다음 작업에 들어가기 전에 적용할 것. 
"""

import numpy as np
import pandas as pd
import matplotlib as plt

file_to_read_name = "jobed_00_forest_and_river_map_info_scan_log.csv"
input_csv_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/" + file_to_read_name
out_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/jobed_00_forest_and_river_map_info_scan_log_fixed.csv"

#### csv를 읽어와서 데이터프레임에 저장
df = pd.read_csv(input_csv_path)

#### 금지구역들을 데이터 프레임에 주입 (x좌표, -5, z좌표, 1(occupancy_status))
def add_forbidden_area(df, x_min, x_max, z_min, z_max):
    """금지구역(x_min~x_max, z_min~z_max)에 해당하는 좌표를 occupancy=1로 추가"""
    xs = np.arange(x_min, x_max)
    zs = np.arange(z_min, z_max)
    xx, zz = np.meshgrid(xs, zs)
    area_df = pd.DataFrame({
        "Player_Pos_X": xx.flatten(),
        "Player_Pos_Y": 0,
        "Player_Pos_Z": zz.flatten(),
        "occupancy_status": np.ones(xx.size, dtype=int)
    })
    df = pd.concat([df, area_df], ignore_index=True)
    return df

#금지구역 1 : x값(150 ~ 210), z값(300 ~ 270) 사각형
df = add_forbidden_area(df, 150, 210, 270, 300)

#금지구역 2 : x값(180 ~ 240), z값(270 ~ 240) 사각형
df = add_forbidden_area(df, 180, 240, 240, 270)

#금지구역 3 : x값(180 ~ 270), z값(240 ~ 180) 사각형
df = add_forbidden_area(df, 180, 270, 180, 240)

#금지구역 4 : x값(210 ~ 270), z값(180 ~ 0) 사각형
df = add_forbidden_area(df, 210, 270, 0, 180)

#### 기존 데이터 프레임의 x와 z좌표가 같은 것들을 덮어씌우기
df = df.drop_duplicates(subset=["Player_Pos_X", "Player_Pos_Z"], keep="last")

#### 데이터프레임을 csv로 저장
df.to_csv(out_path, index=False)