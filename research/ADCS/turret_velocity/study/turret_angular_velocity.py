import pandas as pd
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import numpy as np
plt.rcParams['font.family'] = 'Malgun Gothic'

# 데이터 불러오기
df = pd.read_excel("source/research/body_control/path_planning/turret_velocity/input_data/turret_angular_velocity.xlsx")

time_sec = df["Time"].values
angle_deg = df["Player_Turret_X"].values

# 360도 => 0도 점프 문제 해결
angle_unwrapped = np.rad2deg(np.unwrap(np.deg2rad(angle_deg)))

# 각속도 계산 (deg/s)
dt = np.diff(time_sec)
angular_velocity = np.diff(angle_unwrapped) / dt

# 각가속도 계산 (deg/s²)
angular_acceleration = np.diff(angular_velocity) / dt[1:]

# 각도 선형 회귀
model = LinearRegression()
model.fit(time_sec.reshape(-1, 1), angle_unwrapped)
pred_angle = model.predict(time_sec.reshape(-1, 1))

# 시각화
plt.figure(figsize=(12, 9))

# 각도
plt.subplot(3, 1, 1)
plt.scatter(time_sec, angle_unwrapped, color='blue', s=15, label="포탑 각도")
plt.plot(time_sec, pred_angle, color='red', linestyle='--', label="선형 회귀")
plt.ylabel("각도 (°)")
plt.title("포탑 회전 각도 / 각속도 / 각가속도")
plt.legend()
plt.grid(True)

# 각속도
plt.subplot(3, 1, 2)
plt.plot(time_sec[:-1], angular_velocity, color='green', label="포탑 각속도")
plt.ylabel("각속도 (°/s)")
plt.legend()
plt.grid(True)

# 각가속도
plt.subplot(3, 1, 3)
plt.plot(time_sec[:-2], angular_acceleration, color='purple', label="포탑 각가속도")
plt.xlabel("시간 (s)")
plt.ylabel("각가속도 (°/s²)")
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.savefig('source/research/body_control/path_planning/turret_velocity/output_data/consequence.png')
plt.show()

# 콘솔 출력
print("포탑 각도 선형 회귀 결과")
print(f"회귀식: 각도 = {model.coef_[0]:.5f} × 시간 + {model.intercept_:.2f}")
print(f"결정계수(R²): {model.score(time_sec.reshape(-1,1), angle_unwrapped):.5f}")
print(f"평균 추정 각속도: {model.coef_[0]:.5f} °/s\n")

print("포탑 각속도 통계")
print(f"평균 각속도: {np.mean(angular_velocity):.5f} °/s")
print(f"각속도 표준편차: {np.std(angular_velocity):.5f} °/s\n")

print("포탑 각가속도 통계")
print(f"평균 각가속도: {np.mean(angular_acceleration):.5f} °/s²")
print(f"각가속도 표준편차: {np.std(angular_acceleration):.5f} °/s²")
