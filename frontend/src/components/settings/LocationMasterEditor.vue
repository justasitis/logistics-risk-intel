<script setup lang="ts">
import type { LocationMasterEditRow } from '../../types/config'

const LOCATION_TYPES = ['SEA_AREA', 'CHOKEPOINT', 'AIRPORT', 'PORT']

const props = defineProps<{
  rows: LocationMasterEditRow[]
}>()

function addRow() {
  props.rows.push({
    code: '',
    name: '',
    location_type: 'PORT',
    lat: 0,
    lon: 0,
    default_radius_km: 50,
    aliasesText: '',
  })
}

function removeRow(index: number) {
  props.rows.splice(index, 1)
}
</script>

<template>
  <div class="editor-table-wrap">
    <table class="editor-table">
      <thead>
        <tr>
          <th>코드</th>
          <th>이름</th>
          <th>유형</th>
          <th class="col-num">위도</th>
          <th class="col-num">경도</th>
          <th class="col-num">기본 반경(km)</th>
          <th>별칭(쉼표 구분)</th>
          <th class="col-action"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td class="col-code"><input v-model="row.code" type="text" placeholder="예: SUEZ" /></td>
          <td><input v-model="row.name" type="text" /></td>
          <td>
            <select v-model="row.location_type">
              <option v-for="type in LOCATION_TYPES" :key="type" :value="type">
                {{ type }}
              </option>
            </select>
          </td>
          <td class="col-num"><input v-model.number="row.lat" type="number" step="any" /></td>
          <td class="col-num"><input v-model.number="row.lon" type="number" step="any" /></td>
          <td class="col-num"><input v-model.number="row.default_radius_km" type="number" step="any" /></td>
          <td><input v-model="row.aliasesText" type="text" placeholder="별칭1, 별칭2" /></td>
          <td class="col-action">
            <button type="button" class="row-remove" @click="removeRow(index)">삭제</button>
          </td>
        </tr>
      </tbody>
    </table>
    <button type="button" class="row-add" @click="addRow">행 추가</button>
  </div>
</template>

<style scoped>
.editor-table-wrap { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; overflow-x: auto; }
.editor-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.editor-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--li-text-muted);
  font-size: 11px;
  border-bottom: 1px solid var(--li-border-strong);
  white-space: nowrap;
}
.editor-table td { padding: 4px 6px; border-bottom: 1px solid var(--li-border); }
.editor-table input,
.editor-table select {
  width: 100%;
  box-sizing: border-box;
  padding: 5px 8px;
  border: 1px solid var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  color: var(--li-text);
  background: var(--li-surface-strong);
}
.col-code { min-width: 110px; }
.col-num { min-width: 90px; }
.col-num input { text-align: right; }
.col-action { width: 56px; text-align: center; }
.row-remove {
  border: 1px solid var(--li-risk-critical-border);
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
  border-radius: var(--li-radius-sm);
  font-size: 11px;
  padding: 3px 8px;
  cursor: pointer;
}
.row-add {
  border: 1px solid var(--li-border-strong);
  background: var(--li-surface-strong);
  color: var(--li-text-soft);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  padding: 5px 12px;
  cursor: pointer;
}
.row-add:hover { border-color: var(--li-blue); color: var(--li-blue); }
</style>
