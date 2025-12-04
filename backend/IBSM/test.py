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
import threading

from datetime import datetime

# 현재 시간 기반 파일 이름 생성
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{timestamp}_log.txt"

def write_log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 밀리초 3자리까지
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{now} - {message}\n")

write_log("로그 파일 생성 완료")

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

global_fire_flag = False  # 사격 모드 최초 비활성화 default 값
global_replan_required = True  # TPP 재 계획 플래그, 최초 True로 설정하여, 첫 계획 수립을 유도
global_new_fire_point = None # 사격 불가 시
global_current_target = None # 현재 사격 목표

# 스레드 락 (동시 요청 처리 방지)
info_lock = threading.Lock()
vdrs_lock = threading.Lock()
vdrs_processing = False
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
            write_log(f"  🔍 비교 중 - ID:{current.enemy_id}, 거리:{distance:.2f}m, 타입비교:'{current.unit_type}'=='{unit_type}' -> {current.unit_type == unit_type}")
            if distance <= self.position_threshold and current.unit_type == unit_type:
                write_log(f"기존 적 발견! ID:{current.enemy_id}")
                return current
            current = current.next
        write_log(f"일치하는 적 없음")
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
    
    def write_log_all(self):
        """모든 적 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Enemy ID: {current.enemy_id}, Type: {current.unit_type}, Status: {current.status}, Threat: {current.threat_level}")
            current = current.next
            index += 1

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
                write_log("ID 기반 기존 적 정보 업데이트 중...")
                # 기존 적 찾았으면 위치와 정보 업데이트
                existing_enemy.pos_x = pos_x 
                existing_enemy.pos_y = pos_y
                existing_enemy.pos_z = pos_z
                existing_enemy.body_angle_z = body_angle_z
                existing_enemy.unit_type = unit_type
                existing_enemy.identification_time = identification_time
                existing_enemy.update_speed(speed)
                write_log(f"🔄 적 정보 업데이트! ID: {enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return existing_enemy
            else:
                # ID로 못 찾았으면 해당 ID로 신규 생성
                write_log("ID 기반 신규 적 정보 업데이트 중...")
                write_log(f"📝 ID {enemy_id}로 신규 적 생성 중...")
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
                write_log(f"새로운 적 생성! ID: {enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_enemy
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_enemy = self.find_enemy_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_enemy:
            write_log("기존 적 정보 업데이트 중...")
            # 기존 적이 있으면 정보만 업데이트 (위치와 unit_type은 이미 일치하므로 제외)
            nearby_enemy.identification_time = identification_time
            return nearby_enemy
        
        # Case 3: 완전히 새로운 적 발견 - 자동으로 ID 부여
        write_log("신규 적 정보 업데이트 중...")
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
        write_log(f"🆕 새로운 적 발견! ID: {new_enemy.enemy_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        
        # TCIS로 Enemy 데이터 전송
        send_to_tcis('/internal/enemies', {
            "type": "enemies_update",
            "data": self.get_all_enemies()
        })
        
        return new_enemy

# --------------------------------------------------------------------
# TCIS 연동 함수 (Frontend Communication)
# --------------------------------------------------------------------
# TCIS는 Frontend와 WebSocket 통신을 담당하는 중계 서버입니다.
# IBSM에서 데이터가 변경될 때마다 TCIS로 전송하여 실시간 업데이트를 제공합니다.

TCIS_URL = "http://127.0.0.1:5001"

def send_to_tcis(endpoint, data):
    """
    TCIS로 데이터 전송 (Fire & Forget)
    
    Args:
        endpoint: TCIS 내부 엔드포인트 (/internal/enemies, /internal/allies, /internal/unknowns)
        data: 전송할 JSON 데이터
    
    Note:
        - 타임아웃 10ms, TCIS 오류 시에도 IBSM은 계속 작동
        - TCIS 서버가 다운되어도 IBSM 동작에는 영향 없음
    """
    try:
        requests.post(f"{TCIS_URL}{endpoint}", json=data, timeout=0.01)
    except Exception as e:
        # TCIS 오류 시에도 IBSM은 계속 작동 (로그 미출력)
        pass

# TCIS API 엔드포인트는 app 정의 이후에 선언 (하단 참조)

# --------------------------------------------------------------------

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
    
    def write_log_all(self):
        """모든 아군 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Ally ID: {current.ally_id}, Type: {current.unit_type}, Status: {current.status}")
            current = current.next
            index += 1
    
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
                write_log("ID 기반 기존 아군 정보 업데이트 중...")
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
                write_log("ID 기반 신규 아군 생성 중...")
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
                write_log(f"🆕 새로운 아군 생성! ID: {ally_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_ally
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_ally = self.find_ally_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)
        
        if nearby_ally:
            # 기존 아군이 있으면 정보만 업데이트
            write_log("기존 아군 정보 업데이트 중...")
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
        write_log("신규 아군 정보 업데이트 중...")
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
        write_log(f"🆕 새로운 아군 발견! ID: {new_ally.ally_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        
        # TCIS로 Ally 데이터 전송
        send_to_tcis('/internal/allies', {
            "type": "allies_update",
            "data": self.get_all_allies()
        })
        
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
    
    def write_log_all(self):
        """모든 미식별 객체 정보 출력 (디버깅용)"""
        current = self.head
        index = 1
        while current:
            write_log(f"[{index}] Unknown ID: {current.unknown_id}, Type: {current.unit_type}, Status: {current.status}")
            current = current.next
            index += 1
    
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
                write_log(f"기존 식별 객체 정보 업데이트 ID: {unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                write_log(f"🆕 ID 기반 신규 객체 생성 ID: {unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
                return new_unknown
        
        # Case 2: ID가 None인 경우 - 위치 및 유닛 타입 기반으로 검색
        nearby_unknown = self.find_unknown_by_position(pos_x, pos_y, pos_z, unit_type=unit_type)

        if nearby_unknown:
            write_log("기존 미식별 객체 정보(시간) 업데이트 중...")
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
        write_log(f"신규 객체 추가 | ID: {new_unknown.unknown_id}, 위치: ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
        
        # TCIS로 Unknown 데이터 전송
        send_to_tcis('/internal/unknowns', {
            "type": "unknowns_update",
            "data": self.get_all_unknowns()
        })
        
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
    write_log("get_latest_image() 호출 받음")
    """디렉토리에서 가장 최신 이미지 파일 경로 반환"""
    images = glob.glob(os.path.join(directory, "*.*"))
    if images:
        latest_image = max(images, key=os.path.getmtime)
        return latest_image
    else:
        write_log(f"{directory}에서 이미지를 찾을 수 없습니다.")
        return None

def encode_image_to_base64(image_path):
    write_log("encode_image_to_base64() 호출 받음")
    """이미지 파일을 읽어서 base64로 인코딩"""
    if image_path is None:
        return None
    
    try:
        image = cv2.imread(image_path)
        if image is None:
            write_log(f"이미지 로드 실패: {image_path}")
            return None
        
        # numpy array를 base64로 인코딩
        _, buffer = cv2.imencode('.jpg', image)
        image_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        return image_b64
    except Exception as e:
        write_log(f"이미지 인코딩 실패 ({image_path}): {e}")
        return None
    
# --- VDRS 관련 파일/이미지 유틸리티 함수 최상위로 이동 ---
def get_latest_png(directory):
    write_log("get_latest_png() 호출 받음")
    images = glob.glob(os.path.join(directory, "*.png"))
    if not images:
        return None
    return max(images, key=os.path.getmtime)

def get_next_image(directory, after_time):
    write_log("get_next_image() 호출 받음")
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

def delete_all_images(directory):
    write_log("delete_all_images() 호출 받음")
    images = glob.glob(os.path.join(directory, "*.png"))
    for img in images:
        try:
            os.remove(img)
        except Exception as e:
            write_log(f"이미지 삭제 실패: {img} - {e}")

# --------------------------------------------------------------------

def send_fcs(request_data=None):
    write_log("send_fcs() 호출 받음")
    """FCS에 사격 통제 요청"""
    external_server = "http://192.168.0.21:5000/get_fcs"
    try:
        write_log(f"fcs 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"fcs 수신 데이터 : {ext_result}")
        write_log(f"fcs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"fcs_except 발생 : {str(e)}")
    return ext_result

def send_adcs(request_data=None):
    write_log("send_adcs() 호출 받음")
    external_server = "http://192.168.0.124:5000/get_adcs"
    try:
        write_log(f"adcs 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"adcs 수신 데이터 : {ext_result}")
        write_log(f"adcs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"adcs_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    return ext_result

def send_vdrs(request_data=None):
    write_log("send_vdrs() 호출 받음")
    vdrs_total_start = time.time()
    
    main_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images"
    left_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images\L"
    right_image_dir = r"C:\Users\acorn\Documents\Tank Challenge\capture_images\R"

    # 1. 이미지 경로 탐색
    img_search_start = time.time()
    main_image_path = get_latest_png(main_image_dir)
    main_time = os.path.getmtime(main_image_path) if main_image_path else None

    left_image_path = get_next_image(left_image_dir, main_time) if main_time else None
    right_image_path = get_next_image(right_image_dir, main_time) if main_time else None
    img_search_end = time.time()
    write_log(f"  └ 이미지 경로 탐색 소요시간: {(img_search_end - img_search_start)*1000:.2f}ms")

    # 이미지 경로 유효성 검증
    if not main_image_path or not left_image_path or not right_image_path:
        write_log("⚠️ 이미지 경로 부족: 3장의 이미지가 모두 필요합니다.")
        write_log(f"  └ Main: {main_image_path}, Left: {left_image_path}, Right: {right_image_path}")
        return {"error": "Insufficient images", "required": 3, "found": sum([bool(main_image_path), bool(left_image_path), bool(right_image_path)])}

    # 2. 이미지 인코딩
    img_encode_start = time.time()
    main_image_data = encode_image_to_base64(main_image_path)
    left_image_data = encode_image_to_base64(left_image_path)
    right_image_data = encode_image_to_base64(right_image_path)
    img_encode_end = time.time()
    write_log(f"  └ 이미지 인코딩 소요시간: {(img_encode_end - img_encode_start)*1000:.2f}ms")

    # 이미지 인코딩 성공 여부 검증
    if not main_image_data or not left_image_data or not right_image_data:
        write_log("⚠️ 이미지 인코딩 실패: 일부 이미지를 인코딩하지 못했습니다.")
        write_log(f"  └ Main: {bool(main_image_data)}, Left: {bool(left_image_data)}, Right: {bool(right_image_data)}")
        # 인코딩 실패 시에도 이미지 삭제
        delete_all_images(main_image_dir)
        delete_all_images(left_image_dir)
        delete_all_images(right_image_dir)
        return {"error": "Image encoding failed"}

    # 3. 이미지 삭제
    img_delete_start = time.time()
    delete_all_images(main_image_dir)
    delete_all_images(left_image_dir)
    delete_all_images(right_image_dir)
    img_delete_end = time.time()
    write_log(f"  └ 이미지 삭제 소요시간: {(img_delete_end - img_delete_start)*1000:.2f}ms")

    # 4. 아군 데이터 준비
    data_prep_start = time.time()
    ally = ally_list.find_ally(0)
    if not ally:
        write_log("ID 0번 아군(플레이어 탱크)을 찾을 수 없습니다.")
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
    data_prep_end = time.time()
    write_log(f"  └ 요청 데이터 준비 소요시간: {(data_prep_end - data_prep_start)*1000:.2f}ms")
    
    # 5. VDRS 서버 통신
    external_server = "http://192.168.0.15:5000/get_vdrs"
    try:
        vdrs_comm_start = time.time()
        ext_response = requests.post(external_server, json=request_data, timeout=2)# VDRS 서버 응답 대기를 0.1초로 수정
        ext_result = ext_response.json()
        vdrs_comm_end = time.time()
        write_log(f"  └ VDRS 서버 통신 소요시간: {(vdrs_comm_end - vdrs_comm_start)*1000:.2f}ms")
        write_log(f"vdrs 수신 데이터 : {ext_result}")
        write_log(f"vdrs 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"vdrs_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    
    vdrs_total_end = time.time()
    write_log(f"  └ VDRS 전체 소요시간: {(vdrs_total_end - vdrs_total_start)*1000:.2f}ms")
    
    return ext_result

def process_vdrs_objects(vdrs_data, global_time):
        write_log("process_vdrs_objects() 호출 받음")
        """VDRS에서 탐지된 객체들을 분류 및 리스트에 추가"""
        
        # 상세 디버깅 로그 추가
        write_log(f"🔍 [DEBUG] vdrs_data 타입: {type(vdrs_data)}")
        write_log(f"🔍 [DEBUG] vdrs_data 존재 여부: {vdrs_data is not None}")
        write_log(f"🔍 [DEBUG] vdrs_data가 dict인지: {isinstance(vdrs_data, dict)}")
        
        if vdrs_data:
            if isinstance(vdrs_data, dict):
                write_log(f"🔍 [DEBUG] vdrs_data의 키 목록: {list(vdrs_data.keys())}")
                write_log(f"🔍 [DEBUG] 'detected_objects' 키 존재 여부: {'detected_objects' in vdrs_data}")
            else:
                write_log(f"⚠️ [ERROR] vdrs_data가 dict가 아님! 실제 내용: {vdrs_data}")
        else:
            write_log(f"⚠️ [ERROR] vdrs_data가 None이거나 비어있음!")
        
        if vdrs_data and isinstance(vdrs_data, dict) and 'detected_objects' in vdrs_data:
            detected_objects = vdrs_data.get('detected_objects', [])
            write_log(f"📷 VDRS에서 {len(detected_objects)}개 객체 탐지됨")
            write_log(f"🔍 [DEBUG] detected_objects 타입: {type(detected_objects)}")
            
            for obj in detected_objects:
                if not isinstance(obj, dict):
                    write_log(f"⚠️ [DEBUG] obj가 dict가 아님: {type(obj)}, 값: {obj}")
                    continue
                try:
                    write_log(f"🔍 [DEBUG] 처리 중인 obj 키 목록: {list(obj.keys())}")
                    
                    obj_class = obj.get('class_id', obj.get('class', 'UNKNOWN'))  # class_id도 체크
                    obj_pos = obj.get('object_pos', {})
                    obj_angle = obj.get('object_angle_xy', {})
                    
                    write_log(f"🔍 [DEBUG] obj_class: {obj_class}")
                    write_log(f"🔍 [DEBUG] obj_pos: {obj_pos}")
                    write_log(f"🔍 [DEBUG] obj_angle: {obj_angle}")
                    if not isinstance(obj_pos, dict) or not isinstance(obj_angle, dict):
                        continue
                    pos_x = float(obj_pos.get('x', 0.0))
                    pos_y = float(obj_pos.get('y', 0.0))
                    pos_z = float(obj_pos.get('z', 0.0))
                    angle_x = float(obj_angle.get('x', 0.0))
                    angle_y = float(obj_angle.get('y', 0.0))
                    if obj_class in ['Armored']:
                        write_log(f"적 차량 발견: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                            threat_level=0.8
                        )
                    elif obj_class in ['Infantry']:
                        write_log(f"적 보병 발견: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                        write_log(f"장애물 발견: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                    elif obj_class in ['Civilian', 'Civilian_Vehicle']:
                        write_log(f"민간인 발견: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                    else:
                        write_log(f"미식별 객체 발견: {obj_class} at ({pos_x:.1f}, {pos_y:.1f}, {pos_z:.1f})")
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
                except Exception as e:
                    write_log(f"⚠️ VDRS 객체 처리 중 오류: {e}")
                    import traceback
                    write_log(f"⚠️ 오류 상세: {traceback.format_exc()}")
                    continue
        else:
            write_log("⚠️ VDRS 데이터가 없거나 형식이 올바르지 않습니다.")
            write_log(f"❌ [ERROR] 최종 vdrs_data 내용: {vdrs_data}")

def send_tpp(request_data=None):
    write_log("send_tpp() 호출 받음")
    """TPP에 경로 계획 요청"""
    external_server = "http://192.168.0.132:5000/get_tpp"
    try:
        write_log(f"tpp 발신 데이터 : {request_data}")
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        write_log(f"tpp 수신 데이터 : {ext_result}")
        write_log(f"tpp 수신 데이터 타입 : {type(ext_result)}")
    except Exception as e:
        write_log(f"tpp_except 발생 : {str(e)}")
        ext_result = {"error": str(e)}
    return ext_result

# --------------------------------------------------------------------

app = Flask(__name__)

# TCIS 관련 API 엔드포인트
@app.route('/api/battlefield-data', methods=['GET'])
def get_battlefield_data():
    """TCIS가 전장 데이터 조회 (Query API for TCIS)"""
    return jsonify({
        "enemies": enemy_list.get_all_enemies(),
        "allies": ally_list.get_all_allies(),
        "unknowns": unknown_list.get_all_unknowns(),
        "timestamp": global_time
    })
# --------------------------------------------------------------------

@app.route('/detect', methods=['POST'])
def detect():
    write_log("detect() 호출 받음")
    
    global vdrs_processing
    
    image = request.files.get('image')
    if not image:
        return jsonify({"error": "No image received"}), 400

    # 이미 처리 중이면 즉시 거부 (누적 방지)
    if not vdrs_lock.acquire(blocking=False):
        write_log("⚠️ VDRS 이미 처리 중 - 요청 버림")
        # 가짜 탐지 결과 반환 (시뮬레이터가 멈추지 않도록)
        filtered_results = [
            {
                'className': '',
                'bbox': [0.0, 0.0, 0.0, 0.0],
                'confidence': 0.0,
                'color': '#FF0000',
                'filled': True,
                'updateBoxWhileMoving': False
            }
        ]
        return jsonify(filtered_results)

    try:
        vdrs_processing = True
        write_log("🚀 VDRS 처리 시작")
        
        vdrs_start = time.time()
        
        # VDRS 호출
        vdrs_data = send_vdrs()
        process_vdrs_objects(vdrs_data, global_time)
        
        # 가짜 탐지 결과 생성 (시뮬레이터 표시용)
        filtered_results = [
            {
                'className': '',
                'bbox': [0.0, 0.0, 0.0, 0.0],
                'confidence': 0.0,
                'color': '#FF0000',
                'filled': True,
                'updateBoxWhileMoving': False
            }
        ]
        
        vdrs_end = time.time()
        
        write_log(f"  └ VDRS 소요시간: {(vdrs_end - vdrs_start)*1000:.2f}ms")
        write_log(f"✅ VDRS 처리 완료 및 가짜 데이터 전송: {len(filtered_results)}개 객체")
        
        return jsonify(filtered_results)
        
    except Exception as e:
        write_log(f"❌ VDRS 처리 중 오류 발생: {e}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    finally:
        vdrs_processing = False
        vdrs_lock.release()
        write_log("🔓 VDRS 락 해제")

@app.route('/info', methods=['POST'])
def info(): # 수신 정보 처리 및 메인 처리 로직
    write_log("info() 호출 받음")

    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command
    global global_enemy_id
    global global_ally_id
    global global_time
    global global_replan_required
    global global_fire_flag
    global global_new_fire_point
    global global_current_target

    # Reset global commands and weights
    global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
    global_fire_command = False

    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400
    
    # info로 수신되는 데이터 기본 파싱
    sim_time = request_data["time"]
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

    global_time = sim_time

    # 현재 전차 정보 로그
    write_log(f"현재 전차 위치 및 각도: Pos({player_x:.2f}, {player_y:.2f}, {player_z:.2f}), BodyAngle({player_body_x:.2f}, {player_body_y:.2f}, {player_body_z:.2f}), TurretAngle({player_turret_x:.2f}, {player_turret_y:.2f})")

    # 아군 전차 정보 업데이트(기동 상태)
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
    
    # 적 전차 정보 업데이트(정지 상태)
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
        write_log("ID 0번 아군(플레이어 탱크)을 찾을 수 없습니다.")
        return jsonify({"error": "No ally with ID 0 found"}), 400
    
    # [IBSM 불러오기] enemy_list에서 ID 0번 적(탱크) 가져오기
    enemy = enemy_list.find_enemy(0)
    if not enemy:
        write_log("ID 0번 적(탱크)을 찾을 수 없습니다.")
        return jsonify({"error": "No enemy with ID 0 found"}), 400
    
    # 현재 목표 전차 정보 설정
    global_current_target = {"x": enemy.pos_x, "y": enemy.pos_y, "z": enemy.pos_z}

# -------------------------[공격 임무 기반 로직: 적 인식 상황으로 가정]------------------------------------
    # 1개 API 호출 사이클에 각 모듈이 최대 1번만 호출되어야 함.(반복 처리로 인한 오류 방지)

    # 사격 모드(정상 동작 확인)
    if enemy.status == 'active': # 적 전차가 활성 상태인 경우에만 전투 로직 진입
        if global_fire_flag == True:
            # API 1번 로직
            api1_start = time.time()
            write_log("API 1번 로직: 사격 모드 진입")
            request_data_fcs = {
                "time": global_time,
                "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                "ally_speed": ally.speed,
                "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                "ibsm_target": global_current_target, # 현재 적 전차 정보를 전달
                "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
                "AD_command": global_AD_command, # 스테빌라이저 고도화용
                "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
                "WS_command": global_WS_command, # 스테빌라이저 고도화용
                "WS_weight": global_WS_weight # 스테빌라이저 고도화용
            }
            fcs_data = send_fcs(request_data_fcs)

            global_QE_command = fcs_data['QE_command']
            global_QE_weight = fcs_data['QE_weight']
            global_RF_command = fcs_data['RF_command']
            global_RF_weight = fcs_data['RF_weight']
            global_fire_command = fcs_data['fire_command']
            global_new_fire_point = fcs_data['new_fire_point']
            
            api1_end = time.time()
            write_log(f"  └ API 1번 소요시간: {(api1_end - api1_start)*1000:.2f}ms")

            if global_fire_command == False: # 사격 명령이 내려지지 않은 경우
                write_log("조준 중... 사격 명령 대기")
            if global_fire_command == True: # 사격 명령이 내려진 경우
                write_log("조준 완료, 사격 개시")
            # 신규 지점 이동 명령 처리 로직 추가
            if fcs_data['new_fire_point'] is not None: # fcs에서 신규 목표 지점이 산출된 경우
                write_log("API 1-1번 로직 진입: 목표 지점 산출 상태")
                global_new_fire_point = fcs_data['new_fire_point'] # 최초 사격 지점 할당, 후 4, 5번 로직으로 전환
                global_fire_flag = False # 사격 모드에서 비사격 모드로 전환
                write_log(f"✅ global_new_fire_point 할당 완료: {global_new_fire_point}")
                api1_1_end = time.time()
                write_log(f"  └ API 1-1번 소요시간: {(api1_1_end - api1_start)*1000:.2f}ms")

        # 비 사격 모드
        elif global_fire_flag == False:
            if global_replan_required == True: # 경로 재계산이 필요하면서
                if global_new_fire_point is None: # 목표 지점이 설정되지 않은 경우
                    api23_start = time.time()
                    write_log("API 2번, 3번 로직: 최초 목표 지점 산출 모드 진입")
                    write_log(f"🔍 현재 global_new_fire_point 상태: {global_new_fire_point}")
                    request_data_fcs = {
                        "time": global_time,
                        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                        "ally_speed": ally.speed,
                        "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                        "ibsm_target": global_current_target,
                        "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
                        "AD_command": global_AD_command, # 스테빌라이저 고도화용
                        "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
                        "WS_command": global_WS_command, # 스테빌라이저 고도화용
                        "WS_weight": global_WS_weight # 스테빌라이저 고도화용
                    }
                    fcs_data = send_fcs(request_data_fcs) # 이 시점에서 목표 지점 산출

                    global_QE_command = fcs_data['QE_command']
                    global_QE_weight = fcs_data['QE_weight']
                    global_RF_command = fcs_data['RF_command']
                    global_RF_weight = fcs_data['RF_weight']
                    global_fire_command = fcs_data['fire_command']
                    global_new_fire_point = fcs_data['new_fire_point']
                            
                    if fcs_data['new_fire_point'] is not None: # fcs에서 신규 목표 지점이 산출된 경우
                        write_log("API 2번 로직 진입: 목표 지점 산출 상태")
                        global_new_fire_point = fcs_data['new_fire_point'] # 최초 사격 지점 할당, 후 4, 5번 로직으로 전환
                        write_log(f"✅ global_new_fire_point 할당 완료: {global_new_fire_point}")
                        api2_end = time.time()
                        write_log(f"  └ API 2 전체 소요시간: {(api2_end - api23_start)*1000:.2f}ms")

                    elif fcs_data['new_fire_point'] is None: # fcs에서 목표 지점이 산출되지 않은 경우
                        write_log("API 3번 로직 진입: 조준 또는 사격 개시 상태")
                        global_fire_flag = True # 목표 지점이 없으면 현재 fcs에서 조준 또는 사격을 해야 하는 상태이므로, 사격 모드(스테빌라이저 또는 사격 개시)로 전환
                        api3_end = time.time()
                        write_log(f"  └ API 3 전체 소요시간: {(api3_end - api23_start)*1000:.2f}ms")

                elif global_new_fire_point is not None: # 목표 지점이 설정되어 있는 경우
                    api45_start = time.time()
                    write_log("API 4번, 5번 로직: 최초 목표 지점 산출 후 경로 재계산 모드 진입, TPP->ADCS->FCS 순차 호출")
                    # TPP(경로 계획) 호출
                    tpp_start = time.time()
                    request_data_tpp = {
                        "time": global_time,
                        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                        "target_pos": global_new_fire_point, # 사격 가능 지점으로 이동 명령 설정
                        "unknowns": unknown_list.get_all_unknowns()  # 미식별 객체(장애물 등) 정보
                    }
                    tpp_data = send_tpp(request_data_tpp)
                    tpp_end = time.time()
                    write_log(f"  └ TPP 소요시간: {(tpp_end - tpp_start)*1000:.2f}ms")
                    global_replan_required = False # 경로 재 계산 후 경로 재 계산 필요 없음으로 전환
                    
                    # ADCS(주행 제어) 호출
                    adcs_start = time.time()
                    request_data_adcs = {
                        "time" : global_time, # 시뮬레이터 시각
                        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z}, # 아군 전차 차체 X, Y, Z 위치
                        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z}, # 아군 전차 차체 X, Y, Z 각도
                        "ally_speed": ally.speed, # 아군 전차 속도(m/s)
                        "waypoints" : tpp_data['waypoints'] # 사격 가능 지점으로 이동하는 waypoints, 빈 경로가 넘어가면, 이전에 주행중인 경로를 지속하도록 코드 수정
                    }
                    adcs_data = send_adcs(request_data_adcs)
                    adcs_end = time.time()
                    write_log(f"  └ ADCS 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
                    global_WS_command = adcs_data['WS_command']
                    global_WS_weight = adcs_data['WS_weight']
                    global_AD_command = adcs_data['AD_command']
                    global_AD_weight = adcs_data['AD_weight']

                    # FCS(사격 통제) 호출: 여기서는 스테빌라이저 수행
                    fcs_start = time.time()
                    request_data_fcs = {
                        "time": global_time,
                        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                        "ally_speed": ally.speed,
                        "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                        "ibsm_target": global_current_target,
                        "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
                        "AD_command": global_AD_command, # 스테빌라이저 고도화용 - 이 시점에서 유의미한 AD/WS 값이 갱신됨
                        "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
                        "WS_command": global_WS_command, # 스테빌라이저 고도화용
                        "WS_weight": global_WS_weight # 스테빌라이저 고도화용
                    }
                    fcs_data = send_fcs(request_data_fcs)

                    global_QE_command = fcs_data['QE_command']
                    global_QE_weight = fcs_data['QE_weight']
                    global_RF_command = fcs_data['RF_command']
                    global_RF_weight = fcs_data['RF_weight']
                    global_fire_command = fcs_data['fire_command']
                    global_new_fire_point = fcs_data['new_fire_point']

                    fcs_end = time.time()
                    write_log(f"  └ FCS 소요시간: {(fcs_end - fcs_start)*1000:.2f}ms")
                    
                    # FCS 응답에서 포탑 명령 추출 (주행 중 스테빌라이저)
                    global_QE_command = fcs_data.get('QE_command', '')
                    global_QE_weight = fcs_data.get('QE_weight', 0.0)
                    global_RF_command = fcs_data.get('RF_command', '')
                    global_RF_weight = fcs_data.get('RF_weight', 0.0)
                    
                    # API 4번 로직
                    if fcs_data['new_fire_point'] is not None:
                        write_log("API 4번 로직 진입: 사격 지점 갱신 및 VDRS로 객체 탐지 진행")
                        global_new_fire_point = fcs_data['new_fire_point'] # 사격 지점 갱신
                        global_current_target = fcs_data['fire_target'] # 사격 대상 갱신
                        write_log(f"🔄 global_new_fire_point 갱신됨: {global_new_fire_point}")

                        api4_end = time.time()
                        write_log(f"  └ API 4 전체 소요시간: {(api4_end - api45_start)*1000:.2f}ms")
                        
                    # API 5번 로직
                    elif fcs_data['new_fire_point'] is None: # fcs에서 목표 지점이 산출되지 않은 경우
                        write_log("API 5번 로직 진입: 즉시 사격 모드 전환, VDRS 객체 탐지 미 진행")
                        global_fire_flag = True # 목표 지점이 없으면 사격 모드로 전환(주행 중 도착으로 판단)

                        api5_end = time.time()
                        write_log(f"  └ API 5 전체 소요시간: {(api5_end - api45_start)*1000:.2f}ms")
                    
            elif global_replan_required == False: # 경로 재계산 불 필요 상태이면서, 기존에 이미 1회 TPP 계산이 산출되어 ADCS가 Previous Waypoints를 따라가고 있는 상태
                write_log("API 6번, 7번 로직: 경로 계산 완료 후, 주행 모드 진입, ADCS -> FCS 순차 호출")
                api67_start = time.time()
                adcs_start = time.time()
                # ADCS(주행 제어) 호출
                request_data_adcs = {
                    "time" : global_time, # 시뮬레이터 시각
                    "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z}, # 아군 전차 차체 X, Y, Z 위치
                    "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z}, # 아군 전차 차체 X, Y, Z 각도
                    "ally_speed": ally.speed, # 아군 전차 속도(m/s)
                    "waypoints" : [] # 사격 가능 지점으로 이동하는 waypoints, 빈 경로가 넘어가면, 이전에 주행중인 경로를 지속하도록 코드 수정
                }
                adcs_data = send_adcs(request_data_adcs)
                adcs_end = time.time()
                write_log(f"  └ ADCS 소요시간: {(adcs_end - adcs_start)*1000:.2f}ms")
                global_WS_command = adcs_data['WS_command']
                global_WS_weight = adcs_data['WS_weight']
                global_AD_command = adcs_data['AD_command']
                global_AD_weight = adcs_data['AD_weight']

                # FCS(사격 통제) 호출: 여기서는 스테빌라이저 수행            
                fcs_start = time.time()
                request_data_fcs = {
                        "time": global_time,
                        "ally_body_pos": {"x": ally.pos_x, "y": ally.pos_y, "z": ally.pos_z},
                        "ally_body_angle": {"x": ally.body_angle_x, "y": ally.body_angle_y, "z": ally.body_angle_z},
                        "ally_speed": ally.speed,
                        "ally_turret_angle": {"x": ally.turret_angle_x, "y": ally.turret_angle_y},
                        "ibsm_target": global_current_target,
                        "map_type": 0,  # 맵 종류, 일단 0: forest and river로 고정
                        "AD_command": global_AD_command, # 스테빌라이저 고도화용 - 이 시점에서 유의미한 AD/WS 값이 갱신됨
                        "AD_weight": global_AD_weight, # 스테빌라이저 고도화용
                        "WS_command": global_WS_command, # 스테빌라이저 고도화용
                        "WS_weight": global_WS_weight # 스테빌라이저 고도화용
                    }
                fcs_data = send_fcs(request_data_fcs) # 이 시점에서 목표 지점 산출

                global_QE_command = fcs_data['QE_command']
                global_QE_weight = fcs_data['QE_weight']
                global_RF_command = fcs_data['RF_command']
                global_RF_weight = fcs_data['RF_weight']
                global_fire_command = fcs_data['fire_command']
                global_new_fire_point = fcs_data['new_fire_point']

                fcs_end = time.time()
                write_log(f"  └ fcs 소요시간: {(fcs_end - fcs_start)*1000:.2f}ms")
                # API 7번 로직
                if fcs_data['new_fire_point'] is not None:
                    write_log("API 7번 로직 진입: 기존에 산출된 TPP를 따라 주행 중, 사격 지점 갱신 및 VDRS로 객체 탐지 진행")
                    global_new_fire_point = fcs_data['new_fire_point'] # 사격 지점 갱신
                    global_current_target = fcs_data['fire_target'] # 사격 대상 갱신

                    api7_end = time.time()
                    write_log(f"  └ API 7 전체 소요시간: {(api7_end - api67_start)*1000:.2f}ms")
                # API 6번 로직
                elif fcs_data['new_fire_point'] is None:
                    write_log("API 6번 로직 진입: 기존에 산출된 TPP를 따라 주행 중, 즉시 사격 모드 전환, VDRS 객체 탐지 미 진행")
                    global_fire_flag = True # 목표 지점이 없으면 사격 모드로 전환(도착으로 판단)

                    api6_end = time.time()
                    write_log(f"  └ API 6 전체 소요시간: {(api6_end - api67_start)*1000:.2f}ms")

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    write_log("get_action() 호출 받음")
    
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command
    
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

    write_log(f"get_action()에서 sim으로 전달한 정보: {action}")
    
    # 명령 전달 후 전역 변수 초기화
    global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
    global_fire_command = False
    
    write_log("✅ get_action() 전역 변수 초기화 완료")

    return jsonify(action)

@app.route('/update_obstacle', methods=['POST'])
def update_obstacle():
    """장애물 정보 업데이트 엔드포인트"""
    write_log("update_obstacle() 호출 받음")
    
    # global last_obstacle_update_time, last_obstacle_data_hash
    
    # data = request.get_json()
    # if not data:
    #     return jsonify({'status': 'error', 'message': 'No data received'}), 400
    
    # # obstacles 리스트 추출
    # obstacles = data.get('obstacles', [])
    
    # # 빈 배열은 아예 무시
    # if not obstacles:
    #     write_log("⚠️ 빈 장애물 배열 무시")
    #     return jsonify({'status': 'ignored', 'message': 'Empty obstacles array ignored'}), 200
    
    # unknown_list.clear()  # 기존 장애물 정보 초기화
    # write_log(f"obstacle Data: {data}")
    
    # # 각 장애물을 UnknownList에 추가
    # added_count = 0
    # for idx, obstacle in enumerate(obstacles):
    #     try:
    #         # 장애물의 중심 좌표 계산
    #         x_min = obstacle.get('x_min', 0)
    #         x_max = obstacle.get('x_max', 0)
    #         z_min = obstacle.get('z_min', 0)
    #         z_max = obstacle.get('z_max', 0)
            
    #         # 중심점 계산
    #         pos_x = (x_min + x_max) / 2.0
    #         pos_z = (z_min + z_max) / 2.0
    #         pos_y = 0.0  # 지면 높이
            
    #         # 장애물 크기 계산
    #         size_x = abs(x_max - x_min)
    #         size_z = abs(z_max - z_min)
    #         obstacle_size = max(size_x, size_z)  # 더 큰 값을 크기로 사용
            
    #         # 장애물의 각도 (기본값 0)
    #         object_angle_x = 0.0
    #         object_angle_y = 0.0
            
    #         # UnknownList에 장애물 추가 (ID는 자동 부여)
    #         unknown_list.add_or_update_unknown(
    #             unknown_id=None,  # 자동 ID 부여
    #             pos_x=pos_x,
    #             pos_y=pos_y,
    #             pos_z=pos_z,
    #             object_angle_x=object_angle_x,
    #             object_angle_y=object_angle_y,
    #             unit_type="obstacle",
    #             identification_time=global_time,
    #             speed=0.0  # 장애물은 정적이므로 속도 0
    #         )
            
    #         added_count += 1
            
    #     except Exception as e:
    #         write_log(f"⚠️ 장애물 {idx+1} 추가 실패: {e}")
    
    return jsonify({'status': 'success', 'message': 'Obstacle data received'})

@app.route('/update_bullet', methods=['POST'])
def update_bullet():
    write_log("update_bullet() 호출 받음")
    global global_fire_flag
    global global_current_target

    # 입력 데이터 파싱
    bullet_data = request.get_json()

    # 입력값 검증: bullet_data 존재 여부
    bullet_data_exists = bullet_data is not None
    if not bullet_data_exists:
        return jsonify({
            'status': 'error',
            'message': 'No bullet data received.'
        }), 400

    # 값 추출
    bullet_x = bullet_data['x']
    bullet_y = bullet_data['y']
    bullet_z = bullet_data['z']

    target_x = global_current_target['x']
    target_y = global_current_target['y']
    target_z = global_current_target['z']

    # 유클리드 거리 계산
    distance = math.sqrt(
        (bullet_x - target_x) ** 2 +
        (bullet_y - target_y) ** 2 +
        (bullet_z - target_z) ** 2
    )

    # 판정: padding 이내면 명중
    padding = 3.0
    is_within_padding = distance <= padding

    # 명중 시 global_fire_flag 해제
    if is_within_padding:
        write_log('RESULT: TARGET HIT')
        global_fire_flag = False
        # 적 전차 정보 업데이트(사망 처리)
        result = enemy_list.find_enemy_by_position(pos_x=target_x, pos_y=target_y, pos_z=target_z, unit_type="armored")
        if result:
            # 사망으로 변경
            result.status = "destroyed"
            write_log(f"적 전차(ID: {result.enemy_id})가 파괴되었습니다.")
    else:
        write_log('RESULT: MISS')

    # 결과 반환
    return jsonify({
        'status': 'success',
        'is_hit': is_within_padding,
        'distance': distance,
        'padding': padding
    })

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 100,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 5,
        "rdStartX": 200, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 290,
        "trackingMode": True,
        "detactMode": True,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": True,
        "saveStereoCamera" : True,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    write_log(f"🛠️ Initialization config sent via /init: {config}")
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    write_log("🚀 /start command received")
    return jsonify({"control": ""})

# --------------------------------------------------------------------
# TCIS로 가짜 데이터 전송용 엔드포인트
# --------------------------------------------------------------------
@app.route('/test/send-fake-data', methods=['GET'])
def send_fake_data():
    """테스트용: 가짜 데이터를 TCIS로 전송"""
    
    # 가짜 적 데이터
    fake_enemies = [
        {
            "enemy_id": 1,
            "pos_x": 100.0,
            "pos_y": 10.0,
            "pos_z": 200.0,
            "unit_type": "tank",
            "status": "active",
            "threat_level": 0.8
        },
        {
            "enemy_id": 2,
            "pos_x": 150.0,
            "pos_y": 10.0,
            "pos_z": 250.0,
            "unit_type": "infantry",
            "status": "active",
            "threat_level": 0.5
        }
    ]
    
    # 가짜 아군 데이터
    fake_allies = [
        {
            "ally_id": 1,
            "pos_x": -50.0,
            "pos_y": 10.0,
            "pos_z": -100.0,
            "unit_type": "tank",
            "combat_status": "normal"
        }
    ]
    
    # 가짜 미식별 데이터
    fake_unknowns = [
        {
            "unknown_id": 1,
            "pos_x": 80.0,
            "pos_y": 10.0,
            "pos_z": 120.0
        }
    ]
    
    # TCIS로 전송
    send_to_tcis('/internal/enemies', {
        "type": "enemies_update",
        "data": fake_enemies
    })
    
    send_to_tcis('/internal/allies', {
        "type": "allies_update",
        "data": fake_allies
    })
    
    send_to_tcis('/internal/unknowns', {
        "type": "unknowns_update",
        "data": fake_unknowns
    })
    
    write_log("✅ 테스트 데이터 TCIS로 전송 완료")
    
    return jsonify({
        "status": "success",
        "message": "가짜 데이터 전송 완료",
        "sent": {
            "enemies": len(fake_enemies),
            "allies": len(fake_allies),
            "unknowns": len(fake_unknowns)
        }
    })

# base64 문자열을 numpy array로 변환
def decode_image(b64_string):
    if b64_string is None:
        return None
    img_bytes = base64.b64decode(b64_string)
    img_array = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img

# --------------------------------------------------------------------
# TCIS 테스트용: 10초마다 자동으로 가짜 데이터 전송
# --------------------------------------------------------------------
def auto_send_fake_data():
    """백그라운드에서 10초마다 가짜 데이터를 TCIS로 전송"""
    time.sleep(5)  # 서버 시작 대기
    
    while True:
        try:
            # 가짜 탐지 데이터 (Frontend 형식: tracking_id, class_id, x, z, alive)
            fake_detections = [
                {
                    "tracking_id": 1001,
                    "class_id": 5,  # Tank1
                    "x": 100.0 + (time.time() % 10),
                    "z": 200.0,
                    "alive": True
                },
                {
                    "tracking_id": 1002,
                    "class_id": 4,  # Human1
                    "x": 150.0,
                    "z": 250.0 + (time.time() % 10),
                    "alive": True
                },
                {
                    "tracking_id": 1003,
                    "class_id": 5,  # Tank1
                    "x": 80.0,
                    "z": 120.0 + (time.time() % 5),
                    "alive": True
                }
            ]
            
            # TCIS로 개별 객체 전송 (Frontend가 기대하는 형식)
            for obj in fake_detections:
                send_to_tcis('/internal/detection', obj)
            
            # 가짜 위치 데이터 (내 탱크 위치)
            fake_position = {
                "tanks": [
                    {
                        "tank_id": "17TK-101",
                        "x": -50.0 + (time.time() % 5),
                        "y": -100.0
                    }
                ]
            }
            send_to_tcis('/internal/position', fake_position)
            
            # 가짜 발포 이벤트 (발사)
            fake_fire_event = {
                "type": "fire_event",
                "fire": {
                    "target_tracking_id": 1001,
                    "ally_id": "17TK-101",
                    "class_id": 5
                }
            }
            send_to_tcis('/internal/fire', fake_fire_event)
            
            # 가짜 명중 결과 (hit or miss)
            fire_results = ['hit', 'miss']
            fake_hit_result = {
                "type": "hit_result",
                "data": {
                    "target_tracking_id": 1001,
                    "result": fire_results[int(time.time() / 10) % 2]  # 10초마다 hit/miss 교체
                }
            }
            send_to_tcis('/internal/fire', fake_hit_result)
            
            # 가짜 미션 데이터
            missions = ['attack', 'search', 'defence']
            fake_mission = {
                "mission": missions[int(time.time() / 30) % 3]  # 30초마다 변경
            }
            send_to_tcis('/internal/mission', fake_mission)
            
            write_log(f"🔄 자동 테스트 데이터 TCIS로 전송: detection={len(fake_detections)}개, position/fire(2)/mission")
            
        except Exception as e: 
            write_log(f"자동 전송 오류: {e}")
        
        time.sleep(10)  # 10초 대기

# --------------------------------------------------------------------

if __name__ == '__main__':
    # 백그라운드 스레드로 자동 데이터 전송 시작
    auto_thread = threading.Thread(target=auto_send_fake_data, daemon=True)
    auto_thread.start()
    write_log("자동 테스트 데이터 전송 스레드 시작")
    
    app.run(host='0.0.0.0', port=5000)
