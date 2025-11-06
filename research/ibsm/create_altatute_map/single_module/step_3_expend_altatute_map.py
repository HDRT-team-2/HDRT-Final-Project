"""
시뮬레이터에서 추출한 주행 로그를 3단계 가공하는 코드

credit by : oixxta

2단계 가공된 csv와 비교해서 3000*3000으로 가장 넓지만, 대신 무겁다는 단점이 있음.

반드시, 2단계 가공이 완료된 csv 파일을 이용할 것.
file_to_read_name에 2단계 가공이 완료된 csv파일의 이름을,
input_csv_path에 2단계 가공이 완료된 csv파일의 경로를,
out_path에 3단계 가공된 csv 파일이 저장될 경로를 지정할 것.
"""

import numpy as np
import pandas as pd


file_to_read_name = "filled_jobed_00_forest_and_river_map_info_scan_log_fixed" + ".csv"
input_csv_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/" + file_to_read_name
out_path = "C:/Users/msi/OneDrive/바탕 화면/Jongseong KIM/final_project/HDRT-Final-Project/research/ibsm/create_altatute_map/sutdy/original_drive_log/expended_" + file_to_read_name


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

    # 3000 * 3000으로 확장된 csv 파일 저장
    expanded_df.to_csv(out_path, index=False)

    print("expend_altatute_map has been complete")

expend_altatute_map(input_csv_path, out_path)