# Step 9.15 — HBL 중심 일정 이상 Master–Detail UI

## 목적

긴 일정 이상 목록 아래에 있던 선택 운송 상세를 하나의 Master–Detail 화면으로 통합한다.

- 왼쪽: 일정 이상 화물 목록
- 오른쪽: 선택 화물 상세
- 목록과 상세: 각각 독립 스크롤
- 상세 탭: 요약, Timeline, MI 영향, 원인 후보
- 사용자 대표 식별자: HBL 우선
- 시스템 보조 식별자: B-LAP TR 번호
- 내부 선택 및 분석 연결키: 기존 `transport_key` 유지

## 변경 파일

```text
frontend/src/App.vue
frontend/src/assets/anomaly-master-detail.css
frontend/src/components/AnomalyMasterDetailPanel.vue
frontend/src/components/CauseAnalysisPanel.vue
```

백엔드, API, 일정 이상 탐지, MI 영향 계산, 원인 후보 점수는 변경하지 않는다.

## 선행 조건

Step 9.14.1까지 적용된 프로젝트를 기준으로 한다. Step 9.14.2는 취소된 단계이므로 적용하지 않는다.

다음 파일이 존재해야 한다.

```text
frontend/src/utils/selectionSync.ts
frontend/src/utils/shipmentDisplay.ts
frontend/src/types/causeAnalysis.ts
frontend/src/types/miImpact.ts
frontend/src/components/ScheduleTimeline.vue
```

App.vue에는 다음 상태와 함수가 존재해야 한다.

```text
selectedEventKey
approvedMiEvents
miImpacts
selectedCauseCandidates
selectEvent
selectMiEvent
```

## 주요 동작

1. HBL, TR, 선박명, 항로, 일정 이상 제목을 통합 검색한다.
2. 위험도 필터를 제공한다.
3. 목록에서 이벤트를 선택하면 기존 `selectEvent()`를 호출한다.
4. 기존 선택 고정 로직을 그대로 사용해 지도, Route, AIS, Timeline과 동기화한다.
5. HBL이 있으면 HBL을 대표 제목으로 표시한다.
6. HBL이 없으면 TR 번호를 사용하고 상세 요약에서 `HBL 미등록`을 표시한다.
7. 이전/다음 버튼으로 현재 필터 결과를 연속 검토한다.
8. 원인 확정, 제외, 대기 기능은 기존 CauseAnalysisPanel을 재사용한다.

## 자동 적용이 중단되는 경우

스크립트는 기존 `alerts-section`과 `shipment-section`이 연속해 있는 구조를 전제로 한다. 두 section 사이에 사용자가 직접 추가한 별도 콘텐츠가 있으면 안전을 위해 자동 적용을 중단한다.

그 경우 `PATCH_SNIPPETS/AppVue_STEP9_15.md`에 따라 수동 적용한다.
