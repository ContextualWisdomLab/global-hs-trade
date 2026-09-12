# Global HS Trade

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/ContextualWisdomLab/global-hs-trade)

전 세계 기업의 HS별 수출입 **관측자료**를 수집·검증·집계하는 Python 프로그램입니다. 기업 소재국과 신고 국가, 수출자·수입자·공급자·구매자를 구분합니다. 국가 전체 통계를 개별 기업에 임의 배분하지 않습니다.

이 저장소는 대화에서 개발한 0.2.0 실행본의 코드와 테스트를 이관한 것입니다. **전 세계 전수 데이터나 상용 통관자료 이용권은 포함하지 않습니다.** 공개 저장소에는 가상 데이터만 재현하며, 원본 실행본에 있던 거래 캡처·실제 기업 DB·이전 실행 로그·배포 바이너리는 재배포하지 않습니다.

## 실행

Python 3.11 이상이 필요합니다. 조회·입력·로컬 API에는 외부 패키지나 API 키, `.env`가 필요하지 않습니다.

```bash
git clone https://github.com/ContextualWisdomLab/global-hs-trade.git
cd global-hs-trade
python scripts/create_demo.py --db var/synthetic.sqlite
python -m global_hs_trade dataset-status --db var/synthetic.sqlite
python -m global_hs_trade query --db var/synthetic.sqlite --hs6 090111 --role exporter --flow X
```

예제 생성기는 12개의 가상 거래 경로에 대해 수출·수입 관측 24건을 만듭니다. 모두 `SYNTHETIC` 기업이며, 독립적인 실제 선적 24건이라는 의미가 아닙니다. 기존 경로가 있으면 덮어쓰지 않고 종료 코드 2로 중단합니다. 다른 파일명을 지정해 새 예제를 생성하십시오.

실제 자료는 별도 DB에 보관합니다.

```bash
python -m global_hs_trade init --db var/work.sqlite
python -m global_hs_trade register-source --db var/work.sqlite --file my-source-policy.json
python -m global_hs_trade ingest --db var/work.sqlite --file my-authorized-data.csv --mapping my-mapping.json
```

`examples/rights-policy-template.json`의 권한 기본값은 모두 false입니다. 계약·동의로 확보한 범위에 맞춰 등록해야 합니다. 플래그를 true로 바꾸는 행위 자체가 이용권 취득은 아닙니다. CSV 형식은 `examples/mapped-demo.csv`와 `examples/csv-mapping.json`을 참고하십시오.

내장된 실제 원천 정책도 aggregate export를 기본 허용하지 않습니다. 명시적으로 허용된 aggregate export라도 원문 재배포 권한이 없으면 결과에서 행 단위 증거 표본을 제거합니다.

## 수집과 조회의 경계

| 기능 | 현재 범위 |
|---|---|
| HS·기업·국가·월 집계 | 출처·역할·통화·FOB/CIF·개정판을 분리합니다. 누락은 null이며 0이 아닙니다. |
| JSONL·JSON·CSV 입력 | 적법하게 확보한 품목행 자료를 공통 계약으로 받습니다. |
| HMRC 수집기 | 기업·품목·월의 거래 존재 관측입니다. 거래액이나 선적 수가 아닙니다. 페이지 검증·재개를 지원합니다. |
| UN Comtrade preview | 국가 집계이며 기업 정보가 아닙니다. 제한 응답을 전수 자료로 표시하지 않습니다. |
| 증거 캡처 | URL·확인 범위·전사 여부·SHA-256을 관측 버전에 연결합니다. 해시는 세관 원본의 진위 인증이 아닙니다. |
| 회사 식별 | 출처별 ID 또는 제공된 법인 식별자를 사용합니다. 이름 유사도만으로 합치지 않습니다. |
| 관측 범위 | 국가 코드 지원과 실제 데이터 확보를 구분합니다. 미관측을 무역 실적 0으로 해석하지 않습니다. |

외부 수집 요청을 확인하는 명령은 네트워크나 DB를 변경하지 않습니다.

```bash
python -m global_hs_trade fetch-hmrc --hs6 090111 --start 2025-01 --end 2025-01 --flow M --dry-run
python -m global_hs_trade fetch-comtrade --reporter-code 76 --hs6 090111 --period 2024 --flow X --dry-run
```

실제 수집에는 연결 가능한 네트워크와 적용 가능한 이용 권한이 필요합니다. HMRC 작업은 같은 조건의 `--resume`로 마지막 승인된 페이지 다음부터 재개합니다. `page_limit_reached`는 완료가 아니며 종료 코드 2입니다. `$skip` 기반 수집은 원천이 동시에 변경될 때 스냅샷 일관성을 보장하지 않습니다. 이관 환경의 외부 DNS 연결 실패 때문에 실시간 수집 성공은 검증하지 못했습니다.

## 로컬 API

```bash
python -m global_hs_trade serve --db var/synthetic.sqlite --port 8765
curl 'http://127.0.0.1:8765/v1/dataset-status'
curl 'http://127.0.0.1:8765/v1/trade-stats?hs6=090111&role=exporter&recorded_flow=X'
```

127.0.0.1 단일 사용자 전용입니다. 교차 출처 요청과 쓰기 HTTP 메서드를 허용하지 않으며, GET 요청은 SQLite를 읽기 전용으로 열어 스키마나 WAL 파일을 만들지 않습니다. 인터넷에 노출할 인증·멀티테넌트 서비스가 아닙니다.

## 개발·검증

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes --no-deps -r requirements-dev.txt
python scripts/check.py
python -W error -m compileall -q global_hs_trade scripts
python scripts/verify_install.py
```

시험은 pytest를 사용합니다. 테스트 실행기는 외부 pytest 설정과 비사용 플러그인 자동 로딩을 분리하고 Python 경고를 오류로 처리합니다. 설치 검증기는 로컬 wheel을 빌드하고 별도 가상환경에 오프라인 설치한 뒤, 소스 디렉터리 밖에서 조회를 검증합니다. CI는 Python 3.11·3.12·3.13에서 이 절차를 실행하도록 구성했습니다. CI의 성공 여부는 해당 커밋의 실제 실행 결과로 확인해야 합니다.

도메인·입력 계약은 `docs/DESIGN.md`, `docs/DATA_CONTRACT.md`, `docs/CAPTURE_CONTRACT.md`에 있습니다. 이관 내역과 검증 범위는 `docs/REPOSITORY_IMPORT.md`, 구현 제약은 `docs/LIMITATIONS.md`, 현재 제품·기술 Gap은 `docs/product-technical-gap-baseline.md`를 참고하십시오.

## 라이선스

코드는 저장소의 기존 MIT `LICENSE`를 따릅니다. 제3자 통관자료·서비스 약관·데이터베이스 재배포 권한은 코드 라이선스와 별개입니다. `NOTICE.md`를 함께 확인하십시오.
