"""
v6 생산 최적화 시스템 메인 실행 파일 (제약조건 충돌 모니터링 포함)
파일 분리된 구조로 최적화 실행 및 결과 처리
실시간으로 제약조건 충돌 여부를 모니터링하고 사용자에게 알려주는 기능 추가
"""

import logging
import time
import os
from datetime import datetime
from owlready2 import get_ontology
from ontology.manager import OntologyManager
from production_optimizer import ProductionOptimizer
from constraint_types import ConstraintTypes, LineConstraintConfig

class ConstraintConflictMonitor:
    """제약조건 충돌 모니터링 클래스"""
    
    def __init__(self, logger):
        self.logger = logger
        self.conflicts = []
        self.warnings = []
        self.constraint_stats = {}
    
    def add_conflict(self, conflict_type, description, severity="HIGH"):
        """충돌 추가"""
        conflict = {
            'type': conflict_type,
            'description': description,
            'severity': severity,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        self.conflicts.append(conflict)
        
        # 즉시 로깅
        if severity == "CRITICAL":
            self.logger.error(f"🚨 CRITICAL 충돌: {description}")
        elif severity == "HIGH":
            self.logger.error(f"❌ HIGH 충돌: {description}")
        elif severity == "MEDIUM":
            self.logger.warning(f"⚠️ MEDIUM 충돌: {description}")
        else:
            self.logger.warning(f"⚠️ LOW 충돌: {description}")
    
    def add_warning(self, warning_type, description):
        """경고 추가"""
        warning = {
            'type': warning_type,
            'description': description,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        self.warnings.append(warning)
        self.logger.warning(f"⚠️ 경고: {description}")
    
    def add_constraint_stat(self, constraint_name, status, details=""):
        """제약조건 상태 추가"""
        self.constraint_stats[constraint_name] = {
            'status': status,
            'details': details,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        
        if status == "SUCCESS":
            self.logger.info(f"✅ {constraint_name}: {details}")
        elif status == "WARNING":
            self.logger.warning(f"⚠️ {constraint_name}: {details}")
        elif status == "FAILED":
            self.logger.error(f"❌ {constraint_name}: {details}")
    
    def check_production_vs_time_conflict(self, order_data, lines, time_slots):
        """생산량 vs 시간 제약 충돌 검사 (실제 생산 능력 기반)"""
        self.logger.info("🔍 생산량 vs 시간 제약 충돌 검사 중...")
        
        for product, target_boxes in order_data.items():
            for line in lines:
                # 라인별 시간당 생산 능력 (박스/시간) - 실제 데이터 기반
                hourly_capacity = self._get_line_hourly_capacity(line, product)
                
                # 총 가용 시간 계산 (시간대 × 교대당 시간)
                total_available_time = len(time_slots) * 10.5  # 5일 × 10.5시간
                
                # 목표 생산량을 달성하는데 필요한 시간
                required_time = target_boxes / hourly_capacity
                
                # 실제 충돌 검사: 필요 시간이 가용 시간의 95%를 초과하는 경우
                if required_time > total_available_time * 0.95:
                    self.add_conflict(
                        "PRODUCTION_TIME_CONFLICT",
                        f"제품 {product}: 목표 생산량 {target_boxes}박스가 시간 제약 초과 (라인 {line}, 필요: {required_time:.1f}h, 가용: {total_available_time:.1f}h)",
                        "HIGH"
                    )
                elif required_time > total_available_time * 0.8:
                    # 경고 수준: 80-95% 사용률
                    self.add_warning(
                        "PRODUCTION_TIME_WARNING",
                        f"제품 {product}: 목표 생산량 {target_boxes}박스가 높음 (라인 {line}, 사용률: {required_time/total_available_time*100:.1f}%)"
                    )
    
    def _get_package_count(self, product_code):
        """제품별 박스당 제품 수 반환 (온톨로지 기반)"""
        try:
            if hasattr(self, 'ontology_manager') and self.ontology_manager:
                onto = self.ontology_manager.onto
                if hasattr(onto, 'Product'):
                    # 제품 인스턴스 찾기
                    for product_inst in onto.Product.instances():
                        if hasattr(product_inst, 'hasProductCode') and product_inst.hasProductCode:
                            if product_inst.hasProductCode[0] == product_code:
                                # hasItemsPerBox 속성에서 박스당 제품 수 조회
                                if hasattr(product_inst, 'hasItemsPerBox') and product_inst.hasItemsPerBox:
                                    items_per_box = product_inst.hasItemsPerBox[0]
                                    self.logger.debug(f"제품 {product_code} 박스당 제품 수: {items_per_box}")
                                    return items_per_box
                                break
            
            # 온톨로지에서 찾지 못한 경우 기본값 사용
            self.logger.warning(f"제품 {product_code} 박스당 제품 수를 온톨로지에서 찾을 수 없어 기본값 사용")
            return 1  # 기본값 1개/박스
            
        except Exception as e:
            self.logger.error(f"제품 {product_code} 박스당 제품 수 조회 오류: {e}")
            return 1  # 오류 시 기본값
    
    def _get_line_hourly_capacity(self, line_id, product_code):
        """라인별 시간당 생산 능력 반환 (온톨로지 기반)"""
        try:
            # 온톨로지에서 라인 인스턴스 조회
            if hasattr(self, 'ontology_manager') and self.ontology_manager:
                onto = self.ontology_manager.onto
                if hasattr(onto, 'Line'):
                    # 라인 인스턴스 찾기
                    line_instance = None
                    for line_inst in onto.Line.instances():
                        if line_inst.name.replace('line_', '') == line_id:
                            line_instance = line_inst
                            break
                    
                    if line_instance:
                        # 온톨로지에서 CT Rate와 트랙 수 조회
                        ct_rate = 100  # 기본값
                        tracks = 1      # 기본값
                        
                        # LineProductRelation에서 CT Rate 조회 (첫 번째 제품 기준)
                        if hasattr(onto, 'LineProductRelation'):
                            for relation in onto.LineProductRelation.instances():
                                if relation.hasLine and relation.hasLine[0].name.replace('line_', '') == line_id:
                                    if hasattr(relation, 'hasCTRate') and relation.hasCTRate:
                                        ct_rate = relation.hasCTRate[0]
                                        break
                        
                        # Line에서 트랙 수 조회
                        if hasattr(line_instance, 'hasTrackCount') and line_instance.hasTrackCount:
                            tracks = line_instance.hasTrackCount[0]
                        
                        # 제품별 개입수를 고려한 계산으로 수정
                        # 기본값 대신 실제 제품 정보를 조회해야 함
                        products_per_box = self._get_package_count(product_code)  # 제품별 개입수
                        
                        hourly_capacity = (ct_rate * tracks * 60) / products_per_box
                        
                        self.logger.info(f"라인 {line_id} 온톨로지 기반 생산능력: {hourly_capacity:.0f}박스/시간 (CT: {ct_rate}, 트랙: {tracks})")
                        return hourly_capacity
            
            # 온톨로지에서 찾지 못한 경우 기본값 사용
            self.logger.warning(f"라인 {line_id} 생산능력을 온톨로지에서 찾을 수 없어 기본값 사용")
            return 800  # 기본값 800박스/시간
            
        except Exception as e:
            self.logger.error(f"라인 {line_id} 생산능력 계산 오류: {e}")
            return 800  # 오류 시 기본값
    
    def check_line_constraint_conflicts(self, constraint_config, lines):
        """라인별 제약조건 충돌 검사"""
        self.logger.info("🔍 라인별 제약조건 충돌 검사 중...")
        
        constrained_lines = constraint_config.get_all_constrained_lines()
        
        for line in constrained_lines:
            if line not in lines:
                self.add_conflict(
                    "LINE_CONSTRAINT_MISMATCH",
                    f"제약조건이 설정된 라인 {line}이 활성 라인에 없음",
                    "HIGH"
                )
            
            constraints = constraint_config.get_line_constraints(line)
            for constraint in constraints:
                if constraint['type'] == ConstraintTypes.START_PRODUCT:
                    self.add_constraint_stat(
                        f"START_PRODUCT_{line}",
                        "SUCCESS",
                        f"라인 {line} 시작 제품: {constraint['params']['product']}"
                    )
                elif constraint['type'] == ConstraintTypes.LAST_PRODUCT:
                    self.add_constraint_stat(
                        f"LAST_PRODUCT_{line}",
                        "SUCCESS",
                        f"라인 {line} 마지막 제품: {constraint['params']['product']}"
                    )
                elif constraint['type'] == ConstraintTypes.FORBIDDEN_COMBINATION:
                    forbidden_pairs = constraint['params']['forbidden_pairs']
                    self.add_constraint_stat(
                        f"FORBIDDEN_COMBINATION_{line}",
                        "SUCCESS",
                        f"라인 {line} 금지 조합: {len(forbidden_pairs)}개"
                    )
    
    def check_utilization_conflicts(self, target_utilization):
        """활용률 제약 충돌 검사"""
        self.logger.info("🔍 활용률 제약 충돌 검사 중...")
        
        if target_utilization > 0.95:
            self.add_warning(
                "HIGH_UTILIZATION_TARGET",
                f"높은 활용률 목표 ({target_utilization*100:.1f}%) - 실행 가능성 저하 위험"
            )
        
        if target_utilization == 1.0:
            self.add_conflict(
                "PERFECT_UTILIZATION_CONFLICT",
                "100% 활용률 목표는 물리적으로 달성 불가능할 수 있음 (청소시간, 교체시간 고려)",
                "MEDIUM"
            )
    
    def check_weight_conflicts(self, weights):
        """가중치 설정 충돌 검사"""
        self.logger.info("🔍 가중치 설정 충돌 검사 중...")
        
        if weights.get('changeover_time', 0) > 50:
            self.add_warning(
                "HIGH_CHANGEOVER_WEIGHT",
                f"교체시간 가중치가 매우 높음 ({weights['changeover_time']}) - 다른 목표 달성 어려움"
            )
        
        if weights.get('discontinuity', 0) > 500:
            self.add_warning(
                "HIGH_DISCONTINUITY_WEIGHT",
                f"연속성 가중치가 매우 높음 ({weights['discontinuity']}) - 유연성 저하"
            )
    
    def print_summary(self):
        """충돌 및 경고 요약 출력"""
        self.logger.info("=" * 60)
        self.logger.info("📊 제약조건 충돌 모니터링 요약")
        self.logger.info("=" * 60)
        
        # 충돌 요약
        if self.conflicts:
            self.logger.info(f"🚨 충돌 발견: {len(self.conflicts)}개")
            for i, conflict in enumerate(self.conflicts, 1):
                self.logger.info(f"  {i}. [{conflict['severity']}] {conflict['description']} ({conflict['timestamp']})")
        else:
            self.logger.info("✅ 충돌 없음")
        
        # 경고 요약
        if self.warnings:
            self.logger.info(f"⚠️ 경고: {len(self.warnings)}개")
            for i, warning in enumerate(self.warnings, 1):
                self.logger.info(f"  {i}. {warning['description']} ({warning['timestamp']})")
        else:
            self.logger.info("✅ 경고 없음")
        
        # 제약조건 상태 요약
        if self.constraint_stats:
            self.logger.info(f"📋 제약조건 상태: {len(self.constraint_stats)}개")
            for name, stat in self.constraint_stats.items():
                status_icon = "✅" if stat['status'] == "SUCCESS" else "⚠️" if stat['status'] == "WARNING" else "❌"
                self.logger.info(f"  {status_icon} {name}: {stat['details']} ({stat['timestamp']})")
        
        self.logger.info("=" * 60)
        
        # 권장사항
        if self.conflicts:
            self.logger.info("💡 권장사항:")
            if any(c['severity'] == 'CRITICAL' for c in self.conflicts):
                self.logger.info("  - CRITICAL 충돌이 발견되었습니다. 최적화 실행을 중단하고 제약조건을 검토하세요.")
            if any(c['severity'] == 'HIGH' for c in self.conflicts):
                self.logger.info("  - HIGH 충돌이 발견되었습니다. 최적화 실행 전에 제약조건을 조정하는 것을 권장합니다.")
            if any(c['type'] == 'PRODUCTION_TIME_CONFLICT' for c in self.conflicts):
                self.logger.info("  - 생산량 목표를 시간 제약에 맞게 조정하거나 시간대를 추가하세요.")
            if any(c['type'] == 'LINE_CONSTRAINT_MISMATCH' for c in self.conflicts):
                self.logger.info("  - 제약조건이 설정된 라인이 활성 라인 목록에 포함되어 있는지 확인하세요.")
        
        return len(self.conflicts) == 0

def setup_logging():
    """로깅 설정"""
    # 로그 폴더 생성
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/optimization_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        ]
    )
    return logging.getLogger(__name__)

def main():
    """메인 실행 함수"""
    logger = setup_logging()
    
    logger.info("🚀 v6 생산 최적화 시스템 시작 (제약조건 충돌 모니터링 포함)")
    
    # 제약조건 충돌 모니터 초기화
    conflict_monitor = ConstraintConflictMonitor(logger)
    
    # 전체 프로세스 시작 시간 기록
    total_start_time = time.time()
    
    try:
        # 1. 온톨로지 매니저 초기화
        logger.info("=== 1단계: 온톨로지 매니저 초기화 ===")
        ontology_start_time = time.time()
        
        # 현재 날짜 기준으로 월요일 계산
        from datetime import datetime, timedelta
        current_date = datetime.now().date()
        if current_date.weekday() != 0:  # 0 = 월요일
            days_until_monday = (7 - current_date.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            start_date = current_date + timedelta(days=days_until_monday)
        else:
            start_date = current_date
        
        logger.info(f"📅 시작일: {start_date.strftime('%Y-%m-%d')} (월요일)")
        
        # OntologyManager 초기화
        onto = get_ontology("http://test.org/factory.owl")
        ontology_manager = OntologyManager(onto, monday_date=start_date.strftime('%Y-%m-%d'))
        
        # 사용할 라인 미리 설정 (온톨로지 빌드 시 전달)
        selected_lines = ['13', '16']
        
        # 온톨로지 빌드 (실제 metadata 파일 사용)
        logger.info("📁 실제 데이터 파일 로딩 중...")
        logger.info("  - ../metadata/products.json")
        logger.info("  - ../metadata/lines.json") 
        logger.info("  - ../metadata/change_over.json")
        logger.info("  - ../metadata/order.csv")
        
        results = ontology_manager.build(
            products_path='../metadata/products.json',
            lines_path='../metadata/lines.json',
            changeover_path='../metadata/change_over.json',
            order_path='../metadata/order.csv',
            start_date_str=start_date.strftime('%Y-%m-%d'),
            active_lines=selected_lines  # 활성화된 라인만 전달
        )
        
        # 데이터 구조 확인 로깅 추가
        logger.info("🔍 데이터 구조 확인:")
        if hasattr(ontology_manager, '_changeover_data') and ontology_manager._changeover_data:
            logger.info(f"  - _changeover_data 키: {list(ontology_manager._changeover_data.keys())}")
            if 'changeover' in ontology_manager._changeover_data:
                if 'changeover_rules' in ontology_manager._changeover_data['changeover']:
                    changeover_lines = list(ontology_manager._changeover_data['changeover']['changeover_rules'].keys())
                    logger.info(f"  - changeover_rules 라인: {changeover_lines}")
                else:
                    logger.warning("  - changeover_rules 키를 찾을 수 없음")
            else:
                logger.warning("  - changeover 키를 찾을 수 없음")
        else:
            logger.warning("  - _changeover_data가 None이거나 비어있음")
        
        logger.info(f"✅ 온톨로지 빌드 완료!")
        logger.info(f"  - 라인: {len(results['lines'])}개")
        logger.info(f"  - 제품: {len(results['products'])}개")
        
        ontology_end_time = time.time()
        ontology_elapsed = ontology_end_time - ontology_start_time
        logger.info(f"⏱️ 온톨로지 초기화 소요 시간: {ontology_elapsed:.2f}초")
        
        # 2. 호기별 제약조건 설정 (선택사항)
        logger.info("=== 2단계: 호기별 제약조건 설정 ===")
        constraint_config = LineConstraintConfig()
        
        # 제약조건 추가 (원래 상태로 주석 처리)
        constraint_config.add_line_constraint(
            line_id='13',
            constraint_type=ConstraintTypes.LAST_PRODUCT,
            product='101005023'
        )

        constraint_config.add_line_constraint(
            line_id='16',
            constraint_type=ConstraintTypes.LAST_PRODUCT,
            product='101003558'
        )
    
        
        # 3. 최적화 모델 구축
        logger.info("=== 3단계: 최적화 모델 구축 ===")
        model_start_time = time.time()
        
        # 사용 가능한 라인 중에서 선택 (선택사항)
        available_lines = list(results['lines'].keys())
        
        logger.info(f"선택된 라인: {selected_lines}")
        
        # 제약조건 충돌 사전 검사 (활성화된 라인만)
        logger.info("=== 2.5단계: 제약조건 충돌 사전 검사 ===")
        
        # ConstraintConflictMonitor에 온톨로지 매니저 설정
        conflict_monitor.ontology_manager = ontology_manager
        
        # 온톨로지 매니저에서 order_data와 time_slots 가져오기
        order_data = ontology_manager._order_data
        time_slots = [f"T{i+1}" for i in range(5)]  # 5일치 시간대
        
        # 생산량 vs 시간 제약 충돌 검사 (활성화된 라인만)
        conflict_monitor.check_production_vs_time_conflict(
            order_data, 
            selected_lines,  # 모든 라인이 아닌 선택된 라인만
            time_slots
        )
        
        # 라인별 제약조건 충돌 검사 (활성화된 라인만)
        conflict_monitor.check_line_constraint_conflicts(
            constraint_config, 
            selected_lines  # 모든 라인이 아닌 선택된 라인만
        )
        
        optimizer = ProductionOptimizer(ontology_manager, selected_lines, logger=logger)
        
        # 가동시간 목표 활용률 설정 (원래 설정)
        target_utilization = 0.95  # 95% 활용률 (원래 설정)
        optimizer.set_utilization_target(target_utilization)
        
        # 활용률 제약 충돌 검사
        conflict_monitor.check_utilization_conflicts(target_utilization)
        
        # 가중치 설정 (원래 설정으로 복원)
        weights = {
            'production_time': 1.0,      # 총 생산시간 최대화 (음수 가중치로 최대화)
            'changeover_time': 5.0,      # 총 교체시간 최소화 (원래 설정)
            'changeover_count': 20.0,    # 교체 횟수 페널티 (원래 설정)
            'discontinuity': 200.0,      # 연속성 위반 페널티 (원래 설정)
            'capacity_violation': 1.0,   # 용량 위반 페널티
            'priority_violation': 15.0   # 우선순위 위반 페널티
        }
        optimizer.weights.update(weights)
        
        # 가중치 설정 충돌 검사
        conflict_monitor.check_weight_conflicts(weights)
        
        # 호기별 제약조건 설정
        optimizer.set_line_constraints(constraint_config)
        
        optimizer.build_model()
        
        model_end_time = time.time()
        model_elapsed = model_end_time - model_start_time
        logger.info(f"⏱️ 모델 구축 소요 시간: {model_elapsed:.2f}초")
        
        # 제약조건 충돌 요약 출력
        logger.info("=== 3.5단계: 제약조건 충돌 요약 ===")
        constraints_safe = conflict_monitor.print_summary()
        
        if not constraints_safe:
            logger.warning("⚠️ 제약조건 충돌이 발견되었습니다. 최적화 실행을 계속하시겠습니까?")
            # 실제 운영에서는 사용자 입력을 받거나 자동으로 중단할 수 있음
            # 여기서는 경고만 출력하고 계속 진행
        
        # 4. 최적화 실행
        logger.info("=== 4단계: 최적화 실행 ===")
        solve_start_time = time.time()
        
        success = optimizer.solve()
        
        solve_end_time = time.time()
        solve_elapsed = solve_end_time - solve_start_time
        logger.info(f"⏱️ 최적화 실행 소요 시간: {solve_elapsed:.2f}초")
        
        # 5. 결과 추출 및 처리 (v5 파일 분리 구조 사용)
        if success:
            logger.info("=== 5단계: 결과 추출 및 처리 (파일 분리 구조) ===")
            result_start_time = time.time()
            
            # 최적화 결과 추출
            solution = optimizer.extract_solution()
            
            # 결과 처리기 생성 (v5 새로운 구조)
            logger.info("🔄 결과 처리기 생성 중...")
            result_processor = optimizer.create_result_processor()
            logger.info("✅ 결과 처리기 생성 완료!")
            
            # 결과 출력 (결과 처리기 사용)
            logger.info("📊 최적화 결과 출력 중...")
            result_processor.print_solution(solution)
            
            # 결과 저장 디렉토리 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_dir = os.path.join("results", timestamp)
            os.makedirs(results_dir, exist_ok=True)
            
            # Excel 파일로 저장 (결과 처리기 사용)
            logger.info("📊 Excel 파일 생성 중...")
            excel_output_path = os.path.join(results_dir, f"production_schedule_{timestamp}.xlsx")
            result_processor.export_to_excel(solution, excel_output_path)
            
            # JSON 파일로 저장 (결과 처리기 사용)
            logger.info("📄 JSON 파일 생성 중...")
            json_output_path = os.path.join(results_dir, f"production_schedule_detail_{timestamp}.json")
            result_processor.export_to_json(solution, json_output_path)
            
            # Optimizer 정보를 JSON으로 저장 (새로 추가)
            logger.info("🔍 Optimizer 정보 JSON 파일 생성 중...")
            optimizer_info_path = os.path.join(results_dir, f"optimizer_info_{timestamp}.json")
            result_processor.export_optimizer_info(optimizer_info_path)
            
            logger.info(f"📊 Excel 파일 생성: {excel_output_path}")
            logger.info(f"📄 JSON 파일 생성: {json_output_path}")
            logger.info(f"🔍 Optimizer 정보 JSON 생성: {optimizer_info_path}")
            
            result_end_time = time.time()
            result_elapsed = result_end_time - result_start_time
            logger.info(f"⏱️ 결과 처리 소요 시간: {result_elapsed:.2f}초")
            
            logger.info(f"✅ 최적화 완료! (v5 파일 분리 구조)")
            logger.info(f"   📊 Excel 파일: {excel_output_path}")
            logger.info(f"   📄 JSON 파일: {json_output_path}")
            logger.info(f"   🔍 Optimizer 정보 JSON: {optimizer_info_path}")
            logger.info(f"   🔄 결과 처리기: ProductionResultProcessor 사용")
        else:
            logger.error("❌ 최적화 실패")
            
            # 최적화 실패 시 제약조건 충돌 재검토
            logger.info("🔍 최적화 실패 원인 분석 중...")
            if conflict_monitor.conflicts:
                logger.error("💡 최적화 실패의 주요 원인은 제약조건 충돌일 수 있습니다.")
                logger.error("   - 제약조건을 완화하거나 조정해보세요.")
                logger.error("   - 생산량 목표를 시간 제약에 맞게 조정해보세요.")
                logger.error("   - 라인별 특정 제약을 소프트 제약으로 변경해보세요.")
        
        # 전체 소요 시간 계산
        total_end_time = time.time()
        total_elapsed = total_end_time - total_start_time
        
        # 소요 시간을 분과 초로 변환
        total_minutes = int(total_elapsed // 60)
        total_seconds = int(total_elapsed % 60)
        
        logger.info("=" * 50)
        logger.info("📊 전체 프로세스 소요 시간 요약")
        logger.info(f"⏱️ 온톨로지 초기화: {ontology_elapsed:.2f}초")
        logger.info(f"⏱️ 모델 구축: {model_elapsed:.2f}초")
        logger.info(f"⏱️ 최적화 실행: {solve_elapsed:.2f}초")
        if success:
            logger.info(f"⏱️ 결과 처리: {result_elapsed:.2f}초")
        logger.info(f"⏱️ 전체 소요 시간: {total_minutes}분 {total_seconds}초 ({total_elapsed:.2f}초)")
        logger.info("=" * 50)
        
        # 최종 제약조건 충돌 요약
        logger.info("🔍 최종 제약조건 충돌 상태:")
        if constraints_safe:
            logger.info("✅ 모든 제약조건이 안전하게 설정되었습니다.")
        else:
            logger.info("⚠️ 일부 제약조건 충돌이 발견되었습니다. 결과를 주의 깊게 검토하세요.")
        
        # v5 파일 분리 구조 정보 출력
        if success:
            logger.info("🏗️ v5 파일 분리 구조 정보:")
            logger.info("  - production_optimizer.py: 최적화 실행 담당")
            logger.info("  - production_result_processor.py: 결과 처리 담당")
            logger.info("  - 두 파일이 create_result_processor()로 연결됨")
        
    except Exception as e:
        logger.error(f"❌ 시스템 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        
        # 오류 발생 시에도 전체 소요 시간 기록
        total_end_time = time.time()
        total_elapsed = total_end_time - total_start_time
        total_minutes = int(total_elapsed // 60)
        total_seconds = int(total_elapsed % 60)
        logger.info(f"⏱️ 전체 소요 시간: {total_minutes}분 {total_seconds}초 ({total_elapsed:.2f}초)")

if __name__ == "__main__":
    main()

    