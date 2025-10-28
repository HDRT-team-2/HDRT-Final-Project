# --- 연결 리스트 형태의 웨이포인트(목표) 관리 ---
class WaypointNode:
    def __init__(self, x, z, arrived=False):
        self.x = float(x)
        self.z = float(z)
        self.arrived = bool(arrived)
        self.next = None

class WaypointList:
    def __init__(self):
        self.head = None
        self.tail = None
        self._len = 0

    def append(self, x, z, arrived=False):
        node = WaypointNode(x, z, arrived)
        if not self.head:
            self.head = self.tail = node
        else:
            self.tail.next = node
            self.tail = node
        self._len += 1
        return node

    def peek(self):
        return self.head

    def pop(self):
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None
        node.next = None
        self._len -= 1
        return node

    def mark_head_arrived(self):
        if self.head:
            self.head.arrived = True
            return True
        return False

    def is_empty(self):
        return self.head is None

    def to_list(self):
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z, 'arrived': cur.arrived})
            cur = cur.next
        return out

# 전역 웨이포인트 리스트 인스턴스 (기본값: 빈 리스트)
waypoints = WaypointList()

def auto_locate(obstacles):
    """
    장애물 9개를 그룹 분류/정렬 후, 각 장애물의 중심좌표(x, z)를 group3에 저장하고,
    순서대로 waypoints(연결 리스트)에 추가한다.
    Args:
        obstacles: 장애물 리스트 [{'x_min': ..., 'x_max': ..., 'z_min': ..., 'z_max': ...}, ...]
    Returns:
        group3: [(x, z), ...] 형태의 리스트
    """
    if len(obstacles) != 9:
        print(f"⚠️ 장애물 개수가 9개가 아닙니다. 현재: {len(obstacles)}개")
        return []

    # 1. group1에 9개 장애물 저장 (원본 순서)
    group1 = obstacles.copy()

    # 2. z_max 기준으로 그룹 분류
    a_group, b_group, c_group = [], [], []
    for obstacle in group1:
        z_max = obstacle['z_max']
        if z_max <= 100:
            a_group.append(obstacle)
        elif z_max <= 200:
            b_group.append(obstacle)
        else:
            c_group.append(obstacle)

    print(f"📊 그룹 분류 결과: A그룹({len(a_group)}개), B그룹({len(b_group)}개), C그룹({len(c_group)}개)")

    # 3. 정렬
    a_group.sort(key=lambda x: x['x_max'])
    c_group.sort(key=lambda x: x['x_max'])
    b_group.sort(key=lambda x: x['x_max'], reverse=True)

    # 4. group2 생성 (정렬된 순서)
    group2 = a_group + b_group + c_group

    # 5. 좌표 한개씩 출력
    print("\n📋 최종 정렬된 장애물 좌표:")
    for i, obstacle in enumerate(group2, 1):
        print(f"  {i}번: x_min={obstacle['x_min']:.2f}, x_max={obstacle['x_max']:.2f}, "
              f"z_min={obstacle['z_min']:.2f}, z_max={obstacle['z_max']:.2f}")

    # 6. 각 장애물의 중심좌표 계산하여 group3에 저장
    group3 = []
    for obstacle in group2:
        center_x = (obstacle['x_min'] + obstacle['x_max']) / 2
        center_z = (obstacle['z_min'] + obstacle['z_max']) / 2
        group3.append((center_x, center_z))

    # 7. group3을 waypoints 연결리스트에 추가
    for x, z in group3:
        waypoints.append(x, z)

    # 8. 저장된 좌표쌍 출력
    print("\n🟢 Waypoints에 저장된 좌표쌍:")
    for i, wp in enumerate(waypoints.to_list(), 1):
        print(f"  {i}번: x={wp['x']:.2f}, z={wp['z']:.2f}, arrived={wp['arrived']}")

