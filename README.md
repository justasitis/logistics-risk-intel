# Logistics Risk Intelligence (VDI 클린 소스 트리)

사내 VDI(`C:\dev\logistics-risk-intel`)에서 운영 중인 물류 리스크 인텔리전스 대시보드의
클린 소스 트리다. FastAPI 백엔드 + Vue 3(MapLibre) 프런트엔드.

## 구조

```
api_server.py              # FastAPI 엔트리 (라우터 4개 include)
services/                  # 대시보드 도메인 서비스 (루트 레벨 패키지)
  anomaly_engine.py        # 스케줄 이상 탐지
  dashboard_geo_service.py # 지도용 GeoJSON 생성
  datalake_schedule_client.py  # 데이터레이크 REST 클라이언트
  map_builder.py           # 항만 좌표 / searoute 항로
  schedule_history_service.py
  schedule_timeline_service.py
backend/app/               # MI·AIS·경유지·수동좌표 API (api_server.py가 include)
  api/routes/              # mi_ai, marinesia, stopby_routes, manual_coordinates
  core/                    # mi_settings, marinesia_settings, stopby_settings
  schemas/  services/  prompts/  data/
frontend/                  # Vue 3 + Vite + TypeScript
  src/App.vue              # 루트 컴포넌트 (대시보드 전체)
  src/components/          # LogisticsMap, ScheduleTimeline, Mi*, 패널들
  src/services/ src/utils/ src/composables/ src/types/
data/                      # 런타임 데이터 (git 무시, *.sample.json만 추적)
docs/                      # 각 단계 패치 README (참고용)
```

## 실행

패키지 레지스트리: **npm·pip 모두 사내 Nexus(`http://10.242.199.4:8987`)를 사용**한다.
- npm: VDI의 `.npmrc`가 Nexus를 가리키므로 `npm ci`/`npm install`은 그대로 동작한다.
  `package-lock.json`의 resolved URL도 Nexus 경로로 유지되어 있다.
- pip: Nexus의 PyPI 프록시를 index-url로 지정한다 (레포 이름은 사내 Nexus 설정에 맞게 확인).

백엔드 (프로젝트 루트에서):

```bash
# 주의 1) searoute는 경유항로(stopby) 기능 호환을 위해 1.4.3 고정
# 주의 2) 한글 Windows에서는 UTF-8 모드로 설치 (소스 배포판 빌드 시 cp949 오류 방지)
# 주의 3) 사내 Nexus PyPI 프록시 경유 (레포명 pypi-proxy는 실제 환경에 맞게 확인)
set PYTHONUTF8=1
pip install --index-url http://10.242.199.4:8987/repository/pypi-proxy/simple --trusted-host 10.242.199.4 fastapi uvicorn pandas numpy requests folium searoute==1.4.3 "pydantic>=2.6" pydantic-settings httpx
uvicorn api_server:app --host 127.0.0.1 --port 8000
```

프런트엔드:

```bash
cd frontend
npm ci             # lockfile 기준 설치 (Nexus 경유)
npm run dev        # vite dev 서버, /api → 127.0.0.1:8000 프록시
npm run build      # vue-tsc 타입체크 + vite build
```

## 환경 변수

데이터레이크 (`services/datalake_schedule_client.py`):

- `DATALAKE_BASE_URL`, `DATALAKE_USERNAME`, `DATALAKE_PASSWORD`, `DATALAKE_TIMEOUT`

MI 정제 (Actify/Dify, `backend/app/core/mi_settings.py`, `backend/.env.example` 참고):

- `ACTIFY_BASE_URL`, `ACTIFY_ENDPOINT_PATH`, `ACTIFY_API_KEY`, `ACTIFY_USER`
- `ACTIFY_RESPONSE_MODE`, `ACTIFY_TIMEOUT_SECONDS`, `ACTIFY_VERIFY_SSL`
- `MI_VDI_MAX_CANDIDATES`, `MI_RUN_STORE_DIR`

Marinesia AIS SharePoint (`backend/app/core/marinesia_settings.py`):

- `MARINESIA_SHAREPOINT_ROOT`, `MARINESIA_DEFAULT_COMPANY`
- `MARINESIA_LIVE_HOURS`, `MARINESIA_STALE_WARNING_HOURS`, `MARINESIA_MAX_FILE_SIZE_MB`

경유지(Stop-by) (`backend/app/core/stopby_settings.py`):

- `EUROPE_BLANK_STOPBY_DEFAULT`, `SEAROUTE_ALGORITHM`
- `STOPBY_MAXIMUM_ROUTES`, `STOPBY_ROUTE_CACHE_SIZE`

수동 좌표 (`backend/app/services/manual_coordinate_store.py`):

- `MANUAL_COORDINATE_FILE` (기본: `<프로젝트 루트>/data/manual_coordinates.json`)

프런트엔드 (`frontend/.env.example` 참고):

- `VITE_API_BASE_URL` (같은 origin이면 비워 둠)

## 주의

- `data/*.json`은 런타임 산출물이라 git에서 제외된다. 샘플은 `*.sample.json` 참고.
- 알려진 결함(팝업 XSS 가능성 등)은 Phase 1에서 원형 그대로 보존했다.
