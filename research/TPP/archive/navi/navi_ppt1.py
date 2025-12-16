# -*- coding: utf-8 -*-
"""
동적 장애물 시뮬레이터 (A*, 8방향, 옥타일 휴리스틱 + LOS 직선화)
- 시작점: (30, 30) / 목표점: (280, 280)
- 장애물: 원형 (기존 정사각 → 원), CLEARANCE=3칸 팽창 반영
- 규칙: SPAWN_PERIOD_SEC마다 장애물 1개 생성 → 즉시 재탐색 → 전차는 새 경로를 따라 이동
- 애니메이션: matplotlib FuncAnimation
"""

import math
import heapq
import random
import time
from typing import List, Tuple, Set, Optional

import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.animation import FuncAnimation

# ========== 맵 / 파라미터 ========== 
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True
OBST_SIZE = 25               # (이전: 한 변의 길이, 이제는 지름으로 간주)
OBST_RADIUS = OBST_SIZE // 2
CLEARANCE = 2  # 장애물 팽창 여유 (cells)
START = (20, 20)
GOAL = (280, 280)

# 애니메이션/물리 파라미터
FPS = 30
INTERVAL_MS = int(1000 / FPS)
DT = 1.0 / FPS
AGENT_SPEED_CELLS_PER_SEC = 30.0  # 초당 셀 이동 속도
ARRIVAL_EPS = 0.75                # 노드 도달 판정
SPAWN_PERIOD_SEC = 0.3            # 장애물 생성 주기(초)
MAX_OBST = 999999                 # 원하는 경우 상한 설정

# 장애물 생성 거리 범위 (에이전트 현재 위치 기준)
# 필요 시 수시로 수정해서 사용하면 됨
OBST_SPAWN_MIN_DIST = 50
OBST_SPAWN_MAX_DIST = 80

# 시드(재현용). 랜덤하게 하려면 주석 처리
random.seed(42)


# ===================================
# 유틸리티 함수
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
# 장애물 관련 (원형)
# ===================================
def stamp_circle(blocked: Set[Tuple[int,int]], cx: int, cy: int, radius: int):
    """중심 (cx,cy) 반지름 radius 의 원 내부 셀을 blocked에 추가"""
    r = int(math.ceil(radius))
    x0 = max(0, cx - r)
    x1 = min(GRID_W - 1, cx + r)
    y0 = max(0, cy - r)
    y1 = min(GRID_H - 1, cy + r)
    rr2 = (radius + 1e-9) ** 2
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            dx = x - cx
            dy = y - cy
            if dx*dx + dy*dy <= rr2:
                blocked.add((x, y))

def inflate_and_apply(blocked: Set[Tuple[int,int]], centers: List[Tuple[int,int]]):
    blocked.clear()
    for (cx, cy) in centers:
        stamp_circle(blocked, cx, cy, OBST_RADIUS + CLEARANCE)

def can_place_obstacle(centers: List[Tuple[int,int]], cx: int, cy: int,
                       avoid_pts: List[Tuple[float,float]], min_center_dist=OBST_SIZE):
    # 맵 경계 내부: 원의 바깥쪽까지 모두 들어오도록 여유 확보
    margin = OBST_RADIUS + CLEARANCE + 1
    if not (margin <= cx <= GRID_W - margin - 1): 
        return False
    if not (margin <= cy <= GRID_H - margin - 1): 
        return False

    # 현재 에이전트 위치(avoid_pts[0]) 기준으로 거리 범위 조건 적용
    # (예: 50 ~ 80, 전역 변수로 조정 가능)
    ax0, ay0 = avoid_pts[0]
    d0 = math.hypot(cx - ax0, cy - ay0)
    if not (OBST_SPAWN_MIN_DIST <= d0 <= OBST_SPAWN_MAX_DIST):
        return False

    # 시작/목표/현재위치 등 주요 포인트와 충분히 떨어뜨리기 (유클리드 거리 기준)
    for (ax, ay) in avoid_pts:
        if math.hypot(cx - ax, cy - ay) < min_center_dist:
            return False

    # 기존 장애물과도 너무 가깝지 않게 (원-원 간 중심 거리)
    for (px, py) in centers:
        if math.hypot(cx - px, cy - py) < (OBST_SIZE):
            return False

    return True

def place_random_obstacle(centers: List[Tuple[int,int]],
                          avoid_pts: List[Tuple[float,float]]) -> Optional[Tuple[int,int]]:
    tries = 0
    while tries < 2000:
        tries += 1
        cx = random.randint(OBST_RADIUS+1, GRID_W-OBST_RADIUS-2)
        cy = random.randint(OBST_RADIUS+1, GRID_H-OBST_RADIUS-2)
        if can_place_obstacle(centers, cx, cy, avoid_pts):
            centers.append((cx, cy))
            return (cx, cy)
    return None


# ===================================
# A* 알고리즘
# ===================================
def astar(start, goal, blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    if start == goal:
        return [start]

    # 시작/목표가 막힌 경우 빈 경로
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
# LOS 직선화 및 꺾이는 지점 검출
# ===================================
def bresenham_line(x0, y0, x1, y1):
    dx = abs(x1 - x0); sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0); sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield (x0, y0)
        if x0 == x1 and y0 == y1: 
            break
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
        # 방향 벡터가 바뀌면 코너로 간주
        if v1 != v2:
            turns.append(path[i])
    turns.append(path[-1])
    return turns


# ===================================
# 시각화 & 애니메이션 상태
# ===================================
class Simulator:
    def __init__(self):
        # 장애물/차단맵
        self.centers: List[Tuple[int,int]] = []
        self.blocked: Set[Tuple[int,int]] = set()

        # 에이전트 상태(연속 좌표)
        self.ax = float(START[0])
        self.ay = float(START[1])

        # 현재 목표/경로
        self.goal = GOAL
        self.path: List[Tuple[int,int]] = []
        self.path2: List[Tuple[int,int]] = []
        self.turns: List[Tuple[int,int]] = []

        # 경로 인덱싱(다음 path2 노드)
        self.seg_idx = 0

        # 시간/스폰 타이머
        self.t = 0.0
        self.next_spawn_t = SPAWN_PERIOD_SEC
        self.obst_count = 0

        # 플롯 셋업
        self.fig, self.axplt = plt.subplots(figsize=(7,7))
        self.axplt.set_title("Dynamic Obstacles: A* + LOS Replan (every spawn)")
        self.axplt.set_xlim(0, GRID_W)
        self.axplt.set_ylim(0, GRID_H)
        self.axplt.set_aspect('equal')
        self.axplt.grid(True, alpha=0.2)

        # 드로잉 핸들
        self.obst_patches: List[patches.Circle] = []
        self.infl_patches: List[patches.Circle] = []
        self.path_line, = self.axplt.plot([], [], '-', lw=2, label="Path")
        self.turn_scatter = self.axplt.scatter([], [], s=18, c='k', label='Waypoints')
        self.start_scatter = self.axplt.scatter([START[0]], [START[1]], c='g', s=60, marker='o', label='Start')
        self.goal_scatter  = self.axplt.scatter([self.goal[0]], [self.goal[1]], c='r', s=80, marker='*', label='Goal')
        self.agent_dot, = self.axplt.plot([], [], 'o', ms=8)  # 현재 위치
        self.text_status = self.axplt.text(2, GRID_H-5, "", fontsize=9, va='top')

        self.axplt.legend(loc='lower right')

        # 최초 경로
        self.replan(from_current_pose=False)

    # ---------- 경로계획 ----------
    def replan(self, from_current_pose=True):
        sx, sy = (int(round(self.ax)), int(round(self.ay))) if from_current_pose else START
        inflate_and_apply(self.blocked, self.centers)
        self.path  = astar((sx, sy), self.goal, self.blocked)
        self.path2 = simplify_path(self.path, self.blocked)
        self.turns = find_turn_points(self.path2)
        self.seg_idx = 0  # 새 경로의 첫 세그먼트부터
        # 디버그 출력
        if not self.path:
            print("❌ 경로 없음 (막힘)")
        else:
            print(f"경로 재계획: 원경로 {len(self.path)} → 직선화 {len(self.path2)} (턴 {len(self.turns)})")

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
            return  # 경로 없음/목표 도달

        # 현재 노드 목표
        tx, ty = self.path2[self.seg_idx]
        dx = tx - self.ax
        dy = ty - self.ay
        dist = math.hypot(dx, dy)

        if dist < ARRIVAL_EPS:
            # 다음 세그먼트로
            self.seg_idx += 1
            if self.seg_idx >= len(self.path2):
                # 목표 도달
                self.ax, self.ay = float(tx), float(ty)
                return
            # 다음 타겟으로 즉시 재계산
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
        # 장애물 패치 업데이트(전체 리드로)
        for p in self.obst_patches: 
            p.remove()
        for p in self.infl_patches: 
            p.remove()
        self.obst_patches.clear()
        self.infl_patches.clear()

        for (cx, cy) in self.centers:
            # 본체 (원)
            circ = patches.Circle((cx, cy), radius=OBST_RADIUS,
                                  edgecolor='k', facecolor='0.6')
            self.axplt.add_patch(circ)
            self.obst_patches.append(circ)
            # 팽창(여유)
            infl_r = OBST_RADIUS + CLEARANCE
            circ2 = patches.Circle((cx, cy), radius=infl_r,
                                   edgecolor='r', facecolor='none', linestyle='--', alpha=0.8)
            self.axplt.add_patch(circ2)
            self.infl_patches.append(circ2)

        # 경로 라인
        xs = [p[0] for p in self.path2]
        ys = [p[1] for p in self.path2]
        self.path_line.set_data(xs, ys)

        # 턴 포인트
        if self.turns:
            self.turn_scatter.remove()
            self.turn_scatter = self.axplt.scatter([p[0] for p in self.turns],
                                                   [p[1] for p in self.turns],
                                                   c='k', s=18)

        # 에이전트 위치
        self.agent_dot.set_data([self.ax], [self.ay])

        # 상태 텍스트
        if not self.path2:
            status = "NO PATH"
        elif self.seg_idx >= len(self.path2):
            status = "ARRIVED"
        else:
            status = f"t={self.t:4.1f}s  obst={len(self.centers)}  seg={self.seg_idx+1}/{len(self.path2)}"
        self.text_status.set_text(status)

    # ---------- 애니메이션 프레임 ----------
    def update(self, frame):
        # 시간 진행
        self.t += DT

        # 장애물 생성 타이밍
        if self.t >= self.next_spawn_t and len(self.centers) < MAX_OBST and self.seg_idx < len(self.path2):
            self.spawn_obstacle()
            self.next_spawn_t += SPAWN_PERIOD_SEC

        # 이동
        if self.path2 and self.seg_idx < len(self.path2):
            self.step_agent(DT)

        # 그리기
        self.redraw()
        return (self.path_line, self.agent_dot)


def main():
    sim = Simulator()
    # 애니메이션 시작
    ani = FuncAnimation(sim.fig, sim.update, interval=INTERVAL_MS, blit=False)
    plt.show()


if __name__ == "__main__":
    main()
