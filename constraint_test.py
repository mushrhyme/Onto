#!/usr/bin/env python3
"""
제약조건을 수동으로 추가하여 최적화 테스트
"""

from production_optimizer import ProductionOptimizer
from ontology.manager import OntologyManager
from owlready2 import get_ontology
from pulp import lpSum, LpProblem, LpMinimize

def test_with_constraints():
    """제약조건을 수동으로 추가하여 최적화 테스트"""
    
    print("🔍 제약조건을 수동으로 추가하여 최적화 테스트 시작...")
    
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
    
    # 3. 변수 생성
    print("3️⃣ 변수 생성...")
    optimizer._create_variables()
    
    # 4. 모델 초기화
    print("4️⃣ 모델 초기화...")
    optimizer.model = LpProblem("Production_With_Constraints", LpMinimize)
    
    # 5. 기본 제약조건 추가
    print("5️⃣ 기본 제약조건 추가...")
    
    # 5-1. 생산량 제약조건 (주문량 만큼만 생산)
    print("   📋 생산량 제약조건 추가...")
    for product_code in optimizer.products:
        if product_code in optimizer.order_data:
            total_production = lpSum(optimizer.variables['production'][product_code, line_id, time_slot] 
                                   for line_id in optimizer.lines 
                                   for time_slot in optimizer.ontology_timeslots)
            required_quantity = optimizer.order_data[product_code]
            optimizer.model += total_production >= required_quantity, f"production_min_{product_code}"
            optimizer.model += total_production <= required_quantity * 1.1, f"production_max_{product_code}"
            print(f"      ✅ {product_code}: {required_quantity}개")
    
    # 5-2. 시간 제약조건 (각 시간대별 가용시간)
    print("   📋 시간 제약조건 추가...")
    for time_slot in optimizer.ontology_timeslots:
        # 시간대별 가용시간 (예: 조간 10.5시간, 야간 10.5시간)
        available_time = 10.5 if "야간" in time_slot else 10.5
        if "수요일" in time_slot:
            available_time = 8.0  # 수요일은 8시간
        
        total_production_time = lpSum(optimizer.variables['production_time'][product_code, line_id, time_slot] 
                                     for product_code, line_id in optimizer.valid_product_line_combinations)
        
        optimizer.model += total_production_time <= available_time, f"time_limit_{time_slot}"
        print(f"      ✅ {time_slot}: {available_time}시간")
    
    # 5-3. 라인별 동시 생산 제약 (한 라인에서 한 번에 하나 제품만)
    print("   📋 라인별 동시 생산 제약 추가...")
    for line_id in optimizer.lines:
        for time_slot in optimizer.ontology_timeslots:
            total_products = lpSum(optimizer.variables['production'][product_code, line_id, time_slot] 
                                 for product_code in optimizer.products)
            optimizer.model += total_products <= 1, f"single_product_{line_id}_{time_slot}"
    
    # 6. 목적함수 설정
    print("6️⃣ 목적함수 설정...")
    
    # 총 생산시간 최대화 (가중치 1.0)
    total_production_time = lpSum(optimizer.variables['production_time'][i, j, k] 
                                 for i, j in optimizer.valid_product_line_combinations 
                                 for k in optimizer.ontology_timeslots)
    
    optimizer.model.objective = -total_production_time  # 최대화
    print("   ✅ 목적함수 설정 완료")
    
    # 7. 모델 상태 확인
    print("7️⃣ 모델 상태 확인...")
    print(f"   📋 모델 변수 수: {len(optimizer.variables)}")
    print(f"   📋 모델 제약조건 수: {len(optimizer.model.constraints)}")
    
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
    
    # 8. 최적화 실행
    print("8️⃣ 최적화 실행...")
    success = optimizer.solve()
    
    if success:
        print("✅ 최적화 성공!")
    else:
        print("❌ 최적화 실패!")

if __name__ == "__main__":
    test_with_constraints()
