# ontology 패키지
"""
온톨로지 관리 모듈 패키지

이 패키지는 온톨로지 생성 및 관리를 위한 핵심 모듈들을 포함합니다:
- manager: 온톨로지 생성 및 관리의 중앙 컨트롤러 (기존 ontology_manager.py)
- schema: OWL 온톨로지 스키마 정의 (기존 ontology_schema.py)
- data_loader: 외부 데이터 파일 로딩
- instance_builder: 온톨로지 인스턴스 생성
- production_logic: 생산 관련 비즈니스 로직
- constraint_validator: 생성된 스케줄의 제약조건 검증
"""

from .manager import OntologyManager
from .data_loader import load_json_data, load_order_csv
from .schema import create_schema
from .instance_builder import create_team_instances, create_line_instances, create_product_instances
from .production_logic import create_production_segments, create_changeover_event_instances
from .constraint_validator import ConstraintValidator

__all__ = [
    'OntologyManager',
    'load_json_data', 
    'load_order_csv',
    'create_schema',
    'create_team_instances',
    'create_line_instances', 
    'create_product_instances',
    'create_production_segments',
    'create_changeover_event_instances',
    'ConstraintValidator'
]
