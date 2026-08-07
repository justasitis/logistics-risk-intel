<script setup lang="ts">
import type { CompanyEntry } from '../../types/config'

const props = defineProps<{
  rows: CompanyEntry[]
}>()

function addRow() {
  props.rows.push({ code: '', label: '', lap_code: '' })
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
          <th>법인 코드</th>
          <th>표시명</th>
          <th>LAP 코드</th>
          <th class="col-action"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td><input v-model="row.code" type="text" placeholder="예: SKO" /></td>
          <td><input v-model="row.label" type="text" placeholder="예: 한국" /></td>
          <td><input v-model="row.lap_code" type="text" /></td>
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
.editor-table-wrap { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.editor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.editor-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--li-text-muted);
  font-size: 11px;
  border-bottom: 1px solid var(--li-border-strong);
}
.editor-table td { padding: 4px 8px; border-bottom: 1px solid var(--li-border); }
.editor-table input {
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
