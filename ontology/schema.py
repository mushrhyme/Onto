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
        class TimeSlot(Thing): pass  # 시간대 클래스 (예: '월요일_조간', '월요일_야간')
        class ProductionSegment(Thing): pass  # 생산 세그먼트(작업 단위) 클래스

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
        
        # === TimeSlot 관련 객체 속성들 ===
        class hasDay(ObjectProperty): 
            domain = [TimeSlot]; 
            range = [Day]  # 시간대는 특정 날짜에 속함
        
        class hasShift(ObjectProperty): 
            domain = [TimeSlot]; 
            range = [Shift]  # 시간대는 특정 시프트에 속함
        
        class nextTimeSlot(ObjectProperty): 
            domain = [TimeSlot]; 
            range = [TimeSlot]  # 다음 시간대와의 순서 관계
        
        class previousTimeSlot(ObjectProperty): 
            domain = [TimeSlot]; 
            range = [TimeSlot]  # 이전 시간대와의 순서 관계
        
        class occursInLine(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Line]  # 세그먼트는 특정 라인에서 발생
        
        class occursOnDay(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Day]  # 세그먼트는 특정 날짜에 발생
        
        class occursInShift(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Shift]  # 세그먼트는 특정 시프트에 발생
        
        class occursInTimeSlot(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [TimeSlot]  # 세그먼트는 특정 시간대에 발생
        
        class producesProduct(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [Product]  # 세그먼트는 특정 제품을 생산
        
        class nextSegment(ObjectProperty): 
            domain = [ProductionSegment]; 
            range = [ProductionSegment]  # 다음 세그먼트와 연결

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

        class hasRuleType(DataProperty): 
            domain = [ChangeoverRule]; 
            range = [str]  # 규칙 타입 (예: 'units_per_pack', 'product_type', 'height', 'market_type', 'universal')

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

        # === TimeSlot 관련 데이터 속성들 ===
        class hasTimeSlotName(DataProperty): 
            domain = [TimeSlot]; 
            range = [str]  # 시간대 이름 (예: '월요일_조간')
        
        class hasWorkingHours(DataProperty): 
            domain = [TimeSlot]; 
            range = [float]  # 시간대별 작업 시간 (예: 10.5)
        
        class hasStartTime(DataProperty): 
            domain = [TimeSlot]; 
            range = [float]  # 시작 시간 (예: 0.0)
        
        class hasEndTime(DataProperty): 
            domain = [TimeSlot]; 
            range = [float]  # 종료 시간 (예: 10.5)

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

        # === 제약조건(Constraint) 정의 ===
        # Product는 반드시 제품 코드를 가져야 함 (예: Product.hasProductCode = 'P001')
        Product.is_a.append(hasProductCode.exactly(1))
        
        # TimeSlot은 반드시 날짜와 시프트를 가져야 함
        TimeSlot.is_a.append(hasDay.exactly(1))
        TimeSlot.is_a.append(hasShift.exactly(1)) # 수정된 속성 이름
        TimeSlot.is_a.append(hasTimeSlotName.exactly(1))
        TimeSlot.is_a.append(hasWorkingHours.exactly(1))
        
        # ProductionSegment는 반드시 라인, 날짜, 시프트, 제품, 시간대를 가져야 함
        ProductionSegment.is_a.append(occursInLine.exactly(1))
        ProductionSegment.is_a.append(occursOnDay.exactly(1))
        ProductionSegment.is_a.append(occursInShift.exactly(1))
        ProductionSegment.is_a.append(producesProduct.exactly(1))
        ProductionSegment.is_a.append(occursInTimeSlot.exactly(1))
        
        # 시간 관련 속성들은 선택적 (0 또는 1개)
        ProductionSegment.is_a.append(hasCleaningHours.max(1))
        ProductionSegment.is_a.append(hasChangeoverHours.max(1))

    return onto  # owlready2 온톨로지 객체 (정의 추가됨, 예: onto.Product, onto.Line 등 사용 가능)