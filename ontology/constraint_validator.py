import datetime
from typing import List, Dict, Tuple, Optional

class ConstraintValidator:
    """
    생산 스케줄의 제약조건 검증 및 원인 파악 클래스
    """
    
    def __init__(self, onto, logger=None):
        """
        ConstraintValidator 초기화
        Args:
            onto: owlready2 온톨로지 객체
            logger: 로거 객체
        """
        self.onto = onto
        self.logger = logger
        self.violations = []
        self.explanations = []
    
    def validate_all_constraints(self, segments, lines, products, days, shifts):
        """
        모든 제약조건 검증 실행
        Args:
            segments: 생산 세그먼트 리스트
            lines: 라인 딕셔너리
            products: 제품 딕셔너리
            days: 날짜 딕셔너리
            shifts: 시프트 딕셔너리
        Returns:
            dict: 검증 결과
        """
        self.logger.info("=== 제약조건 검증 시작 ===")
        
        # 1. 시간 충돌 검증
        time_conflicts = self._validate_time_conflicts(segments, lines)
        
        # 2. 자원 충돌 검증
        resource_conflicts = self._validate_resource_conflicts(segments, lines)
        
        # 3. 교체 효율성 검증
        changeover_conflicts = self._validate_changeover_efficiency(segments, lines)
        
        # 4. 용량 위반 검증
        capacity_violations = self._validate_capacity_violations(segments, lines)
        
        # 5. 우선순위 위반 검증
        priority_violations = self._validate_priority_violations(segments, products)
        
        # 6. 순서 위반 검증
        sequence_violations = self._validate_sequence_violations(segments, products)
        
        # 검증 결과 요약
        total_violations = (len(time_conflicts) + len(resource_conflicts) + 
                          len(changeover_conflicts) + len(capacity_violations) + 
                          len(priority_violations) + len(sequence_violations))
        
        self.logger.info(f"=== 제약조건 검증 완료 ===")
        self.logger.info(f"총 위반 사항: {total_violations}개")
        self.logger.info(f"  - 시간 충돌: {len(time_conflicts)}개")
        self.logger.info(f"  - 자원 충돌: {len(resource_conflicts)}개")
        self.logger.info(f"  - 교체 효율성: {len(changeover_conflicts)}개")
        self.logger.info(f"  - 용량 위반: {len(capacity_violations)}개")
        self.logger.info(f"  - 우선순위 위반: {len(priority_violations)}개")
        self.logger.info(f"  - 순서 위반: {len(sequence_violations)}개")
        
        return {
            'time_conflicts': time_conflicts,
            'resource_conflicts': resource_conflicts,
            'changeover_conflicts': changeover_conflicts,
            'capacity_violations': capacity_violations,
            'priority_violations': priority_violations,
            'sequence_violations': sequence_violations,
            'total_violations': total_violations
        }
    
    def _validate_time_conflicts(self, segments, lines):
        """
        시간 충돌 검증
        같은 라인에서 동시에 여러 세그먼트가 실행되는지 확인
        """
        conflicts = []
        
        # 라인별로 세그먼트 그룹화
        segments_by_line = {}
        for segment in segments:
            line = list(segment.occursInLine)[0]
            line_id = line.name.replace('line_', '')
            if line_id not in segments_by_line:
                segments_by_line[line_id] = []
            segments_by_line[line_id].append(segment)
        
        # 각 라인별로 시간 충돌 확인
        for line_id, line_segments in segments_by_line.items():
            # 시간순 정렬
            line_segments.sort(key=lambda s: (
                list(s.occursOnDay)[0].name,
                list(s.occursInShift)[0].hasShiftName[0]
            ))
            
            # 연속된 세그먼트들 간의 시간 겹침 확인
            for i in range(len(line_segments) - 1):
                current = line_segments[i]
                next_seg = line_segments[i + 1]
                
                # 같은 날짜, 같은 시프트에서 시간 겹침 확인
                current_day = list(current.occursOnDay)[0]
                next_day = list(next_seg.occursOnDay)[0]
                current_shift = list(current.occursInShift)[0]
                next_shift = list(next_seg.occursInShift)[0]
                
                if (current_day == next_day and current_shift == next_shift):
                    # 시간 겹침 발생
                    conflict = self._create_time_conflict(current, next_seg, line_id)
                    conflicts.append(conflict)
                    
                    # 원인 설명 생성
                    explanation = self._create_violation_explanation(
                        conflict, 
                        f"라인 {line_id}에서 {current_day.name} {current_shift.hasShiftName[0]}에 "
                        f"두 개의 세그먼트가 동시에 실행되려고 합니다. "
                        f"세그먼트 간의 시간 조정이 필요합니다.",
                        "Critical"
                    )
                    self.explanations.append(explanation)
        
        return conflicts
    
    def _validate_resource_conflicts(self, segments, lines):
        """
        자원 충돌 검증
        라인별 용량 초과 확인
        """
        conflicts = []
        
        # 라인별로 일일 생산량 계산
        daily_production_by_line = {}
        for segment in segments:
            line = list(segment.occursInLine)[0]
            line_id = line.name.replace('line_', '')
            day = list(segment.occursOnDay)[0]
            day_str = day.name.replace('day_', '')
            
            if line_id not in daily_production_by_line:
                daily_production_by_line[line_id] = {}
            if day_str not in daily_production_by_line[line_id]:
                daily_production_by_line[line_id][day_str] = 0
            
            # 생산 시간을 용량으로 변환
            production_hours = list(segment.hasProductionHours)[0]
            daily_production_by_line[line_id][day_str] += production_hours
        
        # 라인별 최대 용량과 비교
        for line_id, daily_production in daily_production_by_line.items():
            if line_id in lines:
                line = lines[line_id]
                max_daily_capacity = list(line.hasMaxDailyCapacity)[0]
                
                for day_str, production_hours in daily_production.items():
                    if production_hours > max_daily_capacity:
                        # 용량 초과 발생
                        conflict = self._create_capacity_violation(
                            line_id, day_str, production_hours, max_daily_capacity
                        )
                        conflicts.append(conflict)
                        
                        # 원인 설명 생성
                        explanation = self._create_violation_explanation(
                            conflict,
                            f"라인 {line_id}에서 {day_str}에 {production_hours:.1f}시간 생산이 계획되었으나 "
                            f"최대 용량은 {max_daily_capacity:.1f}시간입니다. "
                            f"생산량 조정 또는 추가 시프트 운영이 필요합니다.",
                            "Critical"
                        )
                        self.explanations.append(explanation)
        
        return conflicts
    
    def _validate_changeover_efficiency(self, segments, lines):
        """
        교체 효율성 검증
        비효율적인 교체 패턴 확인
        """
        conflicts = []
        
        # 라인별로 교체 이벤트 분석
        changeover_events_by_line = {}
        for segment in segments:
            if segment.nextSegment:
                line = list(segment.occursInLine)[0]
                line_id = line.name.replace('line_', '')
                
                if line_id not in changeover_events_by_line:
                    changeover_events_by_line[line_id] = []
                
                changeover_hours = list(segment.hasChangeoverHours)[0]
                if changeover_hours > 0:
                    changeover_events_by_line[line_id].append({
                        'segment': segment,
                        'changeover_hours': changeover_hours
                    })
        
        # 각 라인별로 교체 효율성 분석
        for line_id, changeover_events in changeover_events_by_line.items():
            if len(changeover_events) > 3:  # 하루에 3번 이상 교체
                # 비효율적 교체 패턴 감지
                total_changeover_time = sum(event['changeover_hours'] for event in changeover_events)
                
                conflict = self._create_changeover_conflict(
                    line_id, len(changeover_events), total_changeover_time
                )
                conflicts.append(conflict)
                
                # 원인 설명 생성
                explanation = self._create_violation_explanation(
                    conflict,
                    f"라인 {line_id}에서 하루에 {len(changeover_events)}번의 교체가 발생합니다. "
                    f"총 교체 시간은 {total_changeover_time:.1f}시간으로 비효율적입니다. "
                    f"제품 그룹화를 통한 교체 횟수 감소가 필요합니다.",
                    "Warning"
                )
                self.explanations.append(explanation)
        
        return conflicts
    
    def _validate_capacity_violations(self, segments, lines):
        """
        용량 위반 검증
        시프트별 용량 초과 확인
        """
        violations = []
        
        # 라인별, 시프트별 생산 시간 계산
        shift_production_by_line = {}
        for segment in segments:
            line = list(segment.occursInLine)[0]
            line_id = line.name.replace('line_', '')
            shift = list(segment.occursInShift)[0]
            shift_name = list(shift.hasShiftName)[0]
            
            if line_id not in shift_production_by_line:
                shift_production_by_line[line_id] = {}
            if shift_name not in shift_production_by_line[line_id]:
                shift_production_by_line[line_id][shift_name] = 0
            
            production_hours = list(segment.hasProductionHours)[0]
            shift_production_by_line[line_id][shift_name] += production_hours
        
        # 라인별 시프트 용량과 비교
        for line_id, shift_production in shift_production_by_line.items():
            if line_id in lines:
                line = lines[line_id]
                normal_capacity = list(line.hasNormalWorkingTime)[0]
                extended_capacity = list(line.hasExtendedWorkingTime)[0]
                
                for shift_name, production_hours in shift_production.items():
                    max_capacity = normal_capacity if shift_name == "조간" else extended_capacity
                    
                    if production_hours > max_capacity:
                        violation = self._create_capacity_violation(
                            line_id, shift_name, production_hours, max_capacity
                        )
                        violations.append(violation)
        
        return violations
    
    def _validate_priority_violations(self, segments, products):
        """
        우선순위 위반 검증
        제품 우선순위에 따른 생산 순서 확인
        """
        violations = []
        
        # 제품별 우선순위 정보 (예시 - 실제로는 제품 데이터에서 가져와야 함)
        product_priorities = {
            'P001': 1,  # 최고 우선순위
            'P002': 2,
            'P003': 3,
            'P004': 4,
            'P005': 5,  # 최저 우선순위
        }
        
        # 라인별로 세그먼트 순서 확인
        segments_by_line = {}
        for segment in segments:
            line = list(segment.occursInLine)[0]
            line_id = line.name.replace('line_', '')
            if line_id not in segments_by_line:
                segments_by_line[line_id] = []
            segments_by_line[line_id].append(segment)
        
        # 각 라인별로 우선순위 위반 확인
        for line_id, line_segments in segments_by_line.items():
            # 시간순 정렬
            line_segments.sort(key=lambda s: (
                list(s.occursOnDay)[0].name,
                list(s.occursInShift)[0].hasShiftName[0]
            ))
            
            # 연속된 세그먼트들 간의 우선순위 확인
            for i in range(len(line_segments) - 1):
                current = line_segments[i]
                next_seg = line_segments[i + 1]
                
                current_product = list(current.producesProduct)[0]
                next_product = list(next_seg.producesProduct)[0]
                
                current_code = list(current_product.hasProductCode)[0]
                next_code = list(next_product.hasProductCode)[0]
                
                if (current_code in product_priorities and 
                    next_code in product_priorities and
                    product_priorities[current_code] > product_priorities[next_code]):
                    # 우선순위 위반 발생
                    violation = self._create_priority_violation(
                        current, next_seg, current_code, next_code,
                        product_priorities[current_code], product_priorities[next_code]
                    )
                    violations.append(violation)
        
        return violations
    
    def _validate_sequence_violations(self, segments, products):
        """
        순서 위반 검증
        제품 간의 필수 생산 순서 확인
        """
        violations = []
        
        # 제품 간 필수 순서 규칙 (예시)
        required_sequences = [
            ('P001', 'P002'),  # P001 다음에 P002가 와야 함
            ('P003', 'P004'),  # P003 다음에 P004가 와야 함
        ]
        
        # 라인별로 세그먼트 순서 확인
        segments_by_line = {}
        for segment in segments:
            line = list(segment.occursInLine)[0]
            line_id = line.name.replace('line_', '')
            if line_id not in segments_by_line:
                segments_by_line[line_id] = []
            segments_by_line[line_id].append(segment)
        
        # 각 라인별로 순서 위반 확인
        for line_id, line_segments in segments_by_line.items():
            # 시간순 정렬
            line_segments.sort(key=lambda s: (
                list(s.occursOnDay)[0].name,
                list(s.occursInShift)[0].hasShiftName[0]
            ))
            
            # 연속된 세그먼트들 간의 순서 확인
            for i in range(len(line_segments) - 1):
                current = line_segments[i]
                next_seg = line_segments[i + 1]
                
                current_product = list(current.producesProduct)[0]
                next_product = list(next_seg.producesProduct)[0]
                
                current_code = list(current_product.hasProductCode)[0]
                next_code = list(next_product.hasProductCode)[0]
                
                # 필수 순서 규칙 확인
                for required_before, required_after in required_sequences:
                    if current_code == required_after and next_code == required_before:
                        # 순서 위반 발생
                        violation = self._create_sequence_violation(
                            current, next_seg, required_before, required_after
                        )
                        violations.append(violation)
        
        return violations
    
    def _create_time_conflict(self, segment1, segment2, line_id):
        """시간 충돌 인스턴스 생성"""
        conflict = self.onto.TimeConflict(f"time_conflict_{line_id}_{segment1.name}_{segment2.name}")
        conflict.hasTimeConflict = [segment1, segment2]
        conflict.hasConflictStartTime = [datetime.datetime.now()]
        conflict.hasConflictEndTime = [datetime.datetime.now()]
        conflict.hasConflictDuration = [0.0]
        return conflict
    
    def _create_capacity_violation(self, line_id, time_period, actual, capacity):
        """용량 위반 인스턴스 생성"""
        violation = self.onto.CapacityViolation(f"capacity_violation_{line_id}_{time_period}")
        violation.hasCapacityExcess = [actual - capacity]
        violation.hasCapacityShortage = [0.0]
        return violation
    
    def _create_changeover_conflict(self, line_id, count, total_time):
        """교체 충돌 인스턴스 생성"""
        conflict = self.onto.ChangeoverConflict(f"changeover_conflict_{line_id}")
        conflict.hasChangeoverOverlap = [total_time]
        conflict.hasInefficientChangeover = [True]
        return conflict
    
    def _create_priority_violation(self, segment1, segment2, product1, product2, priority1, priority2):
        """우선순위 위반 인스턴스 생성"""
        violation = self.onto.PriorityViolation(f"priority_violation_{segment1.name}_{segment2.name}")
        violation.hasPriorityViolation = [list(segment1.producesProduct)[0]]
        violation.hasPriorityLevel = [priority1]
        return violation
    
    def _create_sequence_violation(self, segment1, segment2, required_before, required_after):
        """순서 위반 인스턴스 생성"""
        violation = self.onto.SequenceViolation(f"sequence_violation_{segment1.name}_{segment2.name}")
        violation.hasSequenceViolation = [segment1]
        violation.hasRequiredSequence = [f"{required_before} -> {required_after}"]
        return violation
    
    def _create_violation_explanation(self, violation, explanation_text, severity):
        """위반 원인 설명 인스턴스 생성"""
        explanation = self.onto.ViolationExplanation(f"explanation_{violation.name}")
        explanation.explainsViolation = [violation]
        explanation.hasExplanation = [explanation_text]
        explanation.hasRootCause = ["스케줄링 로직의 제약조건 미반영"]
        explanation.hasImpactAnalysis = ["생산 효율성 저하 및 지연 발생 가능"]
        return explanation
    
    def generate_violation_report(self, validation_results):
        """
        위반 사항 보고서 생성
        Args:
            validation_results: 검증 결과 딕셔너리
        Returns:
            str: 보고서 텍스트
        """
        report = "=== 제약조건 위반 보고서 ===\n\n"
        
        total_violations = validation_results['total_violations']
        report += f"총 위반 사항: {total_violations}개\n\n"
        
        # 각 위반 유형별 상세 보고
        for violation_type, violations in validation_results.items():
            if violation_type != 'total_violations' and violations:
                report += f"## {violation_type.replace('_', ' ').title()}\n"
                report += f"위반 사항: {len(violations)}개\n\n"
                
                for i, violation in enumerate(violations[:5], 1):  # 처음 5개만 표시
                    report += f"{i}. {violation.name}\n"
                
                if len(violations) > 5:
                    report += f"... 외 {len(violations) - 5}개\n"
                report += "\n"
        
        # 원인 분석 요약
        report += "## 원인 분석 요약\n"
        critical_count = sum(1 for exp in self.explanations if "Critical" in str(exp))
        warning_count = sum(1 for exp in self.explanations if "Warning" in str(exp))
        
        report += f"- Critical 위반: {critical_count}개\n"
        report += f"- Warning 위반: {warning_count}개\n\n"
        
        # 개선 제안
        report += "## 개선 제안\n"
        if validation_results['time_conflicts']:
            report += "1. 시간 충돌 해결을 위한 세그먼트 재배치 필요\n"
        if validation_results['capacity_violations']:
            report += "2. 용량 초과 해결을 위한 생산량 조정 또는 추가 시프트 운영 검토\n"
        if validation_results['changeover_conflicts']:
            report += "3. 교체 효율성 개선을 위한 제품 그룹화 전략 수립\n"
        if validation_results['priority_violations']:
            report += "4. 우선순위 기반 스케줄링 로직 강화\n"
        
        return report 