각 변수에 저장되는 데이터 형태(구조)는 아래와 같습니다.

---

### 1. obstacles
- 타입: 리스트(list)
- 내용: 장애물 9개의 딕셔너리(dict) 목록 (입력 그대로)
- 예시:
```python
[
  {'x_min': 10, 'x_max': 20, 'z_min': 30, 'z_max': 40},
  {'x_min': 15, 'x_max': 25, 'z_min': 35, 'z_max': 120},
  # ... 총 9개
]
```

---

### 2. group1
- 타입: 리스트(list)
- 내용: obstacles의 복사본 (원본 순서 그대로)
- 예시: obstacles와 동일

---

### 3. a_group
- 타입: 리스트(list)
- 내용: z_max ≤ 100인 장애물만 모은 리스트 (원본 딕셔너리)
- 예시:
```python
[
  {'x_min': 10, 'x_max': 20, 'z_min': 30, 'z_max': 40},
  # ... z_max가 100 이하인 장애물들
]
```

---

### 4. b_group
- 타입: 리스트(list)
- 내용: 100 < z_max ≤ 200인 장애물만 모은 리스트 (원본 딕셔너리)
- 예시:
```python
[
  {'x_min': 15, 'x_max': 25, 'z_min': 35, 'z_max': 120},
  # ... z_max가 100 초과 200 이하인 장애물들
]
```

---

### 5. c_group
- 타입: 리스트(list)
- 내용: z_max > 200인 장애물만 모은 리스트 (원본 딕셔너리)
- 예시:
```python
[
  {'x_min': 18, 'x_max': 28, 'z_min': 38, 'z_max': 250},
  # ... z_max가 200 초과인 장애물들
]
```

---

### 6. group2
- 타입: 리스트(list)
- 내용: a_group(오름차순) + b_group(내림차순) + c_group(오름차순) 순서로 합친 리스트 (정렬된 장애물)
- 예시:
```python
[
  # a_group 정렬된 장애물들
  {'x_min': 10, 'x_max': 20, 'z_min': 30, 'z_max': 40},
  # ...
  # b_group 정렬된 장애물들
  {'x_min': 15, 'x_max': 25, 'z_min': 35, 'z_max': 120},
  # ...
  # c_group 정렬된 장애물들
  {'x_min': 18, 'x_max': 28, 'z_min': 38, 'z_max': 250},
  # ...
]
```

---

모든 리스트의 각 원소는 장애물 하나를 나타내는 딕셔너리입니다.  
정리:  
- obstacles, group1: 입력 순서  
- a_group, b_group, c_group: z_max 기준 그룹  
- group2: 그룹별 x_max 정렬 후 합친 최종 순서  
- 각 장애물: {'x_min', 'x_max', 'z_min', 'z_max'} 키를 가진 dict