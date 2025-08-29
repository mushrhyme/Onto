#!/usr/bin/env python3
"""
제약조건 진단 스크립트
ConstraintConflictMonitor의 사전 검사를 통과했지만 최적화 실행 시 INFEASIBLE이 발생하는 원인을 찾기 위한 진단 도구
"""

import logging
import time
from datetime import datetime
from owlready2 import get_ontology
from ontology.manager import OntologyManager
from production_optimizer import ProductionOptimizer
from constraint_types import ConstraintTypes, LineConstraintConfig

class ConstraintDiagnostic:
    """제약조건 진단 클래스"""
    
    def __init__(self, logger):
        self.logger = logger
        self.conflicts = []
        self.warnings = []
        self.constraint_stats = {}
        
    def run_full_diagnostic(self):
        """전체 진단 실행"""
        self.logger.info("🔍 === 제약조건 전체 진단 시작 ===")
        
        # 1. 온톨로지 매니저 초기화
        self.logger.info("1️⃣ 온톨로지 매니저 초기화...")
        onto = get_ontology("http://test.org/factory.owl")
        ontology_manager = OntologyManager(onto, monday_date="2025-09-01")
        ontology_manager.build(
            products_path="../metadata/products.json",
            lines_path="../metadata/lines.json", 
            changeover_path="../metadata/change_over.json",
            order_path="../metadata/order.csv",
            start_date_str="2025-09-01"
        )
        
        # 2. 단계별 제약조건 검증
        self.logger.info("2️⃣ 단계별 제약조건 검증...")
        self._step_by_step_constraint_validation(ontology_manager)
        
        # 3. 데이터 일관성 검증
        self.logger.info("3️⃣ 데이터 일관성 검증...")
        self._validate_data_consistency(ontology_manager)
        
        # 4. 제약조건 조합 테스트
        self.logger.info("4️⃣ 제약조건 조합 테스트...")
        self._test_constraint_combinations(ontology_manager)
        
        # 5. 진단 결과 요약
        self.logger.info("5️⃣ 진단 결과 요약...")
        self._print_diagnostic_summary()
        
    def _step_by_step_constraint_validation(self, ontology_manager):
        """단계별 제약조건 검증"""
        self.logger.info("🔍 단계별 제약조건 검증 시작...")
        
        # 1단계: 기본 생산량 제약만
        self.logger.info("   📋 1단계: 기본 생산량 제약만 테스트...")
        try:
            optimizer = ProductionOptimizer(ontology_manager, active_lines=['13'])
            optimizer.weights = {
                'production_time': 1.0,
                'changeover_time': 0.0,      # 교체 제약 제거
                'changeover_count': 0.0,     # 교체 횟수 제약 제거
                'discontinuity': 0.0,        # 연속성 제약 제거
                'capacity_violation': 0.0,   # 용량 제약 제거
                'priority_violation': 0.0    # 우선순위 제약 제거
            }
            optimizer.build_model()
            success = optimizer.solve()
            if success:
                self.logger.info("   ✅ 1단계 성공: 기본 생산량 제약만으로는 실행 가능")
            else:
                self.logger.error("   ❌ 1단계 실패: 기본 생산량 제약에서도 문제 발생")
                self.conflicts.append("BASIC_PRODUCTION_CONSTRAINT_FAILED")
        except Exception as e:
            self.logger.error(f"   ❌ 1단계 오류: {e}")
            self.conflicts.append(f"BASIC_PRODUCTION_ERROR: {e}")
        
        # 2단계: 시간 제약 추가
        self.logger.info("   📋 2단계: 시간 제약 추가 테스트...")
        try:
            optimizer = ProductionOptimizer(ontology_manager, active_lines=['13'])
            optimizer.weights = {
                'production_time': 1.0,
                'changeover_time': 0.0,
                'changeover_count': 0.0,
                'discontinuity': 0.0,
                'capacity_violation': 1.0,   # 시간 제약만 추가
                'priority_violation': 0.0
            }
            optimizer.build_model()
            success = optimizer.solve()
            if success:
                self.logger.info("   ✅ 2단계 성공: 시간 제약까지 추가해도 실행 가능")
            else:
                self.logger.error("   ❌ 2단계 실패: 시간 제약 추가 시 문제 발생")
                self.conflicts.append("TIME_CONSTRAINT_FAILED")
        except Exception as e:
            self.logger.error(f"   ❌ 2단계 오류: {e}")
            self.conflicts.append(f"TIME_CONSTRAINT_ERROR: {e}")
    
    def _validate_data_consistency(self, ontology_manager):
        """데이터 일관성 검증"""
        self.logger.info("🔍 데이터 일관성 검증 시작...")
        
        # 주문 데이터와 시간 계산
        order_data = ontology_manager._order_data
        total_boxes = sum(order_data.values())
        
        # 라인 13의 생산능력 (기본값 사용)
        default_hourly_capacity = 1000  # 박스/시간 (기본값)
        
        # 총 가용 시간 계산
        total_available_hours = 10 * 10.5  # 10개 시간대 × 10.5시간 (수요일 제외)
        total_available_hours += 2 * 8.0   # 수요일 2개 시간대 × 8.0시간
        total_available_hours = 101.0      # 총 101시간
        
        # 필요한 생산 시간 계산
        required_production_hours = total_boxes / default_hourly_capacity
        
        self.logger.info(f"   📊 생산량 vs 시간 분석:")
        self.logger.info(f"      - 총 주문량: {total_boxes:,}박스")
        self.logger.info(f"      - 총 가용시간: {total_available_hours:.1f}시간")
        self.logger.info(f"      - 필요 생산시간: {required_production_hours:.1f}시간")
        self.logger.info(f"      - 시간 활용률: {(required_production_hours/total_available_hours)*100:.1f}%")
        
        if required_production_hours > total_available_hours:
            self.logger.error("   ❌ 생산량이 가용시간을 초과합니다!")
            self.conflicts.append("PRODUCTION_TIME_EXCEEDED")
        elif required_production_hours > total_available_hours * 0.95:
            self.logger.warning("   ⚠️ 생산량이 가용시간의 95%를 초과합니다")
            self.warnings.append("HIGH_TIME_UTILIZATION")
        else:
            self.logger.info("   ✅ 생산량과 시간이 일치합니다")
    
    def _test_constraint_combinations(self, ontology_manager):
        """제약조건 조합 테스트"""
        self.logger.info("🔍 제약조건 조합 테스트 시작...")
        
        # 다양한 가중치 조합으로 테스트
        test_combinations = [
            {
                'name': '최소 제약',
                'weights': {
                    'production_time': 1.0,
                    'changeover_time': 0.1,
                    'changeover_count': 0.1,
                    'discontinuity': 0.1,
                    'capacity_violation': 0.1,
                    'priority_violation': 0.1
                }
            },
            {
                'name': '중간 제약',
                'weights': {
                    'production_time': 1.0,
                    'changeover_time': 1.0,
                    'changeover_count': 1.0,
                    'discontinuity': 1.0,
                    'capacity_violation': 1.0,
                    'priority_violation': 1.0
                }
            },
            {
                'name': '강한 제약',
                'weights': {
                    'production_time': 1.0,
                    'changeover_time': 10.0,
                    'changeover_count': 10.0,
                    'discontinuity': 10.0,
                    'capacity_violation': 10.0,
                    'priority_violation': 10.0
                }
            }
        ]
        
        for i, combo in enumerate(test_combinations, 1):
            self.logger.info(f"   📋 조합 {i}: {combo['name']} 테스트...")
            try:
                optimizer = ProductionOptimizer(ontology_manager, active_lines=['13'])
                optimizer.weights = combo['weights']
                optimizer.build_model()
                success = optimizer.solve()
                
                if success:
                    self.logger.info(f"   ✅ 조합 {i} 성공: {combo['name']}")
                    self.constraint_stats[f"combination_{i}"] = "SUCCESS"
                else:
                    self.logger.error(f"   ❌ 조합 {i} 실패: {combo['name']}")
                    self.constraint_stats[f"combination_{i}"] = "FAILED"
                    self.conflicts.append(f"COMBINATION_{i}_FAILED")
                    
            except Exception as e:
                self.logger.error(f"   ❌ 조합 {i} 오류: {e}")
                self.constraint_stats[f"combination_{i}"] = f"ERROR: {e}"
                self.conflicts.append(f"COMBINATION_{i}_ERROR: {e}")
    
    def _print_diagnostic_summary(self):
        """진단 결과 요약"""
        self.logger.info("🔍 === 제약조건 진단 결과 요약 ===")
        
        if self.conflicts:
            self.logger.error(f"❌ 발견된 충돌: {len(self.conflicts)}개")
            for conflict in self.conflicts:
                self.logger.error(f"   - {conflict}")
        else:
            self.logger.info("✅ 발견된 충돌 없음")
            
        if self.warnings:
            self.logger.warning(f"⚠️ 발견된 경고: {len(self.warnings)}개")
            for warning in self.warnings:
                self.logger.warning(f"   - {warning}")
        else:
            self.logger.info("✅ 발견된 경고 없음")
            
        if self.constraint_stats:
            self.logger.info("📊 제약조건 조합 테스트 결과:")
            for combo, result in self.constraint_stats.items():
                self.logger.info(f"   - {combo}: {result}")
        
        self.logger.info("🔍 === 진단 완료 ===")

def main():
    """메인 실행 함수"""
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 진단 실행
    diagnostic = ConstraintDiagnostic(logger)
    diagnostic.run_full_diagnostic()

if __name__ == "__main__":
    main()
