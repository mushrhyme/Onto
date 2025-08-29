from pulp import *
import datetime
import time
from typing import Dict, Tuple, Optional
import logging
from ontology.manager import OntologyManager
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
import os
from owlready2 import get_ontology
from constraint_types import ConstraintTypes, LineConstraintConfig

class ProductionOptimizer:
    """
    MILP 기반 생산 계획 최적화 모델 (단순화된 구조)
    Mixed Integer Linear Programming을 사용하여 최적의 생산 스케줄 생성
    
    주요 기능:
    - 온톨로지 스키마와 인스턴스를 활용한 최적화
    - 특정 호기(라인)만 활성화하여 최적화 가능
    - 생산시간, 교체시간, 청소시간 최소화
    - 연속성 보장 및 제약조건 관리
    - 다중 목표 최적화 지원
    
    단순화된 구조:
    - O(P×L×T)로 대폭 감소
    - 메모리 사용량 최적화 및 계산 속도 향상
    - 기존 핵심 변수만으로 연속성과 교체 관계 표현
    """
    def __init__(self, ontology_manager, active_lines=None, logger=None):
        """
        ProductionOptimizer 초기화
        Args:
            ontology_manager: OntologyManager 객체 (온톨로지와 데이터 포함)
            active_lines: list, 활성화할 라인 리스트 (None이면 모든 라인 사용)
            logger: 로거 객체 (선택사항)
        """
        self.ontology_manager = ontology_manager
        self.onto = ontology_manager.onto
        # change_over.json 데이터 로드 (changeover_rules 포함)
        self.json_data = ontology_manager._changeover_data  # 교체 데이터
        self.order_data = ontology_manager._order_data  # 주문 데이터
        self.logger = logger or logging.getLogger(__name__)
        
        # 모델 및 변수 초기화
        self.model = None
        self.variables = {}
        self.constraints = []
        
        # 온톨로지에서 데이터 추출
        self._extract_ontology_data()
        
        # 활성화할 라인 설정
        self._setup_active_lines(active_lines)
        
        # 시간 슬롯은 온톨로지 데이터 추출 후에 설정됨 (self.ontology_timeslots)
        
        # 제약조건 가중치
        self.weights = {
            'production_time': 1.0,      # 총 생산시간 최대화 (음수 가중치로 최대화)
            'changeover_time': 5.0,      # 총 교체시간 최소화 
            'changeover_count': 5.0,     # 교체 횟수 최소화
            'cleaning_time': 0.6,        # 총 청소시간 최소화
            'discontinuity': 3.0,        # 연속성 위반 페널티 
            'capacity_violation': 1.0,   # 용량 위반 페널티
            'priority_violation': 15.0   # 우선순위 위반 페널티 
        }
        
        # 호기별 제약조건 설정
        self.line_constraints = LineConstraintConfig()
        
        # ConstraintManager는 build_model에서 초기화 (모델 생성 후)
        self.constraint_manager = None
        
        # 기본 목표 활용률 설정
        self.target_utilization_rate = 0.99  # 기본값 99%
        
    def set_utilization_target(self, target_rate: float = 0.99):
        """
        가동시간 목표 활용률 설정
        
        Args:
            target_rate: 목표 활용률 (0.95 = 95%, 1.0 = 100%)
        
        사용법:
            optimizer.set_utilization_target(0.99)  # 99% 활용률 목표
            optimizer.set_utilization_target(1.0)   # 100% 활용률 목표 (소프트 제약조건으로 처리)
        """
        self.target_utilization_rate = max(0.90, min(1.0, target_rate))
        self.logger.info(f"가동시간 목표 활용률 설정: {self.target_utilization_rate * 100:.1f}%")
        
        if target_rate >= 1.0:
            self.logger.info("100% 활용률 목표: 소프트 제약조건으로 처리하여 실행 가능한 해 보장")
        
        return self
    
    def set_line_constraints(self, constraint_config: LineConstraintConfig):
        """
        호기별 제약조건 설정
        Args:
            constraint_config: LineConstraintConfig 객체
        """
        # 사용 가능한 제품코드와 라인 목록 설정
        constraint_config.set_available_products(self.products)
        constraint_config.set_available_lines(self.lines)
        
        self.line_constraints = constraint_config
        self.logger.info(f"호기별 제약조건 설정 완료: {len(constraint_config.get_all_constrained_lines())}개 호기")
        
    def add_line_constraint(self, line_id: str, constraint_type: str, **kwargs):
        """
        특정 호기에 제약조건 추가 (편의 메서드)
        Args:
            line_id: 호기 ID
            constraint_type: 제약조건 유형
            **kwargs: 제약조건 세부 설정
        """
        # 사용 가능한 제품코드와 라인 목록 설정
        self.line_constraints.set_available_products(self.products)
        self.line_constraints.set_available_lines(self.lines)
        
        self.line_constraints.add_line_constraint(line_id, constraint_type, **kwargs)
        self.logger.info(f"호기 {line_id}에 {constraint_type} 제약조건 추가")
    
    def _extract_ontology_data(self):
        """
        온톨로지에서 데이터 추출
        """
        self.logger.info("온톨로지 데이터 추출 중...")
        
        # 제품 데이터 추출 (제품코드 사용)
        self.products = list(self.order_data.keys())  # ['101003486', '101003487', '101003532', ...]
        
        # 라인 데이터 추출 (온톨로지 인스턴스에서)
        self.lines = []
        self.line_instances = {}
        
        if hasattr(self.onto, 'Line'):
            for line_instance in self.onto.Line.instances():
                line_id = line_instance.name.replace('line_', '')  # 'line_11' -> '11'
                self.lines.append(line_id)
                self.line_instances[line_id] = line_instance
        
        # 온톨로지에서 라인을 찾지 못한 경우 오류 발생
        if not self.lines:
            raise ValueError("온톨로지에서 라인을 찾을 수 없습니다. Line 클래스와 인스턴스를 확인해주세요.")
        
        # 제품 인스턴스 추출 (제품코드 기준)
        self.product_instances = {}
        if hasattr(self.onto, 'Product'):
            for product_instance in self.onto.Product.instances():
                # 제품코드 우선, 없으면 제품명 사용
                if hasattr(product_instance, 'hasProductCode') and product_instance.hasProductCode:
                    product_code = product_instance.hasProductCode[0]
                else:
                    product_code = None
                
                if hasattr(product_instance, 'hasProductName') and product_instance.hasProductName:
                    product_name = product_instance.hasProductName[0]
                else:
                    product_name = product_instance.name
                            
                if product_code:
                    self.product_instances[product_code] = product_instance
                else:
                    self.product_instances[product_name] = product_instance
            
            self.logger.info(f"제품 인스턴스 매핑 완료: {len(self.product_instances)}개")
        else:
            self.logger.warning("온톨로지에 Product 클래스가 없습니다!")
        
        # 라인-제품 관계 추출 (제품코드 기준)
        self.line_product_relations = {}
        if hasattr(self.onto, 'LineProductRelation'):
            for relation in self.onto.LineProductRelation.instances():
                line = relation.hasLine[0] if relation.hasLine else None
                product = relation.handlesProduct[0] if relation.handlesProduct else None
                if line and product:
                    line_id = line.name.replace('line_', '')
                    # 제품코드 우선, 없으면 제품명 사용
                    product_code = product.hasProductCode[0] if product.hasProductCode else None
                    product_name = product.hasProductName[0] if product.hasProductName else product_instance.name
                    
                    if line_id not in self.line_product_relations:
                        self.line_product_relations[line_id] = {}
                    
                    if product_code:
                        self.line_product_relations[line_id][product_code] = relation
                    else:
                        self.line_product_relations[line_id][product_name] = relation
        
        # 교체 규칙 추출
        self.changeover_rules = {}
        if hasattr(self.onto, 'ChangeoverRule'):
            for rule in self.onto.ChangeoverRule.instances():
                # 규칙의 속성들 확인
                if hasattr(rule, 'appliesTo') and rule.appliesTo:
                    line = rule.appliesTo[0]
                else:
                    self.logger.warning(f"appliesTo 속성이 없거나 비어있음")
                    line = None
                
                if line:
                    line_id = line.name.replace('line_', '')
                    if line_id not in self.changeover_rules:
                        self.changeover_rules[line_id] = []
                    self.changeover_rules[line_id].append(rule)
                else:
                    self.logger.warning(f"라인 정보가 없어 규칙 추가 실패")
            
            self.logger.info(f"교체 규칙 추출 완료: {len(self.changeover_rules)}개 라인")
        else:
            self.logger.warning("온톨로지에 ChangeoverRule 클래스가 없습니다!")
        
        # TimeSlot 인스턴스 추출 (온톨로지 기반)
        self.ontology_timeslots = []
        self.timeslot_instances = {}
        if hasattr(self.onto, 'TimeSlot'):
            for timeslot_instance in self.onto.TimeSlot.instances():
                timeslot_name = timeslot_instance.hasTimeSlotName[0] if timeslot_instance.hasTimeSlotName else timeslot_instance.name
                self.ontology_timeslots.append(timeslot_name)
                self.timeslot_instances[timeslot_name] = timeslot_instance
            self.logger.info(f"온톨로지에서 TimeSlot 인스턴스 {len(self.ontology_timeslots)}개 추출 완료")
        else:
            self.logger.error("온톨로지에 TimeSlot 클래스가 없습니다. 시스템을 종료합니다.")
            raise ValueError("TimeSlot 클래스가 온톨로지에 정의되지 않았습니다.")
        
        # valid_product_line_combinations 생성 (ConstraintManager에서 필요)
        self.valid_product_line_combinations = []
        for product in self.products:
            for line in self.lines:
                # CT Rate가 있는 조합만 유효한 것으로 간주
                ct_rate = self._get_capacity_rate(product, line)
                if ct_rate > 0:  # CT Rate가 0보다 큰 경우만 유효
                    self.valid_product_line_combinations.append((product, line))
        
        self.logger.info(f"온톨로지 데이터 추출 완료: {len(self.lines)}개 라인, {len(self.products)}개 제품")
        self.logger.info(f"유효한 제품-라인 조합: {len(self.valid_product_line_combinations)}개")
        self.logger.info(f"시간대: {len(self.ontology_timeslots)}개")
    
    def _setup_active_lines(self, active_lines):
        """
        활성화할 라인 설정
        """
        all_lines = self.lines.copy()
        
        if active_lines is None:
            self.lines = all_lines  # 모든 라인 사용
            self.logger.info(f"모든 라인 활성화: {self.lines}")
        else:
            # 활성화할 라인만 필터링
            self.lines = [line for line in active_lines if line in all_lines]
            inactive_lines = [line for line in active_lines if line not in all_lines]
            if inactive_lines:
                self.logger.warning(f"존재하지 않는 라인 무시: {inactive_lines}")
            self.logger.info(f"활성화된 라인: {self.lines}")
    
    def _get_max_working_hours(self, timeslot_name: str) -> float:
        """
        온톨로지 TimeSlot 인스턴스에서 작업시간 반환
        Args:
            timeslot_name: str, 시간대 이름 (예: '수요일_조간')
        Returns:
            float: 최대 가동시간
        """
        # 온톨로지에서 TimeSlot 인스턴스 찾기
        if timeslot_name in self.timeslot_instances:
            timeslot = self.timeslot_instances[timeslot_name]
            if hasattr(timeslot, 'hasWorkingHours') and timeslot.hasWorkingHours:
                working_hours = timeslot.hasWorkingHours[0]
                return working_hours
        
        # 온톨로지에서 찾지 못한 경우 오류
        self.logger.error(f"온톨로지에서 {timeslot_name} 작업시간을 찾을 수 없습니다.")
        raise ValueError(f"온톨로지에서 시간 설정이 없습니다. OntologyManager가 올바르게 초기화되었는지 확인해주세요.")
    
    def _get_capacity_rate(self, product: str, line: str) -> float:
        """
        제품별 라인별 생산능력 반환 (온톨로지 데이터만 활용)
        Args:
            product: str, 제품명 또는 제품코드
            line: str, 라인명
        Returns:
            float: 분당 생산 개수 (CT Rate), 생산 불가능한 경우 0.0
        """
        # 온톨로지에서 라인-제품 관계 확인
        if line in self.line_product_relations and product in self.line_product_relations[line]:
            relation = self.line_product_relations[line][product]
            if hasattr(relation, 'hasCTRate') and relation.hasCTRate:
                ct_rate = relation.hasCTRate[0]
                if ct_rate is not None and ct_rate > 0:
                    return ct_rate
        
        # 온톨로지에서 찾지 못한 경우 0.0 반환
        return 0.0
    
    def _get_package_count(self, product: str) -> int:
        """
        박스당 제품 수 가져오기 (온톨로지 데이터 활용)
        hasItemsPerBox 속성 사용 (박스당 제품 수)
        """
        # 온톨로지에서 박스당 제품 수 찾기 (hasItemsPerBox 속성 사용)
        if product in self.product_instances:
            instance = self.product_instances[product]
            if hasattr(instance, 'hasItemsPerBox') and instance.hasItemsPerBox:
                return instance.hasItemsPerBox[0]
    
        # 온톨로지에서 찾지 못한 경우 0 반환
        return 0

    def _get_changeover_time(self, from_product: str, to_product: str, line: str) -> float:
        """
        제품 간 교체 시간 조회 (온톨로지 기반)
        Args:
            from_product: str, 이전 제품
            to_product: str, 다음 제품
            line: str, 라인명
        Returns:
            float: 교체 시간 (시간 단위)
        """
        try:
            # 디버깅: 입력 파라미터 상세 정보
            self.logger.debug(f"🔍 _get_changeover_time 함수 호출:")
            self.logger.debug(f"  → from_product: {from_product} (타입: {type(from_product)})")
            self.logger.debug(f"  → to_product: {to_product} (타입: {type(to_product)})")
            self.logger.debug(f"  → line: {line} (타입: {type(line)})")
            self.logger.debug(f"  → self.lines: {self.lines}")
            self.logger.debug(f"  → self.changeover_rules.keys(): {list(self.changeover_rules.keys()) if hasattr(self, 'changeover_rules') else 'None'}")
            
            # line 파라미터 검증
            if not line:
                self.logger.warning(f"교체 시간 조회 실패: 라인 정보가 없음 (제품: {from_product} → {to_product}), 기본값 0.4h 사용")
                return 0.4
            
            self.logger.debug(f"🔍 교체시간 조회: {from_product} → {to_product} @ {line}")
            
            # 온톨로지에서 교체 규칙 조회
            if line in self.changeover_rules:
                line_rules = self.changeover_rules[line]
                self.logger.debug(f"  → 라인 {line}에서 {len(line_rules)}개 규칙 발견")
                
                # 제품별 교체 시간 규칙 찾기
                for i, rule in enumerate(line_rules):
                    self.logger.debug(f"  → 규칙 {i+1} 검사 중...")
                    
                    from_rule = rule.hasFromCondition[0] if rule.hasFromCondition else None
                    to_rule = rule.hasToCondition[0] if rule.hasToCondition else None
                    changeover_time = rule.hasChangeoverTimeValue[0] if rule.hasChangeoverTimeValue else None
                    rule_description = rule.hasRuleDescription[0] if rule.hasRuleDescription else "설명 없음"
                    
                    self.logger.debug(f"    → from_rule: {from_rule}, to_rule: {to_rule}, time: {changeover_time}")
                    
                    match_changeover = self._match_changeover_rule(from_product, to_product, from_rule, to_rule, line)
                    
                    self.logger.debug(f"    → 매칭 결과: {match_changeover}")
                    
                    # 제품 코드 매칭 (실제 제품 코드와 규칙의 from/to 비교)
                    if match_changeover and changeover_time is not None:
                        self.logger.debug(f"✅ 교체 시간 조회 성공: {from_product} → {to_product} @ {line} = {changeover_time}h ({rule_description})")
                        return changeover_time
                    else:
                        self.logger.debug(f"    → 매칭 실패 또는 시간값 없음")
                
                # 규칙을 찾지 못한 경우 기본값 반환
                self.logger.warning(f"❌ 교체 시간 규칙 없음: {from_product} → {to_product} @ {line}, 기본값 0.4h 사용")
                print(from_rule, to_rule, rule_description)
                return 0.4
            else:
                # 온톨로지에 해당 라인의 교체 규칙이 없는 경우 기본값 반환
                self.logger.warning(f"❌ 라인 {line}에 대한 교체 규칙이 온톨로지에 없음, 기본값 0.4h 사용")
                self.logger.debug(f"  → 사용 가능한 라인: {list(self.changeover_rules.keys())}")
                return 0.4
                
        except Exception as e:
            self.logger.warning(f"❌ 교체 시간 조회 실패: {from_product} → {to_product} @ {line}, 오류: {e}, 기본값 0.4h 사용")
            return 0.4
    
    def _match_changeover_rule(self, from_product: str, to_product: str, from_rule, to_rule, line: str) -> bool:
        """
        제품과 교체 규칙 매칭 (온톨로지 기반)
        Args:
            from_product: str, 실제 이전 제품 코드
            to_product: str, 실제 다음 제품 코드
            from_rule: 규칙의 from 값
            to_rule: 규칙의 to 값
            line: str, 라인명 (규칙 타입 결정에 사용)
        Returns:
            bool: 매칭 여부
        """
        try:
            self.logger.debug(f"🔍 규칙 매칭 시작: {from_product} → {to_product} @ {line}")
            self.logger.debug(f"  → 규칙 조건: from={from_rule}, to={to_rule}")
            
            # 온톨로지에서 제품 인스턴스 조회
            from_product_instance = self.product_instances.get(from_product)
            to_product_instance = self.product_instances.get(to_product)
            
            # 제품 인스턴스가 없으면 매칭 실패
            if not from_product_instance or not to_product_instance:
                return False
            
            # 라인별 규칙 타입 확인 (온톨로지 기반)
            rule_type = self._get_rule_type_for_line(line)
            
            # 제품 속성 값 추출
            from_value = self._get_product_attribute_value(from_product_instance, rule_type)
            to_value = self._get_product_attribute_value(to_product_instance, rule_type)
            
            # 속성 값이 없으면 매칭 실패
            if from_value is None or to_value is None:
                return False
            
            # 규칙 조건과 매칭 확인 (데이터 타입 통일)
            try:
                from_rule_int = int(from_rule) if from_rule is not None else None
                to_rule_int = int(to_rule) if to_rule is not None else None
                
                from_match = from_value == from_rule_int
                to_match = to_value == to_rule_int
                
            except (ValueError, TypeError):
                return False
            
            return from_match and to_match
            
        except Exception as e:
            self.logger.error(f"규칙 매칭 중 오류 발생: {e}")
            return False
    
    def _get_rule_type_for_line(self, line: str) -> str:
        """
        라인별 교체 규칙 타입 반환 (온톨로지 기반)
        Args:
            line: str, 라인명
        Returns:
            str: 규칙 타입 (예: 'height', 'product_type', 'units_per_pack', 'market_type', 'universal')
        """
        try:
            # 온톨로지에서 해당 라인의 교체 규칙 조회
            if line in self.changeover_rules and self.changeover_rules[line]:
                # 첫 번째 규칙의 rule_type 반환 (라인별로 동일한 rule_type 사용)
                first_rule = self.changeover_rules[line][0]
                if hasattr(first_rule, 'hasRuleType') and first_rule.hasRuleType:
                    return first_rule.hasRuleType[0]
        except Exception as e:
            self.logger.warning(f"라인 {line}의 규칙 타입 조회 실패: {e}")
        
        return 'unknown'
    
    def _get_product_attribute_value(self, product_instance, rule_type: str):
        """
        제품 인스턴스에서 규칙 타입에 해당하는 속성 값 추출
        products.json과 change_over.json의 실제 키값에 맞춰 수정됨
        Args:
            product_instance: 제품 온톨로지 인스턴스
            rule_type: str, 규칙 타입
        Returns:
            속성 값 또는 None
        """
        try:
            self.logger.debug(f"🔍 제품 {product_instance.name}에서 {rule_type} 속성 값 추출 중...")
            
            # 제품 카테고리 확인
            category = None
            if hasattr(product_instance, 'hasCategory') and product_instance.hasCategory:
                category = product_instance.hasCategory[0]
                self.logger.debug(f"  → 제품 카테고리: {category}")
            
            # 규칙 타입별 매핑 테이블 (change_over.json의 rule_type과 products.json의 키값 매핑)
            mapping = {
                "height": "hasHeight",           # height 규칙 → hasHeight 속성 (용기 높이)
                "items_per_product": "hasItemsPerProduct",  # items_per_box 규칙 → hasItemsPerBox 속성 (계산된 값)
                "product_type": "hasProductType",       # product_type 규칙 → hasProductType 속성 (제품 타입)
                "market_type": "hasMarketType",         # market_type 규칙 → hasMarketType 속성 (시장 타입)
                "universal": None                        # universal 규칙 → 특정 속성 없음
            }
            
            # 매핑된 속성명 가져오기
            attribute_name = mapping.get(rule_type)
            if not attribute_name:
                self.logger.debug(f"  → {rule_type} 규칙은 특정 속성이 없음 (universal 등)")
                return None
            
            # 제품에서 해당 속성 값 조회
            if hasattr(product_instance, attribute_name) and getattr(product_instance, attribute_name):
                value = getattr(product_instance, attribute_name)[0]
                self.logger.debug(f"  → {attribute_name}: {value}")
                return value
            else:
                self.logger.debug(f"  → {attribute_name} 속성이 없거나 비어있음")
                return None
                
        except Exception as e:
            self.logger.error(f"제품 속성 값 추출 중 오류 발생: {e}")
            return None
    
    def _get_setup_time(self, line: str) -> float:
        """
        라인별 작업 준비 시간 반환 (온톨로지 기반)
        Args:
            line: str, 라인명
        Returns:
            float: 작업 준비 시간 (시간 단위)
        """
        # 온톨로지에서 라인 인스턴스 조회
        if line in self.line_instances:
            line_instance = self.line_instances[line]
            if hasattr(line_instance, 'hasSetupTime') and line_instance.hasSetupTime:
                setup_time = line_instance.hasSetupTime[0]
                return setup_time
        
        # 온톨로지에서 찾지 못한 경우 기본값 반환
        return 1.0  # 기본값
        
    def _get_cleanup_time(self, line: str) -> float:
        """
        라인별 청소 시간 반환 (온톨로지 기반)
        Args:
            line: str, 라인명
        Returns:
            float: 청소 시간 (시간 단위)
        """
        # 온톨로지에서 라인 인스턴스 조회
        if line in self.line_instances:
            line_instance = self.line_instances[line]
            if hasattr(line_instance, 'hasCleanupTime') and line_instance.hasCleanupTime:
                cleanup_time = line_instance.hasCleanupTime[0]
                return cleanup_time
        
        # 온톨로지에서 찾지 못한 경우 기본값 반환
        return 2.5  # 기본값
        
    def build_model(self):
        """
        MILP 모델 구축 (단순화된 구조)
        """
        self.logger.info("=== MILP 모델 구축 시작 (단순화된 구조) ===")
        
        # 모델 생성
        self.model = LpProblem("Production_Scheduling_Simplified", LpMinimize)
        
        # 변수 정의
        self._create_variables()
        
        # ConstraintManager 초기화 (필요한 속성들이 모두 생성된 후에)
        from constraint_manager import ConstraintManager
        self.constraint_manager = ConstraintManager(self)
        
        # 새로운 제약조건 추가 (ConstraintManager에 위임)
        self.constraint_manager.add_all_constraints()
        
        # 목적함수 설정
        self._set_objective_function()
        
        self.logger.info("MILP 모델 구축 완료 (단순화된 구조)")
    
    def _create_variables(self):
        """
        결정 변수 생성 (단순화된 구조: 기존 변수만 유지)
        """
        self.logger.info("변수 생성 중... (온톨로지 기반)")
        
        # 실제 생산 가능한 제품-라인 조합 생성
        self.valid_product_line_combinations = []
        for product in self.products:
            for line in self.lines:
                # CT Rate가 있는 조합만 유효한 것으로 간주
                ct_rate = self._get_capacity_rate(product, line)
                if ct_rate > 0:  # CT Rate가 0보다 큰 경우만 유효
                    self.valid_product_line_combinations.append((product, line))
        
        self.logger.info(f"유효한 제품-라인 조합: {len(self.valid_product_line_combinations)}개")
        
        # 유효한 조합이 없으면 기본값 설정
        if len(self.valid_product_line_combinations) == 0:
            # 모든 제품-라인 조합을 기본값으로 설정
            for product in self.products:
                for line in self.lines:
                    self.valid_product_line_combinations.append((product, line))
        
        # === 핵심 변수들만 유지 ===
        
        # 1. 생산 결정 변수 (이진변수) - 유효한 조합만
        # x[i,j,k] = 1: 제품 i를 라인 j에서 시점 k에 생산
        self.variables['production'] = LpVariable.dicts(
            "production",
            [(i, j, k) for i, j in self.valid_product_line_combinations for k in self.ontology_timeslots],
            cat=LpBinary
        )
        
        # 2. 생산 시간 변수 (연속변수) - 유효한 조합만
        # p[i,j,k]: 제품 i를 라인 j에서 시점 k에 생산하는 시간
        self.variables['production_time'] = LpVariable.dicts(
            "production_time",
            [(i, j, k) for i, j in self.valid_product_line_combinations for k in self.ontology_timeslots],
            lowBound=0
        )
        
        # 3. 교체 결정 변수 (이진변수) - 유효한 조합만
        # y[i,i',j,k] = 1: 제품 i에서 i'로 교체
        self.variables['changeover'] = LpVariable.dicts(
            "changeover",
            [(i, i_prime, j, k) for i, j in self.valid_product_line_combinations 
             for i_prime, j_prime in self.valid_product_line_combinations 
             if j == j_prime and i != i_prime  # 같은 라인에서 다른 제품으로 교체
             for k in self.ontology_timeslots],
            cat=LpBinary
        )
        
        # 4. 교체 시간 변수 (연속변수)
        # c[j,k]: 라인 j에서 시점 k에 교체 시간
        self.variables['changeover_time'] = LpVariable.dicts(
            "changeover_time",
            [(j, k) for j in self.lines for k in self.ontology_timeslots],
            lowBound=0
        )
        
        # 5. 청소 시간 변수 (연속변수)
        # clean[j,k]: 라인 j에서 시점 k에 청소 시간
        self.variables['cleaning_time'] = LpVariable.dicts(
            "cleaning_time",
            [(j, k) for j in self.lines for k in self.ontology_timeslots],
            lowBound=0
        )
        
        # 6. 연속성 보너스 변수 (이진변수) - 유효한 조합만
        # cont[i,j,k] = 1: 제품 i가 라인 j에서 시점 k와 k+1에 연속 생산
        self.variables['continuity'] = LpVariable.dicts(
            "continuity",
            [(i, j, k) for i, j in self.valid_product_line_combinations 
             for k in range(len(self.ontology_timeslots) - 1)],  # 마지막 시점 제외
            cat=LpBinary
        )
        
        # 7. 교체 횟수 변수 (이진변수) - 라인별 시간대별 교체 발생 여부
        # changeover_count[j,k] = 1: 라인 j에서 시점 k에 교체 발생
        self.variables['changeover_count'] = LpVariable.dicts(
            "changeover_count",
            [(j, k) for j in self.lines for k in self.ontology_timeslots],
            cat=LpBinary
        )
        
        # 8. 순서 변수 (이진변수) - 시간대 내 제품 생산 순서
        # sequence[p,l,t,pos] = 1: 제품 p를 라인 l에서 시간대 t의 pos 위치에 생산
        self.MAX_POSITIONS = 3  # 시간대 내 최대 생산 제품 수
        self.variables['sequence'] = LpVariable.dicts(
            "sequence",
            [(p, l, t, pos) for p, l in self.valid_product_line_combinations 
             for t in self.ontology_timeslots for pos in range(1, self.MAX_POSITIONS + 1)],
            cat=LpBinary
        )
        
        # 9. 순서 간 교체 보조 변수 (이진변수) - 시간대 내 연속 위치 간 교체
        # sequence_changeover[p1,p2,l,t,pos] = 1: 제품 p1이 pos 위치, p2가 pos+1 위치에 연속 배치
        self.variables['sequence_changeover'] = LpVariable.dicts(
            "sequence_changeover",
            [(p1, p2, l1, t, pos) for p1, l1 in self.valid_product_line_combinations 
             for p2, l2 in self.valid_product_line_combinations 
             for t in self.ontology_timeslots for pos in range(1, self.MAX_POSITIONS)
             if l1 == l2 and p1 != p2],
            cat=LpBinary
        )
        
        # 10. 블록 시작 변수 (이진변수) - 연속된 시간대 블록의 시작점
        self.variables['block_start'] = {}
        for product, line in self.valid_product_line_combinations:
            required_slots = self._calculate_required_time_slots(product, line)
            self.variables['block_start'][product, line] = LpVariable.dicts(
                f"block_start_{product}_{line}",
                range(len(self.ontology_timeslots) - required_slots + 1),
                cat=LpBinary
            )

        
        self.logger.info(f"변수 생성 완료: {len(self.variables)}개 변수 그룹")
    
    
    def _set_objective_function(self):
        self.logger.info("목적함수 설정 중... (블록 단위 설계)")
        objective = 0
        
        # 1. 총 생산시간 최대화
        total_production_time = lpSum(self.variables['production_time'][i, j, k] 
                                     for i, j in self.valid_product_line_combinations 
                                     for k in self.ontology_timeslots)
        objective -= self.weights['production_time'] * total_production_time  # 가중치 1.0
        
        # 2. 총 교체시간 최소화
        total_changeover_time = lpSum(self.variables['changeover_time'][j, k] 
                                     for j in self.lines for k in self.ontology_timeslots)
        objective += self.weights['changeover_time'] * total_changeover_time  # 가중치 5.0
        
        # 3. 총 교체횟수 최소화
        total_changeover_count = lpSum(self.variables['changeover_count'][j, k] 
                                      for j in self.lines for k in self.ontology_timeslots)
        objective += self.weights['changeover_count'] * total_changeover_count  # 가중치 5.0
        
        # 4. 총 청소시간 최소화
        total_cleaning_time = lpSum(self.variables['cleaning_time'][j, k] 
                                   for j in self.lines for k in self.ontology_timeslots)
        objective += self.weights['cleaning_time'] * total_cleaning_time  # 가중치 0.6
        
        # 5. 생산시간 활용률 부족 페널티 추가
        if hasattr(self.constraint_manager, 'production_underutilization_penalties'):
            total_production_underutilization_penalty = lpSum(self.constraint_manager.production_underutilization_penalties)
            objective += 100.0 * total_production_underutilization_penalty
        
        # 6. 동적 활용률 부족 페널티 추가
        if hasattr(self.constraint_manager, 'dynamic_utilization_penalties'):
            total_dynamic_utilization_penalty = lpSum(self.constraint_manager.dynamic_utilization_penalties)
            objective += 75.0 * total_dynamic_utilization_penalty
        
        # 7. 최대 시간 우선 할당 페널티 추가
        if hasattr(self.constraint_manager, 'max_time_priority_penalties'):
            total_max_time_priority_penalty = lpSum(self.constraint_manager.max_time_priority_penalties)
            objective += 50.0 * total_max_time_priority_penalty
        
        # 8. 시간 정규화 페널티 추가
        if hasattr(self.constraint_manager, 'time_normalization_penalties'):
            total_time_normalization_penalty = lpSum(self.constraint_manager.time_normalization_penalties)
            objective += 80.0 * total_time_normalization_penalty
        
        self.model += objective
        self.logger.info("목적함수 설정 완료")
    
    def solve(self, solver_name: str = "PULP_CBC_CMD") -> bool:
        """
        최적화 실행
        Args:
            solver_name: str, 사용할 솔버
        Returns:
            bool: 최적화 성공 여부
        """
        self.logger.info("최적화 실행 시작")
        
        try:
            # 솔버 설정
            if solver_name == "PULP_CBC_CMD":
                solver = PULP_CBC_CMD(msg=0)  # 메시지 출력 안함
            else:
                solver = getSolver(solver_name)
            
            # 최적화 실행
            status = self.model.solve(solver)
            
            if status == LpStatusOptimal:
                self.logger.info("최적화 성공!")
                self.logger.info(f"목적함수 값: {value(self.model.objective):.2f}")
                return True
            elif status == LpStatusInfeasible:
                self.logger.error("문제가 실행 불가능합니다 (제약조건 충돌)")
                return False
            elif status == LpStatusUnbounded:
                self.logger.error("문제가 무한대입니다")
                return False
            else:
                self.logger.error(f"최적화 실패: {status}")
                return False
                
        except Exception as e:
            self.logger.error(f"최적화 실행 중 오류 발생: {e}")
            return False
     
    def _get_product_name(self, product_code: str) -> str:
        """
        제품코드로 제품명 가져오기 (온톨로지 기반)
        """
        # 온톨로지에서 제품명 찾기
        if product_code in self.product_instances:
            instance = self.product_instances[product_code]
            if hasattr(instance, 'hasProductName') and instance.hasProductName:
                return instance.hasProductName[0]
        
        # 온톨로지에서 찾지 못한 경우 제품코드 반환
        return product_code
    
    def _get_track_count(self, line: str) -> int:
        """
        라인별 트랙 수 반환 (온톨로지 기반)
        Args:
            line: str, 라인명
        Returns:
            int: 트랙 수
        """
        # 온톨로지에서 트랙 수 찾기
        if line in self.line_instances:
            line_instance = self.line_instances[line]
            if hasattr(line_instance, 'hasTrackCount') and line_instance.hasTrackCount:
                return line_instance.hasTrackCount[0]
        
        # 온톨로지에서 찾지 못한 경우 기본값 반환
        return 1  # 기본값

    def _calculate_required_time_slots(self, product: str, line: str) -> int:
        """제품별로 필요한 시간대 개수 계산"""
        from math import ceil
        
        target_boxes = self.order_data[product]
        capacity_rate = self._get_capacity_rate(product, line)  # 분당 생산 개수
        track_count = self._get_track_count(line)
        products_per_box = self._get_package_count(product)
        
        if products_per_box == 0:
            products_per_box = 1

        production_per_hour = capacity_rate * track_count * 60 / products_per_box  # 시간당 박스
        required_hours = target_boxes / production_per_hour
        max_hours = self._get_max_working_hours(self.ontology_timeslots[0])
        required_slots = ceil(required_hours / max_hours)
        
        return max(1, required_slots)  # 최소 1시간대 보장

    def extract_solution(self) -> Dict:
        """
        최적화 결과 추출
        Returns:
            dict: 최적화 결과
        """
        if not self.model or LpStatus[self.model.status] != "Optimal":
            self.logger.error("최적화가 성공하지 않았습니다")
            return {}
        
        self.logger.info("최적화 결과 추출")
        
        solution = {
            'production_schedule': {},
            'changeover_events': [],
            'cleaning_events': [],
            'objective_value': value(self.model.objective),
            'statistics': {}
        }
        
        # 생산 스케줄 추출 (유효한 조합만)
        for line in self.lines:
            solution['production_schedule'][line] = {}
            
            for time_slot in self.ontology_timeslots:
                line_schedule = []
                
                # 유효한 제품-라인 조합만 확인
                for product in self.products:
                    if (product, line) in self.valid_product_line_combinations:
                        # 생산 결정 변수
                        prod_var = self.variables['production'][product, line, time_slot]
                        prod_time_var = self.variables['production_time'][product, line, time_slot]
                        
                        if value(prod_var) > 0.5:  # 생산이 결정된 경우
                            production_time = value(prod_time_var)
                            
                            # 생산량 계산 (개수) - 트랙 수 고려
                            capacity_rate = self._get_capacity_rate(product, line)
                            track_count = self._get_track_count(line)
                            production_quantity_units = production_time * capacity_rate * track_count * 60
                            
                            # 개수를 박스로 변환
                            products_per_box = self._get_package_count(product)
                            if products_per_box > 0:
                                production_quantity_boxes = production_quantity_units / products_per_box
                            else:
                                production_quantity_boxes = 0
                            
                            line_schedule.append({
                                'product': product,
                                'production_time': production_time,
                                'production_quantity_units': production_quantity_units,  # 개수
                                'production_quantity_boxes': production_quantity_boxes   # 박스
                            })
                
                if line_schedule:
                    solution['production_schedule'][line][time_slot] = line_schedule
        
        # 교체 이벤트 추출 (수정된 로직)
        for line in self.lines:
            for k, time_slot in enumerate(self.ontology_timeslots):
                # 1. 같은 시간 슬롯 내에서의 교체 이벤트
                productions = solution['production_schedule'][line].get(time_slot, [])
                
                if len(productions) > 1:  # 여러 제품이 생산된 경우
                    for i in range(len(productions) - 1):
                        from_product = productions[i]['product']
                        to_product = productions[i + 1]['product']
                        
                        # 교체 이벤트 추가 (같은 시간 슬롯 내에서는 항상 교체)
                        changeover_time = self._get_changeover_time(from_product, to_product, line)
                        solution['changeover_events'].append({
                            'line': line,
                            'from_product': from_product,
                            'to_product': to_product,
                            'time_slot': time_slot,
                            'changeover_time': changeover_time
                        })

                
                # 2. 모든 연속된 시간대에서 교체 이벤트 감지
                if k > 0:  # 첫 번째 시간대가 아닌 경우
                    previous_time_slot = self.ontology_timeslots[k-1]
                    previous_productions = solution['production_schedule'][line].get(previous_time_slot, [])
                    current_productions = solution['production_schedule'][line].get(time_slot, [])
                    
                    if previous_productions and current_productions:
                        # 이전 시간 슬롯의 마지막 제품과 현재 시간 슬롯의 첫 번째 제품 비교
                        last_product_previous = previous_productions[-1]['product']
                        first_product_current = current_productions[0]['product']
                        
                        if last_product_previous != first_product_current:
                            # 시간대 간 제품이 바뀌면 교체 이벤트
                            changeover_time = self._get_changeover_time(last_product_previous, first_product_current, line)
                            solution['changeover_events'].append({
                                'line': line,
                                'time_slot': time_slot,
                                'from_product': last_product_previous,
                                'to_product': first_product_current,
                                'changeover_time': changeover_time
                            })

                
                # 3. changeover_time 변수 확인 및 실제 교체 원인 분석
                changeover_time = value(self.variables['changeover_time'][line, time_slot])
                if changeover_time > 0:
                    # 실제 교체 변수들 확인
                    actual_changeover_found = False
                    changeover_details = []
                    
                    for p1, line1 in self.valid_product_line_combinations:
                        for p2, line2 in self.valid_product_line_combinations:
                            if line1 == line2 == line and p1 != p2:
                                changeover_var_value = value(self.variables['changeover'][p1, p2, line, time_slot])
                                if changeover_var_value > 0:
                                    actual_changeover_found = True
                                    changeover_time_detail = self._get_changeover_time(p1, p2, line)
                                    changeover_details.append(f"{p1} → {p2} ({changeover_time_detail}h)")
                    
                    # 이미 추가된 교체 이벤트가 있는지 확인
                    existing_event = any(event['time_slot'] == time_slot and event['line'] == line for event in solution['changeover_events'])
                    
                    if not existing_event and actual_changeover_found:
                        # 실제 교체가 발생한 경우
                        solution['changeover_events'].append({
                            'line': line,
                            'time_slot': time_slot,
                            'changeover_time': changeover_time,
                            'details': changeover_details
                        })
        
        # 청소 이벤트 추출
        for line in self.lines:
            for time_slot in self.ontology_timeslots:
                cleaning_time = value(self.variables['cleaning_time'][line, time_slot])
                if cleaning_time > 0:
                    solution['cleaning_events'].append({
                        'line': line,
                        'time_slot': time_slot,
                        'cleaning_time': cleaning_time
                    })
        
        # 통계 정보 (유효한 조합만)
        total_production_time = sum(value(self.variables['production_time'][i, j, k]) 
                                  for i, j in self.valid_product_line_combinations for k in self.ontology_timeslots)
        total_changeover_time = sum(value(self.variables['changeover_time'][j, k]) 
                                  for j in self.lines for k in self.ontology_timeslots)
        total_cleaning_time = sum(value(self.variables['cleaning_time'][j, k]) 
                                for j in self.lines for k in self.ontology_timeslots)
        
        solution['statistics'] = {
            'total_production_time': total_production_time,
            'total_changeover_time': total_changeover_time,
            'total_cleaning_time': total_cleaning_time,
            'total_working_time': total_production_time + total_changeover_time + total_cleaning_time
        }
        
        self.logger.info("최적화 결과 추출 완료")
        
        # 시간 제약조건 위반 검증
        if hasattr(self, 'constraint_manager'):
            violations = self.constraint_manager.verify_time_constraint_violations(self)
            if violations > 0:
                self.logger.error(f"시간 제약 위반 {violations}개 발견!")
        
        return solution
    
    def create_result_processor(self):
        """결과 처리를 위한 프로세서 생성"""
        from production_result_processor import ProductionResultProcessor
        return ProductionResultProcessor(self)