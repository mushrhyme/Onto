#!/usr/bin/env python3
"""
실제 최적화 실행 테스트
"""

from production_optimizer import ProductionOptimizer
from ontology.manager import OntologyManager
from owlready2 import get_ontology

def test_optimization():
    """실제 최적화 실행 테스트"""
    
    print("🔍 실제 최적화 실행 테스트 시작...")
    
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
    
    # 4. 최적화 실행
    print("4️⃣ 최적화 실행...")
    success = optimizer.solve()
    
    if success:
        print("✅ 최적화 성공!")
        
        # 5. 결과 추출
        print("5️⃣ 결과 추출...")
        solution = optimizer.extract_solution()
        
        print(f"   📊 총 생산시간: {solution['statistics']['total_production_time']:.2f}시간")
        print(f"   📊 총 교체시간: {solution['statistics']['total_changeover_time']:.2f}시간")
        print(f"   📊 총 청소시간: {solution['statistics']['total_cleaning_time']:.2f}시간")
        print(f"   📊 총 작업시간: {solution['statistics']['total_working_time']:.2f}시간")
        
        print(f"   🔄 교체 이벤트: {len(solution['changeover_events'])}개")
        print(f"   🧹 청소 이벤트: {len(solution['cleaning_events'])}개")
        
    else:
        print("❌ 최적화 실패!")
        
        # 6. 실패 원인 분석
        print("6️⃣ 실패 원인 분석...")
        
        # 모델 상태 확인
        print(f"   📋 모델 변수 수: {len(optimizer.variables)}")
        print(f"   📋 모델 제약조건 수: {len(optimizer.model.constraints)}")
        
        # 변수별 상태 확인
        for var_name, var_dict in optimizer.variables.items():
            if isinstance(var_dict, dict):
                print(f"   📋 {var_name}: {len(var_dict)}개")
            else:
                print(f"   📋 {var_name}: {type(var_dict)}")

if __name__ == "__main__":
    test_optimization()
