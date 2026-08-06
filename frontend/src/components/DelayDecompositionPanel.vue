<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { getDelayDecomposition } from '../services/delayDecompositionApi'
import type {
  DelayDecompositionCarrier,
  DelayDecompositionResponse,
  DelayDecompositionVoyage,
} from '../types/delayDecomposition'

const data = ref<DelayDecompositionResponse | null>(null)
const loading = ref(false)
const error = ref('')
const selectedGroup = ref('')
const months = ref<number>(12)

// 애니메이션 상태
const splitOn = ref(false)
const firedCount = ref(0)
const statsOn = ref(false)

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

let timers: number[] = []

function clearTimers() {
  timers.forEach((t) => window.clearTimeout(t))
  timers = []
}

onBeforeUnmount(clearTimers)

const groupOptions = computed(() => data.value?.available_groups ?? [])
const headline = computed(() => data.value?.headline ?? null)

const maxShots = computed(() =>
  Math.max(0, ...(data.value?.carriers ?? []).map((c) => c.voyages.length)),
)

// ── 헤드라인 분해 ──
const split = computed(() => {
  const h = headline.value
  if (
    !h ||
    h.dep_delay_days === null ||
    h.voyage_delta_days === null ||
    h.cumulative_delay_days === null
  ) {
    return null
  }
  const dep = h.dep_delay_days
  const voy = h.voyage_delta_days
  const total = Math.abs(dep) + Math.abs(voy)
  if (total <= 0) return null
  return {
    dep,
    voy,
    cum: h.cumulative_delay_days,
    depW: (Math.abs(dep) / total) * 100,
  }
})

const depSegStyle = computed(() => {
  if (!split.value || !splitOn.value) return { left: '0%', width: '100%' }
  return { left: '0%', width: `${split.value.depW}%` }
})

const voySegStyle = computed(() => {
  if (!split.value || !splitOn.value) return { left: '100%', width: '0%' }
  return {
    left: `${split.value.depW}%`,
    width: `${100 - split.value.depW}%`,
  }
})

// ── 탄착군 스케일 ──
interface ScaleDomain {
  lo: number
  hi: number
  ticks: number[]
}

const scale = computed<ScaleDomain>(() => {
  const values: number[] = [0]
  for (const c of data.value?.carriers ?? []) {
    for (const v of c.voyages) values.push(v.voyage_delta_days)
    for (const p of [c.p25, c.p50, c.p75, c.p90]) {
      if (p !== null) values.push(p)
    }
  }
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  const span = Math.max(hi - lo, 4)
  const rawStep = span / 5
  const steps = [1, 2, 4, 5, 10, 20]
  const step = steps.find((s) => s >= rawStep) ?? 40
  lo = Math.floor(lo / step) * step
  hi = Math.ceil(hi / step) * step
  if (lo === hi) {
    lo -= step
    hi += step
  }
  const ticks: number[] = []
  for (let v = lo; v <= hi; v += step) ticks.push(v)
  return { lo, hi, ticks }
})

function pos(v: number): string {
  const { lo, hi } = scale.value
  return `${((v - lo) / (hi - lo)) * 100}%`
}

function tickLabel(v: number): string {
  if (v === 0) return '계획 0'
  return `${v > 0 ? '+' : ''}${v}일`
}

// ── 선사 행 ──
function isThin(c: DelayDecompositionCarrier): boolean {
  return c.p50 === null || c.iqr === null
}

function isOutlier(c: DelayDecompositionCarrier, v: number): boolean {
  return c.p90 !== null && v > c.p90
}

function bandStyle(c: DelayDecompositionCarrier) {
  if (c.p25 === null || c.p75 === null) return { left: '0%', width: '0%' }
  const { lo, hi } = scale.value
  const span = hi - lo
  return {
    left: `${((c.p25 - lo) / span) * 100}%`,
    width: `${((c.p75 - c.p25) / span) * 100}%`,
  }
}

function dotTitle(v: DelayDecompositionVoyage): string {
  return `${v.vessel_nm} ${v.voyage_no} · ${v.hbl_no} · ATA ${v.ata} · ${fmtDays(v.voyage_delta_days)}`
}

// ── 포맷 ──
function fmtDays(v: number | null): string {
  if (v === null) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}일`
}

function coveragePct(v: number): number {
  return Math.round(v <= 1 ? v * 100 : v)
}

// ── 애니메이션 ──
function playAnimation() {
  clearTimers()
  const shots = maxShots.value
  if (reducedMotion) {
    splitOn.value = true
    firedCount.value = shots
    statsOn.value = true
    return
  }
  splitOn.value = false
  firedCount.value = 0
  statsOn.value = false
  timers.push(
    window.setTimeout(() => {
      splitOn.value = true
    }, 450),
  )
  for (let i = 1; i <= shots; i++) {
    timers.push(
      window.setTimeout(() => {
        firedCount.value = i
      }, 700 + 90 * i),
    )
  }
  timers.push(
    window.setTimeout(() => {
      statsOn.value = true
    }, 700 + 90 * shots + 400),
  )
}

// ── 조회 (명시적 조회만 — 마운트 자동 조회 없음) ──
async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getDelayDecomposition({
      group_id: selectedGroup.value || undefined,
      months: months.value,
    })
    data.value = res
    selectedGroup.value = res.group_id
    playAnimation()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '지연 분해 조회 실패'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="ddp">
    <header class="ddp-header">
      <div>
        <p class="ddp-eyebrow">Logistics MI · 도착지연 분해</p>
        <h2 class="ddp-title">도착지연은 어디서 생기는가</h2>
        <p v-if="data" class="ddp-meta">
          {{ data.group_name }} · 최근 {{ data.months }}개월 · 집계
          {{ data.headline.voyage_count }}항차 / 전체 {{ data.headline.total_count }}건
        </p>
      </div>
      <div class="ddp-controls">
        <label class="ddp-field">
          <span>항로 그룹</span>
          <select v-model="selectedGroup" class="ddp-select">
            <option value="" disabled>항로 그룹 선택</option>
            <option v-for="g in groupOptions" :key="g.group_id" :value="g.group_id">
              {{ g.name }}
            </option>
          </select>
        </label>
        <label class="ddp-field">
          <span>기간</span>
          <select v-model.number="months" class="ddp-select">
            <option :value="6">최근 6개월</option>
            <option :value="12">최근 12개월</option>
          </select>
        </label>
        <button class="ddp-btn" :disabled="loading" @click="load">
          {{ loading ? '조회 중…' : '조회' }}
        </button>
      </div>
    </header>

    <p v-if="error" class="ddp-error">{{ error }}</p>
    <p v-if="!data && !loading && !error" class="ddp-empty">
      항로 그룹과 기간을 선택한 뒤 [조회]를 눌러 주세요.
    </p>

    <template v-if="data">
      <!-- 블록 A: 헤드라인 분해 -->
      <section class="ddp-sec">
        <p class="ddp-kicker">Headline</p>
        <h3 class="ddp-h">
          하나의 지연을 둘로 나눕니다
          <span v-if="data.headline.coverage_warn" class="ddp-chip ddp-chip--warn">
            커버리지 {{ coveragePct(data.headline.coverage) }}% · 주의
          </span>
        </h3>

        <div class="ddp-eqbox">
          <div class="ddp-eq">
            <span class="t-ink">ATA − 최초ETA</span><span class="op">=</span
            ><span class="t-red">(ATD − 최초ETD)</span><span class="op">+</span
            ><span class="t-blue">(ATA − ATD) − (최초ETA − 최초ETD)</span>
          </div>
          <div class="ddp-eq-lab">
            <span class="t-ink">입항 누적지연</span>
            <span class="t-red">출항지연</span>
            <span class="t-blue">항해 증감 · 선사 정시성</span>
          </div>
          <p v-if="split" class="ddp-eq-num">
            {{ fmtDays(split.cum) }} = {{ fmtDays(split.dep) }} + {{ fmtDays(split.voy) }}
          </p>

          <div v-if="split" class="ddp-split">
            <div class="ddp-splitbar">
              <div class="ddp-sg ddp-sg--dep" :class="{ on: splitOn }" :style="depSegStyle">
                <span>출항지연 {{ fmtDays(split.dep) }}</span>
              </div>
              <div class="ddp-sg ddp-sg--voy" :class="{ on: splitOn }" :style="voySegStyle">
                <span>항해 증감 {{ fmtDays(split.voy) }}</span>
              </div>
            </div>
            <div class="ddp-splitax">
              <i class="l" :class="{ on: splitOn }">최초ETA 대비</i>
              <i class="r" :class="{ on: splitOn }">입항 누적지연 {{ fmtDays(split.cum) }}</i>
            </div>
          </div>
          <p v-else class="ddp-empty">분해에 필요한 수치가 부족합니다.</p>

          <p class="ddp-why">
            도착이 늦은 이유는 둘뿐입니다. <b>늦게 떠났거나, 바다에서 더 걸렸거나.</b>
            그래서 입항 누적지연은 이 두 항으로 남김없이 분해됩니다.
            나누는 이유는 <b>원인도 대응 부서도 다르기 때문</b>입니다. 합쳐 놓으면
            누구에게 무엇을 요구할지가 나오지 않습니다.
          </p>
        </div>

        <div class="ddp-terms">
          <div class="ddp-tm">
            <div class="ddp-tm-top">
              <span class="ddp-tm-dot ddp-tm-dot--ink"></span><b>입항 누적지연</b>
            </div>
            <div class="ddp-tm-eq">ATA − 최초ETA</div>
            <div class="ddp-tm-q">
              재고를 얼마나 더 쌓아야 하는가?<br />PO를 얼마나 일찍 내야 하는가?
            </div>
            <div class="ddp-tm-b">
              재고 정책과 납기 약속에 직결됩니다. 월간 헤드라인 지표.
            </div>
            <div class="ddp-caveat">※ 도착항까지의 지연. 양하 이후 내륙구간은 제외.</div>
            <div class="ddp-tm-own">OWNER · SCM · 영업</div>
          </div>

          <div class="ddp-tm">
            <div class="ddp-tm-top">
              <span class="ddp-tm-dot ddp-tm-dot--red"></span><b>출항지연</b>
            </div>
            <div class="ddp-tm-eq">ATD − 최초ETD</div>
            <div class="ddp-tm-q">출항을 제때 시키는가?</div>
            <div class="ddp-tm-b">
              선복 배분, 터미널 혼잡, 롤오버에 기인합니다. 부킹·선복 확보 단계에서
              대응합니다.
            </div>
            <div class="ddp-caveat">
              ※ CY 반입일 부재로 자사 화물 반입 지연분은 귀책 분리 불가.
            </div>
            <div class="ddp-tm-own">OWNER · 물류팀 · 포워더</div>
          </div>

          <div class="ddp-tm">
            <div class="ddp-tm-top">
              <span class="ddp-tm-dot ddp-tm-dot--blue"></span><b>항해 증감</b>
            </div>
            <div class="ddp-tm-eq">(ATA−ATD) − (최초ETA−최초ETD)</div>
            <div class="ddp-tm-q">항해를 계획대로 하는가?</div>
            <div class="ddp-tm-b">
              감속운항, 항로 우회, 기항지 스킵에 기인합니다. 선사 선정과 계약 조건으로
              대응합니다.
            </div>
            <div class="ddp-caveat">
              ※ Sea-Intelligence 등 시장 정시성 지표와 직접 비교 불가.
            </div>
            <div class="ddp-tm-own">OWNER · 구매 · 소싱</div>
          </div>
        </div>

        <p class="ddp-bridge">
          세 항 중 <b>항해 증감만 선사별로 비교할 수 있습니다.</b>
          나머지 둘은 항로 특성과 우리 실행에 좌우되지만, 항해 증감은 같은 항로에서
          선사만 바꿔도 달라집니다. 그래서 이 항이 선사 선정과 재계약의 근거가 됩니다.
        </p>
      </section>

      <!-- 블록 B: 선사 정시성 탄착군 -->
      <section class="ddp-sec">
        <p class="ddp-kicker">Carrier Scorecard</p>
        <h3 class="ddp-h">선사 정시성 탄착군</h3>

        <div class="ddp-readnote">
          <b>중앙값이 아니라 탄착군의 폭을 보십시오.</b>
          늘 4일 늦는 선사는 4일 당겨 잡으면 해결되지만, 매번 다른 선사는 계획 자체가
          불가능합니다. 과녁 중심(0일)은 계획대로 항해한 경우이고, 점 하나가 항차 한
          건입니다.
        </div>

        <div class="ddp-bar">
          <button class="ddp-btn" @click="playAnimation">항차 발사</button>
          <span class="ddp-hint"
            >최근 {{ data.months }}개월 항차를 순서대로 착탄시킵니다</span
          >
        </div>

        <div class="ddp-scale">
          <i
            v-for="t in scale.ticks"
            :key="t"
            :class="{ zero: t === 0 }"
            :style="{ left: pos(t) }"
            >{{ tickLabel(t) }}</i
          >
        </div>

        <div class="ddp-rows">
          <div v-for="c in data.carriers" :key="c.carrier_code" class="ddp-row">
            <div class="ddp-who">
              <b>{{ c.carrier_name }}</b>
              <small>{{ c.carrier_code }} · {{ c.voyage_count }}항차</small>
              <span v-if="c.coverage_warn" class="ddp-chip ddp-chip--warn">
                커버리지 {{ coveragePct(c.coverage) }}% · 주의
              </span>
              <p class="ddp-verdict" :class="`tone-${c.verdict_tone}`">{{ c.verdict }}</p>
            </div>
            <div>
              <div class="ddp-plot">
                <div
                  v-for="t in scale.ticks"
                  :key="t"
                  class="ddp-gridline"
                  :class="{ zero: t === 0 }"
                  :style="{ left: pos(t) }"
                ></div>
                <div
                  v-if="!isThin(c)"
                  class="ddp-band"
                  :class="{ on: statsOn }"
                  :style="bandStyle(c)"
                ></div>
                <div
                  v-if="!isThin(c) && c.p50 !== null"
                  class="ddp-med"
                  :class="{ on: statsOn }"
                  :style="{ left: pos(c.p50) }"
                ></div>
                <div
                  v-for="(v, i) in c.voyages"
                  :key="v.hbl_no"
                  class="ddp-dot"
                  :class="{ on: i < firedCount, out: isOutlier(c, v.voyage_delta_days) }"
                  :style="{ left: pos(v.voyage_delta_days) }"
                  :title="dotTitle(v)"
                ></div>
              </div>
              <div class="ddp-stats">
                <span v-if="isThin(c)" class="ddp-thin">표본 부족 · 통계 산출 안 함</span>
                <template v-else>
                  <span><u>중앙값</u> {{ fmtDays(c.p50) }}</span>
                  <span><u>IQR</u> {{ fmtDays(c.iqr) }}</span>
                  <span><u>상단꼬리 P90−P50</u> {{ fmtDays(c.tail) }}</span>
                </template>
              </div>
            </div>
          </div>
        </div>

        <div class="ddp-legend">
          <i><span class="ddp-sw"></span>항차 1건</i>
          <i><span class="ddp-sw ddp-sw--out"></span>P90 초과</i>
          <i><span class="ddp-swb"></span>중간 50% (IQR)</i>
          <i><span class="ddp-swl"></span>중앙값</i>
        </div>
      </section>

      <footer class="ddp-foot">
        <p>집계 단위 · 항로 × 선사 (환적 leg 분리 없음)</p>
        <p>대표값 중앙값, 산포 IQR 및 P90−P50 · 선형보간 · 표준편차 미사용</p>
        <p>최소 표본 10항차 · 미만 판정 보류</p>
        <p>
          당사 정의는 최초ETA 기준 항해일수 증감(일). Sea-Intelligence 등 시장 정시성
          지표와 직접 비교 불가
        </p>
        <p v-for="(n, i) in data.notes" :key="i">{{ n }}</p>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.ddp {
  max-width: 1000px;
  margin: 0 auto;
  padding: 8px 4px 40px;
  color: var(--li-text);
  line-height: 1.6;
}

.ddp-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
  padding-bottom: 14px;
  margin-bottom: 28px;
  border-bottom: 1.5px solid var(--li-text);
}

.ddp-eyebrow {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--li-text-faint);
}

.ddp-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.3;
}

.ddp-meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--li-text-muted);
}

.ddp-controls {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.ddp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--li-text-muted);
}

.ddp-select {
  min-height: 36px;
  padding: 0 10px;
  font-size: 12px;
  color: var(--li-text);
  border: 1px solid var(--li-border-strong);
  border-radius: 6px;
  background: var(--li-surface-strong);
}

.ddp-btn {
  min-height: 36px;
  padding: 0 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--li-text);
  border: 1px solid var(--li-border-strong);
  border-radius: 6px;
  background: var(--li-surface-strong);
  cursor: pointer;
  transition: background 0.15s ease;
}

.ddp-btn:hover {
  background: var(--li-surface-blue);
}

.ddp-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.ddp-error {
  margin: 0 0 16px;
  font-size: 12px;
  color: var(--li-risk-critical);
}

.ddp-empty {
  margin: 24px 0;
  font-size: 12px;
  color: var(--li-text-faint);
}

.ddp-sec {
  margin-bottom: 40px;
}

.ddp-kicker {
  margin: 0 0 8px;
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--li-text-faint);
}

.ddp-h {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.ddp-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 999px;
  border: 1px solid var(--li-border);
}

.ddp-chip--warn {
  color: var(--li-risk-high);
  border-color: var(--li-risk-high-border);
  background: var(--li-risk-high-bg);
}

/* ── 항등식 ── */
.ddp-eqbox {
  margin-top: 16px;
  padding: 24px 26px 20px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  background: var(--li-surface-strong);
  box-shadow: var(--li-shadow-card);
}

.ddp-eq {
  font-size: 14px;
  line-height: 2;
  white-space: nowrap;
  overflow-x: auto;
}

.ddp-eq .op {
  padding: 0 6px;
  color: var(--li-text-faint);
}

.t-ink {
  color: var(--li-text);
  font-weight: 600;
}

.t-red {
  color: var(--li-risk-critical);
  font-weight: 600;
}

.t-blue {
  color: var(--li-blue);
  font-weight: 600;
}

.ddp-eq-lab {
  display: flex;
  gap: 32px;
  margin-top: 2px;
  font-size: 11px;
}

.ddp-eq-num {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--li-text-muted);
}

.ddp-split {
  margin-top: 20px;
}

.ddp-splitbar {
  position: relative;
  height: 34px;
  border-radius: 4px;
  background: var(--li-border);
}

.ddp-sg {
  position: absolute;
  top: 0;
  height: 34px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  transition:
    left 0.8s cubic-bezier(0.35, 0, 0.2, 1),
    width 0.8s cubic-bezier(0.35, 0, 0.2, 1),
    background-color 0.5s ease;
}

.ddp-sg span {
  font-size: 12px;
  color: var(--li-surface-strong);
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.35s ease 0.5s;
}

.ddp-sg.on span {
  opacity: 1;
}

.ddp-sg--dep {
  background-color: var(--li-text);
}

.ddp-sg--dep.on {
  background-color: var(--li-risk-critical);
}

.ddp-sg--voy {
  background-color: var(--li-blue);
}

.ddp-splitax {
  position: relative;
  height: 30px;
  margin-top: 5px;
  font-size: 12px;
  color: var(--li-text-faint);
}

.ddp-splitax i {
  position: absolute;
  font-style: normal;
  white-space: nowrap;
  line-height: 1.5;
  opacity: 0;
  transition: opacity 0.4s ease 0.55s;
}

.ddp-splitax i.on {
  opacity: 1;
}

.ddp-splitax .l {
  left: 0;
}

.ddp-splitax .r {
  right: 0;
}

.ddp-why {
  margin: 18px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--li-border);
  max-width: 70ch;
  font-size: 13px;
  line-height: 1.8;
  color: var(--li-text-soft);
}

/* ── 세 항 카드 ── */
.ddp-terms {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1px;
  margin-top: 18px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  background: var(--li-border);
  overflow: hidden;
}

.ddp-tm {
  padding: 18px 18px 20px;
  background: var(--li-surface-strong);
}

.ddp-tm-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.ddp-tm-top b {
  font-size: 13px;
  font-weight: 600;
}

.ddp-tm-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex: 0 0 auto;
}

.ddp-tm-dot--ink {
  background: var(--li-text);
}

.ddp-tm-dot--red {
  background: var(--li-risk-critical);
}

.ddp-tm-dot--blue {
  background: var(--li-blue);
}

.ddp-tm-eq {
  margin-bottom: 10px;
  font-size: 11px;
  color: var(--li-text-faint);
  line-height: 1.6;
}

.ddp-tm-q {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.6;
}

.ddp-tm-b {
  font-size: 12px;
  color: var(--li-text-muted);
  line-height: 1.7;
}

.ddp-caveat {
  margin-top: 9px;
  font-size: 11px;
  color: var(--li-risk-critical);
  line-height: 1.65;
}

.ddp-tm-own {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dotted var(--li-border-strong);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--li-text-faint);
}

.ddp-bridge {
  margin: 20px 0 0;
  max-width: 70ch;
  font-size: 13px;
  line-height: 1.8;
  color: var(--li-text-soft);
}

/* ── 탄착군 ── */
.ddp-readnote {
  margin: 16px 0 20px;
  padding: 13px 16px;
  max-width: 74ch;
  border-left: 3px solid var(--li-blue);
  background: var(--li-surface-strong);
  font-size: 12px;
  line-height: 1.75;
  color: var(--li-text-soft);
}

.ddp-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.ddp-hint {
  font-size: 11px;
  color: var(--li-text-faint);
}

.ddp-scale {
  position: relative;
  height: 24px;
  margin: 0 0 6px 190px;
  font-size: 12px;
  color: var(--li-text-faint);
}

.ddp-scale i {
  position: absolute;
  font-style: normal;
  transform: translateX(-50%);
  white-space: nowrap;
}

.ddp-scale i.zero {
  color: var(--li-text);
  font-weight: 600;
}

.ddp-row {
  display: grid;
  grid-template-columns: 190px 1fr;
  align-items: center;
  gap: 0;
  padding: 14px 0;
  border-top: 1px solid var(--li-border);
}

.ddp-row:last-child {
  border-bottom: 1px solid var(--li-border);
}

.ddp-who {
  padding-right: 18px;
}

.ddp-who b {
  display: block;
  font-size: 13px;
  font-weight: 600;
}

.ddp-who small {
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--li-text-faint);
}

.ddp-who .ddp-chip {
  margin-top: 6px;
}

.ddp-verdict {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.55;
  color: var(--li-text-muted);
}

.ddp-verdict.tone-ok {
  color: var(--li-risk-low);
}

.ddp-verdict.tone-hot {
  color: var(--li-risk-critical);
}

.ddp-verdict.tone-warn {
  color: var(--li-risk-high);
}

.ddp-verdict.tone-steady {
  color: var(--li-text-soft);
}

.ddp-verdict.tone-hold,
.ddp-verdict.tone-neutral {
  color: var(--li-text-muted);
}

.ddp-plot {
  position: relative;
  height: 56px;
}

.ddp-gridline {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px dotted var(--li-border-strong);
}

.ddp-gridline.zero {
  border-left: 1.5px solid var(--li-text);
  opacity: 0.55;
}

.ddp-band {
  position: absolute;
  top: 16px;
  height: 24px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--li-blue) 16%, transparent);
  opacity: 0;
  transition: opacity 0.5s ease;
}

.ddp-band.on {
  opacity: 1;
}

.ddp-med {
  position: absolute;
  top: 10px;
  height: 36px;
  border-left: 2px solid var(--li-blue);
  opacity: 0;
  transition: opacity 0.5s ease;
}

.ddp-med.on {
  opacity: 1;
}

.ddp-dot {
  position: absolute;
  top: 22px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--li-text);
  opacity: 0;
  transform: translate(-50%, -14px) scale(0.4);
  transition:
    opacity 0.28s ease-out,
    transform 0.34s cubic-bezier(0.2, 1.5, 0.4, 1);
}

.ddp-dot.on {
  opacity: 0.42;
  transform: translate(-50%, 0) scale(1);
}

.ddp-dot.out {
  background: var(--li-risk-critical);
}

.ddp-dot.out.on {
  opacity: 0.75;
}

.ddp-stats {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: var(--li-text-muted);
}

.ddp-stats u {
  text-decoration: none;
  color: var(--li-text-faint);
}

.ddp-thin {
  font-size: 11px;
  color: var(--li-text-faint);
}

.ddp-legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  margin-top: 18px;
  font-size: 11px;
  color: var(--li-text-muted);
}

.ddp-legend i {
  font-style: normal;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.ddp-sw {
  width: 11px;
  height: 11px;
  display: inline-block;
  border-radius: 50%;
  background: var(--li-text);
  opacity: 0.42;
}

.ddp-sw--out {
  background: var(--li-risk-critical);
  opacity: 0.75;
}

.ddp-swb {
  width: 16px;
  height: 9px;
  display: inline-block;
  border-radius: 2px;
  background: color-mix(in srgb, var(--li-blue) 16%, transparent);
}

.ddp-swl {
  width: 2px;
  height: 12px;
  display: inline-block;
  background: var(--li-blue);
}

.ddp-foot {
  margin-top: 36px;
  padding-top: 14px;
  border-top: 1px solid var(--li-border);
  font-size: 11px;
  color: var(--li-text-faint);
  line-height: 2;
}

.ddp-foot p {
  margin: 0;
}

@media (max-width: 680px) {
  .ddp-title {
    font-size: 19px;
  }

  .ddp-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .ddp-scale {
    margin-left: 0;
  }

  .ddp-eqbox {
    padding: 18px 16px 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ddp-sg,
  .ddp-sg span,
  .ddp-splitax i,
  .ddp-dot,
  .ddp-band,
  .ddp-med,
  .ddp-btn {
    transition: none;
  }
}
</style>
