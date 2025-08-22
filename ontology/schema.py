from owlready2 import Thing, ObjectProperty, DataProperty, get_ontology
import datetime

def create_schema(onto):
    """
    온톨로지 클래스, 객체/데이터 속성을 정의합니다.
    v0 방식의 표준적인 owlready2 스타일을 사용합니다.
    
    Args:
        onto: owlready2 온톨로지 객체
    Returns:
        onto: 정의가 추가된 온톨로지 객체
    """
    with onto:
        # === 클래스 정의 ===
        class Team(Thing): pass  # 팀 클래스
        class Line(Thing): pass  # 생산 라인 클래스
        class Product(Thing): pass  # 제품 클래스
        class LineProductRelation(Thing): pass  # 라인-제품 관계 클래스
        class ChangeoverRule(Thing): pass  # 교체 규칙 클래스
        class Shift(Thing): pass  # 근무조(시프트) 클래스
        class Day(Thing): pass  # 날짜 클래스
        class ProductionSchedule(Thing): pass  # 생산 일정 클래스
        class ProductionSegment(Thing): pass  # 생산 세그먼트(작업 단위) 클래스
        class ChangeoverEvent(Thing): pass  # 교체 이벤트 클래스
        class ContinuousProductionRun(Thing): pass  # 연속 생산 구간 클래스
        class ProductionRunStart(Thing): pass  # 생산 구간 시작점 클래스
        class ProductionRunEnd(Thing): pass  # 생산 구간 종료점 클래스

        # === 객체 속성(ObjectProperty) 정의 ===
        class hasTeam(ObjectProperty): 
            domain = [Line]; 
            range = [Team]  # 라인은 팀을 가짐 (예: line.hasTeam = [team])
        
        class hasLine(ObjectProperty): 
            domain = [LineProductRelation]; 
            range = [Line]  # 라인-제품 관계는 라인을 가짐
        
        class handlesProduct(ObjectProperty): 
            domain = [LineProductRelation]; 
            range = [Product]  # 라인-제품 관계는 제품을 가짐
        
        class appliesTo(ObjectProperty): 
            domain = [ChangeoverRule]; 
            range = [Line]  # 교체 규칙은 특정 라인에 적용됨
        
        class hasShift(ObjectProperty): 
            domain = [Day]; 
            range = [Shift]  # 날짜는 시프트를 가짐
        
        class containsSegment(ObjectProperty): 
            domain = [ProductionSchedule]; 
            range = [ProductionSegment]  # 생산 일정은 여러 세그먼트를 포함
        
        class scheduledForDay(ObjectProperty): 
            domain = [ProductionSchedule]; 
            range = [Day]  # 생산 일정은 특정 날짜에 할당됨
        
        class occursInLine(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Line]  # 세그먼트는 특정 라인에서 발생
        
        class occursOnDay(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Day]  # 세그먼트는 특정 날짜에 발생
        
        class occursInShift(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Shift]  # 세그먼트는 특정 시프트에 발생
        
        class producesProduct(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Product]  # 세그먼트는 특정 제품을 생산
        
        class nextSegment(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [ProductionSegment]  # 다음 세그먼트와 연결
        
        class triggersEvent(ObjectProperty): 
            domain = [ChangeoverEvent]; 
            range = [ProductionSegment]  # 교체 이벤트가 트리거하는 세그먼트
        
        class startsRun(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [ProductionRunStart]  # 세그먼트가 생산 구간 시작점과 연결
        
        class endsRun(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [ProductionRunEnd]  # 세그먼트가 생산 구간 종료점과 연결
        
        class hasRunStart(ObjectProperty): 
            domain = [ContinuousProductionRun]; 
            range = [ProductionRunStart]  # 연속 생산 구간의 시작점
        
        class hasRunEnd(ObjectProperty): 
            domain = [ContinuousProductionRun]; 
            range = [ProductionRunEnd]  # 연속 생산 구간의 종료점
        
        class runContainsSegment(ObjectProperty): 
            domain = [ContinuousProductionRun]; 
            range = [ProductionSegment]  # 연속 생산 구간이 포함하는 세그먼트

        # === 데이터 속성(DataProperty) 정의 ===
        # Product(제품) 관련
        class hasProductCode(DataProperty): 
            domain = [Product]; 
            range = [str]  # 제품 코드 (예: 'P001')
        
        class hasProductName(DataProperty): 
            domain = [Product]; 
            range = [str]  # 제품명 (예: '초코파이')
        
        class hasCategory(DataProperty): 
            domain = [Product]; 
            range = [str]  # 제품 카테고리 (예: '스낵')
        
        class hasProductType(DataProperty): 
            domain = [Product]; 
            range = [str]  # 제품 타입 (예: '식품')
        
        class hasChangeoverGroup(DataProperty): 
            domain = [Product]; 
            range = [str]  # 교체 그룹 (예: 'A')
        
        class hasWeight(DataProperty): 
            domain = [Product]; 
            range = [int]  # 중량 (예: 100)
        
        class hasPackageCount(DataProperty): 
            domain = [Product]; 
            range = [int]  # 포장 단위 수량 (예: 10)
        
        class hasProductsPerBox(DataProperty): 
            domain = [Product]; 
            range = [int]  # 박스당 제품 수 (예: 20)

        # Line(생산 라인) 관련
        class hasLineCategory(DataProperty): 
            domain = [Line]; 
            range = [str]  # 라인 카테고리 (예: '자동')
        
        class hasLineType(DataProperty): 
            domain = [Line]; 
            range = [str]  # 라인 타입 (예: '포장')
        
        class hasTrackCount(DataProperty): 
            domain = [Line]; 
            range = [int]  # 트랙 수 (예: 2)
        
        class hasSetupTime(DataProperty): 
            domain = [Line]; 
            range = [float]  # 셋업(준비) 시간 (예: 1.5)
        
        class hasCleanupTime(DataProperty): 
            domain = [Line]; 
            range = [float]  # 청소 시간 (예: 0.5)
        
        class hasNormalWorkingTime(DataProperty): 
            domain = [Line]; 
            range = [float]  # 정상 근무 시간 (예: 8.0)
        
        class hasExtendedWorkingTime(DataProperty): 
            domain = [Line]; 
            range = [float]  # 연장 근무 시간 (예: 2.0)
        
        class hasNormalCapacity(DataProperty): 
            domain = [Line]; 
            range = [int]  # 정상 용량 (예: 1000)
        
        class hasExtendedCapacity(DataProperty): 
            domain = [Line]; 
            range = [int]  # 연장 용량 (예: 1200)
        
        class hasMaxDailyCapacity(DataProperty): 
            domain = [Line]; 
            range = [int]  # 일일 최대 용량 (예: 1500)

        # LineProductRelation(라인-제품 관계) 관련
        class hasCTRate(DataProperty): 
            domain = [LineProductRelation]; 
            range = [float]  # CT(사이클타임) 비율 (예: 0.95)

        # ChangeoverRule(교체 규칙) 관련
        class hasFromCondition(DataProperty): 
            domain = [ChangeoverRule]; 
            range = [str]  # 이전 조건 (예: 'A')
        
        class hasToCondition(DataProperty): 
            domain = [ChangeoverRule]; 
            range = [str]  # 이후 조건 (예: 'B')
        
        class hasChangeoverTimeValue(DataProperty): 
            domain = [ChangeoverRule]; 
            range = [float]  # 교체 시간 값 (예: 0.5)
        
        class hasRuleDescription(DataProperty): 
            domain = [ChangeoverRule]; 
            range = [str]  # 규칙 설명 (예: 'A→B 교체')

        # Shift(시프트) 관련
        class hasShiftType(DataProperty): 
            domain = [Shift]; 
            range = [str]  # 시프트 타입 (예: '주간')
        
        class hasShiftName(DataProperty): 
            domain = [Shift]; 
            range = [str]  # 시프트명 (예: '1조')

        # Day(날짜) 관련
        class hasMaxWorkingTime(DataProperty): 
            domain = [Day]; 
            range = [float]  # 최대 근무 시간 (예: 10.0)

        # ProductionSchedule(생산 일정) 관련
        class hasScheduleDate(DataProperty): 
            domain = [ProductionSchedule]; 
            range = [str]  # 일정 날짜 (예: '2025-07-21')
        
        class hasTotalProductionTime(DataProperty): 
            domain = [ProductionSchedule]; 
            range = [float]  # 총 생산 시간 (예: 7.5)
        
        class hasTotalChangeoverTime(DataProperty): 
            domain = [ProductionSchedule]; 
            range = [float]  # 총 교체 시간 (예: 1.0)

        # ProductionSegment(생산 세그먼트) 관련
        class hasProductionHours(DataProperty): 
            domain = [ProductionSegment]; 
            range = [float]  # 생산 시간 (예: 2.0)
        
        class hasChangeoverHours(DataProperty): 
            domain = [ProductionSegment]; 
            range = [float]  # 교체 시간 (예: 0.5)
        
        class hasCleaningHours(DataProperty): 
            domain = [ProductionSegment]; 
            range = [float]  # 청소 시간 (예: 0.2)
        
        class hasTotalSegmentHours(DataProperty): 
            domain = [ProductionSegment]; 
            range = [float]  # 세그먼트 총 소요 시간 (예: 2.7)
        
        class hasProductionQuantity(DataProperty): 
            domain = [ProductionSegment]; 
            range = [int]  # 생산 수량 (예: 100)
        
        class hasSegmentDate(DataProperty): 
            domain = [ProductionSegment]; 
            range = [datetime.date]  # 세그먼트 날짜 (예: datetime.date(2025,7,21))

        # ContinuousProductionRun(연속 생산 구간) 관련
        class hasRunDuration(DataProperty): 
            domain = [ContinuousProductionRun]; 
            range = [float]  # 연속 생산 구간 소요 시간 (예: 5.0)
        
        class hasRunProduct(DataProperty): 
            domain = [ContinuousProductionRun]; 
            range = [str]  # 연속 생산 제품 코드 (예: 'P001')

        # ProductionRunStart/End(생산 구간 시작/종료) 관련
        class hasRunStartTime(DataProperty): 
            domain = [ProductionRunStart]; 
            range = [str]  # 시작 시각 (예: '08:00')
        
        class hasRunEndTime(DataProperty): 
            domain = [ProductionRunEnd]; 
            range = [str]  # 종료 시각 (예: '12:00')

        # === 제약조건(Constraint) 정의 ===
        # Product는 반드시 제품 코드를 가져야 함 (예: Product.hasProductCode = 'P001')
        Product.is_a.append(hasProductCode.exactly(1))
        
        # ProductionSegment는 반드시 라인, 날짜, 시프트, 제품을 가져야 함
        ProductionSegment.is_a.append(occursInLine.exactly(1))
        ProductionSegment.is_a.append(occursOnDay.exactly(1))
        ProductionSegment.is_a.append(occursInShift.exactly(1))
        ProductionSegment.is_a.append(producesProduct.exactly(1))
        
        # 시간 관련 속성들은 선택적 (0 또는 1개)
        ProductionSegment.is_a.append(hasCleaningHours.max(1))
        ProductionSegment.is_a.append(hasChangeoverHours.max(1))

    return onto  # owlready2 온톨로지 객체 (정의 추가됨, 예: onto.Product, onto.Line 등 사용 가능)