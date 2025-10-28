import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.family'] = 'Malgun Gothic'

v = "50"

# 데이터 불러오기
df = pd.read_excel(f"research/body_control/path_planning/tank_turn_d/data/tank_d_turn_{v}.xlsx")
pos = df[["Time", "Player_Pos_X", "Player_Pos_Y", "Player_Pos_Z"]]

# 서브플롯 생성 (2행 1열)
fig, axes = plt.subplots(2, 1, figsize=(6,8))  # 2행 1열, 가로10, 세로12

# 첫 번째 그래프: 전체 이동 경로
axes[0].plot(pos["Player_Pos_X"], pos["Player_Pos_Z"], label="Tank Path", linewidth=2)
axes[0].set_xlabel("X Position (m)")
axes[0].set_ylabel("Z Position (m)")
axes[0].set_title("Tank Movement Trajectory (Top View)")
axes[0].legend()
axes[0].grid(True)

# 두 번째 그래프: 회전 구간 강조
turn_section = pos[(pos["Time"] >= 8.8) & (pos["Time"] <= 9.2)]
axes[1].plot(pos["Player_Pos_X"], pos["Player_Pos_Z"], color="gray", alpha=0.6, label="Overall Path")
axes[1].plot(turn_section["Player_Pos_X"], turn_section["Player_Pos_Z"], color="red", linewidth=3, label="Steering Phase (8.8~9.2s)")
axes[1].set_xlabel("X Position (m)")
axes[1].set_ylabel("Z Position (m)")
axes[1].set_title("Tank Path Highlighting Steering Phase")
axes[1].legend()
axes[1].grid(True)

plt.title(f'{v}km/h 주행시의 조향 Profile')
plt.tight_layout()
# plt.savefig(f'research/body_control/path_planning/tank_turn_d/study/visualization/tank_d_turn_{v}.png')
plt.show()
