from flask import Flask, request, jsonify
import numpy as np
import matplotlib
import heapq
import math
import traceback
import os

# 서버 환경 고려해서 GUI 없는 백엔드 사용 (화면 직접 보고 싶으면 이 줄 제거)
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)

# ------------------------------------
# 전역 설정
# ------------------------------------
CELL_SIZE = 5.0  # 맵의 한 칸 크기 (미터)

# 🔥 TPP 내부에서 직접 조절하는 장애물 패딩 (미터 느낌의 float)

try:
    TPP_OBSTACLE_PADDING = float(os.environ.get("TPP_OBST_PADDING", "1.0"))
except Exception:
    TPP_OBSTACLE_PADDING = 0.1


# ------------------------------------
# 1. 시각화 유틸리티 (옵션)
# ------------------------------------
def visualize_map(map_info, cell_size):
    """
    obstacle_map: numpy array (H, W, 2)
      - map_info[:, :, 0] == 1 인 곳이 장애물
    cell_size: 한 셀의 실제 길이 (m)
    """
    obstacle = map_info[:, :, 0]
    h, w = obstacle.shape  # H(세로, z방향), W(가로, x방향)

    # 축을 실제 미터 단위로 보이게 하기 위해 extent 사용
    x_max = w * cell_size   # 가로 전체 길이 (m)
    y_max = h * cell_size   # 세로 전체 길이 (m)

    plt.figure(figsize=(8, 8))
    plt.imshow(
        obstacle,
        cmap='Reds',
        origin='lower',
        interpolation='nearest',
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],  # x,y축에 cell_size 반영
    )
    plt.title('Obstacle Map (Red = Obstacle)')

    # 그리드(격자선)
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    # 축 눈금도 실제 거리 기준으로 (예: 50m 간격)
    tick_step = 50.0
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))

    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    plt.tight_layout()
    plt.savefig('obstacle_map.png')
    plt.close()


def visualize_state(obstacle_map, unknowns, path_world, ally_pos, target_pos, cell_size=CELL_SIZE):
    """
    전체 상태 시각화:
      - 장애물 맵
      - IBSM unknown(장애물/차량/보병/전차) 좌표
      - 경로 (waypoints)
      - 아군 현재 위치, 목표 위치

    unknowns 예시:
      {
        "position": {"x": ..., "y": ..., "z": ...},
        "unit_type": "Vehicle" / "Infantry" / "Armored" / "Tank" / "car" 등
      }
    """
    obstacle = obstacle_map[:, :, 0]
    h, w = obstacle.shape
    x_max = w * cell_size
    y_max = h * cell_size

    plt.figure(figsize=(8, 8))
    # 장애물 맵 (0/1) → 300x300m 공간으로 표시
    plt.imshow(
        obstacle,
        cmap='Reds',
        origin='lower',
        interpolation='nearest',
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],
        alpha=0.4,
    )
    plt.title('TPP State (Obstacles / Path / Positions)')
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    # ============================
    # 1) unknown들을 타입별로 분리
    #    - 차량/카: 주황색 원
    #    - 보병: 파란색 삼각형
    #    - 전차/장갑: 빨간색 네모
    #    - 그 외: 회색 x
    # ============================
    car_x, car_z = [], []
    inf_x, inf_z = [], []
    tank_x, tank_z = [], []
    other_x, other_z = [], []

    if unknowns:
        for obj in unknowns:
            try:
                pos = obj.get('position', {})
                ux = float(pos.get('x', 0.0))
                uz = float(pos.get('z', 0.0))
                utype = str(obj.get('unit_type', 'unknown')).lower()
            except Exception:
                continue

            # unit_type에 따라 분류
            if utype in ['car']:
                car_x.append(ux)
                car_z.append(uz)
            elif utype in ['infantry']:
                inf_x.append(ux)
                inf_z.append(uz)
            elif utype in ['tank']:
                tank_x.append(ux)
                tank_z.append(uz)
            else:
                other_x.append(ux)
                other_z.append(uz)

    # 타입별로 그리기
    if tank_x:
        plt.scatter(
            tank_x, tank_z,
            marker='s', s=40,
            color='red',
            label='Tank'
        )
    if inf_x:
        plt.scatter(
            inf_x, inf_z,
            marker='^', s=40,
            color='black',
            label='Infantry'
        )
    if car_x:
        plt.scatter(
            car_x, car_z,
            marker='o', s=40,
            color='green',
            label='Vehicle'
        )
    if other_x:
        plt.scatter(
            other_x, other_z,
            marker='x', s=40,
            color='gray',
            label='Unknown'
        )

    # ============================
    # 2) 경로 (waypoints) - 월드 좌표 그대로 사용 (미터 단위)
    # ============================
    if path_world:
        path_world = np.array(path_world, dtype=float)
        plt.plot(
            path_world[:, 0],
            path_world[:, 1],
            linewidth=2,
            marker='o',
            markersize=4,
            label='Path'
        )

    # ============================
    # 3) 아군 위치
    # ============================
    if ally_pos is not None:
        try:
            plt.scatter(
                ally_pos['x'],
                ally_pos['z'],
                marker='P',
                s=100,
                color='cyan',
                edgecolors='blue',
                label='Ally'
            )
        except Exception:
            pass

    # ============================
    # 4) 목표 위치 (사격 지점)
    # ============================
    if target_pos is not None:
        try:
            plt.scatter(
                target_pos['x'],
                target_pos['z'],
                marker='X',
                s=120,
                color='orange',
                label='Target'
            )
        except Exception:
            pass

    # 축/그리드 설정
    tick_step = 50.0
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))
    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    # 범례
    plt.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig('tpp_state.png')
    plt.close()

    print("맵 이미지 저장완료 (tpp_state.png)")



# (기존 path 전용 시각화는 필요하면 따로 사용)
def visualize_path(obstacle_map, path_world, cell_size=CELL_SIZE):
    """
    obstacle_map: (H, W, 2)
    path_world: [[x, z], ...]  (월드 좌표, 미터 단위)
    """
    obstacle = obstacle_map[:, :, 0]
    h, w = obstacle.shape
    x_max = w * cell_size
    y_max = h * cell_size

    plt.figure(figsize=(8, 8))
    plt.imshow(
        obstacle,
        cmap='Reds',
        origin='lower',
        interpolation='nearest',
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],
    )
    plt.title('Path on Obstacle Map (Red = Obstacle)')
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    if path_world:
        path_world = np.array(path_world, dtype=float)
        plt.plot(
            path_world[:, 0],
            path_world[:, 1],
            linewidth=2,
            marker='o',
            markersize=4,
            label='Planned Path',
        )
        plt.legend()

    tick_step = 50.0
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))
    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    plt.tight_layout()
    plt.savefig('obstacle_map_with_path.png')
    plt.close()


# ------------------------------------
# 2. 맵 및 장애물 처리 로직
# ------------------------------------
def create_obstacle_map(unknowns, cell_size=CELL_SIZE, padding=TPP_OBSTACLE_PADDING):
    """
    unknowns 정보를 바탕으로 장애물 맵 생성
    padding: '미터 느낌' float 값 → 셀 단위 정수로 변환해서 사용
    """
    height, width = 60, 60
    obstacle_map = np.zeros((height, width, 2), dtype=np.int16)

    # padding float → 셀 단위 정수로 변환
    try:
        padding_cells = int(round(float(padding)))
    except Exception:
        padding_cells = 0

    if padding_cells < 0:
        padding_cells = 0

    for obj in unknowns:
        try:
            x_coord = obj['position']['x']
            z_coord = obj['position']['z']
        except KeyError:
            continue

        x = int(round(x_coord / cell_size))
        z = int(round(z_coord / cell_size))

        # padding_cells = 0이면 해당 칸만, 1이면 주변 1칸까지 등
        for dx in range(-padding_cells, padding_cells + 1):
            for dz in range(-padding_cells, padding_cells + 1):
                nx, nz = x + dx, z + dz
                # 원형 padding (유클리드 거리 padding 이하)
                if padding_cells == 0 or dx * dx + dz * dz <= padding_cells * padding_cells:
                    if 0 <= nx < width and 0 <= nz < height:
                        obstacle_map[nz, nx, 0] = 1    # occupancy
                        obstacle_map[nz, nx, 1] = 100  # cost (필요시 사용)

    return obstacle_map


# ------------------------------------
# 3. 경로 탐색 (정석 A*) 로직
# ------------------------------------
def path_planning(obstacle_map, start, goal, cell_size=CELL_SIZE):
    """A* 알고리즘을 사용하여 경로 탐색"""
    occ = obstacle_map[:, :, 0]
    height, width = occ.shape

    def in_bounds(x, z):
        return 0 <= x < width and 0 <= z < height

    def is_free(x, z):
        # 맵 인덱스는 (z, x) 순서
        return occ[z, x] == 0

    def heuristic(a, b):
        # 유클리드 거리
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # 실제 좌표를 격자 인덱스로 변환: (x, z)
    start_idx = (int(round(start[0] / cell_size)), int(round(start[1] / cell_size)))
    goal_idx = (int(round(goal[0] / cell_size)), int(round(goal[1] / cell_size)))

    # 목표점이 맵 밖이거나 장애물이면 경로 탐색 불가
    if not in_bounds(goal_idx[0], goal_idx[1]) or not is_free(goal_idx[0], goal_idx[1]):
        return []

    open_set = []
    # (F = G + H, G, current_node, path)
    heapq.heappush(open_set, (heuristic(start_idx, goal_idx), 0.0, start_idx, [start_idx]))

    g_scores = {start_idx: 0.0}

    # 8방향 (상하좌우+대각선)
    directions = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
    ]

    while open_set:
        est_total, cost, current, path = heapq.heappop(open_set)

        if current == goal_idx:
            # grid 인덱스를 실제 좌표(중앙)로 변환해서 반환
            return [[x * cell_size, z * cell_size] for (x, z) in path]

        # 이미 더 싼 비용으로 방문했던 노드라면 skip
        if cost > g_scores.get(current, float('inf')):
            continue

        x, z = current
        for dx, dz, move_cost in directions:
            nx, nz = x + dx, z + dz
            next_node = (nx, nz)

            if not in_bounds(nx, nz) or not is_free(nx, nz):
                continue

            new_cost = cost + move_cost

            if new_cost < g_scores.get(next_node, float('inf')):
                g_scores[next_node] = new_cost
                f_score = new_cost + heuristic(next_node, goal_idx)
                heapq.heappush(open_set, (f_score, new_cost, next_node, path + [next_node]))

    # 경로 없음
    return []


# ------------------------------------
# 4. LOS 및 경로 단순화 로직
# ------------------------------------
def check_line_of_sight(obstacle_map, p1_coord, p2_coord, cell_size=CELL_SIZE):
    """
    두 실제 좌표 [x, z] 사이에 장애물이 있는지 확인
    Bresenham's line algorithm을 응용한 맵 검사
    """
    occ = obstacle_map[:, :, 0]

    # 실제 좌표를 격자 인덱스로 변환
    x1, z1 = int(round(p1_coord[0] / cell_size)), int(round(p1_coord[1] / cell_size))
    x2, z2 = int(round(p2_coord[0] / cell_size)), int(round(p2_coord[1] / cell_size))

    dx = abs(x2 - x1)
    dz = abs(z2 - z1)
    sx = 1 if x1 < x2 else -1
    sz = 1 if z1 < z2 else -1
    err = dx - dz

    curr_x, curr_z = x1, z1

    while True:
        # 시작점은 이미 안전하다고 가정하고, 중간/끝점에서만 장애물 검사
        if (curr_x != x1 or curr_z != z1) and occ[curr_z, curr_x] == 1:
            return False  # 장애물 발견 (LOS 실패)

        if curr_x == x2 and curr_z == z2:
            break

        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            curr_x += sx
        if e2 < dx:
            err += dx
            curr_z += sz

    return True  # 장애물 없음 (LOS 성공)


def smooth_waypoints(waypoints, obstacle_map, cell_size=CELL_SIZE):
    """
    LOS 검사를 통해 경로 단순화 및 최적화
    입력: [[x, z], ...] (월드 좌표)
    """
    if not waypoints or len(waypoints) <= 2:
        return waypoints

    simplified = [waypoints[0]]
    anchor_idx = 0
    i = 1

    while i < len(waypoints):
        anchor_point = waypoints[anchor_idx]
        current_point = waypoints[i]

        los_success = check_line_of_sight(
            obstacle_map, anchor_point, current_point, cell_size=cell_size
        )

        if los_success:
            # 앵커에서 i번째까지 직선 가능 → 더 멀리 도전
            i += 1
        else:
            # 직전 i-1 가 최대 직진 가능 지점
            simplified.append(waypoints[i - 1])
            anchor_idx = i - 1
            # i는 그대로 두고, 새 anchor 기준으로 다시 검사

    # 마지막 웨이포인트 보장
    if simplified[-1] != waypoints[-1]:
        simplified.append(waypoints[-1])

    return simplified


# ------------------------------------
# 5. Flask 핸들러
# ------------------------------------
@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    try:
        request_data = request.get_json()
    except Exception as e:
        print(f"[TPP-ERR] Invalid JSON: {e}")
        return jsonify({"status": "ERR", "message": f"Invalid JSON: {str(e)}"}), 400

    try:
        ally_pos = request_data['ally_body_pos']
        target_pos = request_data['target_pos']
        unknowns = request_data.get('unknowns', [])

        # 🔥 padding은 IBSM에서 안 받고, TPP 내부 전역 값 사용
        padding = TPP_OBSTACLE_PADDING

        # 🔴 INPUT LOG (IBSM → TPP)
        print(
            f"[TPP-REQ] ally=({ally_pos['x']:.2f},{ally_pos['z']:.2f}), "
            f"target=({target_pos['x']:.2f},{target_pos['z']:.2f}), "
            f"unknowns={len(unknowns)}, padding={padding}"
        )

        # 1. 맵 생성 (패딩 옵션 적용)
        obstacle_map = create_obstacle_map(
            unknowns,
            cell_size=CELL_SIZE,
            padding=padding
        )

        # 2. A* 경로 탐색 (X, Z 평면)
        start_2d = [ally_pos['x'], ally_pos['z']]
        target_2d = [target_pos['x'], target_pos['z']]

        raw_waypoints_2d = path_planning(obstacle_map, start_2d, target_2d)

        # 경로가 없으면 빈 결과 반환
        if not raw_waypoints_2d:
            response_data = {
                "waypoints": [],
                "target_pos": target_pos,
            }

            # 시각화 (경로 없음)
            visualize_state(
                obstacle_map=obstacle_map,
                unknowns=unknowns,
                path_world=[],
                ally_pos=ally_pos,
                target_pos=target_pos,
                cell_size=CELL_SIZE
            )

            # 🔴 OUTPUT LOG — 경로 없음
            print(
                f"[TPP-RESP] waypoints=0, "
                f"target={target_pos}"
            )
            print("[TPP-RESP-DETAIL] Waypoints: (no path)")
            return jsonify(response_data)

        # 3. LOS 단순화
        waypoints_2d = smooth_waypoints(
            raw_waypoints_2d, obstacle_map, cell_size=CELL_SIZE
        )

        # 4. 3D dict 포맷으로 변환: X, Y=0.0, Z
        waypoints_dict = [
            {"x": float(x), "y": 0.0, "z": float(z)} for x, z in waypoints_2d
        ]

        # 5. 응답 데이터 구성 (IBSM 요구사항: waypoints + target_pos만)
        response_data = {
            "waypoints": waypoints_dict,
            "target_pos": target_pos,
        }

        # 🔴 OUTPUT LOG (TPP → IBSM) — 요약
        if waypoints_dict:
            print(
                f"[TPP-RESP] waypoints={len(waypoints_dict)}, "
                f"first_wp={waypoints_dict[0]}, "
                f"target={target_pos}"
            )
        else:
            print(
                f"[TPP-RESP] waypoints=0, "
                f"target={target_pos}"
            )

        # 🔵 DETAIL LOG — 모든 웨이포인트를 한 줄씩 출력
        print("[TPP-RESP-DETAIL] Waypoints:")
        for idx, wp in enumerate(waypoints_dict):
            print(f"   #{idx+1}: {wp}")

        # 🌈 시각화: 장애물 + 경로 + 위치
        # waypoints_2d 는 [[x,z], ...] (월드좌표)
        visualize_state(
            obstacle_map=obstacle_map,
            unknowns=unknowns,
            path_world=waypoints_2d,
            ally_pos=ally_pos,
            target_pos=target_pos,
            cell_size=CELL_SIZE
        )

        return jsonify(response_data)

    except Exception as e:
        print(f"[TPP-ERR] Path planning failed: {e}")
        print(traceback.format_exc())
        return jsonify({
            "status": "ERR",
            "message": f"Path planning failed: {str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


if __name__ == '__main__':
    # dev server
    app.run(host='0.0.0.0', port=5000, debug=True)
