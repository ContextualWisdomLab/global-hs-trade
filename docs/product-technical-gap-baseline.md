# Product–technical Gap baseline

검증 기준일은 2026-09-12이며, 상태는 보호 브랜치가 아니라 PR #2의 exact head에서 관찰한 증거를 나타냅니다. 미병합 항목은 완료가 아닙니다.

## Goal과 현재 상태

Global HS Trade는 적법하게 확보한 기업별 HS 관측을 원천·레코드·버전 단위로 보존하고, 국가 aggregate와 기업 관측을 섞지 않는 로컬 원장입니다. 공개 저장소에는 실제 통관자료나 그 이용권이 포함되지 않습니다.

| 근거 | 현재 상태 | 확인된 Gap | Action |
|---|---|---|---|
| PRD 역할의 `README.md` | Proposed | 실제 원천 확보·권리 검토·운영 배포는 범위 밖입니다. | 사용자가 등록한 source policy와 실제 계약을 별도로 검토하고 권리가 없는 export는 fail closed로 유지합니다. |
| TRD 역할의 `docs/DESIGN.md`·`docs/DATA_CONTRACT.md`·`docs/CAPTURE_CONTRACT.md` | Proposed | 국가 기준선은 완전한 버전 계보가 없고 대용량 처리 성능은 검증되지 않았습니다. | immutable baseline versioning과 현실적 규모의 성능 시험을 후속 ADR에서 정의합니다. |
| Context Map 역할의 `docs/DESIGN.md` | Proposed | identity, trade, sources, coverage, storage 경계는 문서화됐지만 독립 배포 계약은 없습니다. | 현재 단일 제품 안의 모듈 경계를 유지하고 반복 책임이 확인되기 전 서비스 분리를 만들지 않습니다. |
| ERD 근거인 `global_hs_trade/storage.py` schema | Proposed | SQLite 단일 사용자 원장이며 다중 테넌트·복구 SLA·클러스터 운영을 제공하지 않습니다. | 운영 요구가 생기면 source/observation/capture/provenance invariant를 보존한 migration ADR과 fixture를 먼저 추가합니다. |
| UML 흐름 근거인 `global_hs_trade/application.py`·`collection/captures.py` | Proposed | 실시간 외부 API 성공은 현재 환경에서 검증되지 않았습니다. | 네트워크·파싱을 transaction 밖에서 수행하고, 요청 범위 검증 후 capture와 receipt를 원자 저장하는 계약을 유지합니다. |
| PR #2 회귀 및 설치 검증 | Proposed | hosted exact-head Checks와 독립 승인이 아직 필요합니다. | `python scripts/check.py`, `python scripts/verify_install.py`, organization security Checks와 current-head review를 모두 통과한 뒤 ordinary merge합니다. |

## 실패 장면과 운영 행동

- 응답의 신고국·HS6·기간·흐름이 요청과 다르면 저장하지 않고 실패 receipt를 남깁니다.
- capture 저장 중 provenance 또는 receipt가 실패하면 같은 transaction의 모든 쓰기를 되돌립니다.
- 권리 객체가 아니거나 기존 source policy와 충돌하면 등록을 거부합니다.
- 조회 API는 read-only SQLite 연결을 사용합니다. DB가 없거나 손상됐으면 쓰기로 복구하려 하지 않고 요청을 실패시킵니다.
- 실제 원천 export 권리는 기본 false입니다. aggregate export가 허용돼도 원문 재배포 권리가 없으면 행 단위 evidence sample을 내보내지 않습니다.
