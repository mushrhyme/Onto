#!/usr/bin/env python3
"""
최소한의 제약조건으로 최적화 테스트
"""

from production_optimizer import ProductionOptimizer
from ontology.manager import OntologyManager
from owlready2 import get_ontology
from pulp import lpSum, LpProblem, LpMinimize

def test_minimal_optimization():
    """최소한의 제약조건으로 최적화 테스트"""
    
    print("🔍 최소한의 제약조건으로 최적화 테스트 시작...")
    
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
    
    # 3. 변수만 생성 (제약조건 없이)
    print("3️⃣ 변수만 생성 (제약조건 없이)...")
    optimizer._create_variables()
    
    # 4. 모델 직접 초기화
    print("4️⃣ 모델 직접 초기화...")
    optimizer.model = LpProblem("Minimal_Production_Test", LpMinimize)
    
    # 5. 간단한 목적함수 설정
    print("5️⃣ 간단한 목적함수 설정...")
    
    # 1. 총 생산시간 최대화
    total_production_time = lpSum(optimizer.variables['production_time'][i, j, k] 
                                 for i, j in optimizer.valid_product_line_combinations 
                                 for k in optimizer.ontology_timeslots)
    
    # 목적함수를 모델에 설정 (올바른 방법)
    optimizer.model.objective = -total_production_time  # 가중치 1.0, 최대화
    print("   ✅ 간단한 목적함수 설정 완료")
    
    # 6. 모델 상태 확인
    print("6️⃣ 모델 상태 확인...")
    print(f"   📋 모델 변수 수: {len(optimizer.variables)}")
    print(f"   📋 모델 제약조건 수: {len(optimizer.model.constraints)}")
    
    # 변수별 상태 확인
    for var_name, var_dict in optimizer.variables.items():
        if isinstance(var_dict, dict):
            print(f"   📋 {var_name}: {len(var_dict)}개")
        else:
            print(f"   📋 {var_name}: {type(var_dict)}")
    
    # 7. 최적화 실행
    print("7️⃣ 최적화 실행...")
    success = optimizer.solve()
    
    if success:
        print("✅ 최적화 성공!")
    else:
        print("❌ 최적화 실패!")
        
        # 8. 실패 원인 분석
        print("8️⃣ 실패 원인 분석...")
        
        # 제약조건 상세 분석
        print(f"   📋 총 제약조건 수: {len(optimizer.model.constraints)}")
        
        # 제약조건 타입별 분류
        constraint_types = {}
        for constraint in optimizer.model.constraints.values():
            constraint_name = constraint.name
            if constraint_name:
                constraint_type = constraint_name.split('_')[0] if '_' in constraint_name else 'unknown'
                constraint_types[constraint_type] = constraint_types.get(constraint_type, 0) + 1
        
        print("   📋 제약조건 타입별 분류:")
        for constraint_type, count in constraint_types.items():
            print(f"      - {constraint_type}: {count}개")

if __name__ == "__main__":
    test_minimal_optimization()
