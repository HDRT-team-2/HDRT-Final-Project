# -*- coding: utf-8 -*-
"""
동적 장애물 시뮬레이터 (A*, 8방향, 옥타일 휴리스틱 + LOS 직선화)
- 시작점: (30, 30) / 목표점: (280, 280)
- 장애물: 20x20 정사각형, CLEARANCE=1칸 팽창 반영
- 규칙: 주기적으로 장애물 생성 → 즉시 재탐색 → 전차는 새 경로를 따라 이동
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
GRID_W, GRID_H = 300, 300          # 격자 맵 크기
ALLOW_DIAGONAL = True              # A*에서 대각선 이동 허용
OBST_SIZE = 40                     # 장애물 정사각형 한 변(셀)
OBST_HALF = OBST_SIZE // 2         # 반쪽 길이(중심 기준)
CLEARANCE = 1                      # 장애물 팽창 여유(셀)
START = (30, 30)                   # 시작 좌표(셀)
GOAL = (280, 280)                  # 목표 좌표(셀)

# 애니메이션/물리 파라미터
FPS = 30
INTERVAL_MS = int(1000 / FPS)      # 프레임 간격(ms)
DT = 1.0 / FPS                     # 시뮬레이션 시간 스텝(초)
AGENT_SPEED_CELLS_PER_SEC = 20.0   # 전차 이동 속도(셀/초)
ARRIVAL_EPS = 1.0                  # 경유점 도달 판정 반경(셀)
SPAWN_PERIOD_SEC = 0.7             # 장애물 생성 주기(초) — 필요 시 3.0으로 조정
MAX_OBST = 999999                  # 생성할 수 있는 장애물 최대 개수(사실상 무제한)

random.seed(51)  # 재현 가능한 난수(원하면 주석 처리)

# ===================================
# 유틸리티/경계
# ===================================
def in_bounds(x: int, y: int) -> bool:
    """좌표가 맵 내부인지 여부"""
    return 0 <= x < GRID_W and 0 <= y < GRID_H

def neighbors(x: int, y: int):
    """8방향(옵션) 이웃 생성기"""
    steps = [(-1,0),(1,0),(0,-1),(0,1)]
    if ALLOW_DIAGONAL:
        steps += [(-1,-1),(-1,1),(1,-1),(1,1)]
    for dx, dy in steps:
        nx, ny = x+dx, y+dy
        if in_bounds(nx, ny):
            yield nx, ny

def heuristic(a, b):
    """A* 휴리스틱: 옥타일 거리(대각 이동 포함), 아니면 맨해튼"""
    (x1,y1), (x2,y2) = a, b
    dx, dy = abs(x1-x2), abs(y1-y2)
    if ALLOW_DIAGONAL:
        D, D2 = 1.0, math.sqrt(2.0)
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)
    else:
        return dx + dy

# ===================================
# 장애물
# ===================================
def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    """중심(cx,cy)와 반쪽길이 half를 갖는 정사각형을 blocked에 기록"""
    for x in range(cx - half, cx + half):
        for y in range(cy - half, cy + half):
            if in_bounds(x, y):
                blocked.add((x, y))

def inflate_and_apply(blocked: Set[Tuple[int,int]], centers: List[Tuple[int,int]]):
    """장애물 중심 리스트 → 팽창 포함한 차단 셀 집합으로 변환"""
    blocked.clear()
    for (cx, cy) in centers:
        stamp_square(blocked, cx, cy, OBST_HALF + CLEARANCE)

def can_place_obstacle(centers: List[Tuple[int,int]], cx: int, cy: int,
                       avoid_pts: List[Tuple[float,float]], min_manhattan=40) -> bool:
    """
    (cx,cy)에 장애물 배치 가능 여부 판단:
      - 맵 경계 안쪽
      - 시작/목표/현재 위치 근처(min_manhattan) 피하기
      - 기존 장애물과 일정 거리 유지(OBST_SIZE)
    """
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
    """랜덤 위치에 장애물 1개 배치(성공 시 좌표 반환, 실패 시 None)"""
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
    """A* 경로 탐색: blocked는 점유 셀 집합"""
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
            # 경로 복원
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
    """정수 격자에서 (x0,y0)→(x1,y1)까지의 픽셀을 순회(브레젠험)"""
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
    """p0→p1 직선 구간에 장애물(중간 셀)이 있으면 True"""
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked and c not in (p0, p1):
            return True
    return False

def simplify_path(path: List[Tuple[int,int]], blocked: Set[Tuple[int,int]]) -> List[Tuple[int,int]]:
    """경로를 직선 가시선 가능한 꼭짓점들만 남도록 단순화"""
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
    """방향이 바뀌는 지점만 골라 코너(웨이포인트) 목록 생성"""
    if len(path) <= 2:
        return path[:]
    turns = [path[0]]
    for i in range(1, len(path)-1):
        v1 = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1])
        v2 = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
        if v1 != v2:  # 방향 변경 시 코너
            turns.append(path[i])
    turns.append(path[-1])
    return turns

# ===================================
# 시뮬레이터
# ===================================
class Simulator:
    def __init__(self):
        # 장애물 상태
        self.centers: List[Tuple[int,int]] = []  # 장애물 중심 좌표들
        self.blocked: Set[Tuple[int,int]] = set()  # 팽창 반영된 점유 셀

        # 전차 상태(연속 좌표)
        self.ax = float(START[0])
        self.ay = float(START[1])
        self.goal = GOAL

        # 경로 관련
        self.path: List[Tuple[int,int]] = []      # A* 원경로
        self.path2: List[Tuple[int,int]] = []     # LOS 직선화 경로
        self.turns: List[Tuple[int,int]] = []     # 코너들(웨이포인트)
        self.prev_turns: List[Tuple[int,int]] = []# 직전 프린트한 코너들(변경 감지)

        # 진행 상태
        self.seg_idx = 0  # path2 상에서 현재 타겟 인덱스

        # 시간/스폰 관리
        self.t = 0.0
        self.next_spawn_t = SPAWN_PERIOD_SEC
        self.obst_count = 0

        # 플롯 구성
        self.fig, self.axplt = plt.subplots(figsize=(7,7))
        self.axplt.set_title("Dynamic Obstacles: A* + LOS Replan (every 3s)")
        self.axplt.set_xlim(0, GRID_W)
        self.axplt.set_ylim(0, GRID_H)
        self.axplt.set_aspect('equal')
        self.axplt.grid(True, alpha=0.2)

        self.obst_patches: List[patches.Rectangle] = []  # 실제 장애물 사각형
        self.infl_patches: List[patches.Rectangle] = []  # 팽창 테두리(점선)
        self.path_line, = self.axplt.plot([], [], '-', lw=2, label="Path")
        self.turn_scatter = self.axplt.scatter([], [], s=18, c='k', label='Turns')
        self.start_scatter = self.axplt.scatter([START[0]], [START[1]], c='g', s=60, marker='o', label='Start')
        self.goal_scatter  = self.axplt.scatter([self.goal[0]], [self.goal[1]], c='r', s=80, marker='*', label='Goal')
        self.agent_dot, = self.axplt.plot([], [], 'o', ms=8)
        self.text_status = self.axplt.text(2, GRID_H-5, "", fontsize=9, va='top')
        self.axplt.legend(loc='lower right')

        # 최초 경로계획(시작점 기준)
        self.replan(from_current_pose=False)

    def _print_turns_if_changed(self):
        """턴 포인트(웨이포인트) 목록이 바뀌면 콘솔에 출력"""
        if self.turns != self.prev_turns:
            print("\n웨이포인트 변경됨 ({}개):".format(len(self.turns)))
            for i, (x, y) in enumerate(self.turns):
                tag = "START" if i == 0 else "GOAL" if i == len(self.turns)-1 else f"T{i}"
                print(f"  {tag}: ({x}, {y})")
            # 현재 상태 스냅샷 저장(다음 변경 감지 대비)
            self.prev_turns = self.turns[:]

    # ---------- 경로계획 ----------
    def replan(self, from_current_pose=True):
        """
        A* → LOS 직선화 → 턴 포인트 추출
        from_current_pose=True면 현재 위치를 시작점으로 사용, 아니면 START 사용
        """
        sx, sy = (int(round(self.ax)), int(round(self.ay))) if from_current_pose else START
        inflate_and_apply(self.blocked, self.centers)
        self.path  = astar((sx, sy), self.goal, self.blocked)
        self.path2 = simplify_path(self.path, self.blocked)
        self.turns = find_turn_points(self.path2)
        self.seg_idx = 0

        if not self.path:
            print("경로 없음: 장애물에 막혀 있습니다.")
        else:
            print(f"경로 재계획: 원경로 {len(self.path)} → 직선화 {len(self.path2)} (턴 {len(self.turns)})")

        # 변경 시 웨이포인트 목록 출력
        self._print_turns_if_changed()

    # ---------- 장애물 추가 ----------
    def spawn_obstacle(self):
        """랜덤 장애물 1개 배치 후 즉시 재탐색"""
        avoid = [(self.ax, self.ay), START, self.goal]
        placed = place_random_obstacle(self.centers, avoid)
        if placed is not None:
            self.obst_count += 1
            print(f"장애물 생성 #{self.obst_count} at {placed}")
            self.replan(from_current_pose=True)

    # ---------- 에이전트 이동 ----------
    def step_agent(self, dt: float):
        """
        현재 타겟(path2[seg_idx])을 향해 등속 이동.
        도달하면 다음 세그먼트로 넘어감. 목표에 도달하면 정지.
        """
        if not self.path2 or self.seg_idx >= len(self.path2):
            return

        tx, ty = self.path2[self.seg_idx]
        dx = tx - self.ax
        dy = ty - self.ay
        dist = math.hypot(dx, dy)

        # 타겟 경유점 도달 판정
        if dist < ARRIVAL_EPS:
            self.seg_idx += 1
            if self.seg_idx >= len(self.path2):
                # 최종 점에 도달
                self.ax, self.ay = float(tx), float(ty)
                return
            # 다음 경유점 갱신
            tx, ty = self.path2[self.seg_idx]
            dx = tx - self.ax
            dy = ty - self.ay
            dist = math.hypot(dx, dy)

        # 타겟을 향해 한 스텝 전진
        if dist > 1e-6:
            step = AGENT_SPEED_CELLS_PER_SEC * dt
            if step >= dist:
                # 타겟 점을 정확히 찍음
                self.ax, self.ay = float(tx), float(ty)
            else:
                # 정규화된 방향으로 이동
                self.ax += dx / dist * step
                self.ay += dy / dist * step

    # ---------- 드로잉 ----------
    def redraw(self):
        """캔버스 위 모든 요소(장애물/경로/전차/상태 텍스트) 갱신"""
        # 기존 패치 제거
        for p in self.obst_patches: p.remove()
        for p in self.infl_patches: p.remove()
        self.obst_patches.clear()
        self.infl_patches.clear()

        # 장애물 본체(회색) + 팽창 테두리(빨간 점선)
        for (cx, cy) in self.centers:
            rect = patches.Rectangle(
                (cx-OBST_HALF, cy-OBST_HALF),
                OBST_SIZE, OBST_SIZE,
                edgecolor='k', facecolor='0.6'
            )
            self.axplt.add_patch(rect)
            self.obst_patches.append(rect)

            infl = OBST_HALF + CLEARANCE
            rect2 = patches.Rectangle(
                (cx-infl, cy-infl),
                infl*2, infl*2,
                edgecolor='r', facecolor='none',
                linestyle='--', alpha=0.4
            )
            self.axplt.add_patch(rect2)
            self.infl_patches.append(rect2)

        # LOS 직선화 경로
        xs = [p[0] for p in self.path2]
        ys = [p[1] for p in self.path2]
        self.path_line.set_data(xs, ys)

        # 턴 포인트(검정 점)
        if self.turns:
            self.turn_scatter.remove()
            self.turn_scatter = self.axplt.scatter(
                [p[0] for p in self.turns],
                [p[1] for p in self.turns],
                c='k', s=18
            )

        # 전차 위치(파란 점)
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
        """프레임마다 시간 진행, 필요 시 장애물 생성/재탐색, 이동/그리기"""
        self.t += DT

        # 주기적으로 장애물 생성 후 즉시 재탐색
        if self.t >= self.next_spawn_t and len(self.centers) < MAX_OBST and self.seg_idx < len(self.path2):
            self.spawn_obstacle()
            self.next_spawn_t += SPAWN_PERIOD_SEC

        # 현재 경유점으로 이동
        if self.path2 and self.seg_idx < len(self.path2):
            self.step_agent(DT)

        # 화면 갱신
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
