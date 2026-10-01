# ADR-0001: 국가 기준선의 불변 revision 계보

- 상태: Proposed
- 결정일: 2026-10-01
- 입력 head: `f67601cd663abfdba8f44ec500cbde685d16ecb4`
- 소유 경계: Global HS Trade `storage`

## 문제

국가 기준선의 기존 `baseline_key`는 원천·신고국·상대국·기간·방향·HS6·HS 개정판·통화·평가기준·세관 코드·운송수단을 묶습니다. 같은 차원의 새 payload를 저장하면 `baselines` 행을 갱신해 이전 수치와 provenance를 파괴했습니다. 운영자는 값이 왜 바뀌었는지 재구성하거나 이전 수치를 감사할 수 없었습니다.

## 제약과 invariant

- 국가 기준선은 기업 관측이 아니며 `source_version` 계약을 재사용하지 않습니다.
- 기존 `baselines` 조회는 최신 snapshot 하나를 반환해야 합니다.
- 같은 실질 내용의 재수집은 `retrieved_at`이 달라도 새 revision을 만들지 않습니다.
- 이미 본 과거 내용을 다시 입력해도 최신 snapshot을 되돌리지 않습니다.
- 검증·네트워크 작업은 transaction 밖에서 수행하고, revision과 최신 snapshot 갱신은 같은 짧은 SQLite transaction에 둡니다.
- 공개 저장소에는 실제 국가 통계 payload를 fixture로 넣지 않습니다.

## 검토한 대안

1. 기존 행을 계속 덮어쓰기: 가장 단순하지만 감사·변경 설명·복구가 불가능해 기각했습니다.
2. 입력자가 국가 기준선 버전을 제공: UN Comtrade preview가 안정적인 레코드 revision을 제공한다는 근거가 없어, 임의 버전을 발명하게 되므로 기각했습니다.
3. snapshot과 불변 revision을 분리: 기존 조회를 보존하면서 새 내용만 순번을 부여할 수 있어 선택했습니다.
4. 별도 원격 event store: 단일 사용자 로컬 제품의 현재 수요에 비해 운영·배포 책임이 커서 기각했습니다.

## 결정

`baselines`는 최신 snapshot 표면으로 유지합니다. `baseline_versions`는 차원 키별로 증가하는 `baseline_revision`, 실질 payload의 `baseline_content_hash`, 최초 관찰 payload를 보존합니다. content hash는 재수집 시각을 제외한 canonical JSON으로 계산합니다. 새 digest만 revision을 추가하고 최신 snapshot을 갱신합니다. 기존 digest 재입력은 아무 행도 바꾸지 않습니다.

기존 DB를 쓰기 모드로 열면 각 snapshot을 revision 1로 이관합니다. 읽기 전용 legacy DB는 쓰지 않고 현재 snapshot을 revision 1로 투영합니다. `baselines --history`와 `Ledger.baseline_history()`가 revision 계보를 제공합니다.

## 근거와 검증 장면

- 같은 차원의 값 100 뒤 값 125를 저장하면 history는 revision 1·2를 모두 반환하고 최신 조회는 125를 반환합니다.
- 수집 시각만 다른 재수집과 과거 값 재전송은 revision을 늘리거나 최신 값을 되돌리지 않습니다.
- 한 batch 안의 잘못된 기준선은 준비 단계에서 전체 쓰기를 막습니다.
- legacy snapshot은 payload 손실 없이 revision 1로 나타납니다.

근거 테스트는 `tests/test_baseline_versions.py`에 있으며 exact-head CI와 독립 review가 통과하기 전 상태는 Proposed입니다.

## 위험과 후속 작업

- `baseline_revision`은 이 로컬 원장의 수집 계보이며 원천 기관의 공식 revision 번호가 아닙니다.
- canonical hash는 무결성·멱등 키일 뿐 전자서명이나 원격 원본 진위 증명이 아닙니다.
- revision 수가 증가하면 DB 크기도 증가합니다. 현실적 대용량 자료로 보존 비용과 조회 p95를 측정한 뒤 인덱스·보존 정책을 별도 ADR로 결정합니다.
- 실제 원천 장기 보관은 권리 검토와 캡처 계약을 따라야 하며 이 결정이 재배포 권한을 만들지 않습니다.
