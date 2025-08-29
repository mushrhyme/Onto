from owlready2 import Thing, ObjectProperty, DataProperty, destroy_entity, get_ontology
import json
import pandas as pd
import datetime
import os

from config import RESULTS_DIR, LOG_FILE
from utils import setup_logger, get_week_dates
from .schema import create_schema
from .constraint_schema import create_constraint_schema
from .constraint_validator import ConstraintValidator
from .instance_builder import (
    create_team_instances, create_line_instances, create_product_instances,
    create_relations, create_changeover_rule_instances, create_shift_instances, 
    create_day_instances, create_timeslot_instances, create_production_segment_instances
)
from .production_logic import (
    create_production_segments, connect_next_segments_and_calculate_changeover
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

    def load_json_data(self, products_path: str, lines_path: str, changeover_path: str) -> dict:
        """
        JSON 파일 3종(products, lines, changeover) 로드
        반환 예시:
        {
            'products': {...},
            'lines': {...},
            'changeover': {...}
        }
        """
        with open(products_path, 'r', encoding='utf-8') as f:
            products_data = json.load(f)
        with open(lines_path, 'r', encoding='utf-8') as f:
            lines_data = json.load(f)
        with open(changeover_path, 'r', encoding='utf-8') as f:
            changeover_data = json.load(f)

        return {'products': products_data, 'lines': lines_data, 'changeover': changeover_data}  # dict 형태


    def load_order_csv(self, order_path: str) -> dict:
        """
        생산 지시 수량 CSV 파일 로드

        Args:
            order_path: 주문 CSV 파일 경로

        Returns:
            제품별 생산 지시량 딕셔너리
            예시: {'P001': 100, 'P002': 200}
        """
        order_df = pd.read_csv(order_path)
        order_dict = {}
        for _, row in order_df.iterrows():
            product_code = str(row['제품코드'])  # 예: 'P001'
            quantity = int(row['수량'])         # 예: 100
            order_dict[product_code] = quantity
        return order_dict  # {'P001': 100, ...} 


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

    def _create_production_segment_instances(self, json_data: dict, order_data: dict, active_lines=None):
        """
        ProductionSegment 인스턴스 생성 (production_logic.py의 함수들 호출)
        Args:
            json_data: dict, JSON 데이터
            order_data: dict, 주문 데이터
            active_lines: list, 활성화된 라인 ID 리스트 (None이면 모든 라인 처리)
        """
        
        # 활성화된 라인이 설정되지 않은 경우 모든 라인 처리
        if active_lines is None:
            self.logger.info("🔍 활성화된 라인이 설정되지 않아 모든 라인에 대해 세그먼트 생성")
        else:
            self.logger.info(f"🔍 활성화된 라인만 세그먼트 생성: {active_lines}")

        # 기본 인스턴스들이 이미 생성되어 있다고 가정
        teams = {team.name.replace('_team', '팀'): team for team in self.onto.Team.instances()}
        lines = {line.name.replace('line_', ''): line for line in self.onto.Line.instances()}
        products = {prod.hasProductCode[0]: prod for prod in self.onto.Product.instances() if prod.hasProductCode}
        days = {day.name.replace('day_', ''): day for day in self.onto.Day.instances()}
        shifts = {shift.hasShiftName[0]: shift for shift in self.onto.Shift.instances() if shift.hasShiftName}
        timeslots = {ts.hasTimeSlotName[0]: ts for ts in self.onto.TimeSlot.instances() if ts.hasTimeSlotName}
        
        # 생산 세그먼트 생성 (TimeSlot 포함) - 활성화된 라인만 처리
        segments = create_production_segment_instances(self.onto, lines, days, shifts, timeslots, products, order_data, active_lines)
        
        # 세그먼트 연결 및 교체 시간 계산 (활성화된 라인의 세그먼트만 처리)
        if segments:  # 세그먼트가 있는 경우에만 처리
            connect_next_segments_and_calculate_changeover(self.onto, segments, json_data, self._get_date_index_from_segment)
        
        # 연속 생산 구간 식별
        # continuous_runs = identify_continuous_production_runs(self.onto, segments, self._get_date_index_from_segment)
        
        # 교체 이벤트 생성
        # changeover_events = create_changeover_event_instances(self.onto, segments)
        
        return segments

    def _create_line_product_instances(self, json_data: dict, order_data: dict, active_lines=None):
        """
        전체 인스턴스 생성 순서 제어 (기존 방식과 동일한 순서)
        Args:
            json_data: dict, JSON 데이터
            order_data: dict, 주문 데이터
            active_lines: list, 활성화된 라인 ID 리스트 (None이면 모든 라인 처리)
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
        
        # TimeSlot 인스턴스 생성 (새로 추가)
        timeslots = create_timeslot_instances(self.onto, days, shifts, self._default_working_hours)
        
        # 날짜별 인덱스 매핑 생성 (정렬용)
        for i, date in enumerate(date_list):
            self._date_index[date] = i
        
        # 생산 세그먼트 및 관련 인스턴스 생성 (활성화된 라인만)
        segments = self._create_production_segment_instances(json_data, order_data, active_lines)
        
        return {
            'teams': teams,
            'lines': lines,
            'products': products,
            'relations': relations,
            'changeover_rules': changeover_rules,
            'shifts': shifts,
            'days': days,
            'timeslots': timeslots,  # TimeSlot 추가
            'segments': segments,
            'continuous_runs': [], # 연속 생산 구간 제거
            'changeover_events': [] # 교체 이벤트 제거
        }

    def _clear_existing_instances(self):
        """
        기존 인스턴스 삭제
        """
        for inst in list(self.onto.individuals()):
            destroy_entity(inst)
        self.logger.info("기존 인스턴스 삭제 완료")

    def build(self, products_path, lines_path, changeover_path, order_path, start_date_str, active_lines=None):
        """
        완전한 온톨로지 빌드 파이프라인
        Args:
            products_path: str, 제품 정보 JSON 파일 경로
            lines_path: str, 라인 정보 JSON 파일 경로
            changeover_path: str, 교체 규칙 JSON 파일 경로
            order_path: str, 주문 CSV 파일 경로
            start_date_str: str, 시작 날짜 (YYYY-MM-DD)
            active_lines: list, 활성화된 라인 ID 리스트 (None이면 모든 라인 처리)
        """
        self.logger.info("=== 온톨로지 빌드 시작 ===")
        
        # 1. 데이터 로딩
        self.logger.info("1. 데이터 로딩 중...")
        json_data = self.load_json_data(products_path, lines_path, changeover_path)  # dict
        order_data = self.load_order_csv(order_path)  # dict
        
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
        results = self._create_line_product_instances(json_data, order_data, active_lines)
        
        self.logger.info(f"   - 팀: {len(results['teams'])}개")
        self.logger.info(f"   - 라인: {len(results['lines'])}개")
        self.logger.info(f"   - 제품: {len(results['products'])}개")
        self.logger.info(f"   - 시간대: {len(results['timeslots'])}개")  # TimeSlot 추가
        self.logger.info(f"   - 세그먼트: {len(results['segments'])}개")
        self.logger.info(f"   - 연속 생산 구간: {len(results['continuous_runs'])}개")
        self.logger.info(f"   - 교체 이벤트: {len(results['changeover_events'])}개")

        self.logger.info("=== 온톨로지 빌드 완료 ===")
        
        return results

