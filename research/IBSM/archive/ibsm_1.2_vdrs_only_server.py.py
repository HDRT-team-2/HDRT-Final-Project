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
        ext_response = requests.post(external_server, json=request_data, timeout=0.05)# VDRS 서버 응답 대기를 0.1초로 수정
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
        if vdrs_data and isinstance(vdrs_data, dict) and 'detected_objects' in vdrs_data:
            detected_objects = vdrs_data.get('detected_objects', [])
            write_log(f"📷 VDRS에서 {len(detected_objects)}개 객체 탐지됨")
            for obj in detected_objects:
                if not isinstance(obj, dict):
                    continue
                try:
                    obj_class = obj.get('class', 'UNKNOWN')
                    obj_pos = obj.get('object_pos', {})
                    obj_angle = obj.get('object_angle_xy', {})
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
                    continue
        else:
            write_log("⚠️ VDRS 데이터가 없거나 형식이 올바르지 않습니다.")

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

@app.route('/detect', methods=['POST'])
def detect():
    write_log("detect() 호출 받음")
    
    image = request.files.get('image')
    if not image:
        return jsonify({"error": "No image received"}), 400

    try:
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

    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    write_log("get_action() 호출 받음")
    
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command

    global_WS_command, global_WS_weight = "W", 0.4
    global_AD_command, global_AD_weight = "D", 0.1
    
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
        "blStartX": 10,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 10,
        "rdStartX": 10, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 70,
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
