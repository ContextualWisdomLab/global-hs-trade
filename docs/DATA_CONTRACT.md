# 입력·집계 계약

최소 JSONL 관측 형태는 `scripts/create_demo.py`의 `demo_records()`에서 확인할 수 있습니다. 숫자는 소수점 정밀도 손실을 피하기 위해 문자열로 입력하십시오. HS코드는 반드시 문자열입니다. 원천에는 사용권 정책이 먼저 등록되어 있어야 합니다.

| 필드 | 규칙 |
|---|---|
| source_identifier | 등록된 원천 ID. 같은 공급사라도 계약·배포본·자료 성격이 다르면 분리 |
| source_record_identifier / source_version | 원천 내 거래행 ID와 양의 버전 번호. 재시도용 임의 UUID로 매번 바꾸지 않음 |
| period / date_basis | YYYY-MM과 해당 월의 기준. 도착 월·수리 월·선적 월을 구분 |
| reporter_country / recorded_flow | ISO2 또는 ISO3 신고국, 그 신고국 기준 M/X. 원천이 명시한 국가만 입력 |
| hs_code / hs_revision / hs_code_origin | 6~12자리 코드 원문, HS1992~HS2022 또는 UNKNOWN, declared/reported/provider_inferred/user_inferred |
| record_kind | customs_line, bill_of_lading, trader_presence |
| value / value_currency / value_basis / value_origin | 정확한 십진 문자열 또는 null, 통화 코드, FOB/CIF/CUSTOMS/UNKNOWN, reported/estimated/missing |
| net_weight_kg / gross_weight_kg | 각각 kg 기준. 총중량을 순중량에 복사하지 않음 |
| quantity / quantity_unit | 쌍으로 제공. PKG는 상품 개수가 아니라 포장 수일 수 있음 |
| partner_country / partner_basis | 상대국과 원천상의 정의. 불명확하면 null/unknown |
| origin_country / dispatch_country / destination_country | 각각 원산지·출발국·도착국. 기업 소재지에서 자동 추정하지 않음 |
| parties | role, legal_name, country_code, external_identifier 또는 등록번호 정보 |
| event_status | active 또는 cancelled. 취소도 기존 ID의 새 버전으로 입력 |
| document_key | 선택 필드. namespace, identifier, line_identifier, verified. 행 식별이 불명확하면 생략 |
| source_url / retrieved_at | 원천 HTTPS 주소 및 시간대가 있는 수집 시각 |

## 기업 식별

등록번호는 `registry_namespace`, `registry_identifier`, `country_code`를 함께 제공해야 합니다. 등록번호의 유효성을 온라인 조회하는 기능은 없습니다. 원천이 제공한 등록번호 주장으로 취급합니다. 등록번호가 없으면 해당 원천 내 `external_identifier`를 사용합니다. 회사 이름만으로 새 식별자를 계속 생성하면 중복이 생기므로 원천 기업 ID를 유지하십시오.

인접 국가의 동일한 등록번호나 비슷한 상호는 자동 병합하지 않습니다. 본사·자회사·포워더·제조사를 서로 다른 역할과 실체로 남깁니다. 같은 원천 ID의 이름 표기 차이는 같은 집계에 묶고 이름 목록을 보존합니다. 미확인 소재국은 null로 두어야 합니다.

## 무역금액 해석

금액 합계는 원천·기업·역할·HS6·개정판·월·신고국·방향·상대국 정의·통화·평가기준·관측 종류별로 나뉩니다. `reported`와 `estimated`를 합치지 않습니다. 금액 없는 행은 null이며 `missing_value_observations`에 반영합니다. 추정금액 필드는 외부에서 이미 검증한 값을 수용하기 위한 것으로, 이 프로그램이 누락 거래의 금액을 계산하는 것은 아닙니다.

HS6만 같은 여러 국내 세번은 같은 조건일 때 HS6로 합산합니다. 원문 세번은 관측 원장에 남습니다. 여러 HS가 적힌 화물의 전체 금액을 각 HS에 복사한 데이터는 입력해서는 안 됩니다. 단일 필드의 복수 HS 목록은 거부하지만, 원천이 서로 다른 ID로 중복 배분한 금액까지 자동 발견하지는 못합니다. 품목행의 금액 배분 근거를 입력 단계에서 검증해야 합니다.

## 정정·중복

같은 원천·레코드·버전의 내용이 같으면 재수집으로 계산합니다. 수집 시각만 바뀐 경우에도 중복 삽입하지 않습니다. 같은 버전의 내용이 다르면 오류에 남기고 새 버전 제출을 요구합니다. 가장 높은 버전이 취소이면 이전 버전을 집계에 되살리지 않습니다.

출처 간 대조는 verified가 명시된 동일 문서/품목행 키에 한정합니다. 이 플래그는 입력자의 확인 진술이지 프로그램이 문서를 독립적으로 검증했다는 뜻이 아닙니다. 대조 결과는 일치 또는 충돌이며 자동 원천 선택·글로벌 합계는 없습니다. 수출 신고와 상대국 수입 신고는 날짜·평가기준·법적 문서가 달라 하나의 같은 신고행으로 간주하지 않습니다.

## 파일 입력·오류

파일 상한은 128 MiB입니다. 더 큰 파일은 원천의 안정적인 키를 유지하며 나누어 입력하십시오. 정상 관측은 최대 500행의 짧은 쓰기 트랜잭션 단위로 저장합니다. 파싱·API 통신·정규화는 그 밖에서 수행합니다. 일부 오류가 나면 오류 목록과 비정상 종료 코드를 확인하십시오. SQLite는 짧은 쓰기 잠금을 사용하며 잠금이 전혀 없다는 뜻은 아닙니다.

CSV는 매핑된 모든 열이 있어야 합니다. 쉼표가 포함된 천 단위 금액, 통화 환산, 포장 단위 변환을 추측하지 않습니다. 전처리 단계에서 원천에 맞게 변환하고 그 근거를 남기십시오. 원본 파일을 보존하려면 사용자 저장소에 별도 보관해야 합니다. 이 버전은 정규화 관측과 그 해시를 저장하며 원천 파일 전체 바이트를 자동 아카이빙하지 않습니다.
