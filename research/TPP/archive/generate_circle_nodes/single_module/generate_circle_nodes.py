"""
입력받은 좌표를 바탕으로 좌표 주위에 원형을 이루는 노드 좌표들을 생성.

credit by : oixxta

목적 : 주행 모듈과 결합해 맵 상의 obstacle 주위를 빙글빙글 돌며 데이터를 수집하는데 사용할 경로들을 생성하는데
필요한 노드들을 만들기 위함.

설명 : x, z 좌표, 생성할 노드의 갯수, 반지름 길이, 시작위치 각도, 반시계 회전 여부 
이상 총 6개의 파라미터를 입력받고, 좌표를 중심으로
생성할 노드의 갯수만큼의 노드를 최대한 균등한 거리로 생성하는 함수.

또한, 코드로 생성된 좌표들을 시계방향 기준 오후 6시에 가까운 지점부터 차례대로 만들며, 
마지막에 다시 첫 번째 좌표로 돌아오게 함. (결과적으로, 만들고자 하는 노드의 갯수 + 1개의 좌표가 Linked-list에 주입됨.)

기존 버전의 코드보다 시간복잡도(O(n log n) -> O(n)) 및 공간복잡도 개선, 단 한개의 매서드로 압축, 
반시계방향 회전 여부 및 시작 위치의 각도를 자유롭게 할 수 있게 개선.

추가로, 해당 매서드로 생성된 좌표들을 WaypointList에 넣고 확인해 볼 수 있는 예시코드도 함께 동봉됨.

위의 class WaypointNode와 WaypointList는 techgyu가 제작한 웨이포인트 관리 단방향 Linked-list,
generate_circle_nodes 매서드가 개발물.
import math 필요함.
"""


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

# x, y, z 값을 입력받아 원형 노드 좌표를 생성하는 매서드.
import math                         # 필수
import matplotlib.pyplot as plt     # 시각화 테스트용, 실제 구동 시엔 필요없음


def generate_circle_nodes(x, z, num_nodes, radius, start_pos_angle, reverse):
    ### 각 증분(라디안)
    if reverse == True:     # 반시계 회전 여부가 True일 경우 : 
        delta = 2 * math.pi / num_nodes   #원을 한 바퀴(2π 라디안) 도는 각도를 num_nodes 개로 나눈 증분각 계산(반시계방향)
    else:                   # 반시계 회전 여부가 False일 경우 : 
        delta = -2 * math.pi / num_nodes  #원을 한 바퀴(2π 라디안) 도는 각도를 num_nodes 개로 나눈 증분각 계산(시계방향)

    ### 시작각/증분각의 sin,cos를 한 번만 계산
    theta = math.radians(start_pos_angle)   # 시작 각도를 각도에서 라디안으로 변환
    cos_t, sin_t = math.cos(theta), math.sin(theta) # 시작각의 cos와 sin을 미리 계산 : 번째 점의 초기 방향 벡터를 만들 때 사용.
    cos_d, sin_d = math.cos(delta), math.sin(delta) # 증분각의 cos와 sin을 미리 계산 : 재계산을 안함으로서 속도 최적화

    ### 시작 벡터 r*[cosθ, sinθ]
    vx, vz = radius * cos_t, radius * sin_t    # 중심으로부터 start_pos_angle만큼 떨어진 첫 번째 점의 상대좌표.

    for _ in range(num_nodes):                 # 지정한 노드 개수만큼 반복 (각도마다 한 점 생성).
        # 현재 점 기록
        waypoints.append(x + vx, z + vz)       # 현재 중심 (x, z)에 벡터 (vx, vz)를 더해 실제 좌표로 변환하고 리스트에 추가.
        # 다음 점 = 회전행렬 * 현재 벡터
        # [vx', vz'] = [vx*cosΔ - vz*sinΔ, vx*sinΔ + vz*cosΔ]
        nvx = vx * cos_d - vz * sin_d          # 회전 행렬을 이용해 벡터를 Δθ만큼 회전
        nvz = vx * sin_d + vz * cos_d
        vx, vz = nvx, nvz                      # 회전 후 벡터를 다음 루프의 기준으로 갱신.

    waypoints.append(x + vx, z + vz)           # 원의 시작점으로 다시 돌아오는 마지막 점 추가 : 폐곡선 완성을 위해.



generate_circle_nodes(100, 200, num_nodes = 12, radius = 10, start_pos_angle = 270, reverse=False) 
# x, z 좌표, 노드 갯수(짝수로 입력할것!), 반지름 넓이, 타겟과 시작 노드 사이의 각도 : 6시 시작 시, 270으로, 반시계방향 여부(bool)

print(waypoints.to_list())  # 웨이포인트에 generate_circle_nodes가 만든 좌표들이 정상적으로 주입되었는지 확인용



# 이하 시각화 (코드 테스트용, 실제 구동 시엔 필요 없음.)
nodes = waypoints.to_list()
x_vals = [node['x'] for node in nodes]
z_vals = [node['z'] for node in nodes]

plt.figure(figsize=(6,6))
plt.plot(x_vals, z_vals, 'o-', color='royalblue', label='Order Path')

# 점 번호 표시
for i, (px, pz) in enumerate(zip(x_vals, z_vals)):
    plt.text(px, pz, str(i), fontsize=9, ha='center', va='center', color='darkred')

# 중심점 표시
plt.scatter(100, 200, color='red', marker='x', s=100, label='Center')

plt.title("Waypoint Order")
plt.xlabel("X coordinate")
plt.ylabel("Z coordinate")
plt.legend()
plt.grid(True)
plt.gca().set_aspect('equal', adjustable='box')
plt.show()

