#!/usr/bin/env python3
"""
cleaning_time 변수 접근 테스트
"""

from production_optimizer import ProductionOptimizer
from ontology.manager import OntologyManager
from owlready2 import get_ontology

def test_cleaning_time_access():
    """cleaning_time 변수 접근 테스트"""
    
    print("🔍 cleaning_time 변수 접근 테스트 시작...")
    
    # 1. 온톨로지 매니저 초기화
    print("1️⃣ 온톨로지 매니저 초기화...")
    onto = get_ontology("http://test.org/factory.owl")
    ontology_manager = OntologyManager(onto, monday_date="2025-09-01")
    ontology_manager.build(
        products_path="../metadata/products.json",
        lines_path="../metadata/lines.json", 
        changeover_path="../metadata/change_over.json",
        order_path="../metadata/order.csv",
        start_date_str="2025-09-01"
    )
    
    # 2. ProductionOptimizer 생성
    print("2️⃣ ProductionOptimizer 생성...")
    optimizer = ProductionOptimizer(ontology_manager, active_lines=['13'])
    
    # 3. 모델 구축
    print("3️⃣ 모델 구축...")
    optimizer.build_model()
    
    # 4. cleaning_time 변수 확인
    print("4️⃣ cleaning_time 변수 확인...")
    
    if 'cleaning_time' in optimizer.variables:
        print(f"✅ cleaning_time 변수 존재: {len(optimizer.variables['cleaning_time'])}개")
        
        # 첫 번째 키 확인
        first_key = list(optimizer.variables['cleaning_time'].keys())[0]
        print(f"   첫 번째 키: {first_key}")
        
        # 변수 타입 확인
        var_type = type(optimizer.variables['cleaning_time'][first_key])
        print(f"   변수 타입: {var_type}")
        
        # 라인과 시간대 확인
        print(f"   라인 수: {len(optimizer.lines)}")
        print(f"   시간대 수: {len(optimizer.ontology_timeslots)}")
        
        # 예상 키 수
        expected_keys = len(optimizer.lines) * len(optimizer.ontology_timeslots)
        print(f"   예상 키 수: {expected_keys}")
        print(f"   실제 키 수: {len(optimizer.variables['cleaning_time'])}")
        
    else:
        print("❌ cleaning_time 변수가 존재하지 않습니다!")
        print(f"   사용 가능한 변수: {list(optimizer.variables.keys())}")
    
    # 5. 목적함수 설정 시도
    print("5️⃣ 목적함수 설정 시도...")
    try:
        optimizer._set_objective_function()
        print("✅ 목적함수 설정 성공!")
    except Exception as e:
        print(f"❌ 목적함수 설정 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_cleaning_time_access()
