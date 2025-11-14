# 베이스맵 생성 연구 아카이브

## 개요

전장 지도를 단순화된 베이스맵으로 변환하고 고도 등고선을 추가하는 연구 과정을 정리한 디렉토리입니다.

**연구 목표**: 위성/정찰 지도 → 단순화된 베이스맵 + 등고선

## 연구 순서

### 1단계: 베이스맵 생성 (`01_basemap_generation/`)

지형지물(물, 숲, 길, 건물 등)을 구분하여 색상이 단순화된 베이스맵을 생성하는 다양한 접근 방법을 실험했습니다.

#### 01. CV 색상 범위 기반 (`01_cv/`)
- **방법**: OpenCV 색상 범위 임계값을 이용한 규칙 기반 세그멘테이션
- **파일**: `to_simple_map.py`
- **특징**: 초기 실험, 단순 색상 범위로 지형 분류
- **한계**: 색상 범위 특정 및 일반화 어려움

#### 02. HSV 색상 기반 (`02_hsv_color_based/`)
- **방법**: HSV 색상 공간에서 더 정교한 색상 범위 설정
- **파일**: `to_simple_map_hsv.py`, `analyze_colors.py`
- **특징**: RGB보다 색상 구분이 명확한 HSV 색상 공간 활용
- **한계**: 여전히 규칙 기반이라 복잡한 지형에 한계

#### 03. FastSAM 자동 세그멘테이션 (`03_fastsam/`)
- **방법**: FastSAM 딥러닝 모델을 이용한 자동 이미지 세그멘테이션
- **파일**: `fastsam_segmentation.py`
- **특징**: 사전 학습된 모델로 객체 자동 분할
- **한계**: 지형지물 클래스 분류 불가, 추가 라벨링 필요

#### 04. 수동 라벨링 + Random Forest - 기본 (`04_manual_labeling_rf/`)
- **방법**: 수동 라벨링 데이터 + Random Forest 분류기
- **파일**: `train_basemap.py`, `label_tool.py`
- **특징**: RGB + HSV 6차원 특징 벡터 사용
- **라벨**: 배경, 물, 돌, 건물, 길, 나무 (6개 클래스)
- **색상**: 배경(230,230,230), 물(105,195,255), 돌(150,150,150), 건물(154,157,173), 길(253,255,135), 나무(141,201,141)
- **개선점**: 규칙 기반 대비 일반화 성능 향상

#### 05. 수동 라벨링 + Random Forest - 클래스 확장 (`05_manual_labeling_rf/`)
- **방법**: 클래스 추가로 재라벨링 후 학습
- **파일**: `train_basemap.py`, `label_tool.py`
- **특징**: RGB + HSV 6차원 특징 벡터
- **라벨**: 배경, 물, 돌, 건물, 길, 숲, 땅 (7개 클래스)
- **색상**: 04와 동일한 색상 팔레트 사용, 숲(141,201,141), 땅(250,233,210) 추가
- **개선점**: 땅 클래스 추가로 더 세밀한 분류

#### 06. 수동 라벨링 + Random Forest - 색상 조정 (`06_manual_labeling_rf/`)
- **방법**: 동일한 7개 클래스로 재라벨링 후 학습
- **파일**: `train_basemap.py`, `label_tool.py`
- **특징**: RGB + HSV 6차원 특징 벡터
- **라벨**: 배경, 물, 돌, 건물, 길, 숲, 땅 (7개 클래스)
- **색상**: 04~05와 동일 (배경 230, 물 105/195/255, 돌 150, 건물 154/157/173, 길 253/255/135, 숲 141/201/141, 땅 250/233/210)

#### 07. 수동 라벨링 + Random Forest - 최종 색상 변경 (`07_manual_labeling_rf_color_change/`)
- **방법**: 06의 라벨링 데이터 사용, 출력 색상만 변경
- **파일**: `train_basemap.py`
- **특징**: RGB + HSV 6차원 특징 벡터
- **라벨**: 배경, 물, 돌, 건물, 길, 숲, 땅 (7개 클래스, 06과 동일)
- **색상 변경**: 최종 색상 팔레트 적용 (배경 230, 물 105/195/255, 돌 150, 건물 154/157/173, 길 253/255/135, 숲 141/201/141, 땅 250/233/210)
- **결과**: 베이스맵 생성 완료

### 2단계: 등고선 오버레이 (`02_contour_overlay/`)

생성된 베이스맵에 고도 등고선을 추가하는 다양한 필터링 기법을 실험했습니다.

#### 01. 기본 등고선 (`01_contour_overlay_base/`)
- **방법**: 고도 데이터를 그리드로 보간 후 등고선 생성
- **파일**: `add_contours.py`
- **특징**: 필터링 없이 순수 등고선만 추가
- **문제**: 노이즈가 많고 등고선이 지저분함

#### 02. RMS 필터 (`02_contour_overlay_rms_filter/`)
- **방법**: RMS(Root Mean Square) 필터로 고도 데이터 스무딩
- **파일**: `add_contours.py`
- **특징**: `uniform_filter`로 평균 제곱근 계산, window_size=5
- **수식**: RMS = sqrt(평균(값²))
- **개선점**: 노이즈 감소, 하지만 디테일도 일부 손실

#### 03. Savitzky-Golay 필터 (window=21, order=3) (`03_contour_overlay_savgol_w21_i3/`)
- **방법**: Savitzky-Golay 필터로 고도 데이터 스무딩
- **파일**: `add_contours.py`
- **특징**: 
  - `window_length = 21` (홀수)
  - `polyorder = 3` (다항식 차수)
  - 각 행/열에 독립적으로 필터 적용 (양방향)
- **개선점**: 곡선 형태 유지하면서 노이즈 제거
- **장점**: RMS 필터 대비 지형 디테일 보존

#### 04. Savitzky-Golay 필터 (window=31, order=3) (`04_contour_overlay_savgol_w31_i2/`)
- **방법**: Savitzky-Golay 필터, 더 큰 윈도우 사용
- **파일**: `add_contours.py`
- **특징**:
  - `window_length = 31` (03보다 큰 윈도우)
  - `polyorder = 3`
  - 양방향 필터 적용
- **개선점**: 더 부드러운 등고선
- **트레이드오프**: 스무딩 강도 증가, 디테일 약간 감소

#### 05. Savitzky-Golay 필터 (window=31, order=2) - 세밀 조정 (`05_contour_overlay_savgol_details/`)
- **방법**: Savitzky-Golay 필터, 다항식 차수 조정
- **파일**: `add_contours.py`
- **특징**:
  - `window_length = 31`
  - `polyorder = 2` (04보다 낮은 차수)
  - 양방향 필터 적용
- **개선점**: 더 자연스러운 곡선
- **목적**: 등고선 품질 미세 조정

#### 06. Savitzky-Golay + 라벨 표시 (interval=2) (`06_contour_overlay_savgol_w31_i2_lables/`)
- **방법**: Savitzky-Golay 필터 + 등고선 라벨 추가
- **파일**: `add_contours.py`
- **특징**:
  - `window_length = 31`, `polyorder = 2`
  - `interval = 2` (2m 간격 등고선)
  - `label_interval = 2` (모든 등고선에 라벨 표시)
  - 양방향 필터 적용
- **개선점**: 등고선에 고도 수치 표시로 가독성 향상

#### 07. Savitzky-Golay + 라벨 표시 (interval=1) (`07_contour_overlay_savgol_w31_i1_labels/`)
- **방법**: Savitzky-Golay 필터 + 더 촘촘한 등고선
- **파일**: `add_contours.py`
- **특징**:
  - `window_length = 31`, `polyorder = 2`
  - `interval = 1` (1m 간격 등고선, 더 세밀)
  - `label_interval = 2` (2m마다 라벨 표시)
  - 양방향 필터 적용
- **개선점**: 더 상세한 지형 표현

## 디렉토리 구조

```
base_map/
├── README.md                                      # 이 파일
├── label_tool.py                                  # 수동 라벨링 도구
├── train_basemap.py                               # 최종 학습 스크립트 (루트)
├── add_contours.py                                # 최종 등고선 추가 스크립트 (루트)
├── labeled_masks/                                 # 라벨링된 마스크 데이터
├── basemaps/                                      # 최종 생성된 베이스맵
├── 01_basemap_generation/
│   ├── 01_cv/                                    # CV 색상 범위 기반
│   │   └── to_simple_map.py
│   ├── 02_hsv_color_based/                       # HSV 색상 기반
│   │   ├── to_simple_map_hsv.py
│   │   └── analyze_colors.py
│   ├── 03_fastsam/                               # FastSAM 자동 세그멘테이션
│   │   ├── fastsam_segmentation.py
│   │   ├── FastSAM-s.pt
│   │   └── results_fastsam/
│   ├── 04_manual_labeling_rf/                    # RF 기본 (6클래스)
│   │   ├── train_basemap.py
│   │   ├── label_tool.py
│   │   ├── labeled_masks/
│   │   ├── models/
│   │   └── results/
│   ├── 05_manual_labeling_rf/                    # RF 클래스 확장 (7클래스)
│   │   ├── train_basemap.py
│   │   ├── label_tool.py
│   │   ├── labeled_masks/
│   │   ├── models/
│   │   └── results/
│   ├── 06_manual_labeling_rf/                    # RF 색상 조정 (회색톤)
│   │   ├── train_basemap.py
│   │   ├── label_tool.py
│   │   ├── labeled_masks/
│   │   ├── models/
│   │   └── results/
│   └── 07_manual_labeling_rf_color_change/       # RF 최종 색상
│       ├── train_basemap.py
│       ├── label_tool.py
│       ├── labeled_masks/
│       ├── models/
│       └── results/
└── 02_contour_overlay/
    ├── add_contours.py                           # 루트 등고선 스크립트
    ├── basemaps/                                 # 입력 베이스맵들
    ├── 01_contour_overlay_base/                  # 기본 등고선
    │   ├── add_contours.py
    │   └── results/
    ├── 02_contour_overlay_rms_filter/            # RMS 필터
    │   ├── add_contours.py
    │   └── results/
    ├── 03_contour_overlay_savgol_w21_i3/         # Savgol w=21, o=3
    │   ├── add_contours.py
    │   └── results/
    ├── 04_contour_overlay_savgol_w31_i2/         # Savgol w=31, o=3
    │   ├── add_contours.py
    │   └── results/
    ├── 05_contour_overlay_savgol_details/        # Savgol w=31, o=2
    │   ├── add_contours.py
    │   └── results/
    ├── 06_contour_overlay_savgol_w31_i2_lables/  # Savgol + 라벨 (interval=2)
    │   ├── add_contours.py
    │   └── results/
    └── 07_contour_overlay_savgol_w31_i1_labels/  # Savgol + 라벨 (interval=1)
        ├── add_contours.py
        └── results/
```

## 데이터 경로

모든 스크립트는 상대 경로를 사용하여 다음 데이터에 접근합니다:

- **원본 지도 이미지**: `../../../map_images/` (base_map 기준 3단계 위)
- **라벨링된 마스크**: 각 실험 폴더 내 `labeled_masks/` 또는 루트 `labeled_masks/`
- **베이스맵 출력**: 각 실험 폴더 내 `basemaps/` 또는 `results/`
- **고도 데이터**: `../../../map_altitude_300/` (CSV 파일들)
- **등고선 결과**: 각 02_contour_overlay 하위 폴더의 `results/`

## 연구 결론

### 베이스맵 생성
1. **규칙 기반 (01_cv, 02_hsv_color_based)**: 
   - 장점: 빠른 실험, 코드 간단
   - 단점: 일반화 어려움, 조명 변화에 취약
   
2. **딥러닝 자동화 (03_fastsam)**:
   - 장점: 자동 세그멘테이션
   - 단점: 지형 클래스 분류 불가
   
3. **수동 라벨링 + 머신러닝 (04~07)**:
   - 장점: 가장 높은 정확도, 일반화 가능
   - 단점: 초기 라벨링 시간 필요
   - **최종 선택**: 07_manual_labeling_rf_color_change

### 등고선 오버레이
1. **필터링 없음 (01_contour_overlay_base)**:
   - 문제: 노이즈 심함
   
2. **RMS 필터 (02_contour_overlay_rms_filter)**:
   - 개선: 노이즈 감소
   - 문제: 디테일 손실
   
3. **Savitzky-Golay 필터 (03~07)**:
   - 장점: 곡선 형태 유지하면서 스무딩
   - 파라미터 실험:
     - window: 21 → 31 (더 부드러움)
     - order: 3 → 2 (더 자연스러움)
   - 등고선 간격 실험:
     - 06: interval=2m, 모든 등고선에 라벨
     - 07: interval=1m, 2m마다 라벨 (더 상세)
   - **최종 선택**: 용도에 따라 선택
     - 05: 깔끔한 등고선 (라벨 없음)
     - 06: 가독성 중시 (2m 간격)
     - 07: 상세도 중시 (1m 간격)
