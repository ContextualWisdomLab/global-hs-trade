# 변경 기록

## Unreleased

- 정규화 관측의 `source_url`에 사용자정보·비밀번호·fragment·호스트 누락·잘못된 포트가 들어오면 저장 전에 거부해 provenance와 조회 결과에 인증정보가 남지 않도록 했습니다.
- HMRC와 UN Comtrade 요청에서 점이 포함된 HS6 입력을 정규화하고, Comtrade 응답을 요청한 신고국·HS6·기간·흐름에 결속했습니다.
- 증거 캡처, 관측·기준선, provenance 연결, 실행 receipt를 하나의 짧은 SQLite transaction으로 저장하도록 수정했습니다. 네트워크와 검증은 transaction 밖에서 수행합니다.
- 로컬 GET API가 SQLite를 읽기 전용으로 열어 조회 중 스키마나 WAL을 만들지 않도록 했습니다.
- 실제 원천의 aggregate export 기본값을 false로 바꾸고, 원문 재배포 권한이 없을 때 aggregate 결과에서 행 단위 evidence sample을 제거했습니다.
- 원천 정책의 권한 객체와 동시 등록 충돌을 fail closed로 검증하고, 회사 식별 수를 원천 범위 안에서 계산하도록 수정했습니다.
- 동적 SQL 회귀 검사가 f-string, `str.format`, 문자열 결합, 지역 변수 전달을 포함하도록 확장했습니다.

## 0.2.0

- 공개 저장소 이관본의 로컬 관측 원장, HMRC·UN Comtrade preview 수집기, 증거 캡처 계약과 합성 데이터 검증을 추가했습니다.
