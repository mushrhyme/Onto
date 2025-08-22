from owlready2 import Thing, ObjectProperty, DataProperty, get_ontology
import datetime

def create_constraint_schema(onto):
    """
    제약조건 검증을 위한 온톨로지 스키마 확장
    v0 방식의 표준적인 owlready2 스타일을 사용합니다.
    constraint_validator.py에서 실제 사용되는 클래스와 속성만 포함합니다.
    
    Args:
        onto: owlready2 온톨로지 객체
    """
    with onto:
        # 제약조건 관련 클래스 정의 (실제 사용되는 것들만)
        class TimeConflict(Thing): pass
        class CapacityViolation(Thing): pass
        class ChangeoverConflict(Thing): pass
        class PriorityViolation(Thing): pass
        class SequenceViolation(Thing): pass
        class ViolationExplanation(Thing): pass

        # 제약조건 관련 데이터 속성 정의 (constraint_validator.py에서 실제 사용되는 것들만)
        
        # TimeConflict 관련 (실제 사용: hasTimeConflict, hasConflictStartTime, hasConflictEndTime, hasConflictDuration)
        class hasTimeConflict(ObjectProperty): 
            domain = [TimeConflict]; 
            range = [onto.ProductionSegment]  # 직접 참조
        
        class hasConflictStartTime(DataProperty): 
            domain = [TimeConflict]; 
            range = [datetime.datetime]
        
        class hasConflictEndTime(DataProperty): 
            domain = [TimeConflict]; 
            range = [datetime.datetime]
        
        class hasConflictDuration(DataProperty): 
            domain = [TimeConflict]; 
            range = [float]

        # CapacityViolation 관련 (실제 사용: hasCapacityExcess, hasCapacityShortage)
        class hasCapacityExcess(DataProperty): 
            domain = [CapacityViolation]; 
            range = [float]
        
        class hasCapacityShortage(DataProperty): 
            domain = [CapacityViolation]; 
            range = [float]

        # ChangeoverConflict 관련 (실제 사용: hasChangeoverOverlap, hasInefficientChangeover)
        class hasChangeoverOverlap(DataProperty): 
            domain = [ChangeoverConflict]; 
            range = [float]
        
        class hasInefficientChangeover(DataProperty): 
            domain = [ChangeoverConflict]; 
            range = [bool]

        # PriorityViolation 관련 (실제 사용: hasPriorityViolation, hasPriorityLevel)
        class hasPriorityViolation(ObjectProperty): 
            domain = [PriorityViolation]; 
            range = [onto.Product]  # 직접 참조
        
        class hasPriorityLevel(DataProperty): 
            domain = [PriorityViolation]; 
            range = [int]

        # SequenceViolation 관련 (실제 사용: hasSequenceViolation, hasRequiredSequence)
        class hasSequenceViolation(ObjectProperty): 
            domain = [SequenceViolation]; 
            range = [onto.ProductionSegment]  # 직접 참조
        
        class hasRequiredSequence(DataProperty): 
            domain = [SequenceViolation]; 
            range = [str]

        # ViolationExplanation 관련 (실제 사용: hasExplanation, hasRootCause, hasImpactAnalysis)
        class hasExplanation(DataProperty): 
            domain = [ViolationExplanation]; 
            range = [str]
        
        class hasRootCause(DataProperty): 
            domain = [ViolationExplanation]; 
            range = [str]
        
        class hasImpactAnalysis(DataProperty): 
            domain = [ViolationExplanation]; 
            range = [str]

        # 필요한 경우에만 제약조건 추가 (선택적)
        # TimeConflict은 최소 2개의 세그먼트가 있어야 충돌
        TimeConflict.is_a.append(hasTimeConflict.min(2))
        
        # CapacityViolation은 용량 초과 또는 부족 중 하나는 있어야 함
        CapacityViolation.is_a.append(hasCapacityExcess.max(1))
        CapacityViolation.is_a.append(hasCapacityShortage.max(1))
        
        # ViolationExplanation은 반드시 설명이 있어야 함
        ViolationExplanation.is_a.append(hasExplanation.exactly(1))

    return onto  # owlready2 온톨로지 객체 (정의 추가됨) 