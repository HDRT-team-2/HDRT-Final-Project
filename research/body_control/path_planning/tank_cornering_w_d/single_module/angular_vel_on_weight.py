"""
W에 대한 웨이트값 65/65 고정,
D에 대한 웨이트에 대해 변화를 주며 각속도를 계산하기 위한 코드입니다.
실험은 네번, D에 대한 웨이트값은 변화를 주었습니다.
30/65, 40/65, 50/65, 65/65
에 대해서만 진행했고 이 네 번의 결과에 대한 선형회귀 결과 도출 코드파일입니다.
"""
import numpy as np
import matplotlib.pyplot as plt
plt.rc("font", family="Malgun Gothic")

# 데이터
d_weight = np.array([30/65, 40/65, 50/65, 65/65])
ang_vel = np.array([18.47, 24.64, 30.67, 39.74])

# 선형회귀 계산 (1차 방정식 y = a*x + b)
coeffs = np.polyfit(d_weight, ang_vel, 1)  # 1차식
a, b = coeffs
print("=== 선형회귀 결과 ===")
print(f"y = {a:.3f} * x + {b:.3f}")

# 전체 범위 시각화
x_plot = np.linspace(1/65, 65/65, 200)  # 1/65 ~ 65/65
y_plot = a * x_plot + b

# 시각화
plt.figure(figsize=(8,5))
plt.scatter(d_weight, ang_vel, color="blue", label="원 데이터")
plt.plot(x_plot, y_plot, color="red", label=f"선형회귀: Angular Velocity={a:.2f} * D_weight + {b:.2f} (단위 : degree/second)")
plt.xlabel("입력값 D에 대한 weight의 변화")
plt.ylabel("angular velocity [deg/s = ]")
plt.title("65km/h에서 실시\nD의 weight v.s Angular Velocity 선형회귀 ")
plt.grid(True)
plt.legend()
plt.savefig('source/research/body_control/path_planning/tank_cornering_w_d/linear_regression_consequnce.png')
plt.show()
# angular_velocity = 40.372 * (D_weight) + -0.494 (단위 : degree/second)