<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  deleteLeadtimeOverrides,
  getEtaAtaGap,
  getLeadtimeReport,
  getReportSnapshot,
  publishReportSnapshot,
  putLeadtimeOverrides,
} from '../services/leadtimeApi'
import { getApprovedMapZones } from '../services/miRegistryApi'
import type { ApprovedMapZone } from '../services/miRegistryApi'
import type { EtaAtaGapResponse, GapGroupSummary } from '../types/gap'
import type {
  InsightDraftResponse,
  LeadtimeGroup,
  LeadtimeReport,
  LeadtimeRow,
  ReportSnapshot,
} from '../types/leadtime'
import FreightIndicesChart from './FreightIndicesChart.vue'
import MiInsightDraftPanel from './MiInsightDraftPanel.vue'
import MiReportMap from './MiReportMap.vue'

const freightChart = ref<InstanceType<typeof FreightIndicesChart> | null>(null)
const reportMap = ref<InstanceType<typeof MiReportMap> | null>(null)

const report = ref<LeadtimeReport | null>(null)
const insight = ref<InsightDraftResponse | null>(null)
const loading = ref(false)
const error = ref('')

// 승인 MI 이벤트 영향권 — 리포트 지도와 이벤트 목록이 같은 소스를 공유
const approvedZones = ref<ApprovedMapZone[]>([])

const STATUS_LABELS: Record<string, string> = {
  ACTIVE: '진행 중',
  WATCH: '주시',
  IMPROVING: '완화',
  RESOLVED: '해소',
}
const STATUS_ORDER: Record<string, number> = {
  ACTIVE: 0,
  WATCH: 1,
  IMPROVING: 2,
  RESOLVED: 3,
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

const sortedApprovedEvents = computed<ApprovedMapZone[]>(() =>
  [...approvedZones.value].sort((a, b) => {
    const byStatus = (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9)
    return byStatus !== 0 ? byStatus : b.valid_from.localeCompare(a.valid_from)
  }),
)

function zoneLocationNames(zone: ApprovedMapZone): string {
  return zone.locations.map((loc) => loc.name).join(', ') || '-'
}

function zonePeriod(zone: ApprovedMapZone): string {
  return `${zone.valid_from || '-'} ~ ${zone.valid_to ?? '진행 중'}`
}

// 셀 수동 편집 (서버 override 파일에 명시 저장)
const editMode = ref(false)
const editValues = ref<Record<string, string>>({})
const savingCells = ref(false)

// 게시본(스냅샷) — 지정 사용자만 갱신, 전원 열�
const canPublish = ref(false)
const publishedMeta = ref<{ at: string; by: string } | null>(null)
const publishing = ref(false)

// ETA-ATA Gap 요약 (그룹별 배지) — 게시본에 포함되면 그것 사용
const gapData = ref<EtaAtaGapResponse | null>(null)

const GAP_LEVEL_LABELS: Record<string, string> = {
  OK: '정상',
  WATCH: '주의',
  WARN: '경고',
}

const gapByGroup = computed<Map<string, GapGroupSummary>>(() => {
  const map = new Map<string, GapGroupSummary>()
  for (const g of gapData.value?.groups ?? []) map.set(g.group_id, g)
  return map
})

function gapBadge(groupId: string): GapGroupSummary | null {
  return gapByGroup.value.get(groupId) ?? null
}

function formatGapValue(value: number | null): string {
  if (value === null) return '-'
  return value > 0 ? `+${value}` : String(value)
}

function applySnapshot(snapshot: ReportSnapshot) {
  report.value = snapshot.report
  insight.value = snapshot.insight
  gapData.value = snapshot.gap ?? null
  publishedMeta.value = {
    at: snapshot.published_at,
    by: snapshot.published_by,
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const snap = await getReportSnapshot()
    canPublish.value = snap.can_publish
    if (snap.exists && snap.snapshot) {
      applySnapshot(snap.snapshot)
      if (!snap.snapshot.gap) {
        // 구형 게시본(Gap 미포함)이면 Gap만 라이브 조회
        gapData.value = await getEtaAtaGap().catch(() => null)
      }
      return
    }
    // 게시본이 아직 없으면 라이브 집계로 폴�
    publishedMeta.value = null
    const [liveReport, liveGap] = await Promise.all([
      getLeadtimeReport(),
      getEtaAtaGap().catch(() => null),
    ])
    report.value = liveReport
    gapData.value = liveGap
  } catch (e) {
    error.value = e instanceof Error ? e.message : '리포트 조회 실패'
  } finally {
    loading.value = false
  }
}

/** 게시본 갱신 — 라이브 재집계 후 SharePoint에 저장 (지정 사용자만) */
async function publish() {
  publishing.value = true
  error.value = ''
  try {
    applySnapshot(await publishReportSnapshot())
  } catch (e) {
    error.value = e instanceof Error ? e.message : '게시본 갱신 실패'
  } finally {
    publishing.value = false
  }
}

async function loadApprovedEvents() {
  try {
    approvedZones.value = await getApprovedMapZones()
  } catch {
    approvedZones.value = []
  }
}

onMounted(load)
onMounted(loadApprovedEvents)

function cellKey(groupId: string, country: string, stat: string, month: string): string {
  return `${groupId}|${country}|${stat}|${month}`
}

function isEdited(key: string): boolean {
  return (report.value?.edited_cells ?? []).includes(key)
}

function onCellInput(key: string, e: Event) {
  editValues.value[key] = (e.target as HTMLInputElement).value
}

async function saveCells() {
  const overrides: Record<string, number> = {}
  for (const [key, value] of Object.entries(editValues.value)) {
    const num = Number(value)
    if (value.trim() !== '' && Number.isFinite(num)) overrides[key] = num
  }
  savingCells.value = true
  error.value = ''
  try {
    if (Object.keys(overrides).length) await putLeadtimeOverrides(overrides)
    editValues.value = {}
    editMode.value = false
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '편집값 저장 실패'
  } finally {
    savingCells.value = false
  }
}

async function resetCells() {
  savingCells.value = true
  error.value = ''
  try {
    await deleteLeadtimeOverrides()
    editValues.value = {}
    editMode.value = false
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '편집값 초기화 실패'
  } finally {
    savingCells.value = false
  }
}

const STATS = ['Avg', 'Min', 'Max'] as const

interface CountryBlock {
  country: string
  label: string
  fixed: boolean
  rowsByStat: Record<string, LeadtimeRow | undefined>
}

/** 그룹의 행을 국가(또는 고정 행) 단위 블록으로 묶기 — 고정 행(훼리 등) 포함 범용 처리 */
function countryBlocks(group: LeadtimeGroup): CountryBlock[] {
  const blocks: CountryBlock[] = []
  for (const row of group.rows) {
    let block = blocks.find((b) => b.country === row.country)
    if (!block) {
      block = {
        country: row.country,
        label: row.country_label,
        fixed: row.fixed === true,
        rowsByStat: {},
      }
      blocks.push(block)
    }
    block.rowsByStat[row.stat] = row
  }
  return blocks
}

function rowCellText(row: LeadtimeRow | undefined, month: string): string {
  const value = row?.cells[month]
  return value === undefined ? '' : String(value)
}

/** 현재 월 이전에 값이 있는 가장 가까운 월의 값 */
function prevCellValue(row: LeadtimeRow, monthKey: string): number | null {
  if (!report.value) return null
  const cols = report.value.month_columns
  const idx = cols.findIndex((c) => c.key === monthKey)
  for (let i = idx - 1; i >= 0; i -= 1) {
    const prevCol = cols[i]
    if (!prevCol) continue
    const prev = row.cells[prevCol.key]
    if (prev !== undefined && prev !== null) return prev
  }
  return null
}

/** 전월 대비 증감 — 같은 행에서 현재 월 이전에 값이 있는 가장 가까운 월과 비교 */
function cellDelta(row: LeadtimeRow | undefined, monthKey: string): number | null {
  if (!row) return null
  const current = row.cells[monthKey]
  if (current === undefined || current === null) return null
  const prev = prevCellValue(row, monthKey)
  if (prev === null) return null
  const delta = Math.round((current - prev) * 10) / 10
  return delta === 0 ? null : delta
}

function formatDelta(delta: number | null): string {
  if (delta === null) return ''
  return `${delta > 0 ? '▲' : '▼'}${Math.abs(delta)}`
}

function formatSignedDelta(delta: number): string {
  return `Δ${delta > 0 ? '+' : '-'}${Math.abs(delta)}일`
}

interface RegionHighlight {
  label: string // 항로명(첫 열 구분자 값)
  prev: number
  value: number
  delta: number
}

/** 권역(유럽/미주/아시아)별 최신 실적 월 기준 전월 대비 변동(|delta|)이 가장 큰 항로 1개씩 (Avg 행만, 고정 행 제외) */
const regionHighlights = computed<Array<{ region: string; item: RegionHighlight | null }>>(() => {
  const r = report.value
  if (!r) return []
  const actualCols = r.month_columns.filter((c) => c.kind === 'actual')
  const latestCol = actualCols[actualCols.length - 1]
  const bestByRegion = new Map<string, RegionHighlight>()
  if (latestCol) {
    const latest = latestCol.key
    for (const group of r.groups) {
      const region = group.region || '기타'
      for (const block of countryBlocks(group)) {
        if (block.fixed) continue
        const row = block.rowsByStat.Avg
        if (!row) continue
        const current = row.cells[latest]
        if (current === undefined || current === null) continue
        const prev = prevCellValue(row, latest)
        if (prev === null) continue
        const delta = Math.round((current - prev) * 10) / 10
        if (delta === 0) continue
        const best = bestByRegion.get(region)
        if (!best || Math.abs(delta) > Math.abs(best.delta)) {
          bestByRegion.set(region, {
            label: `${group.name}(${block.label})`,
            prev,
            value: current,
            delta,
          })
        }
      }
    }
  }
  return REGION_ORDER.map((name) => ({ region: name, item: bestByRegion.get(name) ?? null }))
})

const highlightMonthLabel = computed<string>(() => {
  const r = report.value
  if (!r) return ''
  const actualCols = r.month_columns.filter((c) => c.kind === 'actual')
  return actualCols[actualCols.length - 1]?.label ?? ''
})

// ---------- 권역(region) 섹션 ----------
const REGION_ORDER = ['유럽', '미주', '아시아']

interface RegionSection {
  name: string
  groups: LeadtimeGroup[]
}

const regionSections = computed<RegionSection[]>(() => {
  const r = report.value
  if (!r) return []
  const byRegion = new Map<string, LeadtimeGroup[]>()
  for (const group of r.groups) {
    const region = group.region || '기타'
    if (!byRegion.has(region)) byRegion.set(region, [])
    byRegion.get(region)?.push(group)
  }
  return [...byRegion.entries()]
    .sort((a, b) => {
      const ia = REGION_ORDER.indexOf(a[0])
      const ib = REGION_ORDER.indexOf(b[0])
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
    })
    .map(([name, groups]) => ({ name, groups }))
})

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function doPrint() {
  window.print()
}

/** 현재 리포트를 단독 HTML 파일로 낙출력 (메일/SharePoint 배포용) */
function exportHtml() {
  if (!report.value) return
  const r = report.value
  const sections = regionSections.value
    .map((section) => {
      const groupsHtml = section.groups
        .map((g) => {
          const head = r.month_columns
            .map((m) => `<th class="${m.kind}">${m.label}</th>`)
            .join('')
          const body = countryBlocks(g).map((block) => {
            const rows = STATS.map((stat, i) => {
              const cells = r.month_columns
                .map((m) => {
                  const d = cellDelta(block.rowsByStat[stat], m.key)
                  const deltaHtml = d === null
                    ? ''
                    : ` <span class="d ${d > 0 ? 'up' : 'down'}">${d > 0 ? '▲' : '▼'}${Math.abs(d)}</span>`
                  return `<td class="${m.kind}">${escapeHtml(rowCellText(block.rowsByStat[stat], m.key))}${deltaHtml}</td>`
                })
                .join('')
              const labelCell = i === 0
                ? `<td rowspan="3" class="country">${escapeHtml(block.label)}${block.fixed ? ' <span class="fixed-badge">고정값</span>' : ''}</td>`
                : ''
              return `<tr>${labelCell}<td class="stat">${stat}</td>${cells}</tr>`
            })
            return rows.join('')
          }).join('')
          return `<div class="card group-card"><h2>${escapeHtml(g.name)}</h2><table><thead><tr><th>${escapeHtml(g.row_label ?? '국가')}</th><th>구분</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`
        })
        .join('')
      return `<h2 class="region-title">${escapeHtml(section.name)} 권역</h2>${groupsHtml}`
    })
    .join('')
  const defs = Object.values(r.definitions).map((d) => `<li>${escapeHtml(d)}</li>`).join('')
  const insightHtml = (() => {
    const draft = insight.value
    if (!draft) return ''
    const sectionsHtml = draft.draft.sections
      .map((s) => `<div class="insight-section"><h3>${escapeHtml(s.title)}</h3><p>${escapeHtml(s.body)}</p></div>`)
      .join('')
    const keyChanges = (draft.draft.key_changes ?? [])
      .map((c, i) => `<div class="key-change"><span class="kc-num">${i + 1}</span><span>${escapeHtml(c)}</span></div>`)
      .join('')
    const keyChangesHtml = keyChanges
      ? `<div class="card"><h2>핵심 변화 (Executive Summary)</h2><div class="kc-grid">${keyChanges}</div></div>`
      : ''
    const points = draft.draft.monitoring_points
      .map((p) => `<li>${escapeHtml(p)}</li>`)
      .join('')
    return `${keyChangesHtml}
<div class="card"><h2>월간 인사이트 (${escapeHtml(draft.month)})</h2>
<p class="meta">AI 생성 검토용 초안 · 생성 ${escapeHtml(draft.generated_at)}</p>
${sectionsHtml}
<h3>익월 체크 포인트</h3><ul>${points}</ul>
<p class="disclaimer">${escapeHtml(draft.draft.disclaimer)}</p></div>`
  })()
  const regionChangesHtml = `<div class="card"><h2>금월 핵심 변동 (${escapeHtml(highlightMonthLabel.value)} 기준 · 권역별 전월 대비 최대 변동 항로)</h2><div class="hl-grid">${regionHighlights.value
    .map((h) => {
      if (!h.item) {
        return `<div class="card hl-card"><div class="hl-label">${escapeHtml(h.region)}</div><div class="hl-empty">데이터 없음</div></div>`
      }
      const item = h.item
      return `<div class="card hl-card ${item.delta > 0 ? 'hl-up' : 'hl-down'}">
<div class="hl-label">${escapeHtml(h.region)} — ${escapeHtml(item.label)}</div>
<div class="hl-value">${item.prev}<span class="hl-unit">일</span> → ${item.value}<span class="hl-unit">일</span></div>
<div class="hl-delta ${item.delta > 0 ? 'up' : 'down'}">전월 대비 ${item.delta > 0 ? 'Δ+' : 'Δ-'}${Math.abs(item.delta)}일</div>
</div>`
    })
    .join('')}</div></div>`
  const eventsHtml = sortedApprovedEvents.value.length
    ? `<div class="card"><h2>승인 MI 이벤트 (리드타임 원인 참고)</h2><table><thead><tr><th>상태</th><th>심각도</th><th>헤드라인</th><th>영향 지역</th><th>기간</th></tr></thead><tbody>${sortedApprovedEvents.value
        .map((ev) => `<tr><td><span class="status-badge status-${ev.status.toLowerCase()}">${statusLabel(ev.status)}</span></td><td>${escapeHtml(ev.severity)}</td><td class="headline">${escapeHtml(ev.headline)}</td><td>${escapeHtml(zoneLocationNames(ev))}</td><td>${escapeHtml(zonePeriod(ev))}</td></tr>`)
        .join('')}</tbody></table></div>`
    : ''
  const html = `<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>물류 MI Report — 항로별 리드타임</title>
<style>
body{font-family:'Malgun Gothic','Pretendard',sans-serif;margin:0;padding:32px;color:#122033;background:#f6f8fb}
.report{max-width:1120px;margin:0 auto}
.hero{background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 55%,#06b6d4 100%);border-radius:20px;padding:26px 30px;color:#fff;box-shadow:0 18px 44px rgba(15,32,54,.16)}
.hero-eyebrow{margin:0 0 6px;font-size:11px;font-weight:800;letter-spacing:.14em;opacity:.85}
.hero h1{margin:0;font-size:24px;font-weight:800;letter-spacing:-.02em}
.hero .meta{color:rgba(255,255,255,.82);font-size:11px;margin:10px 0 0}
h2{font-size:14px;margin:0 0 10px;color:#122033}
h3{font-size:12px;margin:14px 0 6px;color:#344861}
.card{background:rgba(255,255,255,.92);border:1px solid rgba(16,42,67,.11);border-radius:14px;padding:16px 18px;box-shadow:0 12px 28px rgba(15,32,54,.08);margin-top:14px}
.hl-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
.hl-card{margin-top:0}
.hl-up{border-color:rgba(239,68,68,.34)}
.hl-down{border-color:rgba(16,185,129,.31)}
.hl-label{font-size:12px;color:#344861;font-weight:700}
.hl-value{margin-top:8px;font-size:26px;font-weight:800}
.hl-unit{font-size:12px;color:#607086;margin-left:2px}
.hl-delta{margin-top:4px;font-size:12px;font-weight:700}
.hl-empty{margin-top:8px;font-size:12px;color:#8a98aa}
.up{color:#ef4444}
.down{color:#10b981}
.d{font-size:11px;font-weight:700;margin-left:3px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px;border:1px solid rgba(16,42,67,.11);border-radius:10px;overflow:hidden}
th,td{border-bottom:1px solid rgba(16,42,67,.11);border-right:1px solid rgba(16,42,67,.08);padding:6px 8px;text-align:center}
th{background:#eef3f8;color:#344861;font-size:11px;font-weight:800;letter-spacing:.03em}
tr:last-child td{border-bottom:none}
th:last-child,td:last-child{border-right:none}
td.country{font-weight:700;background:#f6f8fb}
td.stat{color:#607086;font-size:11px}
td.forecast,th.forecast{background:rgba(219,234,254,.75);color:#2563eb;font-weight:700}
.fixed-badge{display:inline-block;margin-left:4px;padding:1px 6px;border-radius:999px;font-size:11px;background:rgba(249,115,22,.14);color:#f97316;border:1px solid rgba(249,115,22,.34)}
.meta{color:#607086;font-size:11px;margin:4px 0 10px}
ul{font-size:11px;color:#607086}
.kc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.key-change{display:flex;gap:10px;align-items:flex-start;background:linear-gradient(135deg,rgba(37,99,235,.08),rgba(6,182,212,.10));border:1px solid rgba(37,99,235,.18);border-radius:10px;padding:10px 12px;font-size:12px;line-height:1.5}
.kc-num{display:inline-grid;place-items:center;min-width:22px;height:22px;border-radius:999px;background:linear-gradient(135deg,#2563eb,#06b6d4);color:#fff;font-size:12px;font-weight:800}
.insight-section{border-left:3px solid #2563eb;padding-left:12px;margin-top:12px}
.insight-section h3{margin:0 0 4px}
.insight-section p{margin:0;font-size:12px;line-height:1.6;color:#344861}
.disclaimer{margin:12px 0 0;font-size:11px;color:#b45309;background:rgba(245,158,11,.12);border:1px solid rgba(180,83,9,.28);border-radius:999px;display:inline-block;padding:4px 12px}
.status-badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;border:1px solid transparent;white-space:nowrap}
.status-active{background:rgba(249,115,22,.14);color:#f97316;border-color:rgba(249,115,22,.34)}
.status-watch{background:rgba(37,99,235,.13);color:#2563eb;border-color:rgba(37,99,235,.31)}
.status-improving{background:rgba(6,182,212,.13);color:#06b6d4;border-color:rgba(6,182,212,.31)}
.status-resolved{background:rgba(16,185,129,.13);color:#10b981;border-color:rgba(16,185,129,.31)}
td.headline{text-align:left}
.charts{display:flex;gap:16px;flex-wrap:wrap}
.chart-box{flex:1;min-width:320px}
.graticule line{stroke:rgba(37,99,235,.09);stroke-width:1}
.grid-line{stroke:rgba(16,42,67,.11);stroke-width:1;stroke-dasharray:3 4}
.label-box,.popup-box{fill:rgba(255,255,255,.95);stroke-width:1.2}
.label-text,.popup-title{font-size:11px;font-weight:700}
.popup-sub{font-size:11px;fill:#607086}
.label-link,.popup-link{stroke-width:1;stroke-dasharray:2 2;opacity:.7}
.land{fill:#c9dcec;stroke:rgba(255,255,255,.9);stroke-width:.6}
.zone-fill{opacity:.16}
.zone-ring{opacity:.85}
.zone-label{font-size:12px;font-weight:700;fill:#344861;paint-order:stroke;stroke:rgba(255,255,255,.85);stroke-width:3px}
.footer{margin:18px 0 0;color:#8a98aa;font-size:11px;text-align:center}
.region-title{font-size:16px;margin:26px 0 4px;color:#122033;border-left:4px solid #2563eb;padding-left:10px}
</style></head><body>
<div class="report">
<div class="hero">
<p class="hero-eyebrow">MONTHLY LOGISTICS MI REPORT</p>
<h1>물류 MI Report — 항로별 리드타임</h1>
<p class="meta">조회 시점 기준 자동 집계 · 출처: ${escapeHtml(r.source)} · 생성: ${escapeHtml(r.generated_at)}</p>
</div>
${regionChangesHtml}
${insightHtml}
${(() => {
  const svg = reportMap.value?.getSvgHtml()
  return svg ? `<div class="card"><h2>물류 이벤트 지도 (권역별 포커스)</h2>${svg}</div>` : ''
})()}
${(() => {
  const svg = freightChart.value?.getSvgHtml()
  return svg ? `<div class="card"><h2>시황 (운임지수, USD/40')</h2><div class="charts">${svg}</div></div>` : ''
})()}
${sections}
${eventsHtml}
<div class="card"><h2>정의</h2><ul>${defs}</ul></div>
<p class="footer">SK온 Global물류팀 · Logistics Risk Intelligence — 본 리포트는 자동 집계 결과이며 최종 문서는 담당자가 확정합니다.</p>
</div>
</body></html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `leadtime-report-${r.generated_at.slice(0, 10)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="leadtime-report">
    <section class="hero">
      <div class="hero-left">
        <div class="hero-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 17l5-6 4 3 6-8" />
            <path d="M18 6h3v3" />
            <path d="M3 21h18" />
          </svg>
        </div>
        <div>
          <p class="eyebrow">MONTHLY LOGISTICS MI</p>
          <h2 class="hero-title">물류 MI Report — 항로별 리드타임</h2>
          <p v-if="report" class="hero-meta">
            조회 시점 기준 자동 집계 · B-LAP 출처 · 생성 {{ report.generated_at }}
          </p>
        </div>
      </div>
      <div class="actions">
        <button class="btn" :disabled="loading || savingCells" @click="load">새로고침</button>
        <button
          v-if="canPublish"
          class="btn primary"
          :disabled="publishing"
          title="라이브로 재집계한 뒤 SharePoint 게시본으로 저장합니다"
          @click="publish"
        >
          {{ publishing ? '재집계·저장 중... (수 분 소요 가능)' : '게시본 갱신' }}
        </button>
        <button v-if="canPublish" class="btn" :disabled="!report || savingCells" @click="editMode = !editMode">
          {{ editMode ? '편집 취소' : '셀 편집' }}
        </button>
        <button v-if="canPublish && editMode" class="btn primary" :disabled="savingCells" @click="saveCells">
          {{ savingCells ? '저장 중...' : '편집값 저장' }}
        </button>
        <button v-if="canPublish" class="btn" :disabled="!report || savingCells" @click="resetCells">편집값 되돌리기</button>
        <button class="btn" :disabled="!report" @click="exportHtml">HTML 출력</button>
        <button class="btn" :disabled="!report" @click="doPrint">인쇄</button>
      </div>
    </section>

    <p v-if="publishedMeta" class="publish-banner">
      게시본 · {{ publishedMeta.at }} · {{ publishedMeta.by }} 게시
    </p>
    <p v-else-if="report && !loading" class="publish-banner live">
      라이브 집계 — 저장된 게시본이 없습니다
    </p>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="hint">집계 중...</p>
    <p v-if="report && !report.month_columns.length && !loading" class="hint">
      집계된 운송 데이터가 없습니다.
    </p>

    <template v-if="report">
      <section class="panel">
        <div class="panel-head">
          <h3 class="panel-title">금월 핵심 변동</h3>
          <span class="panel-meta">{{ highlightMonthLabel }} 기준 · 권역별 전월 대비 최대 변동 항로</span>
        </div>
        <div class="hl-grid">
          <div
            v-for="h in regionHighlights"
            :key="h.region"
            class="hl-card"
            :class="h.item ? (h.item.delta > 0 ? 'hl-up' : 'hl-down') : ''"
          >
            <template v-if="h.item">
              <div class="hl-label">{{ h.region }} — {{ h.item.label }}</div>
              <div class="hl-value">
                {{ h.item.prev }}<span class="hl-unit">일</span> → {{ h.item.value }}<span class="hl-unit">일</span>
              </div>
              <div class="hl-delta" :class="h.item.delta > 0 ? 'up' : 'down'">
                전월 대비 {{ formatSignedDelta(h.item.delta) }}
              </div>
            </template>
            <template v-else>
              <div class="hl-label">{{ h.region }}</div>
              <div class="hl-empty">데이터 없음</div>
            </template>
          </div>
        </div>
      </section>

      <MiReportMap v-if="approvedZones.length" ref="reportMap" :zones="approvedZones" />

      <MiInsightDraftPanel v-model:draft="insight" :can-edit="canPublish" />

      <FreightIndicesChart ref="freightChart" />

      <template v-for="section in regionSections" :key="section.name">
        <div class="region-header">
          <span class="region-name">{{ section.name }} 권역</span>
          <span class="region-line"></span>
        </div>

        <section v-for="group in section.groups" :key="group.group_id" class="panel">
        <div class="panel-head">
          <h3 class="panel-title">{{ group.name }}</h3>
          <span
            v-if="gapBadge(group.group_id)"
            class="gap-badge"
            :class="`level-${gapBadge(group.group_id)?.level.toLowerCase()}`"
            :title="gapBadge(group.group_id)?.level_reasons.join(' · ') || 'ETA-ATA Gap 기준 이내'"
          >
            Gap {{ formatGapValue(gapBadge(group.group_id)?.latest_avg_gap ?? null) }}일
            · {{ GAP_LEVEL_LABELS[gapBadge(group.group_id)?.level ?? 'OK'] }}
          </span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{{ group.row_label ?? '국가' }}</th>
                <th>구분</th>
                <th
                  v-for="m in report.month_columns"
                  :key="m.key"
                  :class="{ forecast: m.kind === 'forecast' }"
                >
                  {{ m.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <template v-for="block in countryBlocks(group)" :key="block.country">
                <tr v-for="(stat, i) in STATS" :key="`${block.country}-${stat}`">
                  <td v-if="i === 0" :rowspan="3" class="country">
                    {{ block.label }}
                    <span v-if="block.fixed" class="fixed-badge" title="사용자 제공 고정값 (실데이터 집계 아님)">고정값</span>
                  </td>
                  <td class="stat">{{ stat }}</td>
                  <td
                    v-for="m in report.month_columns"
                    :key="m.key"
                    :class="{
                      forecast: m.kind === 'forecast',
                      edited: isEdited(cellKey(group.group_id, block.country, stat, m.key)),
                    }"
                  >
                    <input
                      v-if="editMode"
                      type="number"
                      step="0.1"
                      class="cell-input"
                      :value="editValues[cellKey(group.group_id, block.country, stat, m.key)] ?? rowCellText(block.rowsByStat[stat], m.key)"
                      @input="onCellInput(cellKey(group.group_id, block.country, stat, m.key), $event)"
                    />
                    <template v-else>
                      <span class="cell-num">{{ rowCellText(block.rowsByStat[stat], m.key) }}</span>
                      <span
                        v-if="cellDelta(block.rowsByStat[stat], m.key) !== null"
                        class="cell-delta"
                        :class="(cellDelta(block.rowsByStat[stat], m.key) ?? 0) > 0 ? 'up' : 'down'"
                      >{{ formatDelta(cellDelta(block.rowsByStat[stat], m.key)) }}</span>
                    </template>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        </section>
      </template>

      <section v-if="sortedApprovedEvents.length" class="panel">
        <div class="panel-head">
          <h3 class="panel-title">승인 MI 이벤트</h3>
          <span class="panel-meta">리드타임 원인 참고 · 상태순 정렬</span>
        </div>
        <div class="table-wrap events-scroll">
          <table>
            <thead>
              <tr>
                <th>상태</th>
                <th>심각도</th>
                <th>헤드라인</th>
                <th>영향 지역</th>
                <th>기간</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ev in sortedApprovedEvents" :key="ev.event_id">
                <td>
                  <span class="status-badge" :class="ev.status.toLowerCase()">
                    {{ statusLabel(ev.status) }}
                  </span>
                </td>
                <td>{{ ev.severity }}</td>
                <td class="headline">{{ ev.headline }}</td>
                <td>{{ zoneLocationNames(ev) }}</td>
                <td class="period">{{ zonePeriod(ev) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel definitions">
        <div class="panel-head">
          <h3 class="panel-title">정의</h3>
        </div>
        <ul>
          <li v-for="(text, key) in report.definitions" :key="key">{{ text }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.leadtime-report {
  max-width: 1160px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ---------- 히어로 ---------- */
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 20px 22px;
  border-radius: var(--li-radius-lg);
  background: linear-gradient(135deg, #1e3a8a 0%, var(--li-blue) 55%, var(--li-cyan) 100%);
  box-shadow: var(--li-shadow-float);
  color: #fff;
}
.hero-left {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.hero-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.28);
  flex-shrink: 0;
}
.eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: rgba(255, 255, 255, 0.85);
}
.hero-title {
  margin: 0;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
}
.hero-meta {
  margin: 8px 0 0;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.82);
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.btn {
  padding: 7px 14px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.14s ease, transform 0.14s ease;
}
.btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.24);
  transform: translateY(-1px);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn.primary {
  background: #fff;
  border-color: transparent;
  color: var(--li-blue);
}

/* ---------- 패널 공통 ---------- */
.region-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}
.region-name {
  font-size: 15px;
  font-weight: 800;
  color: var(--li-text);
  letter-spacing: -0.01em;
}
.region-line {
  flex: 1;
  height: 2px;
  border-radius: 2px;
  background: var(--li-accent-gradient);
  opacity: 0.35;
}
.panel {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-lg);
  padding: 16px 18px;
  box-shadow: var(--li-shadow-card);
}
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--li-text);
}
.panel-meta {
  font-size: 11px;
  color: var(--li-text-faint);
}
.gap-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
  white-space: nowrap;
}
.gap-badge.level-ok {
  background: var(--li-risk-low-bg);
  color: var(--li-risk-low);
  border-color: var(--li-risk-low-border);
}
.gap-badge.level-watch {
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border-color: var(--li-risk-high-border);
}
.gap-badge.level-warn {
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
  border-color: var(--li-risk-critical-border);
}

/* ---------- 핵심 변동 카드 ---------- */
.hl-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 980px) {
  .hl-grid {
    grid-template-columns: 1fr;
  }
}
.hl-card {
  padding: 14px 16px;
  border-radius: var(--li-radius-md);
  background: var(--li-surface);
  border: 1px solid var(--li-border);
  box-shadow: var(--li-shadow-card);
}
.hl-up {
  border-color: var(--li-risk-critical-border);
  box-shadow: 0 14px 30px rgba(239, 68, 68, 0.1);
}
.hl-down {
  border-color: var(--li-risk-low-border);
  box-shadow: 0 14px 30px rgba(16, 185, 129, 0.1);
}
.hl-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--li-text-soft);
}
.hl-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--li-text);
}
.hl-unit {
  font-size: 12px;
  font-weight: 600;
  color: var(--li-text-muted);
  margin-left: 2px;
}
.hl-delta {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 700;
}

/* ---------- 테이블 ---------- */
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  padding: 6px 8px;
  text-align: center;
  color: var(--li-text);
  border-bottom: 1px solid var(--li-border);
  border-right: 1px solid var(--li-border);
}
tr:last-child td {
  border-bottom: none;
}
th:last-child,
td:last-child {
  border-right: none;
}
th {
  background: var(--li-bg-app-2);
  color: var(--li-text-soft);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.03em;
}
th.forecast,
td.forecast {
  background: var(--li-surface-blue);
  color: var(--li-blue);
  font-weight: 700;
}
td.edited {
  text-decoration: underline dotted var(--li-risk-high) 2px;
  text-underline-offset: 3px;
}
td.country {
  font-weight: 700;
  background: var(--li-bg-app-2);
}
td.stat {
  color: var(--li-text-muted);
  font-size: 11px;
}
.cell-num {
  font-weight: 600;
}
.cell-delta {
  margin-left: 4px;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.up {
  color: var(--li-risk-critical);
}
.down {
  color: var(--li-risk-low);
}
.cell-delta.up {
  background: var(--li-risk-critical-bg);
}
.cell-delta.down {
  background: var(--li-risk-low-bg);
}
.hl-delta.up {
  color: var(--li-risk-critical);
}
.hl-delta.down {
  color: var(--li-risk-low);
}
.hl-empty {
  margin-top: 8px;
  font-size: 12px;
  color: var(--li-text-faint);
}
.cell-input {
  width: 64px;
  padding: 2px 4px;
  border: 1px solid var(--li-blue);
  border-radius: 6px;
  font-size: 12px;
  text-align: center;
  color: var(--li-text);
  background: var(--li-surface-strong);
}
.fixed-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 400;
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border: 1px solid var(--li-risk-high-border);
}

/* ---------- 이벤트 ---------- */
.events-scroll {
  max-height: 240px;
  overflow-y: auto;
}
td.headline {
  text-align: left;
}
td.period {
  white-space: nowrap;
  color: var(--li-text-muted);
}
.status-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.status-badge.active {
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border-color: var(--li-risk-high-border);
}
.status-badge.watch {
  background: var(--li-risk-watch-bg);
  color: var(--li-risk-watch);
  border-color: var(--li-risk-watch-border);
}
.status-badge.improving {
  background: var(--li-risk-watch-bg);
  color: var(--li-risk-watch);
  border-color: var(--li-risk-watch-border);
}
.status-badge.resolved {
  background: var(--li-risk-low-bg);
  color: var(--li-risk-low);
  border-color: var(--li-risk-low-border);
}

/* ---------- 정의/기타 ---------- */
.definitions ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--li-text-muted);
}
.publish-banner {
  margin: 0;
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  color: var(--li-blue);
  background: var(--li-surface-blue);
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: 999px;
  padding: 4px 12px;
}
.publish-banner.live {
  color: var(--li-text-muted);
  background: var(--li-bg-app-2);
  border-color: var(--li-border);
}
.hint {
  color: var(--li-text-muted);
  font-size: 12px;
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>

<style>
@media print {
  body * {
    visibility: hidden;
  }
  .leadtime-report,
  .leadtime-report * {
    visibility: visible;
  }
  .leadtime-report {
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
  }
  .leadtime-report .hero .actions {
    display: none;
  }
}
</style>
