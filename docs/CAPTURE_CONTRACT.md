# 증거 캡처 계약

캡처는 수집 응답과 관측 원장을 분리합니다. 외부 요청을 하지 않고 검증된 파일을 재처리할 수 있습니다. 네트워크 단절을 해결하는 프록시·접근 제한 우회 기능은 아닙니다.

## 필수 항목

| 필드 | 계약 |
|---|---|
| schema_version | 정수 1. true는 허용하지 않습니다. |
| adapter | normalized_observations, hmrc_trade, comtrade_preview 중 하나 |
| source_identifier | 로컬에 이용 정책을 등록한 원천 |
| source_url | 인증정보·fragment가 없는 HTTPS URL |
| captured_at | 타임존이 있는 ISO8601 시각 |
| representation | source_json 또는 selected_fields_transcription |
| selection_scope | 캡처에 실제로 담은 기간·행·필드 범위 |
| transcription_note | 옮겨 적은 캡처에서는 필수. 생략·변환·추출 한계를 설명 |
| payload | 어댑터별 객체 또는 배열 |
| payload_sha256 | 정렬된 canonical JSON을 UTF-8로 인코딩한 SHA-256 |
| annotations | 선택 항목. 값의 출처, 충돌, 제외 항목을 설명하는 목록 권장 |

해시용 JSON은 키를 정렬하고 구분자를 `,`와 `:`로 설정하며 Unicode를 그대로 사용합니다. 실수는 정확한 십진 문자열로 인코딩합니다. Python Decimal은 문자열로 정규화하며 binary float는 거부합니다. 이 해시는 다운로드 원본 바이트의 체크섬이 아닙니다.

파일을 준비할 때 제공 함수를 사용할 수 있습니다.

```python
import json
from pathlib import Path
from global_hs_trade.collection.captures import seal_capture
from global_hs_trade.sources.files import read_json

capture = seal_capture(read_json('unsealed-capture.json'))
Path('capture.json').write_text(
    json.dumps(capture, ensure_ascii=False, indent=2), encoding='utf-8'
)
```

`scripts/create_demo.py`와 `tests/test_samples_v020.py`는 가상 관측 캡처를 재현합니다. 실제 거래 캡처는 이 공개 저장소에 포함하지 않습니다. 최대 캡처 크기는 16 MiB입니다. 일반 JSONL·CSV 입력 한도인 128 MiB와 다릅니다.

## 원천 검증과 권한

hmrc_trade는 `hmrc-traders`와 `https://api.uktradeinfo.com/Trade` 조합만 받습니다. comtrade_preview는 `un-comtrade`와 해당 공식 preview 경로만 받습니다. normalized_observations는 이 두 공식 식별자를 사용할 수 없으며, 각 행의 원천·URL이 캡처와 일치해야 합니다.

이는 혼동과 오표기를 줄이는 계약 검증입니다. 파일 작성자가 원천 응답을 조작한 후 해시까지 다시 계산하는 것을 막는 전자서명이 아닙니다. `authenticity_verified`는 false입니다. 실제 원천 인증에는 제공사 서명이나 인증된 다운로드 체계가 별도로 필요합니다.

internal_analysis 권한 없이 입력하지 못합니다. 캡처 목록과 provenance 명령은 원문 payload 대신 메타데이터만 반환합니다. 로컬 DB 파일 소유자의 직접 접근까지 차단하는 보안 경계는 아닙니다.

## 멱등성·정정·실패

관측의 원천/레코드/버전이 같고 내용이 같으면 replay로 처리합니다. 같은 버전의 내용이 다르면 거부하고 감사 기록을 남깁니다. 거부된 내용에는 기존 관측을 뒷받침하는 근거 링크를 추가하지 않습니다.

캡처 일부 행이 잘못되면 유효한 행은 보존하며 `imported_with_rejections`와 종료 코드 2를 반환합니다. 캡처 해시·원천 바인딩이 틀리면 입력 전에 전체를 거부합니다. 캡처의 메타데이터가 달라지면 별도 캡처가 되지만 거래가 다시 늘어나는 것은 아닙니다.

Comtrade 캡처는 국가 기준선만 수정합니다. 회사 원장으로 들어가지 않으며 국가 기준선의 완전한 버전별 계보는 아직 제공하지 않습니다. 수집 시각과 발췌 범위가 명시되지 않은 값을 최신·전수 자료로 승격하지 않습니다.
