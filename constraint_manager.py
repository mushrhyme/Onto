from pulp import lpSum, LpVariable
from constraint_types import ConstraintTypes

class ConstraintManager:
    def __init__(self, optimizer):
        self.optimizer = optimizer
        self.model = optimizer.model
        self.variables = optimizer.variables
        self.logger = optimizer.logger
        self.products = optimizer.products
        self.lines = optimizer.lines
        self.time_slots = optimizer.ontology_timeslots
        self.line_constraints = optimizer.line_constraints
        self.valid_product_line_combinations = optimizer.valid_product_line_combinations
        self.order_data = optimizer.order_data
        self._get_product_name = optimizer._get_product_name
        self._get_capacity_rate = optimizer._get_capacity_rate
        self._get_track_count = optimizer._get_track_count
        self._get_package_count = optimizer._get_package_count
        self._get_changeover_time = optimizer._get_changeover_time
        self._get_setup_time = optimizer._get_setup_time
        self._get_cleanup_time = optimizer._get_cleanup_time
        self._get_max_working_hours = optimizer._get_max_working_hours
        self.MAX_POSITIONS = optimizer.MAX_POSITIONS  # 시간대 내 최대 생산 제품 수

    def add_all_constraints(self):
        """모든 제약조건을 순차적으로 추가"""
        self.logger.info("=== ConstraintManager: 모든 제약조건 추가 시작 ===")
        
        self._add_production_constraints()
        
        self._add_changeover_count_constraints()
        self._add_setup_and_cleaning_constraints()
        self._add_improved_constraints()
        self._add_time_constraints()
        self._add_block_continuity()
        self._add_multi_product_in_slot()
        self._add_total_changeover_limit()
        self._add_line_specific_constraints()
        self.add_time_unit_normalization_constraints()  # 시간 단위 정규화 추가
        
        # 모든 제약조건 추가 완료 후 시간 제약조건 검증
        self._verify_time_constraints()
        
        self.logger.info("=== ConstraintManager: 모든 제약조건 추가 완료 ===")

    def _add_production_constraints(self):
        """
        생산량 제약조건 추가 (유효한 제품-라인 조합만) - 박스 단위
        """
        self.logger.info("생산량 제약조건 추가 중... (박스 단위)")
        
        for product in self.products:
            total_production_boxes = 0
            has_valid_combinations = False
            
            for line in self.lines:
                if (product, line) in self.valid_product_line_combinations:
                    has_valid_combinations = True
                    for time_slot in self.time_slots:
                        capacity_rate = self._get_capacity_rate(product, line)
                        track_count = self._get_track_count(line)
                        production_quantity_units = (self.variables['production_time'][product, line, time_slot] * 
                                                    capacity_rate * track_count * 60)
                        products_per_box = self._get_package_count(product)
                        if products_per_box > 0:
                            production_quantity_boxes = production_quantity_units / products_per_box
                        else:
                            production_quantity_boxes = 0
                        total_production_boxes += production_quantity_boxes
            
            if has_valid_combinations:
                target_boxes = self.order_data[product]
                min_boxes = target_boxes * 1
                max_boxes = target_boxes * 1
                constraint_min = total_production_boxes >= min_boxes
                self.model += constraint_min, f"production_quantity_min_{product}"
                constraint_max = total_production_boxes <= max_boxes
                self.model += constraint_max, f"production_quantity_max_{product}"
                self.logger.info(f"제품 {product} 생산량 제약 완화: {min_boxes:.0f}~{max_boxes:.0f}박스 (목표: {target_boxes:.0f}박스)")
            else:
                self.logger.warning(f"제품 {product}에 대한 유효한 라인이 없습니다. 제약조건을 건너뜁니다.")
        
        self.logger.info(f"생산량 제약조건 추가 완료: {len(self.products)}개 (박스 단위)")
    
    def _add_time_constraints(self):
        self.logger.info("시간 제약조건 추가 중...")
        
        for line in self.lines:
            for time_slot in self.time_slots:
                max_hours = self._get_max_working_hours(time_slot)
                self.logger.debug(f"라인 {line}, {time_slot}: 최대 가동시간 = {max_hours}시간")
                
                # 총 시간 계산: 생산시간 + 교체시간 + 청소시간
                production_time_sum = lpSum([
                    self.variables['production_time'][product, line, time_slot]
                    for product in self.products 
                    if (product, line) in self.valid_product_line_combinations
                ])
                
                # 하드 제약은 add_time_unit_normalization_constraints에서 처리하므로 여기서는 제거
                # (중복 제약 방지)
                
                # 디버깅을 위한 출력 (제약조건이 제대로 설정되었는지 확인)
                self.logger.debug(f"⏰ 시간 제약은 add_time_unit_normalization_constraints에서 처리됨")
                
                # 최소 이용률을 소프트 제약조건으로 변경
                total_time_expr = (production_time_sum + 
                                  self.variables['changeover_time'][line, time_slot] + 
                                  self.variables['cleaning_time'][line, time_slot])
                self._add_soft_utilization_constraint(line, time_slot, total_time_expr, max_hours)
                
                # 동적 활용률 제약 추가 (사용자 설정 활용률 목표)
                target_rate = getattr(self.optimizer, 'target_utilization_rate')
                self.add_dynamic_utilization_constraint(line, time_slot, total_time_expr, max_hours, target_rate=target_rate)
        
        # 시간 제약은 add_all_constraints에서 add_time_unit_normalization_constraints를 통해 처리됨
        # (중복 호출 방지)
        
        self.logger.debug(f"시간 제약조건 추가 완료: {len(self.lines) * len(self.time_slots)}개")
        
        # 시간 제약조건 검증은 add_time_unit_normalization_constraints 이후에 수행
        # (중복 호출 방지)
    
    def _verify_time_constraints(self):
        """시간 제약조건이 실제로 모델에 추가되었는지 검증"""
        self.logger.info("🔍 시간 제약조건 검증 시작...")
        
        time_constraints_found = 0
        for line in self.lines:
            for time_slot in self.time_slots:
                constraint_name = f"total_time_slot_limit_{line}_{time_slot}"
                if constraint_name in self.model.constraints:
                    time_constraints_found += 1
                    self.logger.info(f"✅ {constraint_name}: 모델에 존재")
                else:
                    self.logger.error(f"❌ {constraint_name}: 모델에 없음!")
                    # 디버깅을 위한 추가 정보
                    self.logger.error(f"   → 라인: {line}, 시간대: {time_slot}")
                    self.logger.error(f"   → 사용 가능한 제약조건: {[name for name in self.model.constraints.keys() if 'total_time_slot_limit' in name]}")
        
        self.logger.info(f"🔍 시간 제약조건 검증 완료: {time_constraints_found}/{len(self.lines) * len(self.time_slots)}개 발견")
    
    def verify_time_constraint_violations(self, optimizer):
        """최적화 후 시간 제약조건 위반 여부 검증"""
        self.logger.info("🔍 시간 제약조건 위반 검증 시작...")
        
        violations_found = 0
        for line in self.lines:
            for time_slot in self.time_slots:
                max_hours = self._get_max_working_hours(time_slot)
                
                # 실제 생산시간 계산
                production_time = sum(
                    optimizer.variables['production_time'][product, line, time_slot].value()
                    for product in optimizer.products 
                    if (product, line) in optimizer.valid_product_line_combinations
                    and optimizer.variables['production_time'][product, line, time_slot].value() is not None
                )
                
                # 실제 교체시간
                changeover_time = optimizer.variables['changeover_time'][line, time_slot].value() or 0
                
                # 실제 청소시간
                cleaning_time = optimizer.variables['cleaning_time'][line, time_slot].value() or 0
                
                # 총 시간
                total_time = production_time + changeover_time + cleaning_time
                
                # 위반 여부 확인
                if total_time > max_hours:
                    violations_found += 1
                    self.logger.error(f"❌ 시간 제약 위반: {line} {time_slot}")
                    self.logger.error(f"   - 생산시간: {production_time:.1f}h")
                    self.logger.error(f"   - 교체시간: {changeover_time:.1f}h")
                    self.logger.error(f"   - 청소시간: {cleaning_time:.1f}h")
                    self.logger.error(f"   - 총 시간: {total_time:.1f}h > {max_hours:.1f}h (제한)")
                    self.logger.error(f"   - 초과: {total_time - max_hours:.1f}h")
                else:
                    self.logger.info(f"✅ 시간 제약 준수: {line} {time_slot} = {total_time:.1f}h <= {max_hours:.1f}h")
        
        if violations_found > 0:
            self.logger.error(f"🚨 시간 제약 위반 발견: {violations_found}개 시간대")
        else:
            self.logger.info(f"✅ 모든 시간 제약조건 준수")
        
        return violations_found
        
    def _add_block_continuity(self):
        """
        블록 단위 연속성 제약조건 추가
        제품별 목표 생산량과 라인별 생산 능력을 바탕으로 필요한 시간대 개수를 계산하고,
        이를 연속된 블록으로 배치하는 제약조건
        """
        self.logger.info("블록 단위 연속성 제약 추가 중...")
        
        # block_start 변수가 있는지 확인
        if 'block_start' not in self.variables:
            self.logger.error("❌ block_start 변수가 optimizer.variables에 없습니다!")
            self.logger.error(f"사용 가능한 변수: {list(self.variables.keys())}")
            return
        
        block_constraints_added = 0
        
        for product, line in self.valid_product_line_combinations:
            # 필요한 시간대 개수 계산
            required_slots = self.optimizer._calculate_required_time_slots(product, line)
            
            if required_slots <= 0:
                self.logger.warning(f"제품 {product}, 라인 {line}: 필요 시간대 0, 제약 추가 생략")
                continue
            
            # block_start 변수가 해당 제품-라인 조합에 대해 존재하는지 확인
            if (product, line) not in self.variables['block_start']:
                self.logger.warning(f"제품 {product}, 라인 {line}: block_start 변수가 없음, 제약 추가 생략")
                continue
            
            # 블록 연속성 제약: 블록이 시작되면 required_slots만큼 연속 생산
            for start in range(len(self.time_slots) - required_slots + 1):
                block_start_var = self.variables['block_start'][product, line][start]
                
                # 블록 시작점부터 required_slots만큼 연속으로 생산해야 함
                for k in range(start, start + required_slots):
                    if k < len(self.time_slots):
                        time_slot = self.time_slots[k]
                        production_var = self.variables['production'][product, line, time_slot]
                        
                        # block_start가 1이면 해당 시간대에서 생산해야 함
                        self.model += (
                            production_var >= block_start_var,
                            f"block_continuity_{product}_{line}_{start}_{k}"
                        )
                        block_constraints_added += 1
            
            # 각 제품-라인 조합에 대해 정확히 하나의 블록만 시작
            block_start_vars = [
                self.variables['block_start'][product, line][start] 
                for start in range(len(self.time_slots) - required_slots + 1)
            ]
            
            if block_start_vars:  # 변수가 있는 경우에만 제약 추가
                self.model += (
                    lpSum(block_start_vars) == 1,
                    f"block_start_unique_{product}_{line}"
                )
                block_constraints_added += 1
                
                self.logger.debug(f"제품 {product}, 라인 {line}: {required_slots}개 시간대 블록 제약 추가")
        
        self.logger.info(f"블록 단위 연속성 제약 추가 완료: {block_constraints_added}개 제약조건")

    def _add_multi_product_in_slot(self):
        """
        시간대 내 다중 제품 허용 제약조건 추가
        소량 생산 기준: 목표 생산량을 달성하는데 필요한 시간이 해당 시간대의 최대 가동시간 미만인 제품
        (수요일: 8시간, 그 외: 10.5시간)
        """
        self.logger.info("시간대 내 다중 제품 제약 추가 중... (생산시간 기반 판단)")
        
        constraints_added = 0
        
        for line in self.lines:
            for time_slot in self.time_slots:
                # 해당 시간대의 최대 가동시간
                max_hours = self._get_max_working_hours(time_slot)
                
                # 소량 생산 제품들 식별 (생산시간 기반)
                small_production_products = []
                
                for p in self.products:
                    if (p, line) in self.valid_product_line_combinations:
                        # 목표 생산량 달성에 필요한 시간 계산
                        target_boxes = self.order_data.get(p, 0)
                        if target_boxes <= 0:
                            continue
                        
                        # 시간당 박스 생산량 계산
                        capacity_rate = self._get_capacity_rate(p, line)  # 분당 생산 개수
                        track_count = self._get_track_count(line)  # 트랙 수
                        products_per_box = self._get_package_count(p)  # 개입수
                        
                        if capacity_rate > 0 and products_per_box > 0:
                            # 시간당 박스 생산량 = (분당 개수 * 트랙 수 * 60분) / 개입수
                            boxes_per_hour = (capacity_rate * track_count * 60) / products_per_box
                            
                            # 목표 달성에 필요한 시간 = 목표 박스 / 시간당 박스 생산량
                            required_hours = target_boxes / boxes_per_hour
                            
                            # 소량 생산 판단: 필요 시간 < 해당 시간대 최대 가동시간
                            if required_hours < max_hours:
                                small_production_products.append(p)
                                self.logger.debug(f"제품 {p}: 목표 {target_boxes}박스, 필요시간 {required_hours:.1f}h < 최대시간 {max_hours}h → 소량생산")
                            else:
                                self.logger.debug(f"제품 {p}: 목표 {target_boxes}박스, 필요시간 {required_hours:.1f}h ≥ 최대시간 {max_hours}h → 대량생산")
                
                if small_production_products:  # 소량 생산 제품이 있는 경우만 제약 추가
                    multi_product_allowed = lpSum(
                        self.variables['production'][p, line, time_slot] 
                        for p in small_production_products
                    )
                    self.model += (
                        multi_product_allowed <= 3, 
                        f"multi_product_{line}_{time_slot}"
                    )
                    constraints_added += 1
                    
                    self.logger.debug(f"라인 {line}, {time_slot} (최대 {max_hours}h): {len(small_production_products)}개 소량 생산 제품")
        
        self.logger.info(f"시간대 내 다중 제품 제약 추가 완료: {constraints_added}개 제약조건 (생산시간 기반)")

    def _add_changeover_count_constraints(self):
        self.logger.info("교체 횟수 제약조건 추가 중...")
        
        for line in self.lines:
            for time_slot_idx, time_slot in enumerate(self.time_slots):
                changeover_count_var = self.variables['changeover_count'][line, time_slot]
                changeover_time_var = self.variables['changeover_time'][line, time_slot]
                
                changeover_sum = lpSum(
                    self.variables['changeover'][p1, p2, line, time_slot]
                    for p1, line1 in self.valid_product_line_combinations
                    for p2, line2 in self.valid_product_line_combinations
                    if line1 == line2 == line and p1 != p2
                )

                self.model += (
                    changeover_count_var >= changeover_sum
                ), f"changeover_count_min_{line}_{time_slot}"
                self.model += (
                    changeover_count_var <= changeover_sum
                ), f"changeover_count_max_{line}_{time_slot}"
            
        self.logger.info("교체 횟수 제약조건 추가 완료")

    def _add_total_changeover_limit(self, max_changeovers=5):
        """
        총 교체 횟수 하드 제약 추가
        전체 교체 횟수를 최대 max_changeovers회로 제한
        """
        self.logger.info(f"총 교체 횟수 제한 제약 추가: 최대 {max_changeovers}회")
        
        total_changeover = lpSum(
            self.variables['changeover_count'][j, k] 
            for j in self.lines 
            for k in self.time_slots
        )
        
        # 고유한 제약조건 이름 생성 (최대값과 라인 정보 포함)
        constraint_name = f"total_changeover_limit_max{max_changeovers}_lines{len(self.lines)}"
        
        self.model += (
            total_changeover <= max_changeovers, 
            constraint_name
        )
        
        self.logger.info(f"총 교체 횟수 제한 제약 추가 완료: {constraint_name}")
        self.logger.debug(f"제약 대상 라인: {', '.join(self.lines)}")
        self.logger.debug(f"제약 대상 시간대: {len(self.time_slots)}개")
    
    def _add_setup_and_cleaning_constraints(self):
        self.logger.info("작업 준비 시간과 청소 시간 제약조건 추가 중...")
        
        for line in self.lines:
            first_time_slot = self.time_slots[0]
            setup_time = self._get_setup_time(line)
            self.model += (
                self.variables['cleaning_time'][line, first_time_slot] == setup_time,
                f"setup_time_{line}"
            )
            
            last_time_slot = self.time_slots[-1]
            cleanup_time = self._get_cleanup_time(line)
            self.model += (
                self.variables['cleaning_time'][line, last_time_slot] == cleanup_time,
                f"cleaning_time_{line}"
            )
            
            for time_slot_idx, time_slot in enumerate(self.time_slots):
                if time_slot_idx > 0 and time_slot_idx < len(self.time_slots) - 1:
                    self.model += (
                        self.variables['cleaning_time'][line, time_slot] == 0,
                        f"no_cleaning_middle_{line}_{time_slot}"
                    )
        
        self.logger.info("작업 준비 시간과 청소 시간 제약조건 추가 완료")
    
    def _add_soft_utilization_constraint(self, line, time_slot, total_time, max_hours):
        """
        소프트 제약조건으로 가동시간 활용률 관리
        - 고정 시간(교체시간, 청소시간)을 제외한 나머지 시간을 생산시간으로 최대한 활용
        - 100% 활용 시도 시에도 실행 가능한 해 보장
        """
        from pulp import LpVariable
        
        # 고정 시간 요소들 계산
        fixed_time = self.variables['changeover_time'][line, time_slot] + self.variables['cleaning_time'][line, time_slot]
        
        # 생산 가능한 시간 = 전체 시간 - 고정 시간
        available_production_time = max_hours - fixed_time
        
        # 실제 생산시간
        actual_production_time = lpSum(
            self.variables['production_time'][product, line, time_slot]
            for product in self.products 
            if (product, line) in self.valid_product_line_combinations
        )
        
        # 생산시간 활용률 부족분을 나타내는 슬랙 변수 생성
        production_underutilization_slack = LpVariable(
            f"production_underutil_slack_{line}_{time_slot}",
            lowBound=0
        )
        
        # 소프트 제약조건: 실제 생산시간 + 슬랙 >= 사용 가능한 생산시간
        self.model += (
            actual_production_time + production_underutilization_slack >= available_production_time,
            f"soft_production_utilization_{line}_{time_slot}"
        )
        
        # 슬랙 변수를 목적함수에 페널티로 추가
        if not hasattr(self, 'production_underutilization_penalties'):
            self.production_underutilization_penalties = []
        
        self.production_underutilization_penalties.append(production_underutilization_slack)
        
        self.logger.debug(f"생산시간 활용률 소프트 제약 추가: {line}_{time_slot} (생산 가능 시간 최대 활용)")
    
    def add_time_unit_normalization_constraints(self):
        """
        최대 가동시간 활용 제약조건 추가
        - 0.5시간 단위 정규화 제약 제거
        - 생산 시간이 max_hours 이하로 제한되도록 유지
        - 슬랙 변수를 사용하여 최대 가동시간을 최대한 활용하도록 소프트 제약 추가
        - 예시 출력: 총 30시간 → 10.5h + 10.5h + 9.0h처럼 할당
        """
        self.logger.info("최대 가동시간 활용 제약 추가 중 (0.5시간 정규화 제거)...")
        
        if not hasattr(self, 'time_normalization_penalties'):
            self.time_normalization_penalties = []
        
        for product, line in self.valid_product_line_combinations:
            for time_slot in self.time_slots:
                production_time = self.variables['production_time'][product, line, time_slot]
                production_decision = self.variables['production'][product, line, time_slot]
                max_hours = self._get_max_working_hours(time_slot)
                
                # 생산 시간은 최대 가동시간에서 changeover_time, setup_time, cleanup_time을 뺀 값 이하
                # setup_time: 첫 번째 시간대(월요일 조간)에만 설정, cleanup_time: 마지막 시간대(금요일 야간)에만 설정
                # cleaning_time 변수에 setup_time과 cleanup_time이 저장되어 있음
                setup_time = self.variables['cleaning_time'][line, time_slot] if time_slot == self.time_slots[0] else 0
                cleanup_time = self.variables['cleaning_time'][line, time_slot] if time_slot == self.time_slots[-1] else 0
                changeover_time = self.variables['changeover_time'][line, time_slot]
                
                # 실제 생산에 사용 가능한 시간 = 최대가동시간 - (교체시간 + 준비시간 + 청소시간)
                # PuLP에서는 변수와 변수를 곱할 수 없으므로, production_decision이 1일 때만 제약 적용
                # production_decision이 0일 때는 production_time도 0이 되어야 함
                
                # 1. production_decision이 0일 때 production_time도 0이어야 함
                # 이 제약은 전체 시간 제약에서 자연스럽게 처리되므로 제거
                
                # 2. production_decision이 1일 때는 setup_time, cleanup_time, changeover_time을 고려한 제약
                # 이는 별도의 총 시간 제약에서 처리됨 (이미 _add_time_constraints에서 구현됨)
                
                # 최소 생산 시간 (유연성을 위해 0으로 설정 가능)
                MIN_PRODUCTION_TIME = 1
                self.model += (
                    production_time >= MIN_PRODUCTION_TIME * production_decision,
                    f"min_time_{product}_{line}_{time_slot}"
                )
                
                # 기존 생산시간 제약은 유지 (제품별)
                pass
                
                # 최대 가동시간 활용을 위한 소프트 제약
                slack = LpVariable(f"time_slack_{product}_{line}_{time_slot}", lowBound=0)
                self.model += (
                    production_time + slack >= max_hours * production_decision,
                    f"max_utilization_{product}_{line}_{time_slot}"
                )
                self.time_normalization_penalties.append(slack)
        
        self.logger.info("최대 가동시간 활용 제약 추가 완료")
        
        # === 시간대별 총 시간 제약 추가 ===
        self.logger.info("시간대별 총 시간 제약 추가 중...")
        for line in self.lines:
            for time_slot in self.time_slots:
                max_hours = self._get_max_working_hours(time_slot)
                
                # 해당 호기의 해당 시간대 모든 생산시간 합계
                total_production_time = lpSum([
                    self.variables['production_time'][product, line_product, time_slot]
                    for product, line_product in self.valid_product_line_combinations
                    if line_product == line  # 해당 호기만
                ])
                
                # 해당 호기의 해당 시간대 교체시간
                changeover_time = self.variables['changeover_time'][line, time_slot]
                
                # 해당 호기의 해당 시간대 setup_time과 cleanup_time
                setup_time = self.variables['cleaning_time'][line, time_slot] if time_slot == self.time_slots[0] else 0
                cleanup_time = self.variables['cleaning_time'][line, time_slot] if time_slot == self.time_slots[-1] else 0
                
                # 총 시간이 최대 가동시간을 넘지 않도록 제약 (생산 + 교체 + 준비 + 청소)
                self.model += (
                    total_production_time + changeover_time + setup_time + cleanup_time <= max_hours,
                    f"total_time_slot_limit_{line}_{time_slot}"
                )
                
                self.logger.debug(f"시간대별 제약 추가: {line} {time_slot} <= {max_hours}h")
                
        self.logger.info("시간대별 총 시간 제약 추가 완료")
    
    def add_dynamic_utilization_constraint(self, line, time_slot, total_time, max_hours, target_rate=0.99):
        """
        동적 활용률 제약조건 - 실행 가능성을 보장하면서 최대한 활용
        
        Args:
            line: 라인 ID
            time_slot: 시간대
            total_time: 총 시간 (생산+교체+청소)
            max_hours: 최대 가동시간
            target_rate: 목표 활용률 (기본값: 99%)
        """
        from pulp import LpVariable
        
        # 동적 목표 활용률 - 고정 시간을 고려한 실제 달성 가능한 목표
        estimated_fixed_time = 2.5 + 0.6  # 청소시간 + 예상 교체시간
        available_time = max_hours - estimated_fixed_time
        
        if available_time > 0:
            # 사용 가능한 시간이 있을 때만 활용률 목표 설정
            target_utilization = max_hours * target_rate
            
            # 유연한 활용률 슬랙 변수
            utilization_slack = LpVariable(
                f"dynamic_util_slack_{line}_{time_slot}",
                lowBound=0
            )
            
            # 소프트 제약조건: 목표에 가까운 활용률 달성
            self.model += (
                total_time + utilization_slack >= target_utilization,
                f"dynamic_utilization_{line}_{time_slot}"
            )
            
            # 페널티 추가
            if not hasattr(self, 'dynamic_utilization_penalties'):
                self.dynamic_utilization_penalties = []
            
            self.dynamic_utilization_penalties.append(utilization_slack)
            
            self.logger.debug(f"동적 활용률 제약 추가: {line}_{time_slot} (목표: {target_rate*100:.1f}%, {target_utilization:.1f}시간)")
        else:
            self.logger.warning(f"라인 {line}, {time_slot}: 고정 시간이 너무 커서 동적 활용률 제약 건너뜀")
    
    def _add_improved_constraints(self):
        """정확한 교체 감지 및 제약 추가"""
        self.logger.info("정확한 교체 감지 및 제약 추가 중...")
        
        for line in self.lines:
            for time_slot_idx, time_slot in enumerate(self.time_slots):
                # === 케이스 1: 동일 시간대 내 제품 변경 감지 ===
                # 하나의 시간대에서 제품A → 제품B로 바뀔 때
                for position in range(1, self.MAX_POSITIONS):
                    for p1, line1 in self.valid_product_line_combinations:
                        for p2, line2 in self.valid_product_line_combinations:
                            if line1 == line2 == line and p1 != p2:
                                # position에서 p1, position+1에서 p2로 바뀔 때 교체 발생
                                # AND 연산: changeover[p1,p2] = sequence[p1] AND sequence[p2]
                                self.logger.debug(f"동일시간대 교체 감지 확인: {p1} (위치{position}) -> {p2} (위치{position+1}) @ {time_slot}")
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] <= 
                                    self.variables['sequence'][p1, line, time_slot, position],
                                    f"intra_slot_changeover_1_{p1}_{p2}_{line}_{time_slot}_{position}"
                                )
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] <= 
                                    self.variables['sequence'][p2, line, time_slot, position + 1],
                                    f"intra_slot_changeover_2_{p1}_{p2}_{line}_{time_slot}_{position}"
                                )
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] >= 
                                    self.variables['sequence'][p1, line, time_slot, position] + 
                                    self.variables['sequence'][p2, line, time_slot, position + 1] - 1,
                                    f"intra_slot_changeover_3_{p1}_{p2}_{line}_{time_slot}_{position}"
                                )
                
                # === 케이스 2: 시간대 간 인접 제품 변경 감지 ===
                if time_slot_idx > 0:
                    prev_time_slot = self.time_slots[time_slot_idx - 1]
                    
                    # 이전 시간대의 마지막 제품과 현재 시간대의 첫 번째 제품 비교
                    for p1, line1 in self.valid_product_line_combinations:
                        for p2, line2 in self.valid_product_line_combinations:
                            if line1 == line2 == line and p1 != p2:
                                # 이전 시간대 마지막 위치(p1) AND 현재 시간대 첫 번째 위치(p2)일 때 교체 발생
                                self.logger.debug(f"교체 감지 확인: {p1} (마지막, {prev_time_slot}) -> {p2} (첫 번째, {time_slot})")
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] <= 
                                    self.variables['sequence'][p1, line, prev_time_slot, self.MAX_POSITIONS],
                                    f"inter_slot_changeover_1_{p1}_{p2}_{line}_{time_slot}"
                                )
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] <= 
                                    self.variables['sequence'][p2, line, time_slot, 1],
                                    f"inter_slot_changeover_2_{p1}_{p2}_{line}_{time_slot}"
                                )
                                self.model += (
                                    self.variables['changeover'][p1, p2, line, time_slot] >= 
                                    self.variables['sequence'][p1, line, prev_time_slot, self.MAX_POSITIONS] + 
                                    self.variables['sequence'][p2, line, time_slot, 1] - 1,
                                    f"inter_slot_changeover_3_{p1}_{p2}_{line}_{time_slot}"
                                )
                
                # === sequence와 production 변수 연결 제약 ===
                # sequence 변수가 1이면 해당 제품이 생산되어야 함
                for product, line1 in self.valid_product_line_combinations:
                    if line1 == line:
                        for position in range(1, self.MAX_POSITIONS + 1):
                            # sequence[p,l,t,pos] = 1이면 production[p,l,t] = 1이어야 함
                            self.model += (
                                self.variables['sequence'][product, line, time_slot, position] <= 
                                self.variables['production'][product, line, time_slot],
                                f"sequence_to_production_{product}_{line}_{time_slot}_{position}"
                            )
                
                # === 교체시간 계산 ===
                changeover_vars = []
                for p1, line1 in self.valid_product_line_combinations:
                    for p2, line2 in self.valid_product_line_combinations:
                        if line1 == line2 == line and p1 != p2:
                            # 교체가 발생한 경우에만 교체시간 계산
                            changeover_time = self._get_changeover_time(p1, p2, line)
                            self.logger.debug(f"교체시간 계산: {p1} -> {p2} @ {time_slot} = {changeover_time}h")
                            changeover_vars.append(
                                self.variables['changeover'][p1, p2, line, time_slot] * changeover_time
                            )
                
                # 월요일 조간 디버깅
                if time_slot == "월요일_조간" and line == "16":
                    self.logger.info(f"🔍 월요일_조간 changeover_vars 개수: {len(changeover_vars)}")
                    if changeover_vars:
                        self.logger.info(f"🔍 월요일_조간 changeover_vars 내용:")
                        for i, var in enumerate(changeover_vars):
                            self.logger.info(f"  → [{i}] {var}")
                    else:
                        self.logger.info(f"🔍 월요일_조간 changeover_vars가 비어있음")
                
                # 해당 시간대의 총 교체시간 설정
                if changeover_vars:
                    self.model += (
                        self.variables['changeover_time'][line, time_slot] == lpSum(changeover_vars),
                        f"changeover_time_calculation_{line}_{time_slot}"
                    )
                else:
                    # 교체가 없는 경우 교체시간 0
                    self.model += (
                        self.variables['changeover_time'][line, time_slot] == 0,
                        f"no_changeover_{line}_{time_slot}"
                    )
        
        self.logger.info("정확한 교체 감지 및 제약 추가 완료")
        self.logger.info("🎯 개선사항: 동일 시간대 내 제품 변경 + 시간대 간 인접 제품 변경 정확히 감지")

    def _add_line_specific_constraints(self):
        """호기별 특정 제약조건 추가"""
        self.logger.info("=== 호기별 특정 제약조건 추가 ===")
        
        constrained_lines = self.line_constraints.get_all_constrained_lines()
        if not constrained_lines:
            self.logger.info("설정된 호기별 제약조건이 없습니다.")
            return
        
        for line in constrained_lines:
            if line not in self.lines:
                self.logger.warning(f"호기 {line}가 활성 라인에 없어 제약조건을 건너뜁니다.")
                continue
                
            constraints = self.line_constraints.get_line_constraints(line)
            
            for constraint in constraints:
                constraint_type = constraint['type']
                params = constraint['params']
                
                try:
                    if constraint_type == ConstraintTypes.START_PRODUCT:
                        self._add_start_product_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.START_END_PRODUCT:
                        self._add_start_end_product_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.LAST_PRODUCT:
                        self._add_last_product_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.PRODUCT_SEQUENCE:
                        self._add_product_sequence_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.BLOCK_SEQUENCE:
                        self._add_block_sequence_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.FORBIDDEN_COMBINATION:
                        self._add_forbidden_combination_constraint(line, **params)
                    elif constraint_type == ConstraintTypes.NO_CONSTRAINT:
                        self.logger.info(f"호기 {line}: 제약조건 없음")
                    else:
                        self.logger.warning(f"알 수 없는 제약조건 유형: {constraint_type}")
                        
                except Exception as e:
                    self.logger.error(f"호기 {line}의 {constraint_type} 제약조건 추가 중 오류: {e}")
        
        self.logger.info(f"호기별 제약조건 추가 완료: {len(constrained_lines)}개 호기")
        
        if constrained_lines:
            self.line_constraints.print_constraints_summary(self._get_product_name)
    
    def _add_start_product_constraint(self, line: str, product: str):
        first_slot = self.time_slots[0]
        self.model += (
            self.variables['sequence'][product, line, first_slot, 1] == 1,
            f"start_product_{line}_{product}"
        )
        product_name = self._get_product_name(product)
        self.logger.info(f"호기 {line}: 시작 제품 제약조건 추가 - 제품코드: {product} ({product_name})")
    
    def _add_start_end_product_constraint(self, line: str, product: str):
        first_slot = self.time_slots[0]
        last_slot = self.time_slots[-1]
        self.model += (
            self.variables['sequence'][product, line, first_slot, 1] == 1,
            f"start_end_product_start_{line}_{product}"
        )
        self.model += (
            self.variables['sequence'][product, line, last_slot, self.MAX_POSITIONS] == 1,
            f"start_end_product_end_{line}_{product}"
        )
        product_name = self._get_product_name(product)
        self.logger.info(f"호기 {line}: 시작+끝 제품 제약조건 추가 - 제품코드: {product} ({product_name})")
    
    def _add_last_product_constraint(self, line: str, product: str):
        last_slot = self.time_slots[-1]
        self.model += (
            self.variables['sequence'][product, line, last_slot, self.MAX_POSITIONS] == 1,
            f"last_product_{line}_{product}"
        )
        product_name = self._get_product_name(product)
        self.logger.info(f"호기 {line}: 마지막 제품 제약조건 추가 - 제품코드: {product} ({product_name})")
    
    def _add_product_sequence_constraint(self, line: str, sequence: list):
        for i in range(len(sequence) - 1):
            for j in range(i + 1, len(sequence)):
                product1 = sequence[i]
                product2 = sequence[j]
                for time_slot in self.time_slots:
                    for position in range(1, self.MAX_POSITIONS):
                        self.model += (
                            self.variables['sequence'][product2, line, time_slot, position] +
                            self.variables['sequence'][product1, line, time_slot, position + 1]
                            <= 1,
                            f"sequence_{line}_{product1}_{product2}_{time_slot}_{position}"
                        )
        
        sequence_with_names = [f"{p}({self._get_product_name(p)})" for p in sequence]
        self.logger.info(f"호기 {line}: 제품 순서 제약조건 추가 - 순서: {' > '.join(sequence_with_names)}")
    
    def _add_forbidden_combination_constraint(self, line: str, forbidden_pairs: list):
        for product1, product2 in forbidden_pairs:
            for time_slot in self.time_slots:
                for position in range(1, self.MAX_POSITIONS):
                    self.model += (
                        self.variables['sequence'][product1, line, time_slot, position] +
                        self.variables['sequence'][product2, line, time_slot, position + 1]
                        <= 1,
                        f"forbidden_{line}_{product1}_{product2}_{time_slot}_{position}"
                    )
        
        forbidden_pairs_with_names = [
            f"{p1}({self._get_product_name(p1)}) ↔ {p2}({self._get_product_name(p2)})"
            for p1, p2 in forbidden_pairs
        ]
        self.logger.info(f"호기 {line}: 금지 조합 제약조건 추가 - 금지 조합: {', '.join(forbidden_pairs_with_names)}")
    
    def _add_block_sequence_constraint(self, line: str, block_sequence: list):
        """
        블록 단위 제품 순서 제약조건 추가
        - 블록 단위로 연속성을 보장하여 제품 순서를 제어
        - 예: [새우탕(2블록), 짜파(3블록), 신라면(4블록)] 순서로 배치
        
        Args:
            line: 라인 ID
            block_sequence: 블록 순서 리스트 [{'product': 'product_id', 'blocks': 2}, ...]
        """
        self.logger.info(f"호기 {line}: 블록 단위 순서 제약조건 추가 중...")
        
        if not block_sequence:
            self.logger.warning(f"호기 {line}: 블록 순서가 비어있어 제약조건을 건너뜁니다.")
            return
        
        # block_start 변수가 있는지 확인
        if 'block_start' not in self.variables:
            self.logger.error(f"❌ 호기 {line}: block_start 변수가 optimizer.variables에 없습니다!")
            return
        
        # 각 제품별로 필요한 블록 수 계산
        total_blocks_needed = sum(block_info['blocks'] for block_info in block_sequence)
        if total_blocks_needed > len(self.time_slots):
            self.logger.warning(f"호기 {line}: 필요 블록 수({total_blocks_needed})가 시간대 수({len(self.time_slots)})를 초과합니다.")
            return
        
        # 블록 순서 제약조건 추가
        current_block_position = 0
        
        for i, block_info in enumerate(block_sequence):
            product = block_info['product']
            required_blocks = block_info['blocks']
            
            if (product, line) not in self.valid_product_line_combinations:
                self.logger.warning(f"호기 {line}: 제품 {product}가 유효한 조합에 없어 건너뜁니다.")
                continue
            
            # 해당 제품의 블록들이 연속으로 배치되어야 함
            for block_idx in range(required_blocks):
                if current_block_position + block_idx >= len(self.time_slots):
                    self.logger.warning(f"호기 {line}: 블록 {block_idx}가 시간대 범위를 초과합니다.")
                    break
                
                time_slot = self.time_slots[current_block_position + block_idx]
                
                # 해당 시간대에서 해당 제품이 생산되어야 함
                self.model += (
                    self.variables['production'][product, line, time_slot] == 1,
                    f"block_sequence_production_{line}_{product}_{current_block_position + block_idx}"
                )
                
                # block_start 변수와 연결 (첫 번째 블록인 경우)
                if block_idx == 0:
                    if (product, line) in self.variables['block_start']:
                        # block_start 변수가 존재하는 경우 연결
                        for start_idx in range(len(self.time_slots) - required_blocks + 1):
                            if start_idx == current_block_position:
                                self.model += (
                                    self.variables['block_start'][product, line][start_idx] == 1,
                                    f"block_sequence_start_{line}_{product}_{start_idx}"
                                )
                            else:
                                self.model += (
                                    self.variables['block_start'][product, line][start_idx] == 0,
                                    f"block_sequence_no_start_{line}_{product}_{start_idx}"
                                )
            
            # 다음 제품의 블록 시작 위치 업데이트
            current_block_position += required_blocks
        
        # 블록 순서 제약: 이전 제품의 모든 블록이 완료된 후 다음 제품 시작
        for i in range(len(block_sequence) - 1):
            current_product = block_sequence[i]['product']
            next_product = block_sequence[i + 1]['product']
            current_blocks = block_sequence[i]['blocks']
            
            # 현재 제품의 마지막 블록과 다음 제품의 첫 번째 블록 간 순서 제약
            current_last_block = current_block_position - (sum(block_info['blocks'] for block_info in block_sequence[i+1:]))
            next_first_block = current_last_block
            
            if current_last_block < len(self.time_slots) and next_first_block < len(self.time_slots):
                # 현재 제품의 마지막 시간대와 다음 제품의 첫 번째 시간대 간 순서 제약
                self.model += (
                    self.variables['production'][current_product, line, self.time_slots[current_last_block - 1]] >= 
                    self.variables['production'][next_product, line, self.time_slots[next_first_block]],
                    f"block_sequence_order_{line}_{current_product}_{next_product}"
                )
        
        # 블록 순서 정보 로깅
        sequence_info = []
        for block_info in block_sequence:
            product_name = self._get_product_name(block_info['product'])
            sequence_info.append(f"{product_name}({block_info['blocks']}블록)")
        
        self.logger.info(f"호기 {line}: 블록 단위 순서 제약조건 추가 완료")
        self.logger.info(f"  → 순서: {' → '.join(sequence_info)}")
        self.logger.info(f"  → 총 {total_blocks_needed}개 블록, {len(self.time_slots)}개 시간대")