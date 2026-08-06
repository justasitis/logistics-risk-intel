
<script setup lang="ts">

import '@/assets/readability.css'

import {

  computed,

  onBeforeUnmount,

  onMounted,

  ref,

  watch,

} from 'vue'


 

import LogisticsMap from '@/components/LogisticsMap.vue'

import AisUploadPanel from '@/components/AisUploadPanel.vue'

import MiWorkspaceView from '@/views/MiWorkspaceView.vue'

import AnomalyMasterDetailPanel from '@/components/AnomalyMasterDetailPanel.vue'

import '@/assets/anomaly-master-detail.css'

import MiImpactPanel from '@/components/MiImpactPanel.vue'

import VesselMmsiManager from '@/components/VesselMmsiManager.vue'

import MarinesiaSharePointStatus from '@/components/MarinesiaSharePointStatus.vue'

import InventoryImpactPanel from '@/components/InventoryImpactPanel.vue'

import LeadtimeReportPanel from '@/components/LeadtimeReportPanel.vue'

import GapPanel from '@/components/GapPanel.vue'

import NotificationCenter from '@/components/NotificationCenter.vue'

import RouteMasterPanel from '@/components/RouteMasterPanel.vue'

import { getRegistryMapZones } from '@/services/miRegistryApi'

import {
  buildRegistryZoneGeoJson,
  type RegistryMapZone,
} from '@/services/miUpload'


 

import type {

  DashboardResponse,

  GeoJsonFeatureCollection,

  ScheduleEvent,

  TransportRecord,

  ScheduleTimelineResponse,

  AisMapItem,

  AisUploadResult,

} from '@/types/dashboard'


 

import {

  fetchDashboard,

  fetchScheduleTimeline,

} from '@/services/dashboardApi'

import {

  buildAisGeoJson,

  matchAisToTransports,

  summarizeAisItems,

} from '@/services/aisUpload'

import { analyzeCauseCandidates } from '@/services/causeAnalysis'

import {

  fetchMarinesiaHealth,

  fetchMarinesiaLatest,

  selectMarinesiaByMmsiMaster,

  toAisUploadResult,

  type MarinesiaHealth,

} from '@/services/marinesiaSharePoint'


 

import { useVesselMmsiMaster } from '@/composables/useVesselMmsiMaster'


 

import { useMiWorkspace } from '@/composables/useMiWorkspace'

import {

  analyzeMiImpact,

  buildMiZoneGeoJson,

} from '@/services/miImpact'

import type { RefinedMiEvent } from '@/types/mi'


 

import {

  buildStopbyRoutes,

  type StopbyRouteSummary,

} from '@/services/stopbyRoutes'


 

import {

  shipmentDisplayId,

} from '@/utils/shipmentDisplay'


 

import {

  aisSelectionId,

  createLatestRequestGuard,

  eventSelectionKey,

  findLinkedAisForTransport,

  findTransportForEvent,

  matchedTransportKey,

  type TransportSelectionSource,

} from '@/utils/selectionSync'


 

import {

  ensureAisTransportLinks,

} from '@/utils/aisTransportLink'


 

import {

  inspectTransportRoute,

  mergeStopbyRoutes,

} from '@/utils/stopbyRouteMerge'


 

import {

  buildActiveCargoAisView,

  findActiveCargoAisForTransport,

} from '@/utils/activeCargoAis'


 

import CoordinateRegistryPanel

  from '@/components/CoordinateRegistryPanel.vue'


 

import {

  fetchManualCoordinates,

  type ManualCoordinateEntry,

} from '@/services/manualCoordinatesApi'


 

import {

  applyManualCoordinatesToPorts,

  deriveMissingCoordinateItems,

} from '@/utils/manualCoordinates'


 

type WorkspaceMode = 'dashboard' | 'mi' | 'vessel'


 

const activeWorkspace = ref<

  'dashboard' | 'mi' | 'vessel' | 'inventory' | 'report' | 'gap' | 'routes'

>('dashboard')

const now = ref(new Date())

const dashboard = ref<DashboardResponse | null>(null)

const loading = ref(false)

const errorMessage = ref('')

const selectedCompany = ref('SKO')

const selectedTransportKey = ref('')

 

function handleSelectHbl(hblNo: string) {

  const target = transports.value.find(

    (t) => (t.hbl_no ?? '') === hblNo

  )

  if (target) {

    selectedTransportKey.value = target.transport_key

  }

  activeWorkspace.value = 'dashboard'

}


 

const scheduleTimeline = ref<ScheduleTimelineResponse | null>(null)

const timelineLoading = ref(false)

const timelineError = ref('')

const aisUpload = ref<AisUploadResult | null>(null)

const selectedAisId = ref('')


 

const selectedEventKey = ref('')

const transportSelectionSource =

  ref<TransportSelectionSource>('INIT')


 

const timelineRequestGuard =

  createLatestRequestGuard()


 

const marinesiaLoading = ref(false)

const marinesiaError = ref('')

const marinesiaMessage = ref('')

const marinesiaSourceFile = ref('')

const marinesiaGeneratedAt = ref('')

const marinesiaHealth = ref<MarinesiaHealth | null>(null)


 

const coordinatePanelOpen = ref(false)


 

const manualCoordinates =

  ref<ManualCoordinateEntry[]>([])


 

const coordinateLoading = ref(false)

const coordinateError = ref('')


 

const {

  mappings: vesselMmsiMappings,

} = useVesselMmsiMaster()


 

let clockTimer: number | undefined

let activeController: AbortController | null = null

let timelineController:

  AbortController | null = null

let marinesiaController: AbortController | null = null


 

const companyOptions = [

  { value: '', label: '전체 법인' },

  { value: 'SKO', label: 'SKO — 한국' },

  { value: 'SKBM', label: 'SKBM — 헝가리' },

  { value: 'SKOH', label: 'SKOH — 헝가리' },

  { value: 'SKOJ', label: 'SKOJ — 중국' },

  { value: 'SKOY', label: 'SKOY — 중국' },

  { value: 'SKBA', label: 'SKBA — 미국' },

]


 

const emptyGeoJson = {

  type: 'FeatureCollection' as const,

  features: [],

}


 

const formattedTime = computed(() =>

  new Intl.DateTimeFormat('ko-KR', {

    year: 'numeric',

    month: '2-digit',

    day: '2-digit',

    weekday: 'short',

    hour: '2-digit',

    minute: '2-digit',

    second: '2-digit',

    hour12: false,

  }).format(now.value),

)


 

const summary = computed(() => dashboard.value?.summary ?? {

  active_transports: 0,

  etd_repeated_delay: 0,

  eta_repeated_delay: 0,

  lead_time_anomaly: 0,

  high_critical: 0,

  anomaly_transports: 0,

})


 

const metrics = computed(() => [

  {

    label: '활성 운송건',

    value: summary.value.active_transports,

    tone: 'blue',

  },

  {

    label: 'ETA 반복 지연',

    value: summary.value.eta_repeated_delay,

    tone: 'red',

  },

  {

    label: 'ETD 반복 지연',

    value: summary.value.etd_repeated_delay,

    tone: 'orange',

  },

  {

    label: 'Lead Time 이상',

    value: summary.value.lead_time_anomaly,

    tone: 'green',

  },

])


 

const events = computed(() => dashboard.value?.events ?? [])

const transports = computed(() => dashboard.value?.transports ?? [])

const routes = computed(

  () => dashboard.value?.map.routes ?? emptyGeoJson,

)


 

const effectiveRoutes = computed(

  () =>

    mergeStopbyRoutes(

      routes.value,

      stopbyRoutes.value,

    ),

)


 

const ports = computed(

  () => dashboard.value?.map.ports ?? emptyGeoJson,

)


 


 

const matchedAisItems =

  computed<AisMapItem[]>(() => {

    if (!aisUpload.value) return []


 

    const baseMatched =

      matchAisToTransports(

        aisUpload.value.items,

        transports.value,

      )


 

    return ensureAisTransportLinks(

      baseMatched,

      transports.value,

    )

  })


 

const approvedMiEvents = computed<RefinedMiEvent[]>(() =>

  miWorkspaceState.reviewResult?.canonical_payload.events ?? [],

)


 

const registryZoneRows = ref<RegistryMapZone[]>([])

const showRegistryZones = ref(
  localStorage.getItem('lri-registry-zones-visible') !== 'off',
)

const registryZones = computed(() =>
  buildRegistryZoneGeoJson(registryZoneRows.value),
)

async function loadRegistryZones() {
  try {
    registryZoneRows.value = await getRegistryMapZones()
  } catch {
    registryZoneRows.value = []
  }
}

function toggleRegistryZones() {
  showRegistryZones.value = !showRegistryZones.value
  localStorage.setItem(
    'lri-registry-zones-visible',
    showRegistryZones.value ? 'on' : 'off',
  )
}

function handleRegistryChanged() {
  void loadRegistryZones()
}

const miZones = computed(() =>

  buildMiZoneGeoJson(approvedMiEvents.value),

)


 

const miAnalysis = computed(() =>

  analyzeMiImpact(

    approvedMiEvents.value,

    effectiveRoutes.value,

    matchedAisItems.value,

  ),

)


 

const miImpacts = computed(() => miAnalysis.value.impacts)

const miImpactedRoutes = computed(() => miAnalysis.value.impactedRoutes)

const miImpactSummary = computed(() => miAnalysis.value.summary)


 

const selectedMiEvent = computed(() =>

  approvedMiEvents.value.find(

    (event) => event.event_id === selectedMiEventId.value,

  ) ?? approvedMiEvents.value[0] ?? null,

)


 

const causeAnalysis = computed(() =>

  analyzeCauseCandidates({

    scheduleEvents: events.value,

    transports: transports.value,

    miEvents: approvedMiEvents.value,

    miImpacts: miImpacts.value,

    aisItems: matchedAisItems.value,

  }),

)


 

const selectedCauseCandidates = computed(() => {

  const transportKey =

    selectedTransport.value?.transport_key ?? ''


 

  if (!transportKey) return []


 

  return causeAnalysis.value.candidates.filter(

    (candidate) =>

      candidate.transport_key === transportKey,

  )

})


 

const aisSummary = computed(() => summarizeAisItems(matchedAisItems.value))

const allAisVessels = computed(() => {

  if (!aisUpload.value) {

    return []

  }


 

  const baseMatched =

    matchAisToTransports(

      aisUpload.value.items,

      transports.value,

    )


 

  return ensureAisTransportLinks(

    baseMatched,

    transports.value,

  )

})


 

const activeCargoAisView = computed(() =>

  buildActiveCargoAisView(

    allAisVessels.value,

    transports.value,

    {

      // 현재 Overview 응답에 실제 ATD가 없으므로

      // current_etd를 운항 시작 기준으로 사용

      requireActualDeparture: false,

      scheduledDepartureGraceDays: 0,


 

      // 오래된 과거 선적 제거

      maxVoyageDays: 120,

      etaOverdueGraceDays: 30,

    },

  ),

)


 

const activeCargoAisItems = computed(

  () => activeCargoAisView.value.items,

)


 

const aisVessels =

  computed<GeoJsonFeatureCollection>(

    () => ({

      type: 'FeatureCollection',


 

      features:

        activeCargoAisItems.value

          .filter((item) => {

            const longitude = Number(

              item.current_lon,

            )


 

            const latitude = Number(

              item.current_lat,

            )


 

            return (

              Number.isFinite(longitude)

              && Number.isFinite(latitude)

            )

          })

          .map((item) => ({

            type: 'Feature',


 

            id: item.ais_id,


 

            geometry: {

              type: 'Point',

              coordinates: [

                Number(item.current_lon),

                Number(item.current_lat),

              ],

            },


 

            properties: {

              ...item,


 

              // MapLibre의 선택 Layer에서 사용하는

              // 고유 식별자를 반드시 포함

              ais_id: item.ais_id,


 

              heading: Number.isFinite(

                Number(item.heading),

              )

                ? (

                    (

                      Number(item.heading)

                      % 360

                    )

                    + 360

                  ) % 360

                : 0,

            },

          })),

    }),

  )


 

const selectedAis = computed<AisMapItem | null>(() => {

  if (selectedAisId.value) {

    const selected = matchedAisItems.value.find(

      (item) => item.ais_id === selectedAisId.value,

    )

    if (selected) return selected

  }


 

  const transportKey = selectedTransportKey.value

  if (!transportKey) return null

  return matchedAisItems.value.find(

    (item) => item.matched_transport_key === transportKey,

  ) ?? null

})


 

const stopbyRoutes = ref<

  GeoJsonFeatureCollection | null

>(null)

const stopbyRouteSummary =

  ref<StopbyRouteSummary | null>(null)

const stopbyRouteLoading = ref(false)

const stopbyRouteError = ref('')

const stopbyRouteWarnings = ref<string[]>([])


 

let stopbyRouteController:

  AbortController | null = null


 

const selectedTransport = computed<TransportRecord | null>(() => {

  if (!selectedTransportKey.value) {

    return transports.value[0] ?? null

  }


 

void loadMarinesiaFromSharePoint(true)


 

  return (

    transports.value.find(

      (item) => item.transport_key === selectedTransportKey.value,

    ) ?? null

  )

})


 

const lastUpdatedLabel = computed(() => {

  const value = dashboard.value?.generated_at

  if (!value) return '-'


 

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return value


 

  return new Intl.DateTimeFormat('ko-KR', {

    hour: '2-digit',

    minute: '2-digit',

    second: '2-digit',

    hour12: false,

  }).format(date)

})


 

const {

  state: miWorkspaceState,

  initializeMiPersistence,

} = useMiWorkspace()

const selectedMiEventId = ref('')


 

const missingCoordinateItems = computed(

  () =>

    deriveMissingCoordinateItems(

      transports.value,

      ports.value,

      manualCoordinates.value,

    ),

)


 

const effectivePorts = computed(

  () =>

    applyManualCoordinatesToPorts(

      ports.value,

      manualCoordinates.value,

    ),

)


 

function syncSelectedTransportAis() {

  const linkedAis =

    findActiveCargoAisForTransport(

      activeCargoAisItems.value,

      selectedTransport.value,

    )


 

  console.log(

    '[Selected cargo vessel]',

    {

      trprNo:

        selectedTransport.value

          ?.trpr_no,

      vesselName:

        selectedTransport.value

          ?.vessel_name,

      linkedAisId:

        linkedAis?.ais_id ?? '',

      linkedAisVessel:

        linkedAis?.vessel_name ?? '',

      linkedTrprNo:

        linkedAis?.matched_trpr_no

        ?? '',

      matchMethod:

        linkedAis

          ?.active_match_method

        ?? '',

    },

  )


 

  selectedAisId.value =

    linkedAis?.ais_id ?? ''

}


 

function formatDate(value?: string | null) {

  if (!value) return '-'


 

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return value


 

  return new Intl.DateTimeFormat('ko-KR', {

    month: '2-digit',

    day: '2-digit',

  }).format(date)

}


 

function signedDays(value?: number | null) {

  if (value === null || value === undefined) return '-'

  if (value > 0) return `+${value}일`

  return `${value}일`

}


 

function severityClass(severity?: string) {

  return `severity-${(severity ?? 'normal').toLowerCase()}`

}


 

function selectEvent(

  event: ScheduleEvent,

) {

  selectedEventKey.value =

    eventSelectionKey(event)


 

  const matchedTransport =

    findTransportForEvent(

      event,

      transports.value,

    )


 

  if (!matchedTransport) {

    console.warn(

      '[Event transport match failed]',

      {

        eventId: event.event_id,

        transportKey:

          event.transport_key,

        trprNo: event.trpr_no,

      },

    )

    return

  }


 

  transportSelectionSource.value =

    'EVENT'


 

  selectedTransportKey.value =

    matchedTransport.transport_key


 

  // AIS 선택은 selectedTransport watcher에서 처리

}


 

function handleAisLoaded(

  result: AisUploadResult,

) {

  aisUpload.value = result


 

  syncSelectedTransportAis()


 

  const matched = matchAisToTransports(

    result.items,

    transports.value,

  )


 

  const currentAisExists = matched.some(

    (item) =>

      item.ais_id === selectedAisId.value,

  )


 

  // 현재 선택 AIS가 새 데이터에도 존재하면 유지한다.

  if (currentAisExists) {

    return

  }


 

  const first = matched.find(

    (item) =>

      item.current_lat !== null

      && item.current_lon !== null,

  )


 

  selectedAisId.value =

    first?.ais_id ?? ''


 

  // selectedTransportKey는 여기서 변경하지 않는다.

}


 

async function loadMarinesiaFromSharePoint(

  silent = false,

) {

  marinesiaController?.abort()

  const controller = new AbortController()

  marinesiaController = controller


 

  marinesiaLoading.value = true

  marinesiaError.value = ''

  if (!silent) marinesiaMessage.value = ''


 

  try {

    const companies = selectedCompany.value

      ? [selectedCompany.value]

      : []


 

    const [health, response] = await Promise.all([

      fetchMarinesiaHealth(controller.signal),

      fetchMarinesiaLatest(

        companies,

        controller.signal,

      ),

    ])


 

    const selection = selectMarinesiaByMmsiMaster(

      response.items,

      vesselMmsiMappings.value,

    )

    const result = toAisUploadResult(

      response,

      selection,

    )


 

    marinesiaHealth.value = health

    marinesiaSourceFile.value = response.source_file

    marinesiaGeneratedAt.value = (

      response.generated_at ?? ''

    )

    marinesiaMessage.value = (

      `SharePoint AIS ${result.items.length}척 반입 · `

      + `MMSI Master ${selection.mapped_count}척 · `

      + `임시 후보 ${selection.automatic_count}척`

    )


 

    handleAisLoaded(result)

  } catch (error) {

    if (

      error instanceof DOMException

      && error.name === 'AbortError'

    ) {

      return

    }


 

    marinesiaError.value = error instanceof Error

      ? error.message

      : String(error)


 

    if (!silent) {

      aisUpload.value = null

      selectedAisId.value = ''

    }

  } finally {

    if (marinesiaController === controller) {

      marinesiaLoading.value = false

    }

  }

}


 

function clearAisUpload() {

  aisUpload.value = null

  selectedAisId.value = ''


 

  if (

    transportSelectionSource.value === 'AIS'

  ) {

    transportSelectionSource.value =

      'MANUAL'

  }

}


 

function selectAis(payload: {

  aisId: string

  transportKey?: string

}) {

  transportSelectionSource.value =

    'AIS'


 

  selectedEventKey.value = ''


 

  selectedAisId.value =

    String(payload.aisId ?? '').trim()


 

  const transportKey = String(

    payload.transportKey ?? '',

  ).trim()


 

  if (transportKey) {

    selectedTransportKey.value =

      transportKey

  }

}


 

function selectMiEvent(eventId: string) {

  selectedMiEventId.value = eventId


 

  const firstImpact = miImpacts.value.find(

    (impact) => impact.event_id === eventId,

  )


 

  if (firstImpact?.transport_key) {

    selectedTransportKey.value = firstImpact.transport_key

  }

}


 

async function refreshStopbyRoutes(

  sourceRoutes = routes.value,

  sourceTransports = transports.value,

) {

  stopbyRouteController?.abort()

  const controller = new AbortController()

  stopbyRouteController = controller


 

  stopbyRouteLoading.value = true

  stopbyRouteError.value = ''


 

  try {

    const response = await buildStopbyRoutes(

      sourceRoutes,

      sourceTransports,

      controller.signal,

    )


 

    stopbyRoutes.value = response.routes

    stopbyRouteSummary.value = response.summary

    stopbyRouteWarnings.value = response.warnings

  } catch (error) {

    if (

      error instanceof DOMException

      && error.name === 'AbortError'

    ) {

      return

    }


 

    stopbyRoutes.value = null

    stopbyRouteSummary.value = null

    stopbyRouteWarnings.value = []

    stopbyRouteError.value = error instanceof Error

      ? error.message

      : String(error)

  } finally {

    if (stopbyRouteController === controller) {

      stopbyRouteLoading.value = false

    }

  }

}


 

async function loadDashboard(forceRefresh = false) {

  activeController?.abort()

  const controller = new AbortController()

  activeController = controller


 

  loading.value = true

  errorMessage.value = ''


 

  try {

    const response = await fetchDashboard(

      {

        companies: selectedCompany.value

          ? [selectedCompany.value]

          : [],

        etdDays: 365,

        historyDays: 180,

        recentWindowDays: 14,

        maxInfoRows: 5000,

        maxEvents: 200,

        maxMapRoutes: 1000,

        refresh: forceRefresh,

      },

      controller.signal,

    )


 

    dashboard.value = response


 

    void refreshStopbyRoutes(

      routes.value,

      transports.value,

    )


 

    const currentStillExists = response.transports.some(

      (item) =>

        item.transport_key === selectedTransportKey.value,

    )


 

    if (!currentStillExists) {

      selectedTransportKey.value =

        response.events[0]?.transport_key

        ?? response.transports[0]?.transport_key

        ?? ''

    }

  } catch (error) {

    if (error instanceof DOMException && error.name === 'AbortError') {

      return

    }


 

    errorMessage.value =

      error instanceof Error

        ? error.message

        : '대시보드 데이터를 불러오지 못했습니다.'

  } finally {

    if (activeController === controller) {

      loading.value = false

      activeController = null

    }

  }

}


 

async function loadSelectedTimeline(

  transport:

    | TransportRecord

    | null

    | undefined,

) {

  timelineController?.abort()


 

  const requestToken =

    timelineRequestGuard.begin()


 

  scheduleTimeline.value = null

  timelineError.value = ''


 

  if (!transport?.trpr_no) {

    timelineLoading.value = false

    return

  }


 

  const requestedTransportKey =

    String(

      transport.transport_key ?? '',

    ).trim()


 

  const controller =

    new AbortController()


 

  timelineController = controller

  timelineLoading.value = true


 

  try {

    const result =

      await fetchScheduleTimeline(

        {

          trprNo: transport.trpr_no,

          cmpyCd: transport.cmpy_cd,

          plntCd: transport.plnt_cd,

          historyDays: 1500,

          includeNoChange: false,

        },

        controller.signal,

      )


 

    // 이전 요청이 늦게 도착한 경우 무시

    if (

      !timelineRequestGuard.isCurrent(

        requestToken,

      )

    ) {

      return

    }


 

    // 응답이 현재 선택 운송건과 다르면 무시

    if (

      selectedTransport.value

        ?.transport_key

      !== requestedTransportKey

    ) {

      return

    }


 

    scheduleTimeline.value = result

  } catch (error) {

    if (

      error instanceof DOMException

      && error.name === 'AbortError'

    ) {

      return

    }


 

    if (

      timelineRequestGuard.isCurrent(

        requestToken,

      )

    ) {

      timelineError.value =

        error instanceof Error

          ? error.message

          : '일정 변경이력을 불러오지 못했습니다.'

    }

  } finally {

    if (

      timelineController === controller

    ) {

      timelineController = null

    }


 

    if (

      timelineRequestGuard.isCurrent(

        requestToken,

      )

    ) {

      timelineLoading.value = false

    }

  }

}


 

async function loadManualCoordinates() {

  coordinateLoading.value = true

  coordinateError.value = ''


 

  try {

    manualCoordinates.value =

      await fetchManualCoordinates()

  } catch (error) {

    coordinateError.value =

      error instanceof Error

        ? error.message

        : String(error)

  } finally {

    coordinateLoading.value = false

  }

}


 

function normalizeCoordinateCode(

  value: string,

) {

  return value

    .trim()

    .toUpperCase()

    .replace(/[^A-Z0-9]/g, '')

}

function upsertManualCoordinateState(

  entry: ManualCoordinateEntry,

) {

  const code = normalizeCoordinateCode(

    entry.location_code,

  )


 

  manualCoordinates.value = [

    ...manualCoordinates.value.filter(

      (item) =>

        normalizeCoordinateCode(

          item.location_code,

        ) !== code,

    ),

    entry,

  ]

}

async function handleCoordinateSaved(

  entry: ManualCoordinateEntry,

) {

  // 저장 응답을 먼저 화면 상태에 반영한다.

  upsertManualCoordinateState(entry)


 

  // Backend 원본과 다시 동기화한다.

  await loadManualCoordinates()


 

  await refreshStopbyRoutes(

    routes.value,

    transports.value,

  )

}


 

async function handleCoordinateDeleted(

  payload: {

    locationCode: string

  },

) {

  const code = normalizeCoordinateCode(

    payload.locationCode,

  )


 

  manualCoordinates.value =

    manualCoordinates.value.filter(

      (item) =>

        normalizeCoordinateCode(

          item.location_code,

        ) !== code,

    )


 

  await loadManualCoordinates()


 

  await refreshStopbyRoutes(

    routes.value,

    transports.value,

  )

}


 

watch(

  () =>

    selectedTransport.value

      ?.transport_key,

  () => {

    syncSelectedTransportAis()


 

    void loadSelectedTimeline(

      selectedTransport.value,

    )

  },

)


 

watch(

  () => approvedMiEvents.value.map((event) => event.event_id).join('|'),

  () => {

    const currentExists = approvedMiEvents.value.some(

      (event) => event.event_id === selectedMiEventId.value,

    )


 

    if (!currentExists) {

      selectedMiEventId.value = approvedMiEvents.value[0]?.event_id ?? ''

    }

  },

  { immediate: true },

)


 

watch(

  () =>

    activeCargoAisView.value

      .diagnostics,

  (diagnostics) => {

    console.log(

      '[Active cargo AIS filter]',

      diagnostics,

    )

  },

  {

    immediate: true,

    deep: true,

  },

)


 

watch(

  activeCargoAisItems,

  (items) => {

    if (

      selectedAisId.value

      && !items.some(

        (item) =>

          item.ais_id

          === selectedAisId.value,

      )

    ) {

      selectedAisId.value = ''

    }


 

    syncSelectedTransportAis()

  },

  {

    deep: true,

  },

)


 

watch(

  () =>

    activeCargoAisView.value

      .diagnostics,

  (diagnostics) => {

    console.log(

      '[Active cargo AIS filter]',

      diagnostics,

    )

  },

  {

    immediate: true,

    deep: true,

  },

)


 

onMounted(() => {

  void loadRegistryZones()

  window.addEventListener('mi-registry-changed', handleRegistryChanged)

  void loadManualCoordinates()

  void initializeMiPersistence()

  clockTimer = window.setInterval(() => {

    now.value = new Date()

  }, 1000)

  // 시작 시 자동 overview 조회는 하지 않는다.

  // 사용자가 법인 변경/새로고침으로 명시 조회할 때만 loadDashboard가 동작한다.

})


 

onBeforeUnmount(() => {

  if (clockTimer) {

    window.clearInterval(clockTimer)

  }

  activeController?.abort()

  timelineController?.abort()

  timelineRequestGuard.invalidate()

  marinesiaController?.abort()

  stopbyRouteController?.abort()

})

</script>


 

<template>

  <div class="app-shell logistics-light-theme">

    <header class="topbar">

      <div class="brand">

        <div class="brand-mark">LRI</div>


 

        <div>

          <h1>Global Logistics Risk Intelligence</h1>

          <p>B-LAP Schedule Anomaly Trigger Hub</p>

        </div>

      </div>


 

      <div class="topbar-status">

        <nav class="workspace-tabs" aria-label="작업 화면 전환">

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'dashboard' }"

            @click="activeWorkspace = 'dashboard'"

          >

            운송 이상 · AIS

          </button>


 

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'mi' }"

            @click="activeWorkspace = 'mi'"

          >

            외부 MI 정제

          </button>


 

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'vessel' }"

            @click="activeWorkspace = 'vessel'"

          >

            선박 MMSI 관리

          </button>


 

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'inventory' }"

            disabled

            title="현재 사용하지 않는 탭입니다"

            @click="activeWorkspace = 'inventory'"

          >

            재고 영향

          </button>


 

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'report' }"

            @click="activeWorkspace = 'report'"

          >

            MI 리포트

          </button>



          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'gap' }"

            @click="activeWorkspace = 'gap'"

          >

            지연 추이

          </button>


 

          <button

            type="button"

            class="workspace-tab"

            :class="{ active: activeWorkspace === 'routes' }"

            @click="activeWorkspace = 'routes'"

          >

            경로 조회

          </button>


 

        </nav>


 

        <label

          v-if="activeWorkspace !== 'mi'"

          class="company-filter"

        >

          <span>법인</span>

          <select

            v-model="selectedCompany"

            :disabled="loading"

            @change="loadDashboard(true)"

          >

            <option

              v-for="option in companyOptions"

              :key="option.value"

              :value="option.value"

            >

              {{ option.label }}

            </option>

          </select>

        </label>


 

        <AisUploadPanel

          v-if="activeWorkspace === 'dashboard'"

          :result="aisUpload"

          @loaded="handleAisLoaded"

          @cleared="clearAisUpload"

        />


 

        <NotificationCenter @select-hbl="handleSelectHbl" />



        <span class="live-badge">

          <span class="live-dot"></span>

          LIVE

        </span>


 

        <span>{{ formattedTime }}</span>

      </div>

    </header>


 

    <main

      v-if="activeWorkspace === 'dashboard'"

      class="dashboard"

    >

      <div
        v-if="!dashboard && !loading"
        class="idle-banner"
      >
        법인을 선택하거나 새로고침을 눌러 데이터를 조회하세요.
      </div>



      <section class="map-panel">

        <button
          type="button"
          class="registry-zone-toggle"
          :class="{ off: !showRegistryZones }"
          @click="toggleRegistryZones"
        >
          레지스트리 영향권 {{ showRegistryZones ? 'ON' : 'OFF' }}
        </button>

        <LogisticsMap

          :routes="effectiveRoutes"

          :ports="effectivePorts"

          :ais-vessels="aisVessels"

          :mi-zones="miZones"
          :registry-zones="registryZones"

          :show-registry-zones="showRegistryZones"

          :mi-impacted-routes="miImpactedRoutes"

          :selected-transport-key="selectedTransportKey"

          :selected-ais-id="selectedAisId"

          :selected-mi-event-id="selectedMiEventId"

          :loading="loading"

          @select-transport="selectedTransportKey = $event"

          @select-ais="selectAis"

          @select-mi="selectMiEvent"

        />


 

        <section v-if="aisUpload" class="panel-section ais-section">

          <div class="section-heading">

            <div>

              <span class="eyebrow">AIS POSITION</span>

              <h2>화물 현재 위치</h2>

            </div>

            <span class="event-count">{{ aisSummary.mappable }}</span>

          </div>


 

          <div class="ais-summary-grid">

            <div><span>LIVE</span><strong>{{ aisSummary.live }}</strong></div>

            <div><span>STALE</span><strong>{{ aisSummary.stale }}</strong></div>

            <div><span>B-LAP 연결</span><strong>{{ aisSummary.linked }}</strong></div>

            <div><span>미연결</span><strong>{{ aisSummary.unlinked }}</strong></div>

          </div>


 

          <div v-if="selectedAis" class="ais-detail-card">

            <div class="ais-detail-title">

              <div>

                <span :class="`ais-status status-${selectedAis.position_status.toLowerCase()}`">

                  {{ selectedAis.position_status }}

                </span>

                <strong>{{ selectedAis.vessel_name }}</strong>

              </div>

              <span>{{ selectedAis.speed ?? '-' }} kn</span>

            </div>


 

            <dl class="ais-detail-grid">

              <div><dt>현재 좌표</dt><dd>{{ selectedAis.current_lat?.toFixed(4) ?? '-' }}, {{ selectedAis.current_lon?.toFixed(4) ?? '-' }}</dd></div>

              <div><dt>Heading</dt><dd>{{ selectedAis.heading ?? '-' }}°</dd></div>

              <div><dt>다음 항만</dt><dd>{{ selectedAis.next_port || '-' }}</dd></div>

              <div><dt>AIS ETA</dt><dd>{{ selectedAis.eta_ais || '-' }}</dd></div>

              <div><dt>마지막 수신</dt><dd>{{ selectedAis.last_seen_at || '-' }}</dd></div>

              <div><dt>연결 방식</dt><dd>{{ selectedAis.match_method || '미연결' }}</dd></div>

            </dl>

          </div>


 

          <div v-if="aisUpload.warnings.length" class="ais-warning">

            {{ aisUpload.warnings[0] }}

          </div>

        </section>

      </section>


 

      <aside class="side-panel">

        <div v-if="errorMessage" class="error-banner">

          <strong>데이터 조회 실패</strong>

          <span>{{ errorMessage }}</span>

        </div>


 

        <MarinesiaSharePointStatus

          :loading="marinesiaLoading"

          :root-exists="marinesiaHealth?.root_exists ?? false"

          :file-found="

            marinesiaHealth?.latest_file_found ?? false

          "

          :source-file="marinesiaSourceFile"

          :generated-at="marinesiaGeneratedAt"

          :message="marinesiaMessage"

          :error="marinesiaError"

          :total="aisSummary.total"

          :mappable="aisSummary.mappable"

          :live="aisSummary.live"

          :stale="aisSummary.stale"

          @refresh="loadMarinesiaFromSharePoint(false)"

        />


 

        <MiImpactPanel

          v-if="approvedMiEvents.length"

          :events="approvedMiEvents"

          :impacts="miImpacts"

          :summary="miImpactSummary"

          :selected-event-id="selectedMiEvent?.event_id"

          @select-event="selectMiEvent"

        />


 


        <section class="panel-section">

          <div class="section-heading">

            <div>

              <span class="eyebrow">OVERVIEW</span>

              <h2>일정 이상 현황</h2>

            </div>


 

            <button

              type="button"

              class="ghost-button"

              :disabled="loading"

              @click="loadDashboard(true)"

            >

              {{ loading ? '조회 중' : '새로고침' }}

            </button>

          </div>


 

          <div class="metrics-grid">

            <article

              v-for="metric in metrics"

              :key="metric.label"

              class="metric-card"

              :class="`metric-${metric.tone}`"

            >

              <span>{{ metric.label }}</span>

              <strong>{{ metric.value.toLocaleString() }}</strong>

            </article>

          </div>


 

          <div class="source-summary">

            <span>

              원본 {{ dashboard?.source_counts.info_rows ?? 0 }}행

            </span>

            <span>

              변경이력 {{ dashboard?.source_counts.history_rows ?? 0 }}행

            </span>

            <span>

              지도 {{ dashboard?.source_counts.map_routes ?? 0 }}개

            </span>

          </div>

        </section>


 

        <AnomalyMasterDetailPanel

          :events="events"

          :transports="transports"

          :selected-transport="selectedTransport"

          :selected-event-key="selectedEventKey"

          :timeline="scheduleTimeline"

          :timeline-loading="timelineLoading"

          :timeline-error="timelineError"

          :mi-events="approvedMiEvents"

          :mi-impacts="miImpacts"

          :cause-candidates="selectedCauseCandidates"

          @select-event="selectEvent"

          @select-mi="selectMiEvent"

        />

      </aside>

    </main>


 

    <section

      v-else-if="activeWorkspace === 'mi'"

      class="mi-workspace-host"

    >

      <MiWorkspaceView />

    </section>


 

    <section

      v-else-if="activeWorkspace === 'vessel'"

      class="mi-workspace-host vessel-workspace-host"

    >

      <VesselMmsiManager

        :transports="transports"

        :ais-items="matchedAisItems"

      />

    </section>



    <section

      v-else-if="activeWorkspace === 'inventory'"

      class="mi-workspace-host"

    >

      <InventoryImpactPanel />

    </section>



    <section

      v-else-if="activeWorkspace === 'report'"

      class="mi-workspace-host"

    >

      <LeadtimeReportPanel />

    </section>



    <section

      v-else-if="activeWorkspace === 'gap'"

      class="mi-workspace-host"

    >

      <GapPanel />

    </section>



    <section

      v-else

      class="mi-workspace-host"

    >

      <RouteMasterPanel />

    </section>


 

    <footer

      v-if="activeWorkspace === 'dashboard'"

      class="statusbar"

    >


 

      <div v-if="approvedMiEvents.length">

        <span

          class="status-indicator"

          :class="miImpactSummary.impacted_transport_count > 0 ? 'warning' : 'ok'"

        ></span>

        MI {{ approvedMiEvents.length }}건 · 영향 운송

        {{ miImpactSummary.impacted_transport_count }}건

      </div>


 

      <div>

        <span

          class="status-indicator"

          :class="errorMessage ? 'error' : 'ok'"

        ></span>

        FastAPI {{ errorMessage ? '오류' : '연결 정상' }}

      </div>


 

      <div>

        <span class="status-indicator ok"></span>

        B-LAP Data Lake

      </div>


 

      <button

        type="button"

        class="status-coordinate-button"

        @click="coordinatePanelOpen = true"

      >

        <span

          class="status-indicator"

          :class="

            missingCoordinateItems.length > 0

              ? 'warning'

              : 'ok'

          "

        ></span>


 

        좌표 미등록

        {{ missingCoordinateItems.length }}개

      </button>


 

      <div v-if="aisUpload">

        <span class="status-indicator" :class="aisSummary.mappable > 0 ? 'ok' : 'warning'"></span>

        AIS {{ aisSummary.mappable }}척 · B-LAP 연결 {{ aisSummary.linked }}척

      </div>


 

      <div class="status-message">

        마지막 갱신: {{ lastUpdatedLabel }}

      </div>


 

      <div v-if="stopbyRouteSummary">

        경유항로 {{ stopbyRouteSummary.generated }}건 ·

        IF {{ stopbyRouteSummary.explicit_stopby }}건 ·

        유럽 기본 {{

          stopbyRouteSummary.europe_default_stopby

        }}건

      </div>


 

      <div v-if="stopbyRouteError">

        경유항로 생성 실패: {{ stopbyRouteError }}

      </div>


 

    </footer>


 

    <CoordinateRegistryPanel

      :open="coordinatePanelOpen"

      :missing-items="missingCoordinateItems"

      :registered-items="manualCoordinates"

      @close="coordinatePanelOpen = false"

      @saved="handleCoordinateSaved"

      @deleted="handleCoordinateDeleted"

    />


 

  </div>

</template>


 

<style scoped>

.company-filter {

  display: flex;

  align-items: center;

  gap: 7px;

  color: #789aae;

  font-size: 10px;

}


 

.company-filter select {

  min-width: 142px;

  padding: 6px 9px;

  border: 1px solid rgba(78, 180, 243, 0.25);

  border-radius: 6px;

  background: #07192a;

  color: #d9f1ff;

  outline: none;

}


 

.error-banner {

  display: flex;

  flex-direction: column;

  gap: 4px;

  margin: 12px 12px 0;

  padding: 10px;

  border: 1px solid rgba(255, 72, 104, 0.42);

  border-radius: 7px;

  background: rgba(111, 22, 43, 0.24);

  color: #ff9bad;

  font-size: 10px;

}


 

.source-summary {

  display: flex;

  flex-wrap: wrap;

  gap: 6px;

  margin-top: 10px;

}


 

.source-summary span {

  padding: 4px 6px;

  border-radius: 4px;

  background: rgba(48, 141, 193, 0.12);

  color: #6f9ab4;

  font-size: 8px;

}


 

.alert-card {

  width: 100%;

  color: inherit;

  text-align: left;

}


 

.alert-card.selected {

  border-color: rgba(99, 220, 255, 0.55);

  background: rgba(12, 55, 84, 0.86);

  box-shadow: 0 0 15px rgba(29, 190, 242, 0.1);

}


 

.risk-score {

  display: grid;

  place-items: center;

  width: 31px;

  height: 25px;

  border-radius: 6px;

  background: rgba(255, 255, 255, 0.055);

  color: #a9c8db;

  font-size: 9px;

  font-weight: 800;

}


 

.empty-list {

  padding: 18px 10px;

  color: #66899f;

  font-size: 10px;

  line-height: 1.55;

  text-align: center;

}


 

.selected-severity {

  display: flex;

  align-items: center;

  justify-content: space-between;

  margin: 10px 0 13px;

  color: #7399b0;

  font-size: 9px;

}


 

.severity-pill {

  padding: 4px 8px;

  border-radius: 20px;

  font-weight: 800;

}


 

.severity-pill.severity-critical {

  background: rgba(255, 49, 88, 0.18);

  color: #ff6e89;

}


 

.severity-pill.severity-high {

  background: rgba(255, 138, 40, 0.18);

  color: #ffad68;

}


 

.severity-pill.severity-medium {

  background: rgba(255, 210, 74, 0.16);

  color: #ffe083;

}


 

.severity-pill.severity-low,

.severity-pill.severity-normal {

  background: rgba(50, 207, 163, 0.15);

  color: #6be5c2;

}


 

.signal-list {

  display: flex;

  flex-wrap: wrap;

  gap: 5px;

}


 

.signal-list span {

  padding: 5px 7px;

  border: 1px solid rgba(71, 190, 236, 0.19);

  border-radius: 5px;

  background: rgba(11, 49, 76, 0.55);

  color: #75bcd9;

  font-size: 8px;

}


 

.status-indicator.error {

  background: #ff4e70;

  box-shadow: 0 0 6px rgba(255, 78, 112, 0.8);

}


 

.status-coordinate-button {

  display: inline-flex;

  align-items: center;

  gap: 6px;

  margin: 0;

  padding: 0;

  border: 0;

  background: transparent;

  color: inherit;

  cursor: pointer;

  font: inherit;

}


 

.status-coordinate-button:hover {

  color: #55d9ff;

  text-decoration: underline;

}


 

.status-coordinate-button.disabled {

  cursor: default;

  text-decoration: none;

}


 

.status-coordinate-button.disabled:hover {

  color: inherit;

}


 

.ais-summary-grid {

  display: grid;

  grid-template-columns: repeat(4, minmax(0, 1fr));

  gap: 7px;

}


 

.ais-summary-grid > div {

  padding: 9px 5px;

  border: 1px solid rgba(73, 177, 218, 0.14);

  border-radius: 7px;

  background: rgba(5, 27, 45, 0.58);

  text-align: center;

}


 

.ais-summary-grid span {

  display: block;

  margin-bottom: 4px;

  color: #6b8ea2;

  font-size: 9px;

}


 

.ais-summary-grid strong {

  color: #d8f2ff;

  font-size: 15px;

}


 

.ais-detail-card {

  margin-top: 10px;

  padding: 11px;

  border: 1px solid rgba(47, 220, 171, 0.18);

  border-radius: 8px;

  background: rgba(5, 34, 42, 0.56);

}


 

.ais-detail-title,

.ais-detail-title > div {

  display: flex;

  align-items: center;

}


 

.ais-detail-title {

  justify-content: space-between;

  gap: 8px;

  color: #80a1b3;

  font-size: 10px;

}


 

.ais-detail-title > div {

  min-width: 0;

  gap: 7px;

}


 

.ais-detail-title strong {

  overflow: hidden;

  color: #dff7ff;

  font-size: 13px;

  text-overflow: ellipsis;

  white-space: nowrap;

}


 

.ais-status {

  padding: 3px 6px;

  border-radius: 9px;

  font-size: 8px;

  font-weight: 800;

}


 

.status-live { background: rgba(54, 226, 174, .16); color: #70eac3; }

.status-stale { background: rgba(255, 184, 77, .16); color: #ffc76f; }

.status-no_signal,

.status-error,

.status-unknown { background: rgba(133, 151, 164, .16); color: #9baeb9; }


 

.ais-detail-grid {

  display: grid;

  grid-template-columns: repeat(2, minmax(0, 1fr));

  gap: 9px 11px;

  margin: 11px 0 0;

}


 

.ais-detail-grid dt {

  margin-bottom: 3px;

  color: #5f8296;

  font-size: 9px;

}


 

.ais-detail-grid dd {

  margin: 0;

  overflow: hidden;

  color: #cbe7f4;

  font-size: 10px;

  text-overflow: ellipsis;

  white-space: nowrap;

}


 

.ais-warning {

  margin-top: 8px;

  color: #ffbd68;

  font-size: 9px;

}


 

.registry-zone-toggle {

  position: absolute;

  top: 58px;

  right: 18px;

  z-index: 10;

  padding: 5px 12px;

  border: 1px solid var(--li-border);

  border-radius: 999px;

  background: var(--li-surface-strong);

  color: var(--li-text);

  font-size: 12px;

  cursor: pointer;

  box-shadow: var(--li-shadow-card);

}

.registry-zone-toggle.off {

  color: var(--li-text-faint);

}



.map-panel {

  position: relative;

}



.idle-banner {

  grid-column: 1 / -1;

  padding: 10px 14px;

  border-bottom: 1px solid var(--li-border);

  background: var(--li-surface-blue);

  color: var(--li-blue);

  font-size: 12px;

  font-weight: 700;

  text-align: center;

}



.workspace-tabs {

  display: inline-flex;

  align-items: center;

  gap: 4px;

  padding: 3px;

  border: 1px solid var(--li-border, rgba(37, 99, 235, 0.14));

  border-radius: 999px;

  background: rgba(255, 255, 255, 0.62);

  box-shadow: 0 6px 18px rgba(15, 32, 54, 0.08);

}


 

.workspace-tab {

  min-height: 31px;

  padding: 0 12px;

  color: var(--li-text-muted, #607086);

  font-size: 11px;

  font-weight: 750;

  border: 0;

  border-radius: 999px;

  background: transparent;

  cursor: pointer;

  transition:

    color 140ms ease,

    background 140ms ease,

    box-shadow 140ms ease;

}


 

.workspace-tab:hover {

  color: var(--li-blue, #2563eb);

  background: rgba(37, 99, 235, 0.07);

}


 

.workspace-tab.active {

  color: #ffffff;

  background: var(

    --li-accent-gradient,

    linear-gradient(135deg, #2563eb, #06b6d4)

  );

  box-shadow: 0 7px 16px rgba(37, 99, 235, 0.22);

}



.workspace-tab:disabled {

  opacity: 0.45;

  cursor: not-allowed;

}


 

.mi-workspace-host {

  min-width: 0;

  min-height: 0;

  padding: 18px;

  overflow: auto;

  background: transparent;

}


 

.side-panel {

  min-width: 0;

  overflow-x: hidden;

  overflow-y: auto;

}


 

.dashboard {

  grid-template-columns:

    minmax(0, 1fr)

    minmax(340px, 390px);

}


 

</style>