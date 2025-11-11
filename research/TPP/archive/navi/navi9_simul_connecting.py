# -*- coding: utf-8 -*-
"""
경로탐색기 (A*, 8방향, 옥타일 휴리스틱 + LOS 직선화)
- 시작점: (30, 30) / 목표점: (280, 280) 고정
- 장애물 크기: 20x20 정사각형 (중심 기준), 최소거리 3칸으로 팽창 반영
- 장애물 개수를 입력받아 임의 배치(시작/목표와 겹치지 않게)
- 경로 계산 후:
  * 꺾이는 지점(코너)을 print
  * 플롯에 꺾이는 지점 작은 검정 점으로 표시
  * Flask 시뮬레이션 서버(navi_drive.py)가 자동으로 실행되어 웨이포인트 전송
"""

import math
import heapq
import random
import time
import requests
import subprocess, os, sys
from typing import List, Tuple, Set
import matplotlib.pyplot as plt
from matplotlib import patches

# ========== 맵 / 파라미터 ==========
GRID_W, GRID_H = 300, 300
ALLOW_DIAGONAL = True
OBST_SIZE = 20
OBST_HALF = OBST_SIZE // 2
CLEARANCE = 3
START = (30, 30)
GOAL = (280, 280)
SERVER_URL = "http://127.0.0.1:5000/set_waypoints"

# ===================================
# 자동 서버 실행
# ===================================
def ensure_server_running():
    """Flask 서버(navi_drive.py)가 안 켜져 있으면 자동으로 실행"""
    try:
        requests.get("http://127.0.0.1:5000/start", timeout=1.0)
        print("✅ navi_drive 서버 감지됨.")
        return
    except Exception:
        print("⚠️ 서버 미동작 → 자동 실행 시도...")

    drive_path = os.path.join(os.path.dirname(__file__), "navi_drive.py")
    if not os.path.exists(drive_path):
        print("❌ navi_drive.py 파일을 찾을 수 없습니다:", drive_path)
        return

    subprocess.Popen(
        ["cmd", "/c", "start", "navi_drive (server)", "cmd", "/k", "python", drive_path],
        close_fds=True
    )


    # 서버 기동 확인 (최대 10초)
    for _ in range(20):
        try:
            time.sleep(0.5)
            requests.get("http://127.0.0.1:5000/start", timeout=1.0)
            print("✅ navi_drive 서버 기동 확인.")
            return
        except Exception:
            pass
    print("❌ 서버 기동 확인 실패(포트 충돌/권한 문제 가능).")

# ===================================
# 유틸리티 함수
# ===================================
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
        return D*(dx+dy) + (D2-2*D)*min(dx,dy)
    else:
        return dx + dy

# ===================================
# 장애물 관련
# ===================================
def stamp_square(blocked: Set[Tuple[int,int]], cx: int, cy: int, half: int):
    for x in range(cx - half, cx + half):
        for y in range(cy - half, cy + half):
            if in_bounds(x, y):
                blocked.add((x, y))

def generate_random_obstacles(n: int, start, goal) -> List[Tuple[int,int]]:
    centers = []
    tries = 0
    while len(centers) < n and tries < n * 100:
        tries += 1
        cx = random.randint(OBST_HALF+1, GRID_W-OBST_HALF-2)
        cy = random.randint(OBST_HALF+1, GRID_H-OBST_HALF-2)
        if abs(cx - start[0]) + abs(cy - start[1]) < 40: continue
        if abs(cx - goal[0]) + abs(cy - goal[1]) < 40: continue
        if any(abs(cx - px) + abs(cy - py) < OBST_SIZE for px, py in centers): continue
        centers.append((cx, cy))
    return centers

# ===================================
# A* 알고리즘
# ===================================
def astar(start, goal, blocked):
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
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path
        cx, cy = cur
        for nx, ny in neighbors(cx, cy):
            if (nx, ny) in blocked: continue
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
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 >= dy: err += dy; x0 += sx
        if e2 <= dx: err += dx; y0 += sy

def line_blocked(p0, p1, blocked):
    for c in bresenham_line(p0[0], p0[1], p1[0], p1[1]):
        if c in blocked and c not in (p0, p1): return True
    return False

def simplify_path(path, blocked):
    if not path: return []
    simp = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = i + 1
        while j + 1 < len(path) and not line_blocked(path[i], path[j+1], blocked):
            j += 1
        simp.append(path[j])
        i = j
    return simp

def find_turn_points(path):
    if len(path) <= 2: return path
    turns = [path[0]]
    for i in range(1, len(path)-1):
        v1 = (path[i][0]-path[i-1][0], path[i][1]-path[i-1][1])
        v2 = (path[i+1][0]-path[i][0], path[i+1][1]-path[i][1])
        if v1[0]*v2[1] - v1[1]*v2[0] != 0:
            turns.append(path[i])
    turns.append(path[-1])
    return turns

# ===================================
# 시각화 + 서버 전송
# ===================================
def visualize(centers, start, goal, path, turns):
    fig, ax = plt.subplots(figsize=(7,7))
    ax.set_title("Tank Path (A* + LOS + Turn Points)")
    ax.set_xlim(0, GRID_W)
    ax.set_ylim(0, GRID_H)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)

    # 장애물
    for (cx, cy) in centers:
        ax.add_patch(patches.Rectangle((cx-OBST_HALF, cy-OBST_HALF),
                                       OBST_SIZE, OBST_SIZE,
                                       edgecolor='k', facecolor='0.6'))
        infl_half = OBST_HALF + CLEARANCE
        ax.add_patch(patches.Rectangle((cx-infl_half, cy-infl_half),
                                       infl_half*2, infl_half*2,
                                       edgecolor='r', facecolor='none', linestyle='--', alpha=0.8))
    # 경로
    xs = [p[0] for p in path]
    ys = [p[1] for p in path]
    ax.plot(xs, ys, '-', lw=2, label="Path")

    # 꺾이는 지점
    if turns:
        ax.scatter([p[0] for p in turns], [p[1] for p in turns],
                   c='k', s=20, label='Turns')
    ax.scatter(start[0], start[1], c='g', s=60, marker='o', label='Start')
    ax.scatter(goal[0], goal[1], c='r', s=80, marker='*', label='Goal')
    ax.legend()
    plt.show()

def send_to_server(turns):
    payload = {"waypoints": [{"x": int(x), "z": int(y)} for (x,y) in turns[1:]]}
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=5)
        print("서버 응답:", r.json())
    except Exception as e:
        print("⚠️ 서버 전송 실패:", e)

# ===================================
# 메인
# ===================================
def main():
    ensure_server_running()  # 서버 자동 확인 및 실행
    print("==== 오프라인 전차 경로탐색 시뮬레이터 ====")
    while True:
        try:
            n = int(input("장애물 개수 입력 (예: 10): ").strip())
            if n >= 0: break
        except:
            print("정수를 입력하세요.")

    centers = generate_random_obstacles(n, START, GOAL)
    blocked = set()
    for cx, cy in centers:
        stamp_square(blocked, cx, cy, OBST_HALF + CLEARANCE)

    print("경로 계산 중...")
    path = astar(START, GOAL, blocked)
    if not path:
        print("❌ 경로를 찾지 못했습니다.")
        return
    path2 = simplify_path(path, blocked)
    print(f"원 경로 {len(path)}개 → 직선화 후 {len(path2)}개")
    turns = find_turn_points(path2)
    print("꺾이는 지점(웨이포인트):")
    for i, (x,y) in enumerate(turns):
        tag = "START" if i==0 else "GOAL" if i==len(turns)-1 else f"T{i}"
        print(f"  {tag}: ({x}, {y})")

    send_to_server(turns)
    visualize(centers, START, GOAL, path2, turns)

if __name__ == "__main__":
    main()
