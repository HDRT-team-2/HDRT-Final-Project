# -*- coding: utf-8 -*-
"""
오프라인 전차 경로탐색 + 이동 시뮬레이션 (A*, 8방향, 옥타일 휴리스틱)
- 터미널에서 장애물 중심 좌표 여러 줄 입력 (예: "120 180"), 끝나면 "ok"
- 목표 좌표 1개 입력 (예: "280 280")
- 각 장애물은 20x20 정사각형(중심 기준)
- 경로계획 시, 장애물과 최소거리 3칸(그리드) 여유 확보(장애물 팽창)
- A* 후 가시선(LOS) 직선화 → matplotlib 애니메이션으로 전차 이동
"""

import math
import heapq
import sys
import time
from typing import List, Tuple, Set

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches

# ========== 맵 / 파라미터 ==========
GRID_W, GRID_H = 300, 300        # 300 x 300 (1셀 = 1 단위)
ALLOW_DIAGONAL = True             # 8방향
OBST_SIZE      = 20               # 장애물 한 변 길이 (정사각형)
OBST_HALF      = OBST_SIZE // 2   # 10
CLEARANCE      = 3                # 장애물과 최소거리 3칸(팽창 반경)
REACH_DIST     = 1.5              # 웨이포인트 도달 반경
TANK_SPEED     = 4.0              # 셀/초
DT             = 0.03             # 시뮬레이션 시간 간격(초)

# ========== 유틸 ==========
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
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)   # 옥타일
    else:
        return dx + dy

# ========== 장애물 반영 ==========
def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    """중심(cx,cy)와 반경 half(절반 변 길이)로 정사각형을 막힌 영역으로 표시."""
    x0, x1 = cx - half, cx + half - 1
    y0, y1 = cy - half, cy + half - 1
    for x in range(x0, x1+1):
        for y in range(y0, y1+1):
            if in_bounds(x, y):
                blocked.add((x, y))

# ========== A* ==========
def astar(start: Tuple[int,int], goal: Tuple[int,int], blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if start == goal: return [start]
    if start in blocked or goal in blocked: return []

    D2 = math.sqrt(2.0)
    g = {start: 0.0}
    f = {start: heuristic(start, goal)}
    came = {}
    pq = [(f[start], start)]
    seen = set()

    while pq:
        _, cur = heapq.heappop(pq)
        if cur in seen: continue
        seen.add(cur)

        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]; path.append(cur)
            path.reverse()
            return path

        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx,ny) in blocked: continue
            step_cost = D2 if (nx!=cx and ny!=cy) else 1.0
            ng = g[cur] + step_cost
            if ng < g.get((nx,ny), 1e18):
                came[(nx,ny)] = cur
                g[(nx,ny)] = ng
                f[(nx,ny)] = ng + heuristic((nx,ny), goal)
                heapq.heappush(pq, (f[(nx,ny)], (nx,ny)))
    return []

# ========== 가시선 직선화 ==========
def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        yield (x, y)
        if x == x1 and y == y1: break
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
    if not path_points: return []
    simp = [path_points[0]]
    i = 0
    while i < len(path_points) - 1:
        j = i + 1
        while j + 1 < len(path_points) and not line_blocked(path_points[i], path_points[j+1], blocked):
            j += 1
        simp.append(path_points[j])
        i = j
    return simp

# ========== 입력 ==========
def read_obstacles():
    """
    장애물 중심 좌표를 여러 줄 입력 (예: 120 180). 끝나면 'ok'
    - 실제 장애물은 20x20으로 표시
    - 경로계획용 막힌 영역은 최소거리 3을 반영해 26x26(=20 + 2*3)로 확장
    """
    print("장애물 중심 좌표를 줄마다 입력하세요 (예: 120 180). 다 입력했으면 'ok' 입력.")
    centers = []
    while True:
        line = input("> ").strip()
        if line.lower() == "ok":
            break
        try:
            x_str, z_str = line.replace(",", " ").split()
            x, z = int(float(x_str)), int(float(z_str))
            centers.append((x, z))
        except:
            print("형식: x z   (예: 120 180)  또는 ok")
            continue
    return centers

def read_point(prompt, default=None):
    while True:
        line = input(f"{prompt} ").strip()
        if not line and default is not None:
            return default
        try:
            xs, zs = line.replace(",", " ").split()
            return (int(float(xs)), int(float(zs)))
        except:
            print("형식: x z   (예: 50 50)")
            continue

# ========== 시뮬레이션/시각화 ==========
def simulate_and_plot(centers, start, goal, path):
    fig, ax = plt.subplots(figsize=(7,7))
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
                (cx-OBST_HALF, cy-OBST_HALF),
                OBST_SIZE, OBST_SIZE,
                linewidth=1, edgecolor='k', facecolor='0.6', alpha=0.9
            )
        )
        # 팽창 영역(경로계획에 사용)
        infl_half = OBST_HALF + CLEARANCE
        ax.add_patch(
            patches.Rectangle(
                (cx-infl_half, cy-infl_half),
                2*infl_half, 2*infl_half,
                linewidth=1.2, edgecolor='tab:red', facecolor='none', linestyle='--', alpha=0.9
            )
        )

    # 경로
    if len(path) >= 2:
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]
        ax.plot(xs, ys, '-', lw=2, alpha=0.95, label='Path')
    ax.scatter([start[0]],[start[1]], c='g', s=60, marker='o', label='Start')
    ax.scatter([goal[0]],[goal[1]],   c='r', s=80, marker='*', label='Goal')
    tank_dot, = ax.plot([start[0]],[start[1]], 'o', ms=8, label='Tank')
    ax.legend(loc='upper left')

    # 전차 이동 애니메이션(경로 선분 보간)
    def seg_len(a, b): return math.hypot(b[0]-a[0], b[1]-a[1])

    segs = []
    for i in range(len(path)-1):
        a, b = path[i], path[i+1]
        L = seg_len(a, b)
        if L > 0:
            segs.append((a, b, L))

    pos_x, pos_y = float(start[0]), float(start[1])
    last_time = time.time()
    cur_seg = 0
    cur_t = 0.0

    if not segs:
        tank_dot.set_data([pos_x],[pos_y])
        plt.show()
        return

    while True:
        now = time.time()
        dt = max(now - last_time, DT)
        last_time = now

        a, b, L = segs[cur_seg]
        dx, dy = (b[0]-a[0]), (b[1]-a[1])
        ux, uy = (dx/L, dy/L) if L > 0 else (0.0, 0.0)

        cur_t += (TANK_SPEED * dt) / L
        if cur_t >= 1.0:
            pos_x, pos_y = float(b[0]), float(b[1])
            cur_seg += 1
            cur_t = 0.0
            if cur_seg >= len(segs):
                tank_dot.set_data([pos_x],[pos_y])
                plt.pause(0.001)
                print("✅ 목표 도착!")
                break
        else:
            pos_x = a[0] + dx * cur_t
            pos_y = a[1] + dy * cur_t

        tank_dot.set_data([pos_x],[pos_y])
        plt.pause(DT)

    plt.show()

# ========== 메인 ==========
def main():
    print("==== 오프라인 전차 경로탐색 시뮬레이터 (장애물 최소거리 3 적용) ====")
    print("맵: 300x300, 장애물: 20x20 (중심 기준), 경로계획은 장애물 +3칸 여유를 둠")

    # 1) 장애물 입력
    centers = read_obstacles()

    # 2) 시작/목표 입력 (기본 시작 50,50)
    start = read_point("시작 좌표 입력 (기본: 50 50, 그냥 Enter):", default=(50,50))
    goal  = read_point("목표 좌표 입력 (예: 280 280):")

    # 3) 막힘영역 구성: 경로계획용은 팽창(half + CLEARANCE)
    blocked_inflated: Set[Tuple[int,int]] = set()
    for (cx, cy) in centers:
        stamp_square(blocked_inflated, cx, cy, OBST_HALF + CLEARANCE)

    # 4) 경로계산 (A* + LOS)
    print("경로 계산 중 ... (장애물 최소거리 3 반영)")
    path = astar(start, goal, blocked_inflated)
    if not path:
        print("❌ 경로를 찾지 못했습니다. 장애물/목표를 확인해주세요.")
        return

    path2 = simplify_path_los(path, blocked_inflated)
    print(f"원 경로 길이: {len(path)}  →  직선화 후: {len(path2)}")

    # 5) 시뮬레이션 시각화
    simulate_and_plot(centers, start, goal, path2)

if __name__ == "__main__":
    main()
