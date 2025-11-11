# -*- coding: utf-8 -*-
"""
동적 장애물 시뮬레이터 (A*, 8방향, 옥타일 휴리스틱 + LOS 직선화)
- 시작점: (30, 30) / 목표점: (280, 280)
- 장애물: 20x20 정사각형, CLEARANCE=3칸 팽창 반영
- 규칙: 3초마다 장애물 1개 생성 → 즉시 재탐색 → 전차는 새 경로를 따라 이동
- 재탐색 시 꺾이는 지점(웨이포인트)이 변경되면 print로 출력
- 애니메이션: matplotlib FuncAnimation
"""

import math
import heapq
import random
from typing import List, Tuple, Set, Optional

import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.animation import FuncAnimation

# ========== 맵 / 파라미터 ==========
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True
OBST_SIZE = 40
OBST_HALF = OBST_SIZE // 2
CLEARANCE = 3  # 장애물 팽창 여유
START = (30, 30)
GOAL = (280, 280)

# 애니메이션/물리 파라미터
FPS = 30
INTERVAL_MS = int(1000 / FPS)
DT = 1.0 / FPS
AGENT_SPEED_CELLS_PER_SEC = 20.0  # 초당 셀 이동 속도
ARRIVAL_EPS = 1.0                # 노드 도달 판정
SPAWN_PERIOD_SEC = 0.7         # 장애물 생성 주기(초)
MAX_OBST = 999999                 # 원하는 경우 상한 설정

random.seed(51)  # 재현용 (원하면 주석 처리)

# ===================================
# 유틸리티/경계
# ===================================
def in_bounds(x: int, y: int) -> bool:
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def neighbors(x: int, y: int):
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
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)  # 옥타일
    else:
        return dx + dy

# ===================================
# 장애물
# ===================================
def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    for x in range(cx - half, cx + half):
        for y in range(cy - half, cy + half):
            if in_bounds(x, y):
                blocked.add((x, y))

def inflate_and_apply(blocked: Set[Tuple[int,int]], centers: List[Tuple[int,int]]):
    blocked.clear()
    for (cx, cy) in centers:
        stamp_square(blocked, cx, cy, OBST_HALF + CLEARANCE)

def can_place_obstacle(centers: List[Tuple[int,int]], cx: int, cy: int,
                       avoid_pts: List[Tuple[float,float]], min_manhattan=40) -> bool:
    if not (OBST_HALF + CLEARANCE + 1 <= cx <= GRID_W - OBST_HALF - CLEARANCE - 2): return False
    if not (OBST_HALF + CLEARANCE + 1 <= cy <= GRID_H - OBST_HALF - CLEARANCE - 2): return False
    for (ax, ay) in avoid_pts:
        if abs(cx - ax) + abs(cy - ay) < min_manhattan:
            return False
    for (px, py) in centers:
        if abs(cx - px) + abs(cy - py) < OBST_SIZE:
            return False
    return True

def place_random_obstacle(centers: List[Tuple[int,int]],
                          avoid_pts: List[Tuple[float,float]]) -> Optional[Tuple[int,int]]:
    for _ in range(2000):
        cx = random.randint(OBST_HALF+1, GRID_W-OBST_HALF-2)
        cy = random.randint(OBST_HALF+1, GRID_H-OBST_HALF-2)
        if can_place_obstacle(centers, cx, cy, avoid_pts):
            centers.append((cx, cy))
            return (cx, cy)
    return None

# ===================================
# A*
# ===================================
def astar(start, goal, blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
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
            step = D2 if (nx != cx and ny != cy) else 1.0
            ng = g[cur] + step
            if ng < g.get((nx, ny), 1e18):
                came[(nx, ny)] = cur
                g[(nx, ny)] = ng
                f[(nx, ny)] = ng + heuristic((nx, ny), goal)
                heapq.heappush(pq, (f[(nx, ny)], (nx, ny)))
    return []

# ===================================
# LOS 직선화 및 턴 포인트
# ===================================
def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield (x0, y0)
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy

def line_blocked(p0, p1, blocked: Set[Tuple[int,int]]) -> bool:
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked and c not in (p0, p1):
            return True
    return False

def simplify_path(path: List[Tuple[int,int]], blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if not path:
        return []
    simp = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = i + 1
        while j + 1 < len(path) and not line_blocked(path[i], path[j+1], blocked):
            j += 1
        simp.append(path[j])
        i = j
    return simp

def find_turn_points(path: List[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if len(path) <= 2:
        return path[:]
    turns = [path[0]]
    for i in range(1, len(path)-1):
        v1 = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1])
        v2 = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
        if v1 != v2:  # 방향이 바뀌면 코너
            turns.append(path[i])
    turns.append(path[-1])
    return turns

# ===================================
# 시뮬레이터
# ===================================
class Simulator:
    def __init__(self):
        self.centers: List[Tuple[int,int]] = []
        self.blocked: Set[Tuple[int,int]] = set()

        # 에이전트 상태
        self.ax = float(START[0])
        self.ay = float(START[1])
        self.goal = GOAL

        # 경로/턴 포인트
        self.path: List[Tuple[int,int]] = []
        self.path2: List[Tuple[int,int]] = []
        self.turns: List[Tuple[int,int]] = []
        self.prev_turns: List[Tuple[int,int]] = []  # ← 변경 추적용

        # 진행 인덱스
        self.seg_idx = 0

        # 시간/스폰
        self.t = 0.0
        self.next_spawn_t = SPAWN_PERIOD_SEC
        self.obst_count = 0

        # 플롯
        self.fig, self.axplt = plt.subplots(figsize=(7,7))
        self.axplt.set_title("Dynamic Obstacles: A* + LOS Replan (every 3s)")
        self.axplt.set_xlim(0, GRID_W)
        self.axplt.set_ylim(0, GRID_H)
        self.axplt.set_aspect('equal')
        self.axplt.grid(True, alpha=0.2)

        self.obst_patches: List[patches.Rectangle] = []
        self.infl_patches: List[patches.Rectangle] = []
        self.path_line, = self.axplt.plot([], [], '-', lw=2, label="Path")
        self.turn_scatter = self.axplt.scatter([], [], s=18, c='k', label='Turns')
        self.start_scatter = self.axplt.scatter([START[0]], [START[1]], c='g', s=60, marker='o', label='Start')
        self.goal_scatter  = self.axplt.scatter([self.goal[0]], [self.goal[1]], c='r', s=80, marker='*', label='Goal')
        self.agent_dot, = self.axplt.plot([], [], 'o', ms=8)
        self.text_status = self.axplt.text(2, GRID_H-5, "", fontsize=9, va='top')
        self.axplt.legend(loc='lower right')

        # 최초 경로
        self.replan(from_current_pose=False)

    def _print_turns_if_changed(self):
        if self.turns != self.prev_turns:
            print("\n🧭 웨이포인트 변경됨 ({}개):".format(len(self.turns)))
            for i, (x, y) in enumerate(self.turns):
                tag = "START" if i == 0 else "GOAL" if i == len(self.turns)-1 else f"T{i}"
                print(f"  {tag}: ({x}, {y})")
            self.prev_turns = self.turns[:]  # 스냅샷 저장

    # ---------- 경로계획 ----------
    def replan(self, from_current_pose=True):
        sx, sy = (int(round(self.ax)), int(round(self.ay))) if from_current_pose else START
        inflate_and_apply(self.blocked, self.centers)
        self.path  = astar((sx, sy), self.goal, self.blocked)
        self.path2 = simplify_path(self.path, self.blocked)
        self.turns = find_turn_points(self.path2)
        self.seg_idx = 0

        if not self.path:
            print("❌ 경로 없음 (막힘)")
        else:
            print(f"경로 재계획: 원경로 {len(self.path)} → 직선화 {len(self.path2)} (턴 {len(self.turns)})")
        # 변화가 있으면 웨이포인트 출력
        self._print_turns_if_changed()

    # ---------- 장애물 추가 ----------
    def spawn_obstacle(self):
        avoid = [(self.ax, self.ay), START, self.goal]
        placed = place_random_obstacle(self.centers, avoid)
        if placed is not None:
            self.obst_count += 1
            print(f"🧱 장애물 생성 #{self.obst_count} at {placed}")
            self.replan(from_current_pose=True)

    # ---------- 에이전트 이동 ----------
    def step_agent(self, dt: float):
        if not self.path2 or self.seg_idx >= len(self.path2):
            return

        tx, ty = self.path2[self.seg_idx]
        dx = tx - self.ax
        dy = ty - self.ay
        dist = math.hypot(dx, dy)

        if dist < ARRIVAL_EPS:
            self.seg_idx += 1
            if self.seg_idx >= len(self.path2):
                self.ax, self.ay = float(tx), float(ty)
                return
            tx, ty = self.path2[self.seg_idx]
            dx = tx - self.ax
            dy = ty - self.ay
            dist = math.hypot(dx, dy)

        if dist > 1e-6:
            step = AGENT_SPEED_CELLS_PER_SEC * dt
            if step >= dist:
                self.ax, self.ay = float(tx), float(ty)
            else:
                self.ax += dx / dist * step
                self.ay += dy / dist * step

    # ---------- 드로잉 ----------
    def redraw(self):
        for p in self.obst_patches: p.remove()
        for p in self.infl_patches: p.remove()
        self.obst_patches.clear()
        self.infl_patches.clear()

        for (cx, cy) in self.centers:
            rect = patches.Rectangle((cx-OBST_HALF, cy-OBST_HALF), OBST_SIZE, OBST_SIZE,
                                     edgecolor='k', facecolor='0.6')
            self.axplt.add_patch(rect)
            self.obst_patches.append(rect)
            infl = OBST_HALF + CLEARANCE
            rect2 = patches.Rectangle((cx-infl, cy-infl), infl*2, infl*2,
                                      edgecolor='r', facecolor='none', linestyle='--', alpha=0.4)
            self.axplt.add_patch(rect2)
            self.infl_patches.append(rect2)

        xs = [p[0] for p in self.path2]
        ys = [p[1] for p in self.path2]
        self.path_line.set_data(xs, ys)

        if self.turns:
            self.turn_scatter.remove()
            self.turn_scatter = self.axplt.scatter([p[0] for p in self.turns],
                                                   [p[1] for p in self.turns],
                                                   c='k', s=18)

        self.agent_dot.set_data([self.ax], [self.ay])

        if not self.path2:
            status = "NO PATH"
        elif self.seg_idx >= len(self.path2):
            status = "ARRIVED"
        else:
            status = f"t={self.t:4.1f}s  obst={len(self.centers)}  seg={self.seg_idx+1}/{len(self.path2)}"
        self.text_status.set_text(status)

    # ---------- 애니메이션 프레임 ----------
    def update(self, frame):
        self.t += DT

        # 3초마다 장애물 생성 & 즉시 재탐색
        if self.t >= self.next_spawn_t and len(self.centers) < MAX_OBST and self.seg_idx < len(self.path2):
            self.spawn_obstacle()
            self.next_spawn_t += SPAWN_PERIOD_SEC

        if self.path2 and self.seg_idx < len(self.path2):
            self.step_agent(DT)

        self.redraw()
        return (self.path_line, self.agent_dot)

# ===================================
# 메인
# ===================================
def main():
    sim = Simulator()
    ani = FuncAnimation(sim.fig, sim.update, interval=INTERVAL_MS, blit=False)
    plt.show()

if __name__ == "__main__":
    main()
