"""
최적설계 과정을 시행해봤습니다.
1. 샘플링 기법 선택 - DOE(Design Of Experiment)
- sampling_lhs 파일입니다. LHS(Latin HyperCube) method
2. 샘플링된 샘플들을 활용한 실험 
- cal_ang_w_d 파일입니다 20개 W, D 웨이트값들에 대해 각가속도 실험을 한 결과 도출 코드입니다.
3. Surrogate Model 도출
- 아이디어와 방식은 선형회귀와 동일합니다. 다만, 1차원의 직선이 아닌 3차원의 곡평면 형태로 인풋에 대한 아웃풋을 도출해냅니다.
- 선형회귀보다 더 정확한 각속도 output을 도출해낼 수 있을 것입니다.
- 해당 코드파일은 output들을 서로게이트 모델로 회귀시키고 예측값을 내는 모델 생성 코드입니다.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error
from mpl_toolkits.mplot3d import Axes3D
plt.rc("font", family="Malgun Gothic")

# 데이터 로드
# Build paths relative to this script so it works when executed from any CWD
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
EXCEL_PATH = os.path.join(
    BASE_DIR,
    "source",
    "research",
    "body_control",
    "path_planning",
    "tank_cornering_surrogate_w_d",
    "input_data",
    "experiment_data.xlsx",
)
df = pd.read_excel(EXCEL_PATH)

X = df[['w_weight','d_weight']].values
y = df['omega'].values

# RSM(2차 다항) 생성 및 학습
poly = PolynomialFeatures(degree=2, include_bias=True)
X_poly = poly.fit_transform(X)  # columns: [1, w, d, w^2, w*d, d^2]

model = LinearRegression(fit_intercept=False)
model.fit(X_poly, y)
y_pred = model.predict(X_poly)

# 성능 지표
r2 = r2_score(y, y_pred)
rmse = np.sqrt(mean_squared_error(y, y_pred))
print(f"RSM (2차 다항식) fit results:")
print(f"  R^2   = {r2:.4f}")
print(f"  RMSE  = {rmse:.4f}")

# 회귀 계수 확인 (연결된 폴리 항 순서 확인)
feature_names = poly.get_feature_names_out(['w_weight','d_weight'])
coefs = model.coef_
print("\nModel terms and coefficients:")
for name, c in zip(feature_names, coefs):
    print(f"  {name:10s} : {c:+.6e}")

# 그리드 예측 (시각화를 위한 격자)
w_lin = np.linspace(df['w_weight'].min(), df['w_weight'].max(), 60)
d_lin = np.linspace(df['d_weight'].min(), df['d_weight'].max(), 60)
W, D = np.meshgrid(w_lin, d_lin)
X_grid = np.column_stack([W.ravel(), D.ravel()])
Xg_poly = poly.transform(X_grid)
Yg = model.predict(Xg_poly).reshape(W.shape)

# 시각화
plt.figure(figsize=(12,9))

# 데이터 좌표를 포함한 3D 이미지
ax = plt.subplot(2,2,1, projection='3d')
surf = ax.plot_surface(W, D, Yg, cmap='viridis', alpha=0.8, linewidth=0, antialiased=True)
ax.scatter(df['w_weight'], df['d_weight'], df['omega'], color='r', s=40, label='data')
ax.set_xlabel('w_weight'); ax.set_ylabel('d_weight'); ax.set_zlabel('omega')
ax.set_title('2차 다항식으로 표현된 RSM surrogate model 생성 결과')
ax.legend()
plt.colorbar(surf, ax=ax, shrink=0.5, aspect=8)

# contour (top view)
ax2 = plt.subplot(2,2,2)
cont = ax2.contourf(W, D, Yg, levels=30, cmap='viridis')
ax2.scatter(df['w_weight'], df['d_weight'], c='r', s=30)
ax2.set_xlabel('w_weight'); ax2.set_ylabel('d_weight')
ax2.set_title('RSM contour (예측)')
plt.colorbar(cont, ax=ax2)

# 예측 V.S 실제
ax3 = plt.subplot(2,2,3)
ax3.scatter(y, y_pred, s=40)
mn = min(min(y), min(y_pred)); mx = max(max(y), max(y_pred))
ax3.plot([mn,mx],[mn,mx],'k--', linewidth=1)
ax3.set_xlabel('실제 각속도'); ax3.set_ylabel('예측된 각속도')
ax3.set_title('예측 V.S 실제')

# 잔차
ax4 = plt.subplot(2,2,4)
residuals = y - y_pred
ax4.scatter(range(len(y)), residuals, s=30)
ax4.axhline(0, color='k', linestyle='--')
ax4.set_xlabel('sample index'); ax4.set_ylabel('residual (y - y_pred)')
ax4.set_title('잔차')

plt.tight_layout()
# Save figure to output dir (script-relative)
OUT_DIR = os.path.join(
    BASE_DIR,
    "source",
    "research",
    "body_control",
    "path_planning",
    "tank_cornering_surrogate_w_d",
    "output_data",
)
os.makedirs(OUT_DIR, exist_ok=True)
plt.savefig(os.path.join(OUT_DIR, 'surrogate_model_completed.png'))
plt.show()

# 모델 저장 / 예측 csv 저장
# df_pred_grid = pd.DataFrame({'w_weight': X_grid[:,0], 'd_weight': X_grid[:,1], 'y_pred': Yg.ravel()})
# df_pred_grid.to_excel('rsm_prediction_grid.xlsx', index=False)

# Surrogate 모델 수식 출력 (2차 다항식)
terms = poly.get_feature_names_out(['w_weight','d_weight'])
coefs = model.coef_

# 수식 문자열 만들기
equation = "omega = "
for coef, term in zip(coefs, terms):
    sign = "+" if coef >= 0 else "-"
    equation += f" {sign} {abs(coef):.6f}*{term}"

print("\n2차 다항식 RSM surrogate 모델 수식:")
print(equation)

# omega =  - 0.003936*1 - 0.002758*w_weight + 0.619642*d_weight + 0.000012*w_weight^2 + 0.000105*w_weight * d_weight - 0.000167*d_weight^2