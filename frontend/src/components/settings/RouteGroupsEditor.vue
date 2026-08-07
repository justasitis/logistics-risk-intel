<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import TagInput from './TagInput.vue'
import type { RouteGroupEdit } from '../../types/config'

const REGION_OPTIONS = ['유럽', '미주', '아시아']

const props = defineProps<{
  groups: RouteGroupEdit[]
}>()

const selectedIndex = ref(0)

const selectedGroup = computed<RouteGroupEdit | null>(
  () => props.groups[selectedIndex.value] ?? null,
)

watch(
  () => props.groups.length,
  (length) => {
    if (selectedIndex.value >= length) {
      selectedIndex.value = Math.max(0, length - 1)
    }
  },
)

function addGroup() {
  props.groups.push({
    group_id: '',
    isNew: true,
    name: '',
    region: '유럽',
    arvl_codes: [],
    stopby_match: [],
    stopby_exclude: [],
    delay_target: false,
    metric_inland: false,
    row_label: '',
    rows: [],
  })
  selectedIndex.value = props.groups.length - 1
}

function removeGroup(index: number) {
  props.groups.splice(index, 1)
}

function addRow(group: RouteGroupEdit) {
  group.rows.push({
    row_id: '',
    label: '',
    field: '',
    codesText: '',
    exclude_field: '',
    exclude_codesText: '',
  })
}

function removeRow(group: RouteGroupEdit, index: number) {
  group.rows.splice(index, 1)
}
</script>

<template>
  <div class="route-groups-editor">
    <aside class="group-list">
      <button
        v-for="(group, index) in groups"
        :key="index"
        type="button"
        class="group-item"
        :class="{ active: index === selectedIndex }"
        @click="selectedIndex = index"
      >
        <span class="group-name">{{ group.name || '(이름 없음)' }}</span>
        <span class="group-meta">{{ group.group_id || '신규' }} · {{ group.region }}</span>
      </button>
      <button type="button" class="group-add" @click="addGroup">그룹 추가</button>
    </aside>

    <div v-if="selectedGroup" class="group-form">
      <div class="form-grid">
        <label class="form-field">
          <span>그룹 ID{{ selectedGroup.isNew ? '' : ' (읽기 전용)' }}</span>
          <input
            v-model="selectedGroup.group_id"
            type="text"
            :readonly="!selectedGroup.isNew"
            placeholder="예: EU_MED"
          />
        </label>
        <label class="form-field">
          <span>그룹명</span>
          <input v-model="selectedGroup.name" type="text" />
        </label>
        <label class="form-field">
          <span>권역</span>
          <select v-model="selectedGroup.region">
            <option v-for="option in REGION_OPTIONS" :key="option" :value="option">
              {{ option }}
            </option>
          </select>
        </label>
        <div class="form-field form-checks">
          <label class="check">
            <input v-model="selectedGroup.delay_target" type="checkbox" />
            지연 목표 관리 (delay_target)
          </label>
          <label class="check">
            <input v-model="selectedGroup.metric_inland" type="checkbox" />
            내륙운송 지표 (metric=inland)
          </label>
        </div>
      </div>

      <div class="form-field">
        <span>도착항 코드 (arvl_codes)</span>
        <TagInput v-model="selectedGroup.arvl_codes" placeholder="코드 입력 후 Enter" />
      </div>
      <div class="form-field">
        <span>경유지 매칭 (stopby_match)</span>
        <TagInput v-model="selectedGroup.stopby_match" placeholder="코드 입력 후 Enter" />
      </div>
      <div class="form-field">
        <span>경유지 제외 (stopby_exclude)</span>
        <TagInput v-model="selectedGroup.stopby_exclude" placeholder="코드 입력 후 Enter" />
      </div>

      <section class="rows-block">
        <h4 class="block-title">행 그룹 (row_groups)</h4>
        <table class="editor-table">
          <thead>
            <tr>
              <th>행 ID</th>
              <th>라벨</th>
              <th>필드</th>
              <th>코드(쉼표 구분)</th>
              <th>제외 필드</th>
              <th>제외 코드(쉼표 구분)</th>
              <th class="col-action"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in selectedGroup.rows" :key="rowIndex">
              <td><input v-model="row.row_id" type="text" /></td>
              <td><input v-model="row.label" type="text" /></td>
              <td><input v-model="row.field" type="text" /></td>
              <td><input v-model="row.codesText" type="text" /></td>
              <td><input v-model="row.exclude_field" type="text" /></td>
              <td><input v-model="row.exclude_codesText" type="text" /></td>
              <td class="col-action">
                <button
                  type="button"
                  class="row-remove"
                  @click="removeRow(selectedGroup, rowIndex)"
                >
                  삭제
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <button type="button" class="row-add" @click="addRow(selectedGroup)">행 추가</button>
      </section>

      <button type="button" class="group-remove" @click="removeGroup(selectedIndex)">
        이 그룹 삭제
      </button>
    </div>

    <p v-else class="empty-hint">그룹이 없습니다. '그룹 추가'로 새 그룹을 만드세요.</p>
  </div>
</template>

<style scoped>
.route-groups-editor {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 14px;
  align-items: start;
}
.group-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.group-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  cursor: pointer;
  text-align: left;
}
.group-item.active {
  border-color: var(--li-blue);
  background: var(--li-surface-blue);
}
.group-name { font-size: 12px; color: var(--li-text); font-weight: 600; }
.group-meta { font-size: 11px; color: var(--li-text-faint); }
.group-add {
  padding: 6px 10px;
  border: 1px dashed var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  background: transparent;
  color: var(--li-text-muted);
  font-size: 12px;
  cursor: pointer;
}
.group-add:hover { border-color: var(--li-blue); color: var(--li-blue); }
.group-form { display: flex; flex-direction: column; gap: 12px; }
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px 14px;
}
.form-field { display: flex; flex-direction: column; gap: 4px; }
.form-field > span { font-size: 11px; color: var(--li-text-muted); }
.form-field input[type='text'],
.form-field select {
  padding: 6px 8px;
  border: 1px solid var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  color: var(--li-text);
  background: var(--li-surface-strong);
}
.form-field input[readonly] {
  background: var(--li-bg-app-2);
  color: var(--li-text-faint);
}
.form-checks { justify-content: flex-end; gap: 6px; }
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--li-text-soft);
}
.rows-block { display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.block-title { margin: 0; font-size: 12px; color: var(--li-text-soft); }
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
.group-remove {
  align-self: flex-start;
  border: 1px solid var(--li-risk-critical-border);
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  padding: 6px 12px;
  cursor: pointer;
}
.empty-hint { margin: 0; font-size: 12px; color: var(--li-text-faint); }
</style>
