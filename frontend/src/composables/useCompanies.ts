// 법인 목록 공유 소스 — GET /api/config/companies 조회, 실패 시 하드코딩 기본값
// App.vue / useMiWorkspace / RouteMasterPanel / MiRefinementPanel 이 모두 여기를 사용한다.
import { computed, reactive } from 'vue'
import { fetchConfigSection } from '../services/configApi'
import { isCompaniesData, type CompanyEntry } from '../types/config'

// API 조회 실패 시 기본값 (기존 하드코딩 목록과 동일)
const FALLBACK_COMPANIES: CompanyEntry[] = [
  { code: 'SKO', label: '한국', lap_code: '' },
  { code: 'SKBM', label: '헝가리', lap_code: '' },
  { code: 'SKOH', label: '헝가리', lap_code: '' },
  { code: 'SKOJ', label: '중국', lap_code: '' },
  { code: 'SKOY', label: '중국', lap_code: '' },
  { code: 'SKBA', label: '미국', lap_code: '' },
]

const state = reactive({
  companies: [...FALLBACK_COMPANIES] as CompanyEntry[],
  loaded: false,
})

let loadPromise: Promise<void> | null = null

// App 마운트 시 한 번 호출 — 법인 목록은 설정값이므로 자동 조회 허용
async function loadCompanies(): Promise<void> {
  if (!loadPromise) {
    loadPromise = (async () => {
      try {
        const section = await fetchConfigSection('companies')
        if (isCompaniesData(section.data) && section.data.companies.length > 0) {
          state.companies = section.data.companies.map((company) => ({ ...company }))
        }
        state.loaded = true
      } catch {
        // 조회 실패 시 기본값 목록 유지
      }
    })()
  }
  return loadPromise
}

export const companyCodes = computed(() => state.companies.map((company) => company.code))

export function useCompanies() {
  return {
    companies: computed(() => state.companies),
    companyCodes,
    companiesLoaded: computed(() => state.loaded),
    loadCompanies,
  }
}
