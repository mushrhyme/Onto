#!/usr/bin/env python3
"""
최종 진단: ProductionOptimizer의 build_model 메서드를 직접 호출
"""

from production_optimizer import ProductionOptimizer
from ontology.manager import OntologyManager
from owlready2 import get_ontology

def final_diagnosis():
    """최종 진단: ProductionOptimizer의 build_model 메서드를 직접 호출"""
    
    print("🔍 === 최종 진단: ProductionOptimizer의 build_model 메서드를 직접 호출 ===")
    
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
    
    # 3. build_model 메서드 직접 호출
    print("3️⃣ build_model 메서드 직접 호출...")
    try:
        optimizer.build_model()
        print("   ✅ build_model 메서드 호출 성공!")
        
        # 4. 모델 상태 확인
        print("4️⃣ 모델 상태 확인...")
        print(f"   📋 모델 변수 수: {len(optimizer.variables)}")
        print(f"   📋 모델 제약조건 수: {len(optimizer.model.constraints)}")
        
        # 변수별 상태 확인
        for var_name, var_dict in optimizer.variables.items():
            if isinstance(var_dict, dict):
                print(f"   📋 {var_name}: {len(var_dict)}개")
            else:
                print(f"   📋 {var_name}: {type(var_dict)}")
        
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
        
        # 5. 최적화 실행
        print("5️⃣ 최적화 실행...")
        success = optimizer.solve()
        
        if success:
            print("✅ 최적화 성공!")
        else:
            print("❌ 최적화 실패!")
            
    except Exception as e:
        print(f"   ❌ build_model 메서드 호출 실패: {e}")
        print(f"   📋 오류 타입: {type(e).__name__}")
        print(f"   📋 오류 상세: {str(e)}")

if __name__ == "__main__":
    final_diagnosis()
