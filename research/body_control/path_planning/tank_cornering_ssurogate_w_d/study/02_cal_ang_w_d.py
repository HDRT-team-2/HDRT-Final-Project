"""
각 데이터 엑셀 파일들의 
최대 속도(W웨이트값으로 제어) 주행시
조향했을 때(D웨이트값으로 제어)
전차의 각속도를 계산하는 파일입니다.

surrogate model을 만들기 위해, 각 W와 D의 웨이트값(input)에 대한 각속도(output)을 여러번의 실험 데이터로 참고하기 위함입니다.
surrogate model이란,
                (linear regression과 동일한 개념과 원리이되, 1차원의 직선 형태의 회귀선이 아닌, 
                3차원의 곡평면 형태로 입력 데이터에 대한 예측 회귀 방정식 그래프라 이해하시면 됩니다.)

해당 코드파일을 Run하기 위해서는, 
tank_cornering_surrogate_w_d 폴더 내의 데이터 폴더에서의 엑셀 파일명의 뒤 w와 d에 해당하는 부분만 수치를 바꿔주시면 run 할 수 있습니다.
해당 W와 D의 실험 웨이트값 폴더 형태는 24 ~ 44번 line을 참고하실 수 있으며, 이 참고값은 주석처리 해놨습니다.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.rc("font", family="Malgun Gothic")

W_WEIGHT = 10
D_WEIGHT = 42

# OLHS 20점 샘플링 결과 (w_weight, d_weight) - 분모 65 기준:
#  1: w = 46/65, d = 43/65  완료
#  2: w = 63/65, d = 59/65  완료
#  3: w = 42/65, d = 34/65  완료
#  4: w = 51/65, d = 49/65  완료
#  5: w = 59/65, d = 62/65  완료
#  6: w = 3/5, d = 14/65    완료
#  7: w = 23/65, d = 29/65  완료
#  8: w = 43/65, d = 6/65   완료
#  9: w = 1/65, d = 9/65    완료
# 10: w = 4/65, d = 2/65    완료
# 11: w = 27/65, d = 25/65  완료
# 12: w = 23/65, d = 48/65  완료
# 13: w = 35/65, d = 31/65  완료
# 14: w = 31/65, d = 17/65  완료
# 15: w = 58/65, d = 58/65  완료
# 16: w = 19/65, d = 38/65  완료
# 17: w = 13/65, d = 53/65  완료
# 18: w = 16/65, d = 11/65  완료
# 19: w = 10/65, d = 42/65  완료
# 20: w = 54/65, d = 21/65  완료

EXCEL_PATH = f"research/body_control/path_planning/tank_cornering_ssurogate_w_d/data/w_{W_WEIGHT}_d_{D_WEIGHT}.xlsx"


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
plt.text(0.60, 0.60, f"평균 각속도: {abs(np.mean(yaw_rate_deg[start_idx:])):.4f} deg/s\n(W weight : {W_WEIGHT}/65)\n(D weight : {D_WEIGHT}/65)",
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
# plt.savefig(f'source/research/body_control/tank_cornering_ssurogate_w_d/w_{W_WEIGHT}_d_{D_WEIGHT}_omega_{abs(np.mean(yaw_rate_deg[start_idx:])):.4f}.png')
plt.show()