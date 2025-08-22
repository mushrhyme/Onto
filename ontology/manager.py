from owlready2 import Thing, ObjectProperty, DataProperty, destroy_entity, get_ontology
import json
import pandas as pd
import datetime
from typing import Dict
import logging
import os

from config import RESULTS_DIR, LOG_FILE
from utils import setup_logger, get_week_dates
from .data_loader import load_json_data, load_order_csv
from .schema import create_schema
from .constraint_schema import create_constraint_schema
from .constraint_validator import ConstraintValidator
from .instance_builder import (
    create_team_instances, create_line_instances, create_product_instances,
    create_relations, create_changeover_rule_instances, create_shift_instances, create_day_instances
)
from .production_logic import (
    create_production_segments, connect_next_segments_and_calculate_changeover,
    identify_continuous_production_runs, create_changeover_event_instances
)
class OntologyManager:
    def __init__(self, onto, monday_date=None, logger=None):
        """
        OntologyManager 초기화
        
        Args:
            onto: owlready2 온톨로지 객체
            monday_date: 월요일 날짜 (datetime.date 객체 또는 "YYYY-MM-DD" 문자열)
            logger: 로거 객체 (선택사항)
        """
        # 결과 폴더 생성
        os.makedirs(RESULTS_DIR, exist_ok=True)
        
        # 로깅 설정
        if logger is None:
            self.logger = setup_logger(LOG_FILE)
        else:
            self.logger = logger
            
        self.onto = onto
        
        # 월요일 날짜 설정
        if monday_date is None:
            # 기본값: 오늘 날짜에서 가장 가까운 월요일
            today = datetime.date.today()
            days_since_monday = today.weekday()  # 0=월요일, 1=화요일, ..., 6=일요일
            self.monday_date = today - datetime.timedelta(days=days_since_monday)
        elif isinstance(monday_date, str):
            # 문자열을 datetime.date 객체로 변환
            self.monday_date = datetime.datetime.strptime(monday_date, "%Y-%m-%d").date()
        else:
            # datetime.date 객체인 경우
            self.monday_date = monday_date
        
        # 날짜별 최대 가동시간 설정 (기본값)
        self._default_working_hours = {
            0: 10.5,  # 월요일
            1: 10.5,  # 화요일
            2: 8.0,   # 수요일 (특별한 날)
            3: 10.5,  # 목요일
            4: 10.5,  # 금요일
        }
        
        # 날짜별 인덱스 매핑 (정렬용)
        self._date_index = {}

    def set_working_hours(self, working_hours_dict):
        """
        날짜별 최대 가동시간 설정
        
        Args:
            working_hours_dict: {요일인덱스: 시간} 형태의 딕셔너리
                예: {0: 10.5, 1: 10.5, 2: 8.0, 3: 10.5, 4: 10.5}
        """
        self._default_working_hours.update(working_hours_dict)
        self.logger.info(f"날짜별 가동시간 설정 업데이트: {working_hours_dict}")

    def _get_date_index(self, date):
        """
        날짜의 인덱스를 반환 (정렬용)
        
        Args:
            date: datetime.date 객체
            
        Returns:
            int: 날짜 인덱스 (0=월요일, 1=화요일, ..., 4=금요일)
        """
        return (date - self.monday_date).days

    def _get_date_index_from_segment(self, segment):
        """
        세그먼트에서 날짜 인덱스를 반환 (정렬용)
        
        Args:
            segment: ProductionSegment 인스턴스
            
        Returns:
            int: 날짜 인덱스 (0=월요일, 1=화요일, ..., 4=금요일)
        """
        day = list(segment.occursOnDay)[0]
        day_name = day.name  # 예: "day_2025-07-21"
        date_str = day_name.replace('day_', '')  # "2025-07-21"
        
        # _date_index에서 찾기
        if date_str in self._date_index:
            return self._date_index[date_str]
        
        # 없으면 날짜 계산
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            return self._get_date_index(date)
        except ValueError:
            # 기본값 반환
            return 0

    def _get_week_dates(self):
        """
        월요일을 기준으로 한 주의 날짜들을 반환
        
        Returns:
            list: [월요일, 화요일, 수요일, 목요일, 금요일] 날짜 리스트
        """
        week_dates = []
        for i in range(5):  # 월요일부터 금요일까지
            date = self.monday_date + datetime.timedelta(days=i)
            week_dates.append(date)
        return week_dates

    def _create_schema(self):
        """
        온톨로지 스키마 생성 (기본 스키마 + 제약조건 스키마)
        """
        create_schema(self.onto)  # 기본 스키마
        create_constraint_schema(self.onto)  # 제약조건 스키마
        self.logger.info("온톨로지 스키마 생성 완료 (기본 + 제약조건)")

    def validate_constraints(self, results):
        """
        생성된 스케줄에 대한 제약조건 검증
        Args:
            results: build() 메서드의 결과
        Returns:
            dict: 검증 결과
        """
        self.logger.info("=== 제약조건 검증 시작 ===")
        
        # ConstraintValidator 인스턴스 생성
        validator = ConstraintValidator(self.onto, self.logger)
        
        # 제약조건 검증 실행
        validation_results = validator.validate_all_constraints(
            results['segments'],
            results['lines'],
            results['products'],
            results['days'],
            results['shifts']
        )
        
        # 위반 보고서 생성
        violation_report = validator.generate_violation_report(validation_results)
        
        # 보고서 저장
        report_path = os.path.join(RESULTS_DIR, f"constraint_violation_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(violation_report)
        
        self.logger.info(f"제약조건 위반 보고서 저장: {report_path}")
        
        return {
            'validation_results': validation_results,
            'violation_report': violation_report,
            'report_path': report_path
        }

    def _create_production_segment_instances(self, json_data: dict, order_data: dict):
        """
        ProductionSegment 인스턴스 생성 (production_logic.py의 함수들 호출)
        """

        # 기본 인스턴스들이 이미 생성되어 있다고 가정
        teams = {team.name.replace('_team', '팀'): team for team in self.onto.Team.instances()}
        lines = {line.name.replace('line_', ''): line for line in self.onto.Line.instances()}
        products = {prod.hasProductCode[0]: prod for prod in self.onto.Product.instances() if prod.hasProductCode}
        days = {day.name.replace('day_', ''): day for day in self.onto.Day.instances()}
        shifts = {shift.hasShiftName[0]: shift for shift in self.onto.Shift.instances() if shift.hasShiftName}
        
        # 생산 세그먼트 생성
        segments = create_production_segments(self.onto, json_data, order_data, lines, products, days, shifts)
        
        # 세그먼트 연결 및 교체 시간 계산
        connect_next_segments_and_calculate_changeover(self.onto, segments, json_data, self._get_date_index_from_segment)
        
        # 연속 생산 구간 식별
        continuous_runs = identify_continuous_production_runs(self.onto, segments, self._get_date_index_from_segment)
        
        # 교체 이벤트 생성
        changeover_events = create_changeover_event_instances(self.onto, segments)
        
        return segments, continuous_runs, changeover_events

    def _create_line_product_instances(self, json_data: dict, order_data: dict):
        """
        전체 인스턴스 생성 순서 제어 (기존 방식과 동일한 순서)
        """
        self._clear_existing_instances()
        
        # 기본 인스턴스 생성
        teams = create_team_instances(self.onto, json_data)
        lines = create_line_instances(self.onto, json_data, teams)
        products = create_product_instances(self.onto, json_data, order_data)
        relations = create_relations(self.onto, json_data, order_data, lines, products)
        changeover_rules = create_changeover_rule_instances(self.onto, json_data, lines)
        shifts = create_shift_instances(self.onto)
        
        # 날짜 리스트 생성 및 Day 인스턴스 생성
        week_dates = self._get_week_dates()
        date_list = [date.strftime('%Y-%m-%d') for date in week_dates]
        days = create_day_instances(self.onto, shifts, date_list, self._default_working_hours)
        
        # 날짜별 인덱스 매핑 생성 (정렬용)
        for i, date in enumerate(date_list):
            self._date_index[date] = i
        
        # 생산 세그먼트 및 관련 인스턴스 생성
        segments, continuous_runs, changeover_events = self._create_production_segment_instances(json_data, order_data)
        
        return {
            'teams': teams,
            'lines': lines,
            'products': products,
            'relations': relations,
            'changeover_rules': changeover_rules,
            'shifts': shifts,
            'days': days,
            'segments': segments,
            'continuous_runs': continuous_runs,
            'changeover_events': changeover_events
        }

    def _clear_existing_instances(self):
        """
        기존 인스턴스 삭제
        """
        for inst in list(self.onto.individuals()):
            destroy_entity(inst)
        self.logger.info("기존 인스턴스 삭제 완료")

    def build(self, products_path, lines_path, changeover_path, order_path, start_date_str):
        """
        완전한 온톨로지 빌드 파이프라인
        Args:
            products_path: str, 제품 정보 JSON 파일 경로
            lines_path: str, 라인 정보 JSON 파일 경로
            changeover_path: str, 교체 규칙 JSON 파일 경로
            order_path: str, 주문 CSV 파일 경로
            start_date_str: str, 시작 날짜 (YYYY-MM-DD)
        """
        self.logger.info("=== 온톨로지 빌드 시작 ===")
        
        # 1. 데이터 로딩
        self.logger.info("1. 데이터 로딩 중...")
        json_data = load_json_data(products_path, lines_path, changeover_path)  # dict
        order_data = load_order_csv(order_path)  # dict
        
        # 데이터 저장 (ProductionOptimizer에서 사용)
        self._changeover_data = json_data
        self._order_data = order_data
        
        self.logger.info(f"   - JSON 데이터 로드 완료: {len(json_data['products']['products'])}개 제품, {len(json_data['lines']['lines'])}개 라인")
        self.logger.info(f"   - 주문 데이터 로드 완료: {len(order_data)}개 제품")

        # 2. 온톨로지 스키마 정의
        self.logger.info("2. 온톨로지 스키마 정의 중...")
        self._create_schema()  # 원본과 동일한 방식
        self.logger.info("   - 클래스, 속성, 제약조건 정의 완료")

        # 3. 전체 인스턴스 생성 (원본과 동일한 방식)
        self.logger.info("3. 전체 인스턴스 생성 중...")
        results = self._create_line_product_instances(json_data, order_data)
        
        self.logger.info(f"   - 팀: {len(results['teams'])}개")
        self.logger.info(f"   - 라인: {len(results['lines'])}개")
        self.logger.info(f"   - 제품: {len(results['products'])}개")
        self.logger.info(f"   - 세그먼트: {len(results['segments'])}개")
        self.logger.info(f"   - 연속 생산 구간: {len(results['continuous_runs'])}개")
        self.logger.info(f"   - 교체 이벤트: {len(results['changeover_events'])}개")

        # 4. 결과 저장
        self.logger.info("4. 결과 저장 중...")
        self._save_build_results(
            results['teams'], results['lines'], results['products'], 
            results['relations'], results['changeover_rules'], 
            results['shifts'], results['days'], results['segments'], 
            results['continuous_runs'], results['changeover_events']
        )
        
        self.logger.info("=== 온톨로지 빌드 완료 ===")
        
        return results

    def _save_build_results(self, teams, lines, products, relations, changeover_rules, 
                           shifts, days, segments, continuous_runs, changeover_events):
        """
        빌드 결과를 로그에 저장
        """
        self.logger.info("=== 빌드 결과 요약 ===")
        self.logger.info(f"팀: {len(teams)}개")
        self.logger.info(f"라인: {len(lines)}개")
        self.logger.info(f"제품: {len(products)}개")
        self.logger.info(f"라인-제품 관계: {len(relations)}개")
        self.logger.info(f"교체 규칙: {len(changeover_rules)}개")
        self.logger.info(f"시프트: {len(shifts)}개")
        self.logger.info(f"날짜: {len(days)}개")
        self.logger.info(f"생산 세그먼트: {len(segments)}개")
        self.logger.info(f"연속 생산 구간: {len(continuous_runs)}개")
        self.logger.info(f"교체 이벤트: {len(changeover_events)}개")

    def test_ontology_creation(self, json_data=None):
        """
        온톨로지 생성 테스트 (기존 메서드 유지)
        """
        print("=== 온톨로지 생성 결과 ===")
        
        # 1) 생성된 인스턴스 수 확인
        print(f"Team 인스턴스 수: {len(list(self.onto.Team.instances()))}")
        print(f"Line 인스턴스 수: {len(list(self.onto.Line.instances()))}")
        print(f"Product 인스턴스 수: {len(list(self.onto.Product.instances()))}")
        print(f"LineProductRelation 인스턴스 수: {len(list(self.onto.LineProductRelation.instances()))}")
        print(f"ChangeoverRule 인스턴스 수: {len(list(self.onto.ChangeoverRule.instances()))}")
        print(f"Shift 인스턴스 수: {len(list(self.onto.Shift.instances()))}")
        print(f"Day 인스턴스 수: {len(list(self.onto.Day.instances()))}")
        print(f"ProductionSegment 인스턴스 수: {len(list(self.onto.ProductionSegment.instances()))}")
        print(f"ChangeoverEvent 인스턴스 수: {len(list(self.onto.ChangeoverEvent.instances()))}")
        print(f"ContinuousProductionRun 인스턴스 수: {len(list(self.onto.ContinuousProductionRun.instances()))}")
        print(f"ProductionRunStart 인스턴스 수: {len(list(self.onto.ProductionRunStart.instances()))}")
        print(f"ProductionRunEnd 인스턴스 수: {len(list(self.onto.ProductionRunEnd.instances()))}")
        
        # 2) 실제 교체 규칙 정보 출력
        print("\n=== 실제 교체 규칙 정보 (처음 3개 라인) ===")
        if json_data and 'changeover_rules' in json_data:
            for i, (line_id, rule_info) in enumerate(json_data['changeover_rules'].items()):
                if i >= 3:
                    break
                print(f"라인 {line_id} ({rule_info['description']}):")
                for rule in rule_info['rules'][:3]:  # 처음 3개 규칙만 출력
                    print(f"  {rule['from']} → {rule['to']}: {rule['time']}시간 ({rule['description']})")
                print()
        
        # 3) 제품 정보 출력
        print("=== 제품 정보 (처음 5개) ===")
        for i, product in enumerate(self.onto.Product.instances()):
            if i >= 5:
                break
            product_code = list(product.hasProductCode)[0] if product.hasProductCode else "N/A"
            product_name = list(product.hasProductName)[0] if product.hasProductName else "N/A"
            product_category = list(product.hasCategory)[0] if product.hasCategory else "N/A"
            print(f"제품 {i+1}: {product_code} - {product_name} ({product_category})")
        
        # 4) 라인 정보 출력
        print("\n=== 라인 정보 (처음 5개) ===")
        for i, line in enumerate(self.onto.Line.instances()):
            if i >= 5:
                break
            line_category = list(line.hasLineCategory)[0] if line.hasLineCategory else "N/A"
            line_type = list(line.hasLineType)[0] if line.hasLineType else "N/A"
            normal_hours = list(line.hasNormalWorkingTime)[0] if line.hasNormalWorkingTime else "N/A"
            extended_hours = list(line.hasExtendedWorkingTime)[0] if line.hasExtendedWorkingTime else "N/A"
            normal_capacity = list(line.hasNormalCapacity)[0] if line.hasNormalCapacity else "N/A"
            extended_capacity = list(line.hasExtendedCapacity)[0] if line.hasExtendedCapacity else "N/A"
            max_daily_capacity = list(line.hasMaxDailyCapacity)[0] if line.hasMaxDailyCapacity else "N/A"
            print(f"라인 {i+1}: {line.name} - {line_category} ({line_type})")
            print(f"  조간: {normal_hours}시간 ({normal_capacity}박스), 야간: {extended_hours}시간 ({extended_capacity}박스)")
            print(f"  하루 최대 용량: {max_daily_capacity}박스")
        
        # 5) 라인-제품 관계 정보 출력
        print("\n=== 라인-제품 관계 정보 (처음 5개) ===")
        for i, relation in enumerate(self.onto.LineProductRelation.instances()):
            if i >= 5:
                break
            line_name = list(relation.hasLine)[0].name if relation.hasLine else "N/A"
            product_code = list(relation.handlesProduct)[0].hasProductCode[0] if relation.handlesProduct and relation.handlesProduct[0].hasProductCode else "N/A"
            ct_rate = list(relation.hasCTRate)[0] if relation.hasCTRate else "N/A"
            print(f"관계 {i+1}: {line_name} - {product_code} (CT Rate: {ct_rate})")
        
        # 6) Day와 Shift 정보 출력
        print("\n=== Day와 Shift 정보 ===")
        for day_name, day in self.onto.Day.instances():
            if not day_name.endswith('요일'):  # 영문 코드는 건너뛰기
                continue
            shifts = [shift.hasShiftName[0] for shift in day.hasShift if shift.hasShiftName]
            max_working_time = list(day.hasMaxWorkingTime)[0] if day.hasMaxWorkingTime else "N/A"
            print(f"{day_name}: {', '.join(shifts)} (최대 가동시간: {max_working_time}시간)")
        
        # 7) 생성된 세그먼트와 이벤트 정보 출력
        print(f"\n=== 생성된 세그먼트 정보 ===")
        segments = list(self.onto.ProductionSegment.instances())
        print(f"총 세그먼트 수: {len(segments)}")
        if segments:
            print(f"첫 번째 세그먼트 예시:")
            first_segment = segments[0]
            line_name = list(first_segment.occursInLine)[0].name if first_segment.occursInLine else "N/A"
            day_name = list(first_segment.occursOnDay)[0].name if first_segment.occursOnDay else "N/A"
            shift_name = list(first_segment.occursInShift)[0].hasShiftName[0] if first_segment.occursInShift and first_segment.occursInShift[0].hasShiftName else "N/A"
            product_code = list(first_segment.producesProduct)[0].hasProductCode[0] if first_segment.producesProduct and first_segment.producesProduct[0].hasProductCode else "N/A"
            schedule_date = str(list(first_segment.hasSegmentDate)[0]) if first_segment.hasSegmentDate else "N/A"
            production_hours = list(first_segment.hasProductionHours)[0] if first_segment.hasProductionHours else "N/A"
            changeover_hours = list(first_segment.hasChangeoverHours)[0] if first_segment.hasChangeoverHours else "N/A"
            cleaning_hours = list(first_segment.hasCleaningHours)[0] if first_segment.hasCleaningHours else "N/A"
            total_segment_hours = list(first_segment.hasTotalSegmentHours)[0] if first_segment.hasTotalSegmentHours else "N/A"
            quantity = list(first_segment.hasProductionQuantity)[0] if first_segment.hasProductionQuantity else "N/A"
            
            print(f"  라인: {line_name}, 날짜: {schedule_date}, 시프트: {shift_name}")
            print(f"  제품: {product_code}, 생산시간: {production_hours}시간, 교체시간: {changeover_hours}시간, 청소시간: {cleaning_hours}시간, 총시간: {total_segment_hours}시간, 수량: {quantity}")
        
        print(f"\n=== 생성된 교체 이벤트 정보 ===")
        changeover_events = list(self.onto.ChangeoverEvent.instances())
        print(f"총 교체 이벤트 수: {len(changeover_events)}")
        
        # 연속 생산 구간 정보 출력
        print(f"\n=== 생성된 연속 생산 구간 정보 ===")
        continuous_runs = list(self.onto.ContinuousProductionRun.instances())
        print(f"총 연속 생산 구간 수: {len(continuous_runs)}")
        if continuous_runs:
            print(f"연속 생산 구간 예시:")
            for i, run in enumerate(continuous_runs[:3]):  # 처음 3개만 출력
                product_code = list(run.hasRunProduct)[0] if run.hasRunProduct else "N/A"
                duration = list(run.hasRunDuration)[0] if run.hasRunDuration else "N/A"
                start_time = list(run.hasRunStart[0].hasRunStartTime)[0] if run.hasRunStart and run.hasRunStart[0].hasRunStartTime else "N/A"
                end_time = list(run.hasRunEnd[0].hasRunEndTime)[0] if run.hasRunEnd and run.hasRunEnd[0].hasRunEndTime else "N/A"
                segment_count = len(list(run.runContainsSegment)) if run.runContainsSegment else 0
                print(f"  구간 {i+1}: {product_code} ({start_time} → {end_time}, {segment_count}개 세그먼트, {duration:.1f}시간)")

    def build_with_validation(self, products_path, lines_path, changeover_path, order_path, start_date_str):
        """
        온톨로지 빌드 + 제약조건 검증 통합 실행
        Args:
            products_path: str, 제품 정보 JSON 파일 경로
            lines_path: str, 라인 정보 JSON 파일 경로
            changeover_path: str, 교체 규칙 JSON 파일 경로
            order_path: str, 주문 CSV 파일 경로
            start_date_str: str, 시작 날짜 (YYYY-MM-DD)
        Returns:
            dict: 빌드 결과 + 검증 결과
        """
        # 1. 온톨로지 빌드
        build_results = self.build(products_path, lines_path, changeover_path, order_path, start_date_str)
        
        # 2. 제약조건 검증
        validation_results = self.validate_constraints(build_results)
        
        # 3. 통합 결과 반환
        return {
            'build_results': build_results,
            'validation_results': validation_results
        }
