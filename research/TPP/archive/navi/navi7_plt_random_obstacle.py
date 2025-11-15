# -*- coding: utf-8 -*-
"""
오프라인 전차 경로탐색 + 이동 시뮬레이션 (A*, 8방향, 옥타일 휴리스틱)
- 시작점: (30, 30) 고정
- 목표점: (280, 280) 고정
- 장애물: 20x20 정사각형, 개수만 입력 받아 랜덤 배치
- 배치 규칙: 시작/목표 주변(팽창 고려) 및 서로 겹치지 않도록 배치
- 경로계획: 장애물 최소거리 3칸(그리드) 여유 확보(장애물 팽창)
- A* 후 가시선(LOS) 직선화 → matplotlib 애니메이션 이동
"""

import math
import heapq
import time
from typing import List, Tuple, Set

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

# ================== 전역 파라미터 ==================
GRID_W, GRID_H = 300, 300        # 300 x 300 (1셀 = 1 단위)
ALLOW_DIAGONAL = True            # 8방향
OBST_SIZE      = 30              # 장애물 한 변 길이 (정사각형)
OBST_HALF      = OBST_SIZE // 2  # 10
CLEARANCE      = 5               # 장애물과 최소거리 3칸(팽창 반경)
REACH_DIST     = 1.5             # 웨이포인트 도달 반경 (시각화용)
TANK_SPEED     = 4.0             # 셀/초 (시각화 이동 속도)
DT             = 0.03            # 시뮬레이션 프레임 시간(초)

START          = (30, 30)
GOAL           = (280, 280)

# 랜덤 재현성을 원하면 주석 해제
RANDOM_SEED    = None  # 예: 42

# ================== 유틸 함수 ==================
def in_bounds(x, y):
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def neighbors(x, y):
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x+dx, y+dy
        if in_bounds(nx, ny):
            yield nx, ny

def heuristic(a, b):
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)   # 옥타일 휴리스틱
    else:
        return dx + dy

# ================== 장애물 반영 ==================
def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    """
    중심(cx,cy)와 반경 half(절반 변 길이)로 정사각형을 막힌 영역으로 표시.
    half = 10 → 20x20, half = 13 → 26x26 등
    """
    x0, x1 = cx - half, cx + half - 1
    y0, y1 = cy - half, cy + half - 1
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            if in_bounds(x, y):
                blocked.add((x, y))

def rect_overlap(c1: Tuple[int,int], half1: int, c2: Tuple[int,int], half2: int) -> bool:
    """두 정사각형 중심/반경(half) 기준으로 축정렬 박스 겹침 여부."""
    (x1, y1), (x2, y2) = c1, c2
    return (abs(x1 - x2) < (half1 + half2)) and (abs(y1 - y2) < (half1 + half2))

def safe_center_range(half: int):
    """정사각형이 경계를 넘지 않도록 중심 좌표 범위 생성."""
    return (half, GRID_W - half - 1), (half, GRID_H - half - 1)

def generate_random_obstacles(count: int,
                              start: Tuple[int,int],
                              goal: Tuple[int,int],
                              obst_half: int,
                              clearance: int,
                              max_tries_per_obst: int = 500) -> List[Tuple[int,int]]:
    """
    무작위 장애물 중심 좌표 생성.
    - 실제 장애물 half = OBST_HALF
    - 충돌/배치 판단은 '팽창된 반경':  infl_half = obst_half + clearance
    - 시작/목표 지점도 infl_half를 적용해 충돌 금지
    - 서로 간에도 infl_half 기준으로 겹치지 않게
    """
    rng = np.random.default_rng(RANDOM_SEED)
    infl_half = obst_half + clearance
    (xmin, xmax), (ymin, ymax) = safe_center_range(infl_half)

    centers: List[Tuple[int,int]] = []
    tries_total = 0

    for _ in range(count):
        placed = False
        for _ in range(max_tries_per_obst):
            tries_total += 1
            cx = int(rng.integers(xmin, xmax + 1))
            cy = int(rng.integers(ymin, ymax + 1))

            # 시작/목표와 충돌 금지(팽창 반경으로 검사)
            if rect_overlap((cx, cy), infl_half, start, infl_half):  # start도 여유 반경만큼 피해 두기
                continue
            if rect_overlap((cx, cy), infl_half, goal, infl_half):
                continue

            # 기존 장애물과도 겹치지 않게
            ok = True
            for (px, py) in centers:
                if rect_overlap((cx, cy), infl_half, (px, py), infl_half):
                    ok = False
                    break
            if not ok:
                continue

            centers.append((cx, cy))
            placed = True
            break

        if not placed:
            print("⚠️  충분한 빈 공간을 찾지 못해 일부 장애물은 배치하지 못했습니다.")
            break

    if tries_total > 0:
        pass  # 필요하면 진단 출력 가능

    return centers

# ================== A* 경로계획 ==================
def astar(start: Tuple[int,int], goal: Tuple[int,int], blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if start == goal:
        return [start]
    if start in blocked or goal in blocked:
        return []

    D2 = math.sqrt(2.0)
    g = {start: 0.0}
    f = {start: heuristic(start, goal)}
    came = {}
    pq = [(f[start], start)]
    seen = set()

    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen:
            continue
        seen.add(cur)

        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path

        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx, ny) in blocked:
                continue
            step_cost = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step_cost
            if ng < g.get((nx, ny), 1e18):
                came[(nx, ny)] = cur
                g[(nx, ny)] = ng
                f[(nx, ny)] = ng + heuristic((nx, ny), goal)
                heapq.heappush(pq, (f[(nx, ny)], (nx, ny)))
    return []

# ================== 가시선(Line-of-Sight) 직선화 ==================
def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x, y)
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x += sx
        if e2 <= dx:
            err += dx; y += sy

def line_blocked(p0, p1, blocked):
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked and c not in (p0, p1):
            return True
    return False

def simplify_path_los(path_points, blocked):
    if not path_points:
        return []
    simp = [path_points[0]]
    i = 0
    while i < len(path_points) - 1:
        j = i + 1
        while j + 1 < len(path_points) and not line_blocked(path_points[i], path_points[j + 1], blocked):
            j += 1
        simp.append(path_points[j])
        i = j
    return simp

# ================== 시뮬레이션/시각화 ==================
def simulate_and_plot(centers, start, goal, path):
    import matplotlib.pyplot as plt
    from matplotlib import patches

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.set_title("Tank Path Planning (with 3-cell Clearance) & Simulation")
    ax.set_xlim(0, GRID_W)
    ax.set_ylim(0, GRID_H)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)

    # 장애물 시각화: 실제 20x20(짙은 회색) + 팽창(옅은 빨간 테두리)
    for (cx, cy) in centers:
        # 실제 장애물
        ax.add_patch(
            patches.Rectangle(
                (cx - OBST_HALF, cy - OBST_HALF),
                OBST_SIZE, OBST_SIZE,
                linewidth=1, edgecolor='k', facecolor='0.6', alpha=0.9
            )
        )
        # 팽창 영역(경로계획에 사용)
        infl_half = OBST_HALF + CLEARANCE
        ax.add_patch(
            patches.Rectangle(
                (cx - infl_half, cy - infl_half),
                2 * infl_half, 2 * infl_half,
                linewidth=1.2, edgecolor='tab:red', facecolor='none', linestyle='--', alpha=0.9
            )
        )

    # 경로
    if len(path) >= 2:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', lw=2, alpha=0.95, label='Path')
    ax.scatter([start[0]], [start[1]], c='g', s=60, marker='o', label='Start')
    ax.scatter([goal[0]], [goal[1]],   c='r', s=80, marker='*', label='Goal')
    tank_dot, = ax.plot([start[0]], [start[1]], 'o', ms=8, label='Tank')
    ax.legend(loc='upper left')

    # 전차 이동 애니메이션(경로 선분 보간)
    def seg_len(a, b): return math.hypot(b[0] - a[0], b[1] - a[1])

    segs = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        L = seg_len(a, b)
        if L > 0:
            segs.append((a, b, L))

    pos_x, pos_y = float(start[0]), float(start[1])
    last_time = time.time()
    cur_seg = 0
    cur_t = 0.0

    if not segs:
        tank_dot.set_data([pos_x], [pos_y])
        plt.show()
        return

    while True:
        now = time.time()
        dt = max(now - last_time, DT)
        last_time = now

        a, b, L = segs[cur_seg]
        dx, dy = (b[0] - a[0]), (b[1] - a[1])
        ux, uy = (dx / L, dy / L) if L > 0 else (0.0, 0.0)

        cur_t += (TANK_SPEED * dt) / L
        if cur_t >= 1.0:
            pos_x, pos_y = float(b[0]), float(b[1])
            cur_seg += 1
            cur_t = 0.0
            if cur_seg >= len(segs):
                tank_dot.set_data([pos_x], [pos_y])
                plt.pause(0.001)
                print("✅ 목표 도착!")
                break
        else:
            pos_x = a[0] + dx * cur_t
            pos_y = a[1] + dy * cur_t

        tank_dot.set_data([pos_x], [pos_y])
        plt.pause(DT)

    plt.show()

# ================== 메인 ==================
def main():
    print("==== 오프라인 전차 경로탐색 시뮬레이터 ====")
    print(f"맵: {GRID_W}x{GRID_H}, 장애물: 20x20, 최소거리(팽창): {CLEARANCE}칸")
    print(f"시작점(고정): {START}, 목표점(고정): {GOAL}")

    # 1) 장애물 개수 입력
    while True:
        try:
            n = int(input("배치할 장애물 개수 입력 (예: 8): ").strip())
            if n < 0:
                print("0 이상의 정수를 입력하세요.")
                continue
            break
        except:
            print("정수로 입력하세요. 예: 8")

    # 2) 장애물 무작위 배치 (시작/목표와 겹치지 않고 서로도 겹치지 않게)
    centers = generate_random_obstacles(
        count=n,
        start=START,
        goal=GOAL,
        obst_half=OBST_HALF,
        clearance=CLEARANCE
    )
    print(f"배치된 장애물 수: {len(centers)} / 요청: {n}")

    # 3) 경로계획용 막힘 영역(팽창 반영)
    blocked_inflated: Set[Tuple[int, int]] = set()
    for (cx, cy) in centers:
        stamp_square(blocked_inflated, cx, cy, OBST_HALF + CLEARANCE)

    # 4) 경로계산 (A* + LOS)
    print("경로 계산 중 ...")
    path = astar(START, GOAL, blocked_inflated)
    if not path:
        print("❌ 경로를 찾지 못했습니다. 장애물/목표를 확인해주세요.")
        return

    path2 = simplify_path_los(path, blocked_inflated)
    print(f"원 경로 길이: {len(path)}  →  직선화 후: {len(path2)}")

    # 5) 시뮬레이션 시각화
    simulate_and_plot(centers, START, GOAL, path2)

if __name__ == "__main__":
    main()
