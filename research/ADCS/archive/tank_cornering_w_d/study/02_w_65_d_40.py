# yaw_stable_visual.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fractions import Fraction
plt.rc("font", family="Malgun Gothic")

EXCEL_PATH = "source/research/body_control/path_planning/tank_cornering_w_d/input_data/w_65_d_40.xlsx"

W_WEIGHT = 65/65
D_WEIGHT = 40/65

frac_W = Fraction(W_WEIGHT).limit_denominator(65)
frac_D = Fraction(D_WEIGHT).limit_denominator(65)

SHEET_NAME = 0
TIME_COL = "Time"
X_COL = "Player_Pos_X"
Z_COL = "Player_Pos_Z"

df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
t = df[TIME_COL].to_numpy()
x = df[X_COL].to_numpy()
z = df[Z_COL].to_numpy()

dx = np.diff(x)
dz = np.diff(z)
t_mid = (t[1:] + t[:-1])/2
heading = np.arctan2(dz, dx)
heading = np.unwrap(heading)

# 각속도 계산
yaw_rate = np.gradient(heading, t_mid)  # rad/s
yaw_rate_deg = np.degrees(yaw_rate)     # rad/s => deg/s

# 원운동 안정 판단 (간단히 각속도 ±1 std 범위 유지)
yaw_mean = np.mean(yaw_rate_deg)
yaw_std = np.std(yaw_rate_deg)
stable_idx = np.where(np.abs(yaw_rate_deg - yaw_mean) <= yaw_std)[0]
start_idx = stable_idx[0]

# 반지름 계산
xc = np.mean(x[start_idx:])
zc = np.mean(z[start_idx:])
r = np.sqrt((x[start_idx+1:] - xc)**2 + (z[start_idx+1:] - zc)**2)

print("=== 원운동 안정 구간 분석 ===")
print(f"시작 시간: {t_mid[start_idx]:.2f} s")
print(f"반지름 평균: {np.mean(r):.2f}")
print(f"각속도 평균: {np.mean(yaw_rate_deg[start_idx:]):.2f} deg/s")

# 시각화
plt.figure(figsize=(12,6))

# Top view 궤적
plt.subplot(1,2,1)
plt.plot(x, z, label="Trajectory", linewidth=1.2)
plt.scatter(x[start_idx:], z[start_idx:], color="red", s=20, label="안정된 원운동 회전 구간")
plt.xlabel("X 좌표 현황")
plt.ylabel("Z 좌표 현황")
plt.title("탱크 이동 경로 (Top View)")
plt.axis('equal')
plt.grid(True)
plt.legend()

# 각속도 시계열 (안정 원운동 구간만)
plt.subplot(1,2,2)
plt.text(0.60, 0.60, f"평균 각속도: {np.mean(yaw_rate_deg[start_idx:]):.2f} deg/s\n(W weight : {frac_W})\n(D weight : {frac_D})",
         horizontalalignment='right',
         verticalalignment='top',
         transform=plt.gca().transAxes,
         fontsize=14,
         bbox=dict(facecolor='white', alpha=0.7, edgecolor='gray'))
plt.plot(t_mid[start_idx:], yaw_rate_deg[start_idx:], label="안정 원운동 구간 각속도 (deg/s)")
plt.xlabel("시간 [s]")
plt.ylabel("각속도 [deg/s]")
plt.title("안정 원운동 구간 각속도")
plt.grid(True)
plt.legend()

plt.tight_layout()
plt.savefig('source/research/body_control/path_planning/tank_cornering_w_d/output_data/w_65_d_40.png')
plt.show()