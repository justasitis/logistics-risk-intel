<script setup lang="ts">
import TagInput from './TagInput.vue'
import type { CarrierInferenceData } from '../../types/config'

const VIA_OPTIONS = ['SUEZ', 'CAPE']

const props = defineProps<{
  model: CarrierInferenceData
}>()

function addVesselRule() {
  props.model.vessel_carrier_rules.push({ keyword: '', carrier_cd: '', carrier_nm: '' })
}

function removeVesselRule(index: number) {
  props.model.vessel_carrier_rules.splice(index, 1)
}

function addViaRule() {
  props.model.carrier_via_rules.push({ carrier_cd: '', carrier_nm_contains: '', via: 'SUEZ' })
}

function removeViaRule(index: number) {
  props.model.carrier_via_rules.splice(index, 1)
}
</script>

<template>
  <div class="carrier-editor">
    <section class="block">
      <h4 class="block-title">ADRIA 도착항 (adria_arrival_ports)</h4>
      <TagInput v-model="model.adria_arrival_ports" placeholder="항구 코드 입력 후 Enter" />
    </section>

    <section class="block">
      <h4 class="block-title">선박명 → 선사 추론 규칙 (vessel_carrier_rules)</h4>
      <table class="editor-table">
        <thead>
          <tr>
            <th>키워드</th>
            <th>선사 코드</th>
            <th>선사명</th>
            <th class="col-action"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(rule, index) in model.vessel_carrier_rules" :key="index">
            <td><input v-model="rule.keyword" type="text" /></td>
            <td><input v-model="rule.carrier_cd" type="text" /></td>
            <td><input v-model="rule.carrier_nm" type="text" /></td>
            <td class="col-action">
              <button type="button" class="row-remove" @click="removeVesselRule(index)">삭제</button>
            </td>
          </tr>
        </tbody>
      </table>
      <button type="button" class="row-add" @click="addVesselRule">행 추가</button>
    </section>

    <section class="block">
      <h4 class="block-title">경유지 추론 규칙 (carrier_via_rules)</h4>
      <table class="editor-table">
        <thead>
          <tr>
            <th>선사 코드</th>
            <th>선사명 포함 문자열</th>
            <th>경유</th>
            <th class="col-action"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(rule, index) in model.carrier_via_rules" :key="index">
            <td><input v-model="rule.carrier_cd" type="text" /></td>
            <td><input v-model="rule.carrier_nm_contains" type="text" /></td>
            <td>
              <select v-model="rule.via">
                <option v-for="option in VIA_OPTIONS" :key="option" :value="option">
                  {{ option }}
                </option>
              </select>
            </td>
            <td class="col-action">
              <button type="button" class="row-remove" @click="removeViaRule(index)">삭제</button>
            </td>
          </tr>
        </tbody>
      </table>
      <button type="button" class="row-add" @click="addViaRule">행 추가</button>
    </section>
  </div>
</template>

<style scoped>
.carrier-editor { display: flex; flex-direction: column; gap: 18px; }
.block { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.block-title { margin: 0; font-size: 12px; color: var(--li-text-soft); }
.block .tag-input { width: 100%; box-sizing: border-box; }
.editor-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.editor-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--li-text-muted);
  font-size: 11px;
  border-bottom: 1px solid var(--li-border-strong);
}
.editor-table td { padding: 4px 8px; border-bottom: 1px solid var(--li-border); }
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
