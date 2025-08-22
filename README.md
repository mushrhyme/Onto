# 생산 최적화 시스템

이 프로젝트는 생산 라인의 최적화를 위한 온톨로지 기반 시스템입니다. Mixed Integer Linear Programming(MILP)과 OWL 온톨로지를 결합하여 효율적인 생산 스케줄을 생성합니다.

## 시스템 아키텍처

### 핵심 구성 요소 (모듈화 구조)

```
main.py (메인 실행 - 전체 워크플로우 제어)
├── ontology/ (온톨로지 관리 패키지)
│   ├── __init__.py (패키지 초기화)
│   ├── constraint_schema.py (제약조건 스키마 정의)
│   ├── constraint_validator.py (제약조건 검증)
│   ├── data_loader.py (데이터 로딩)
│   ├── instance_builder.py (인스턴스 생성)
│   ├── manager.py (온톨로지 관리 - 메인 컨트롤러)
│   ├── production_logic.py (생산 로직)
│   └── schema.py (온톨로지 스키마 정의)
├── constraint_manager.py (제약조건 관리)
├── constraint_types.py (제약조건 타입)
├── production_optimizer.py (MILP 최적화 - 메인 컨트롤러)
├── production_result_processor.py (결과 처리 및 출력)
├── config.py (설정)
├── utils.py (유틸리티)
└── results/ (결과 파일 저장)
```

## 제약조건 목록 및 종속성

이 섹션에서는 생산 최적화 시스템에 적용된 제약조건과 그 종속성을 설명합니다.

#### 1. 생산량 제약조건
- **설명**: 유효한 제품-라인 조합에 대해 목표 생산량을 박스 단위로 설정합니다.
- **종속성**: 유효한 제품-라인 조합이 존재해야 합니다.

#### 2. 시간 제약조건
- **설명**: 각 라인과 시간대에 대해 최대 및 최소 가동시간을 설정합니다.
- **종속성**: 시간 슬롯과 라인 정보가 필요합니다.

#### 3. 블록 연속성 제약조건
- **설명**: 제품별 목표 생산량과 라인별 생산 능력을 바탕으로 필요한 시간대 개수를 계산하고, 이를 연속된 블록으로 배치합니다.
- **종속성**: `block_start` 변수가 필요합니다.

#### 4. 다중 제품 허용 제약조건
- **설명**: 시간대 내 다중 제품 생산을 허용하며, 소량 생산 기준을 적용합니다.
- **종속성**: 각 제품의 목표 생산량과 시간당 박스 생산량이 필요합니다.

#### 5. 교체 횟수 제약조건
- **설명**: 각 라인과 시간대에 대해 교체 횟수를 제한합니다.
- **종속성**: 교체 결정 변수와 교체 시간 변수가 필요합니다.

#### 6. 총 교체 횟수 제한
- **설명**: 전체 교체 횟수를 최대 5회로 제한합니다.
- **종속성**: 각 라인과 시간대의 교체 횟수 합계가 필요합니다.

#### 7. 작업 준비 및 청소 시간 제약조건
- **설명**: 각 라인에 대해 작업 준비 시간과 청소 시간을 설정합니다.
- **종속성**: 각 라인의 첫 번째 및 마지막 시간대에 대한 정보가 필요합니다.

#### 8. 제품 순서 제약조건
- **설명**: 시간대 내 제품 생산 순서를 설정합니다.
- **종속성**: `sequence` 변수가 필요합니다.

#### 9. 개선된 교체 제약조건
- **설명**: 실제 제품 순서 기반으로 교체를 고려합니다.
- **종속성**: 연속된 시간대 간의 제품 순서 정보가 필요합니다.

#### 10. 호기별 특정 제약조건
- **설명**: 각 호기에 대해 특정 제약조건을 추가합니다.
- **종속성**: `LineConstraintConfig`에 정의된 제약조건이 필요합니다.

이러한 제약조건들은 `constraint_manager.py`와 `production_optimizer.py` 파일에 구현되어 있으며, 각 제약조건은 `ConstraintManager` 클래스의 메서드를 통해 추가됩니다.

## 실행 방법

### 기본 실행
```bash
# ontology 환경 활성화
conda activate ontology

# 메인 스크립트 실행
python main.py
```

## 결과 파일

실행 결과는 `results/` 폴더에 타임스탬프별로 저장됩니다:

- `production_schedule_YYYYMMDD_HHMMSS.xlsx` - Excel 형태의 생산 일정
- `production_schedule_detail_YYYYMMDD_HHMMSS.json` - 상세 JSON 데이터
- `logs/optimization_YYYYMMDD_HHMMSS.log` - 실행 로그

## 개발자 가이드

### 새로운 제약조건 추가
1. `constraint_types.py`에 새 제약조건 타입 추가
2. `constraint_setup.py`에 설정 함수 추가
3. `production_optimizer.py`에 MILP 제약조건 구현
4. `constraint_validator.py`에 검증 로직 추가

### 새로운 최적화 목표 추가
1. `production_optimizer.py`의 `weights` 딕셔너리에 가중치 추가
2. `_build_objective_function()` 메서드에 목적 함수 항 추가
3. 필요시 새로운 변수 및 제약조건 정의

## 성능 최적화

- **병렬 처리**: 라인별 독립적 처리 가능
- **메모리 관리**: 대용량 데이터셋 지원
- **캐싱**: 반복 계산 최소화
- **로깅**: 상세한 성능 모니터링
