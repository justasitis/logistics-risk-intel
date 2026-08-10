import { computed, ref } from 'vue'
import type {
  VesselMmsiMapping,
  VesselMmsiSource,
} from '@/types/vesselMmsi'
import {
  createVesselMapping,
  normalizeVesselName,
} from '@/services/vesselMmsi'

const STORAGE_KEY = 'logistics-risk:vessel-mmsi-master:v2-exact-name'

function loadMappings(): VesselMmsiMapping[] {
  if (typeof window === 'undefined') return []

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []

    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []

    const normalized = parsed.filter(
      (value): value is VesselMmsiMapping => (
        Boolean(value)
        && typeof value === 'object'
        && typeof (
          value as VesselMmsiMapping
        ).vessel_name === 'string'
        && typeof (
          value as VesselMmsiMapping
        ).mmsi_no === 'string'
      ),
    ).map((mapping) => {
      const canonicalName = normalizeVesselName(mapping.vessel_name)
      return {
        ...mapping,
        vessel_name: canonicalName,
        normalized_vessel_name: canonicalName,
      }
    })

    // 과거 "선박명+항차"로 저장된 엔트리는 로드 시 같은 canonical
    // 키로 정규화되므로, 여기서 하나로 병합한다 (뒤쪽 엔트리 우선).
    const merged = new Map<string, VesselMmsiMapping>()
    for (const mapping of normalized) {
      merged.set(mapping.vessel_name, mapping)
    }
    return [...merged.values()]
  } catch {
    return []
  }
}

const mappings = ref<VesselMmsiMapping[]>(loadMappings())
const storageError = ref('')

function persist(): void {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(mappings.value),
    )
    storageError.value = ''
  } catch (error) {
    storageError.value = error instanceof Error
      ? error.message
      : '브라우저 저장소에 매핑을 저장하지 못했습니다.'
  }
}

export function useVesselMmsiMaster() {
  function upsert(
    vesselName: string,
    mmsiNo: string,
    source: VesselMmsiSource = 'MANUAL',
    notes = '',
  ): VesselMmsiMapping {
    const mapping = createVesselMapping(
      vesselName,
      mmsiNo,
      source,
      notes,
    )

    const index = mappings.value.findIndex(
      (item) => item.vessel_name === mapping.vessel_name,
    )

    if (index >= 0) {
      mappings.value[index] = mapping
    } else {
      mappings.value.push(mapping)
    }

    mappings.value = [...mappings.value].sort(
      (left, right) => left.vessel_name.localeCompare(
        right.vessel_name,
      ),
    )
    persist()

    return mapping
  }

  function upsertMany(
    values: VesselMmsiMapping[],
  ): number {
    const index = new Map(
      mappings.value.map((mapping) => [
        normalizeVesselName(mapping.vessel_name),
        {
          ...mapping,
          vessel_name: normalizeVesselName(mapping.vessel_name),
          normalized_vessel_name: normalizeVesselName(mapping.vessel_name),
        },
      ]),
    )

    for (const mapping of values) {
      const key = normalizeVesselName(mapping.vessel_name)
      if (!key) continue

      index.set(key, {
        ...mapping,
        vessel_name: key,
        normalized_vessel_name: key,
      })
    }

    mappings.value = [...index.values()].sort(
      (left, right) => left.vessel_name.localeCompare(
        right.vessel_name,
      ),
    )
    persist()
    return values.length
  }

  function remove(vesselName: string): void {
    mappings.value = mappings.value.filter(
      (mapping) => mapping.vessel_name !== vesselName,
    )
    persist()
  }

  function clearAll(): void {
    mappings.value = []
    persist()
  }

  return {
    mappings: computed(() => mappings.value),
    mappingCount: computed(() => mappings.value.length),
    storageError: computed(() => storageError.value),
    upsert,
    upsertMany,
    remove,
    clearAll,
  }
}
