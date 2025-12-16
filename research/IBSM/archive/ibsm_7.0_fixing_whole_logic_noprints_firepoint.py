# IBSM(Integrated Battlefield Situation Management)
from flask import Flask, request, jsonify
import requests
from typing import Optional
import math
import time
import os
import glob
import cv2
import base64
import numpy as np

# --------------------------------------------------------------------
# info, get_action | Tank Turret Rotation Control
global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
# info, get_action | Tank Fire Control
global_fire_command = False

global_enemy_id = 1
global_ally_id = 1
global_unknown_id = 1

# 시뮬레이터 시간 (초기값은 0.0, /info 엔드포인트에서 업데이트됨)
global_time = 0.0

global_replan_required = False  # TPP 재 계획 플래그
# --------------------------------------------------------------------
# Hostile Object Info - Linked List
class EnemyNode:
    """적 객체 노드"""
    def __init__(self, enemy_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                 unit_type, identification_time, status="active", speed=0.0, threat_level=0.0):
        self.enemy_id = enemy_id  # 적 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.body_angle_x = body_angle_x  # 차체 X 각도
        self.body_angle_y = body_angle_y  # 차체 Y 각도
        self.body_angle_z = body_angle_z  # 차체 Z 각도
        self.unit_type = unit_type  # "infantry", "tank", "armored", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = status  # 상태: "destroyed", "active", "missing"
        self.speed = speed  # 속도 (m/s)
        self.threat_level = threat_level  # 적 위협도 (0.0 ~ 1.0)
        self.next: Optional['EnemyNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["destroyed", "active", "missing"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "enemy_id": self.enemy_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "body_angle": {"x": self.body_angle_x, "y": self.body_angle_y, "z": self.body_angle_z},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed,
            "threat_level": self.threat_level
        }

class EnemyList:
    """적 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[EnemyNode] = None
        self.count = 0
        self.position_threshold = 5.0  # 5m 이내면 같은 객체로 판단
    
    def find_enemy_by_position(self, pos_x, pos_y, pos_z, unit_type):
        """위치 및 유닛 타입 기반으로 적 검색 (거리 임계값 이내)"""
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            if distance <= self.position_threshold and current.unit_type == unit_type:
                return current
            current = current.next
        return None
    
    def find_enemy(self, enemy_id):
        """적 ID로 검색"""
        current = self.head
        while current:
            if current.enemy_id == enemy_id:
                return current
            current = current.next
        return None
    
    def get_all_enemies(self):
        """모든 적 정보 반환"""
        enemies = []
        current = self.head
        while current:
            enemies.append(current.to_dict())
            current = current.next
        return enemies
    
    def clear(self):
        """모든 적 제거"""
        self.head = None
        self.count = 0

    def add_or_update_enemy(self, enemy_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                           unit_type, identification_time, speed=0.0, threat_level=0.0, ):
        """적 업데이트 또는 신규 추가
        - enemy_id가 주어지면: 해당 ID의 적을 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - enemy_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_enemy_id
        
        # Case 1: ID가 주어진 경우 - 해당 ID의 적 찾아서 업데이트 또는 그 ID로 신규 생성
        if enemy_id is not None:
            existing_enemy = self.find_enemy(enemy_id)
            if existing_enemy:
                # 기존 적 찾았으면 위치와 정보 업데이트
                existing_enemy.pos_x = pos_x 
                existing_enemy.pos_y = pos_y
                existing_enemy.pos_z = pos_z
                existing_enemy.body_angle_z = body_angle_z
                existing_enemy.unit_type = unit_type
                existing_enemy.identification_time = identification_time
                existing_enemy.update_speed(speed)
                return existing_enemy
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                new_enemy = EnemyNode(
                    enemy_id, pos_x, pos_y, pos_z, 
                    body_angle_x, body_angle_y, body_angle_z,  # 순서 수정!
                    unit_type, identification_time, 
                    "active",  # status
                    speed,  # speed
                    threat_level  # threat_level
                )

                if not self.head:
                    self.head = new_enemy
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_enemy
                
                self.count += 1
                # global_enemy_id는 증가시키지 않음 (지정된 ID 사용)
                return new_enemy
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_enemy = self.find_enemy_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_enemy:
            # 기존 적이 있으면 정보만 업데이트 (위치와 unit_type은 이미 일치하므로 제외)
            nearby_enemy.identification_time = identification_time
            return nearby_enemy
        
        # Case 3: 완전히 새로운 적 발견 - 자동으로 ID 부여
        new_enemy = EnemyNode(
            global_enemy_id, 
            pos_x, 
            pos_y, 
            pos_z, 
            body_angle_x, 
            body_angle_y, 
            body_angle_z,  # 순서 수정!
            unit_type, 
            identification_time,
            "active",  # status
            speed,  # speed
            threat_level  # threat_level
        )

        if not self.head:
            self.head = new_enemy
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_enemy
        
        self.count += 1
        global_enemy_id += 1  # 새로운 적 발견 시 ID 증가
        return new_enemy

# Enemy List 전역 인스턴스
enemy_list = EnemyList()

# --------------------------------------------------------------------
# Ally Object Info - Linked List
class AllyNode:
    """아군 객체 노드"""
    def __init__(self, ally_id, pos_x, pos_y, pos_z, body_angle_x, body_angle_y, body_angle_z,
                 turret_angle_x, turret_angle_y, unit_type, identification_time, speed,
                 mission_number=None, combat_status="normal"):
        self.ally_id = ally_id  # 아군 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.body_angle_x = body_angle_x  # 차체 X 각도
        self.body_angle_y = body_angle_y  # 차체 Y 각도
        self.body_angle_z = body_angle_z  # 차체 Z 각도
        self.turret_angle_x = turret_angle_x  # 포탑 X 각도
        self.turret_angle_y = turret_angle_y  # 포탑 Y 각도
        self.unit_type = unit_type  # "infantry", "tank", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = "active"  # 상태: "destroyed", "active", "missing"
        self.speed = speed  # 속도 (m/s)
        self.mission_number = mission_number  # 임무 번호
        self.combat_status = combat_status  # 전투 상태
        self.next: Optional['AllyNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["destroyed", "active", "missing"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "ally_id": self.ally_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "body_angle": {"x": self.body_angle_x, "y": self.body_angle_y, "z": self.body_angle_z},
            "turret_angle": {"x": self.turret_angle_x, "y": self.turret_angle_y},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed,
            "mission_number": self.mission_number,
            "combat_status": self.combat_status
        }

class AllyList:
    """아군 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[AllyNode] = None
        self.count = 0
        self.position_threshold = 5.0  # 5m 이내면 같은 객체로 판단
    
    def find_ally_by_position(self, pos_x, pos_y, pos_z, unit_type=None, threshold=None):
        """위치 및 유닛 타입 기반으로 아군 검색 (거리 임계값 이내)"""
        if threshold is None:
            threshold = self.position_threshold
        
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            if distance <= threshold:
                if unit_type is None or current.unit_type == unit_type:
                    return current
            current = current.next
        return None
    
    def find_ally(self, ally_id):
        """아군 ID로 검색"""
        current = self.head
        while current:
            if current.ally_id == ally_id:
                return current
            current = current.next
        return None
    
    def get_all_allies(self):
        """모든 아군 정보 반환"""
        allies = []
        current = self.head
        while current:
            allies.append(current.to_dict())
            current = current.next
        return allies
    
    def get_active_allies(self):
        """활성 상태의 아군만 반환"""
        allies = []
        current = self.head
        while current:
            if current.status == "active":
                allies.append(current.to_dict())
            current = current.next
        return allies
    
    def clear(self):
        """모든 아군 제거"""
        self.head = None
        self.count = 0
        
    def add_or_update_ally(self, pos_x, pos_y, pos_z, unit_type, identification_time, speed,
                          body_angle_x, body_angle_y, body_angle_z, turret_angle_x, turret_angle_y, 
                          ally_id=None, mission_number=0, combat_status="normal"):
        """아군 업데이트 또는 신규 추가 - 모든 정보 포함
        - ally_id가 주어지면: 해당 ID의 아군을 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - ally_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_ally_id
        
        # Case 1: ID가 주어진 경우
        if ally_id is not None:
            existing_ally = self.find_ally(ally_id)
            if existing_ally:
                # 기존 아군 찾았으면 모든 정보 업데이트
                existing_ally.update_position(pos_x, pos_y, pos_z)
                existing_ally.body_angle_x = body_angle_x
                existing_ally.body_angle_y = body_angle_y
                existing_ally.body_angle_z = body_angle_z
                existing_ally.unit_type = unit_type
                existing_ally.identification_time = identification_time
                existing_ally.update_speed(speed)
                existing_ally.turret_angle_x = turret_angle_x
                existing_ally.turret_angle_y = turret_angle_y
                existing_ally.mission_number = mission_number
                existing_ally.combat_status = combat_status
                return existing_ally
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                new_ally = AllyNode(
                    ally_id, pos_x, pos_y, pos_z, 
                    body_angle_x, body_angle_y, body_angle_z,
                    turret_angle_x, turret_angle_y,
                    unit_type, identification_time, speed,
                    mission_number, combat_status
                )
                
                if not self.head:
                    self.head = new_ally
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_ally
                
                self.count += 1
                return new_ally
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_ally = self.find_ally_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)
        
        if nearby_ally:
            # 기존 아군이 있으면 정보만 업데이트
            nearby_ally.pos_x
            nearby_ally.pos_y
            nearby_ally.pos_z
            nearby_ally.body_angle_x
            nearby_ally.body_angle_y
            nearby_ally.body_angle_z
            nearby_ally.identification_time = identification_time
            nearby_ally.update_speed(speed)
            nearby_ally.turret_angle_x = turret_angle_x
            nearby_ally.turret_angle_y = turret_angle_y
            nearby_ally.mission_number = mission_number
            nearby_ally.combat_status = combat_status
            return nearby_ally
        
        # Case 3: 완전히 새로운 아군 발견 - 자동으로 ID 부여
        new_ally = AllyNode(
            global_ally_id, pos_x, pos_y, pos_z,
            body_angle_x, body_angle_y, body_angle_z,
            turret_angle_x, turret_angle_y,
            unit_type, identification_time, speed,
            mission_number, combat_status
        )
        
        if not self.head:
            self.head = new_ally
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_ally
        
        self.count += 1
        global_ally_id += 1
        return new_ally
    
    def get_ally_position(self, ally_id):
        """아군 ID로 위치 정보 반환 (x, y, z 튜플)"""
        ally = self.find_ally(ally_id)
        if ally:
            return ally.pos_x, ally.pos_y, ally.pos_z
        return None, None, None
    
    def remove_ally(self, ally_id):
        """아군 제거"""
        if not self.head:
            return False
        
        if self.head.ally_id == ally_id:
            self.head = self.head.next  # type: ignore
            self.count -= 1
            return True
        
        current = self.head
        while current.next:
            next_node = current.next
            if hasattr(next_node, 'ally_id') and next_node.ally_id == ally_id:
                current.next = next_node.next
                self.count -= 1
                return True
            current = next_node
        
        return False

# Ally List 전역 인스턴스
ally_list = AllyList()

# --------------------------------------------------------------------
# Unknown Object Info - Linked List
class UnknownNode:
    """미식별 객체 노드 (장애물, 민간인 등)"""
    def __init__(self, unknown_id, pos_x, pos_y, pos_z, object_angle_x, object_angle_y,
                 unit_type, identification_time, status="active", speed=0.0):
        self.unknown_id = unknown_id  # 미식별 객체 식별 번호
        self.pos_x = pos_x  # X 위치
        self.pos_y = pos_y  # Y 위치
        self.pos_z = pos_z  # Z 위치
        self.object_angle_x = object_angle_x  # 객체 수평 각도
        self.object_angle_y = object_angle_y  # 객체 수직 각도
        self.unit_type = unit_type  # "obstacle", "civilian", "vehicle", "building", etc.
        self.identification_time = identification_time  # 식별 시각
        self.status = status  # 상태: "active", "inactive", "removed"
        self.speed = speed  # 속도 (m/s) - 이동 가능한 객체의 경우
        self.next: Optional['UnknownNode'] = None
    
    def update_position(self, x, y, z):
        """위치 업데이트"""
        self.pos_x = x
        self.pos_y = y
        self.pos_z = z
    
    def update_status(self, status):
        """상태 업데이트"""
        if status in ["active", "inactive", "removed"]:
            self.status = status
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = speed
    
    def to_dict(self):
        """JSON 형태로 변환"""
        return {
            "unknown_id": self.unknown_id,
            "position": {"x": self.pos_x, "y": self.pos_y, "z": self.pos_z},
            "object_angle": {"x": self.object_angle_x, "y": self.object_angle_y},
            "unit_type": self.unit_type,
            "identification_time": self.identification_time,
            "status": self.status,
            "speed": self.speed
        }

class UnknownList:
    """미식별 객체 Linked List 관리"""
    def __init__(self):
        self.head: Optional[UnknownNode] = None
        self.count = 0
        self.position_threshold = 5.0  # 5m 이내면 같은 객체로 판단
    
    def find_unknown_by_position(self, pos_x, pos_y, pos_z, unit_type):
        """위치 및 유닛 타입 기반으로 미식별 객체 검색 (거리 임계값 이내)"""
        current = self.head
        while current:
            distance = math.sqrt(
                (current.pos_x - pos_x)**2 + 
                (current.pos_y - pos_y)**2 + 
                (current.pos_z - pos_z)**2
            )
            if distance <= self.position_threshold and current.unit_type == unit_type:
                return current
            current = current.next
        return None
    
    def find_unknown(self, unknown_id):
        """미식별 객체 ID로 검색"""
        current = self.head
        while current:
            if current.unknown_id == unknown_id:
                return current
            current = current.next
        return None
    
    def get_all_unknowns(self):
        """모든 미식별 객체 정보 반환"""
        unknowns = []
        current = self.head
        while current:
            unknowns.append(current.to_dict())
            current = current.next
        return unknowns
    
    def clear(self):
        """모든 미식별 객체 제거"""
        self.head = None
        self.count = 0
      
    def add_or_update_unknown(self, unknown_id, pos_x, pos_y, pos_z, object_angle_x, object_angle_y,
                             unit_type, identification_time, speed=0.0):
        """미식별 객체 업데이트 또는 신규 추가
        - unknown_id가 주어지면: 해당 ID의 객체를 찾아서 업데이트, 없으면 그 ID로 신규 생성
        - unknown_id가 None이면: 위치 기반으로 검색 후 업데이트 또는 신규 추가 (자동 ID 부여)
        """
        global global_unknown_id
        global global_replan_required
        
        # Case 1: ID가 주어진 경우
        if unknown_id is not None:
            existing_unknown = self.find_unknown(unknown_id)
            if existing_unknown:
                # 기존 객체 찾았으면 위치와 정보 업데이트
                existing_unknown.update_position(pos_x, pos_y, pos_z)
                existing_unknown.object_angle_x = object_angle_x
                existing_unknown.object_angle_y = object_angle_y
                existing_unknown.unit_type = unit_type
                existing_unknown.identification_time = identification_time
                existing_unknown.update_speed(speed)
                return existing_unknown
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                new_unknown = UnknownNode(
                    unknown_id, pos_x, pos_y, pos_z, 
                    object_angle_x, object_angle_y,
                    unit_type, identification_time,
                    "active", speed
                )
                
                if not self.head:
                    self.head = new_unknown
                else:
                    current = self.head
                    while current.next:
                        current = current.next
                    current.next = new_unknown
                global_replan_required = True  # 새로운 미식별 객체 발견 시 재계획 필요
                self.count += 1
                return new_unknown
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_unknown = self.find_unknown_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_unknown:
            # 기존 객체가 있으면 정보만 업데이트
            nearby_unknown.identification_time = identification_time
            nearby_unknown.update_speed(speed)
            return nearby_unknown
        
        # Case 3: 완전히 새로운 객체 발견 - 자동으로 ID 부여
        new_unknown = UnknownNode(
            global_unknown_id, pos_x, pos_y, pos_z,
            object_angle_x, object_angle_y,
            unit_type, identification_time,
            "active", speed
        )
        global_replan_required = True  # 새로운 미식별 객체 발견 시 재계획 필요
        if not self.head:
            self.head = new_unknown
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_unknown
        
        self.count += 1
        global_unknown_id += 1
        return new_unknown
    
    def remove_unknown(self, unknown_id):
        """미식별 객체 제거"""
        if not self.head:
            return False
        
        if self.head.unknown_id == unknown_id:
            self.head = self.head.next  # type: ignore
            self.count -= 1
            return True
        
        current = self.head
        while current.next:
            next_node = current.next
            if hasattr(next_node, 'unknown_id') and next_node.unknown_id == unknown_id:
                current.next = next_node.next
                self.count -= 1
                return True
            current = next_node
        
        return False

# Unknown List 전역 인스턴스
unknown_list = UnknownList()

# --------------------------------------------------------------------
# Helper functions for image processing

def get_latest_image(directory):
    """디렉토리에서 가장 최신 이미지 파일 경로 반환"""
    images = glob.glob(os.path.join(directory, "*.*"))
    if images:
        latest_image = max(images, key=os.path.getmtime)
        return latest_image
    else:
        return None

def encode_image_to_base64(image_path):
    """이미지 파일을 읽어서 base64로 인코딩"""
    if image_path is None:
        return None
    
    try:
        image = cv2.imread(image_path)
        if image is None:
            return None
        
        # numpy array를 base64로 인코딩
        _, buffer = cv2.imencode('.jpg', image)
        image_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        return image_b64
    except Exception as e:
        return None

# --------------------------------------------------------------------

def send_fcs(request_data=None):
    """FCS에 사격 통제 요청"""
    external_server = "http://192.168.0.21:5000/get_fcs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
    except Exception as e:
        ext_result = {"error": str(e)}
    return ext_result

def send_adcs(request_data=None):
    external_server = "http://192.168.0.124:5000/get_adcs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
    except Exception as e:
        ext_result = {"error": str(e)}
    return ext_result

def send_vdrs(request_data=None):
    main_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images"
    left_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images\L"
    right_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images\R"

    # 메인 이미지(가장 최신)와, 그 직후 생성된 L/R 이미지만 전송
    def get_latest_png(directory):
        images = glob.glob(os.path.join(directory, "*.png"))
        if not images:
            return None
        return max(images, key=os.path.getmtime)

    main_image_path = get_latest_png(main_image_dir)
    main_time = os.path.getmtime(main_image_path) if main_image_path else None

    def get_next_image(directory, after_time):
        images = glob.glob(os.path.join(directory, "*.png"))
        # after_time보다 크면서 가장 작은(가장 가까운) 생성시간
        next_img = None
        min_dt = float('inf')
        for img in images:
            t = os.path.getmtime(img)
            if t > after_time and (t - after_time) < min_dt:
                min_dt = t - after_time
                next_img = img
        return next_img

    left_image_path = get_next_image(left_image_dir, main_time) if main_time else None
    right_image_path = get_next_image(right_image_dir, main_time) if main_time else None

    main_image_data = encode_image_to_base64(main_image_path)
    left_image_data = encode_image_to_base64(left_image_path)
    right_image_data = encode_image_to_base64(right_image_path)

    # === 이미지 전송 후 모든 이미지 삭제 (main, L, R 디렉토리 비우기) ===
    def delete_all_images(directory):
        images = glob.glob(os.path.join(directory, "*.png"))
        for img in images:
            try:
                os.remove(img)
            except Exception as e:
                print()

    delete_all_images(main_image_dir)
    delete_all_images(left_image_dir)
    delete_all_images(right_image_dir)


    # [IBSM 불러오기] ally_list에서 ID 0번 아군(플레이어 탱크) 가져오기
    ally = ally_list.find_ally(0)
    if not ally:
        return jsonify({"error": "No ally with ID 0 found"}), 400

    request_data = {
    "time": global_time,  # 시뮬레이터 시각
    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},  # 아군 전차 차체 X, Y, Z 위치
    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},  # 아군 전차 차체 X, Y, Z 각도
    "ally_speed": ally.speed,  # 아군 전차 속도(m/s)
    "image_b64": main_image_data,  # base64 인코딩된 메인 이미지
    "stereo_image_left_b64": left_image_data,  # base64 인코딩된 왼쪽 스테레오 이미지
    "stereo_image_right_b64": right_image_data,  # base64 인코딩된 오른쪽 스테레오 이미지
    }
    
    external_server = "http://192.168.0.15:5000/get_vdrs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
    except Exception as e:
        ext_result = {"error": str(e)}
    return ext_result

def send_tpp(request_data=None):
    """TPP에 경로 계획 요청"""
    external_server = "http://192.168.0.132:5000/get_tpp"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
    except Exception as e:
        ext_result = {"error": str(e)}
    return ext_result

# --------------------------------------------------------------------

app = Flask(__name__)

@app.route('/info', methods=['POST'])
def info():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command
    global global_enemy_id
    global global_ally_id
    global global_time
    global global_replan_required

    # Reset global commands and weights
    global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
    global_fire_command = False

    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400

    time = request_data["time"]
    distance = request_data["distance"]

    player_x = request_data["playerPos"]["x"]
    player_y = request_data["playerPos"]["y"]
    player_z = request_data["playerPos"]["z"]

    player_speed = request_data["playerSpeed"]
    player_health = request_data["playerHealth"]
    player_turret_x = request_data["playerTurretX"]
    player_turret_y = request_data["playerTurretY"]
    player_body_x = request_data["playerBodyX"]
    player_body_y = request_data["playerBodyY"]
    player_body_z = request_data["playerBodyZ"]

    enemy_x = request_data["enemyPos"]["x"]
    enemy_y = request_data["enemyPos"]["y"]
    enemy_z = request_data["enemyPos"]["z"]

    enemy_speed = request_data["enemySpeed"]
    enemy_health = request_data["enemyHealth"]
    enemy_turret_x = request_data["enemyTurretX"]
    enemy_turret_y = request_data["enemyTurretY"]
    enemy_body_x = request_data["enemyBodyX"]
    enemy_body_y = request_data["enemyBodyY"]
    enemy_body_z = request_data["enemyBodyZ"]

    global_time = time

    # [IBSM 업데이트] Tank Commander - Ally (모든 정보 포함)
    ally_list.add_or_update_ally(
        pos_x=player_x,
        pos_y=player_y,
        pos_z=player_z,
        unit_type="armored",
        identification_time=global_time,
        speed=player_speed,
        body_angle_x=player_body_x,
        body_angle_y=player_body_y,
        body_angle_z=player_body_z,
        turret_angle_x=player_turret_x,
        turret_angle_y=player_turret_y,
        ally_id=0,
        mission_number=0,
        combat_status="active"
    )
    
    # [IBSM 업데이트] Tank Commander - Enemy
    enemy_list.add_or_update_enemy(
        enemy_id=0,
        pos_x=enemy_x, 
        pos_y=enemy_y, 
        pos_z=enemy_z,
        body_angle_x=enemy_body_x,
        body_angle_y=enemy_body_y,
        body_angle_z=enemy_body_z,
        unit_type="armored",
        identification_time=global_time, 
        speed=enemy_speed, 
        threat_level=0.0
    )
    
    # [IBSM 불러오기] ally_list에서 ID 0번 아군(플레이어 탱크) 가져오기
    ally = ally_list.find_ally(0)
    if not ally:
        return jsonify({"error": "No ally with ID 0 found"}), 400
    
    # [IBSM 불러오기] enemy_list에서 ID 0번 적 가져오기
    enemy = enemy_list.find_enemy(0)
    if not enemy:
        return jsonify({"error": "No enemy with ID 0 found"}), 400
    
    current_target_pos = {"x": enemy.pos_x, "y": enemy.pos_y, "z": enemy.pos_z}

# -------------------------[공격 임무 기반 로직: 적 인식 상황으로 가정]------------------------------------
    # 개선된 단일 패스 로직 (info 1회 호출 내)

    # 1. FCS에 현재 위치에서 적 공격 가능 여부 1회 요청
    #     - 사격 가능: 사격 명령 반환 (TPP/ADCS/VDRS 호출 없음)
    #     - 사격 불가: FCS가 제안한 사격 가능 위치 반환

    # 1. FCS에 현재 위치에서 적 공격 가능 여부 1회 요청
    request_data_fcs = {
        "time": global_time,
        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
        "ally_speed": ally.speed,
        "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
        "ibsm_target": current_target_pos,
        "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
        "AD_command": global_AD_command, # 스테빌라이저 고도화용
        "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
        "WS_command": global_WS_command, # 스테빌라이저 고도화용
        "WS_weight": global_WS_weight # 스테빌라이저 고도화용
    }
    fcs_data = send_fcs(request_data_fcs)

    # 사격 가능: 사격 명령 반환 (TPP/ADCS/VDRS 호출 없음)
    if fcs_data['new_fire_point'] is None:
        # 1-1. 사격 가능 시: 사격 명령 반환
        global_QE_command = fcs_data['QE_command']
        global_QE_weight = fcs_data['QE_weight']
        global_RF_command = fcs_data['RF_command']
        global_RF_weight = fcs_data['RF_weight']
        global_fire_command = fcs_data['fire_command']

    elif fcs_data['new_fire_point'] is not None:
        # 1-2. 사격 불가 시: FCS가 제안한 사격 가능 위치로 이동
        
        # 새로운 타겟 위치 설정 (FCS가 제안한 사격 가능 위치)
        new_fire_point = fcs_data['new_fire_point']
        global_fire_point = new_fire_point

        # 2. (사격 불가 시) TPP에 현재 위치 → 사격 가능 위치 경로 1회 요청
        if global_replan_required == True: # 경로 재계산이 필요할 때에만 재계산 요청
            request_data_tpp = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "target_pos": new_fire_point, # 사격 가능 지점으로 이동 명령 설정
                "unknowns": unknown_list.get_all_unknowns()  # 미식별 객체(장애물 등) 정보
            }
            tpp_data = send_tpp(request_data_tpp)
            global_replan_required = False # 경로 재 계산 후 경로 재 계산 필요 없음으로 전환
        else: # replan_required가 False일 때
            tpp_data = {
                "waypoints": [],  # 빈 경로 반환
                "target_pos": []
            }
 
        # 3. ADCS에 해당 경로로 이동 명령 1회 요청
        request_data_adcs = {
            "time" : global_time, # 시뮬레이터 시각
            "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z}, # 아군 전차 차체 X, Y, Z 위치
            "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z}, # 아군 전차 차체 X, Y, Z 각도
            "ally_speed": ally.speed, # 아군 전차 속도(m/s)
            "waypoints" : tpp_data['waypoints'] # 사격 가능 지점으로 이동하는 waypoints, 빈 경로가 넘어가면, 이전에 주행중인 경로를 지속하도록 코드 수정
        }
        adcs_data = send_adcs(request_data_adcs)
        global_WS_command = adcs_data['WS_command']
        global_WS_weight = adcs_data['WS_weight']
        global_AD_command = adcs_data['AD_command']
        global_AD_weight = adcs_data['AD_weight']

        request_data_fcs = {
            "time": global_time,
            "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
            "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
            "ally_speed": ally.speed,
            "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
            "ibsm_target": current_target_pos,
            "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
            "AD_command": global_AD_command, # 스테빌라이저 고도화용
            "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
            "WS_command": global_WS_command, # 스테빌라이저 고도화용
            "WS_weight": global_WS_weight # 스테빌라이저 고도화용
        }
        global_QE_command = fcs_data['QE_command']
        global_QE_weight = fcs_data['QE_weight']

        fcs_data = send_fcs(request_data_fcs)
        

        # 4. VDRS에 이동 경로 상 장애물 탐지 1회 요청
        vdrs_data = send_vdrs()
    
        # VDRS 데이터 처리 (탐지된 객체들을 분류)
        if vdrs_data and isinstance(vdrs_data, dict) and 'detected_objects' in vdrs_data:
            detected_objects = vdrs_data.get('detected_objects', [])
            
            for obj in detected_objects:
                if not isinstance(obj, dict):
                    continue
                
                try:
                    obj_class = obj.get('class', 'UNKNOWN')  # 객체 클래스 (TANK, INFANTRY, OBSTACLE 등)
                    obj_pos = obj.get('object_pos', {})  # 객체 위치 {x, y, z}
                    obj_angle = obj.get('object_angle_xy', {})  # 객체 각도 {x, y}
                    
                    if not isinstance(obj_pos, dict) or not isinstance(obj_angle, dict):
                        continue
                    
                    pos_x = float(obj_pos.get('x', 0.0))
                    pos_y = float(obj_pos.get('y', 0.0))
                    pos_z = float(obj_pos.get('z', 0.0))
                    angle_x = float(obj_angle.get('x', 0.0))
                    angle_y = float(obj_angle.get('y', 0.0))
                    
                    # 객체 클래스에 따라 분류
                    if obj_class in ['Armored']:
                        # 적 전차로 분류 (아군인지 적군인지는 추가 로직 필요)
                        # 일단 적으로 간주하고 추가
                        enemy_list.add_or_update_enemy(
                            enemy_id=None,  # 자동 ID 부여
                            pos_x=pos_x,
                            pos_y=pos_y,
                            pos_z=pos_z,
                            body_angle_x=angle_x,
                            body_angle_y=angle_y,
                            body_angle_z=0.0,
                            unit_type=obj_class,
                            identification_time=global_time,
                            speed=0.0,
                            threat_level=0.8
                        )

                    elif obj_class in ['Infantry']:
                        # 보병으로 분류
                        enemy_list.add_or_update_enemy(
                            enemy_id=None,
                            pos_x=pos_x,
                            pos_y=pos_y,
                            pos_z=pos_z,
                            body_angle_x=angle_x,
                            body_angle_y=angle_y,
                            body_angle_z=0.0,
                            unit_type=obj_class,
                            identification_time=global_time,
                            speed=0.0,
                            threat_level=0.3
                        )

                    elif obj_class in ['Vehicle']:
                        # 장애물로 분류
                        unknown_list.add_or_update_unknown(
                            unknown_id=None,
                            pos_x=pos_x,
                            pos_y=pos_y,
                            pos_z=pos_z,
                            object_angle_x=angle_x,
                            object_angle_y=angle_y,
                            unit_type=obj_class,
                            identification_time=global_time,
                            speed=0.0
                        )
                        # - 장애물 있으면 "경로 재계산 필요" 플래그만 반환 (즉시 재호출 X, 다음 info에서 반영)

                    elif obj_class in ['Civilian', 'Civilian_Vehicle']:
                        # 민간인/민간 차량으로 분류
                        unknown_list.add_or_update_unknown(
                            unknown_id=None,
                            pos_x=pos_x,
                            pos_y=pos_y,
                            pos_z=pos_z,
                            object_angle_x=angle_x,
                            object_angle_y=angle_y,
                            unit_type=obj_class,
                            identification_time=global_time,
                            speed=0.0
                        )
                        # - 장애물 있으면 "경로 재계산 필요" 플래그만 반환 (즉시 재호출 X, 다음 info에서 반영)
                    
                    else:
                        # 미식별 객체로 분류
                        unknown_list.add_or_update_unknown(
                            unknown_id=None,
                            pos_x=pos_x,
                            pos_y=pos_y,
                            pos_z=pos_z,
                            object_angle_x=angle_x,
                            object_angle_y=angle_y,
                            unit_type="unknown",
                            identification_time=global_time,
                            speed=0.0
                        )
                        # - 장애물 있으면 "경로 재계산 필요" 플래그만 반환 (즉시 재호출 X, 다음 info에서 반영)
                    
                except Exception as e:
                    continue
        else:
            print()

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":  {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},
        "fire": global_fire_command
    }


    return jsonify(action)

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    unknown_list.clear()  # 기존 장애물 정보 초기화
    """장애물 정보 업데이트 엔드포인트"""
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    
    # obstacles 리스트 추출
    obstacles = data.get('obstacles', [])
    
    if not obstacles:
        return jsonify({'status': 'warning', 'message': 'No obstacles in data'}), 200
    
    # 각 장애물을 UnknownList에 추가
    added_count = 0
    for idx, obstacle in enumerate(obstacles):
        try:
            # 장애물의 중심 좌표 계산
            x_min = obstacle.get('x_min', 0)
            x_max = obstacle.get('x_max', 0)
            z_min = obstacle.get('z_min', 0)
            z_max = obstacle.get('z_max', 0)
            
            # 중심점 계산
            pos_x = (x_min + x_max) / 2.0
            pos_z = (z_min + z_max) / 2.0
            pos_y = 0.0  # 지면 높이
            
            # 장애물 크기 계산
            size_x = abs(x_max - x_min)
            size_z = abs(z_max - z_min)
            obstacle_size = max(size_x, size_z)  # 더 큰 값을 크기로 사용
            
            # 장애물의 각도 (기본값 0)
            object_angle_x = 0.0
            object_angle_y = 0.0
            
            # UnknownList에 장애물 추가 (ID는 자동 부여)
            unknown_list.add_or_update_unknown(
                unknown_id=None,  # 자동 ID 부여
                pos_x=pos_x,
                pos_y=pos_y,
                pos_z=pos_z,
                object_angle_x=object_angle_x,
                object_angle_y=object_angle_y,
                unit_type="obstacle",
                identification_time=global_time,
                speed=0.0  # 장애물은 정적이므로 속도 0
            )
            
            added_count += 1
            
        except Exception as e:
            print()
    
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 10,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 10,
        "rdStartX": 153, #Red Start Position
        "rdStartY": 30,
        "rdStartZ": 90,
        "trackingMode": True,
        "detactMode": False,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": True,
        "saveStereoCamera" : True,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    send_vdrs()
    return jsonify({"control": ""})

# base64 문자열을 numpy array로 변환
def decode_image(b64_string):
    if b64_string is None:
        return None
    img_bytes = base64.b64decode(b64_string)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
