<template>
  <div class="review-queue-view">
    <main class="queue-shell">
      <header class="queue-header">
        <div>
          <h1>{{ currentDocument.label }}审核</h1>
          <p>处理自动核验结果和人工复核任务</p>
        </div>
        <button class="create-button" type="button" :disabled="creating" @click="onCreate">
          {{ creating ? '正在发起' : createButtonText }}
        </button>
      </header>

      <nav class="document-switcher" aria-label="材料类型">
        <button
          v-for="item in documentOptions"
          :key="item.value"
          type="button"
          :class="{ active: activeDocumentType === item.value }"
          @click="onSwitchDocument(item.value)"
        >
          {{ item.shortLabel }}
        </button>
      </nav>

      <section class="status-summary" aria-label="审核状态筛选">
        <button
          v-for="item in statusItems"
          :key="item.value"
          type="button"
          :class="['status-item', item.className, { active: filterStatus === item.value }]"
          @click="onSetFilter(item.value)"
        >
          <strong>{{ item.count }}</strong>
          <span>{{ item.label }}</span>
        </button>
      </section>

      <section class="queue-panel" aria-labelledby="queue-title">
        <div class="queue-toolbar">
          <div>
            <h2 id="queue-title">审核任务</h2>
            <p>{{ filteredTotal }} 条记录<span v-if="filterStatus">，当前仅显示{{ activeStatusLabel }}</span></p>
          </div>
          <form class="queue-search" role="search" @submit.prevent="onSearch">
            <input
              :value="keyword"
              type="search"
              :placeholder="`搜索${currentDocument.subjectLabel}`"
              @input="emit('update:keyword', $event.target.value)"
            />
            <button type="submit">搜索</button>
          </form>
        </div>

        <div v-if="loading" class="queue-skeleton" aria-label="正在加载">
          <div v-for="item in 5" :key="item" />
        </div>

        <template v-else-if="records.length">
          <div class="queue-table" role="table" aria-label="审核任务列表">
            <div class="table-header" role="row">
              <span>审核对象</span>
              <span>材料信息</span>
              <span>核验情况</span>
              <span>状态</span>
              <span>更新时间</span>
              <span>操作</span>
            </div>
            <article
              v-for="record in records"
              :key="record.id"
              class="queue-row"
              role="row"
              tabindex="0"
              @click="onOpen(record.id)"
              @keydown.enter="onOpen(record.id)"
            >
              <div class="subject-cell">
                <strong>{{ recordTitle(record) }}</strong>
                <small>{{ recordPrimaryMeta(record) }}</small>
              </div>
              <div class="material-cell">
                <span>{{ recordSecondaryMeta(record) }}</span>
                <small>{{ recordFooterText(record) }}</small>
              </div>
              <div class="match-cell">
                <strong>{{ formatRatio(record.match_ratio) }}</strong>
                <small>字段匹配率</small>
              </div>
              <div class="state-cell">
                <span :class="['state-label', `state-${record.review_status || 'default'}`]">
                  {{ statusText(record.review_status) }}
                </span>
              </div>
              <time>{{ formatDate(record.updated_at || record.created_at) }}</time>
              <button type="button" class="open-button" @click.stop="onOpen(record.id)">查看</button>
            </article>
          </div>

          <div v-if="!listFinished" class="load-more">
            <button type="button" :disabled="listLoading" @click="onLoadMore">
              {{ listLoading ? '加载中' : '加载更多' }}
            </button>
          </div>
          <p v-else class="list-end">已显示全部记录</p>
        </template>

        <div v-else class="queue-empty">
          <strong>暂无审核任务</strong>
          <p>当前筛选条件下没有记录</p>
          <button v-if="filterStatus || keyword" type="button" @click="clearFilters">清除筛选</button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentDocument: { type: Object, required: true },
  documentOptions: { type: Array, required: true },
  activeDocumentType: { type: String, required: true },
  stats: { type: Object, required: true },
  filterStatus: { type: String, required: true },
  keyword: { type: String, required: true },
  filteredTotal: { type: Number, required: true },
  records: { type: Array, required: true },
  loading: { type: Boolean, required: true },
  creating: { type: Boolean, required: true },
  listLoading: { type: Boolean, required: true },
  listFinished: { type: Boolean, required: true },
  createButtonText: { type: String, required: true },
  onSwitchDocument: { type: Function, required: true },
  onSetFilter: { type: Function, required: true },
  onSearch: { type: Function, required: true },
  onCreate: { type: Function, required: true },
  onOpen: { type: Function, required: true },
  onLoadMore: { type: Function, required: true },
  recordTitle: { type: Function, required: true },
  recordPrimaryMeta: { type: Function, required: true },
  recordSecondaryMeta: { type: Function, required: true },
  recordFooterText: { type: Function, required: true },
  formatRatio: { type: Function, required: true },
  statusText: { type: Function, required: true },
})

const emit = defineEmits(['update:keyword'])

const statusItems = computed(() => [
  { value: '', label: '全部任务', count: props.stats.total || 0, className: 'status-all' },
  { value: 'pending', label: '待审核', count: props.stats.pending || 0, className: 'status-pending' },
  { value: 'flagged', label: '异常', count: props.stats.flagged || 0, className: 'status-flagged' },
  { value: 'confirmed', label: '已认可', count: props.stats.confirmed || 0, className: 'status-confirmed' },
])

const activeStatusLabel = computed(() => statusItems.value.find((item) => item.value === props.filterStatus)?.label || '全部任务')

function clearFilters() {
  emit('update:keyword', '')
  props.onSetFilter('')
  props.onSearch()
}

function formatDate(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.review-queue-view {
  min-height: 100%;
  padding-bottom: 28px;
  color: #1f2933;
  background: #eef1f4;
  --queue-accent: #1769aa;
  --queue-border: #d9dee5;
  --queue-muted: #66717d;
}

.queue-shell {
  width: min(100% - 32px, 1240px);
  margin: 0 auto;
}

.queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 78px;
}

.queue-header h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  line-height: 1.4;
}

.queue-header p,
.queue-toolbar p {
  margin: 3px 0 0;
  color: var(--queue-muted);
  font-size: 12px;
}

.create-button,
.queue-search button {
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--queue-accent);
  border-radius: 4px;
  color: #fff;
  background: var(--queue-accent);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.create-button:disabled,
.load-more button:disabled { opacity: 0.55; cursor: wait; }

.create-button:focus-visible,
.document-switcher button:focus-visible,
.status-item:focus-visible,
.queue-search input:focus-visible,
.queue-search button:focus-visible,
.queue-row:focus-visible,
.open-button:focus-visible,
.load-more button:focus-visible,
.queue-empty button:focus-visible {
  outline: 2px solid #0b518a;
  outline-offset: 2px;
}

.document-switcher {
  display: flex;
  overflow-x: auto;
  background: #fff;
  border: 1px solid var(--queue-border);
  border-bottom: 0;
}

.document-switcher button {
  flex: 0 0 auto;
  min-width: 118px;
  height: 45px;
  padding: 0 16px;
  border: 0;
  border-right: 1px solid #edf0f2;
  border-bottom: 3px solid transparent;
  color: #53606c;
  background: #fff;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.document-switcher button:hover { background: #f7f9fb; }
.document-switcher button.active { color: var(--queue-accent); border-bottom-color: var(--queue-accent); font-weight: 600; }

.status-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  background: #fff;
  border: 1px solid var(--queue-border);
}

.status-item {
  display: grid;
  gap: 2px;
  min-height: 72px;
  padding: 12px 18px;
  border: 0;
  border-right: 1px solid #edf0f2;
  border-bottom: 3px solid transparent;
  color: inherit;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.status-item:last-child { border-right: 0; }
.status-item:hover { background: #f7f9fb; }
.status-item strong { font-size: 23px; font-weight: 650; font-variant-numeric: tabular-nums; }
.status-item span { color: var(--queue-muted); font-size: 12px; }
.status-item.active { background: #f5f9fc; border-bottom-color: var(--queue-accent); }
.status-pending strong, .status-flagged strong { color: #b4232f; }
.status-confirmed strong { color: #24734b; }

.queue-panel {
  margin-top: 14px;
  background: #fff;
  border: 1px solid var(--queue-border);
}

.queue-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 66px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--queue-border);
}

.queue-toolbar h2 { margin: 0; font-size: 15px; font-weight: 650; }
.queue-search { display: flex; width: min(100%, 340px); }
.queue-search input {
  min-width: 0;
  flex: 1;
  height: 36px;
  padding: 0 11px;
  border: 1px solid #bfc7d0;
  border-right: 0;
  border-radius: 4px 0 0 4px;
  color: inherit;
  background: #fff;
  font: inherit;
  font-size: 13px;
}
.queue-search button { border-radius: 0 4px 4px 0; }

.table-header,
.queue-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.5fr) minmax(190px, 1.15fr) 110px 100px 130px 58px;
  gap: 18px;
  align-items: center;
}

.table-header {
  min-height: 38px;
  padding: 0 16px;
  color: #707b86;
  background: #f7f8fa;
  border-bottom: 1px solid var(--queue-border);
  font-size: 11px;
}

.queue-row {
  min-height: 74px;
  padding: 12px 16px;
  border-bottom: 1px solid #edf0f2;
  cursor: pointer;
  transition: background-color 140ms ease;
}

.queue-row:hover { background: #f8fafb; }
.queue-row:last-child { border-bottom: 0; }
.subject-cell, .material-cell, .match-cell { display: grid; gap: 4px; min-width: 0; }
.subject-cell strong { overflow: hidden; font-size: 14px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.subject-cell small, .material-cell small, .match-cell small { color: #7a8590; font-size: 11px; }
.material-cell span { overflow: hidden; color: #394550; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.match-cell strong { font-size: 15px; font-variant-numeric: tabular-nums; }
.state-label { display: inline-block; width: fit-content; padding: 3px 7px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.state-pending { color: #9f1f2d; background: #fdecef; }
.state-flagged { color: #a33b13; background: #fff0e7; }
.state-confirmed { color: #17643c; background: #e9f6ee; }
.state-default { color: #59636d; background: #edf0f2; }
.queue-row time { color: #68737e; font-size: 11px; font-variant-numeric: tabular-nums; }
.open-button { padding: 6px 0; border: 0; color: var(--queue-accent); background: transparent; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }

.queue-skeleton { padding: 0 16px; }
.queue-skeleton div { height: 73px; border-bottom: 1px solid #edf0f2; background: #f2f4f6; animation: skeleton 1.2s ease-in-out infinite alternate; }
@keyframes skeleton { from { opacity: 0.55; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .queue-skeleton div { animation: none; background: #f6f7f8; } }

.load-more, .queue-empty { display: flex; justify-content: center; padding: 20px; }
.load-more button, .queue-empty button { padding: 8px 16px; border: 1px solid #b7c0c8; border-radius: 4px; color: #394550; background: #fff; font: inherit; font-size: 12px; cursor: pointer; }
.list-end { margin: 0; padding: 18px; color: #8a949d; font-size: 11px; text-align: center; }
.queue-empty { min-height: 180px; align-items: center; flex-direction: column; color: #606b75; }
.queue-empty strong { font-size: 14px; }.queue-empty p { margin: 6px 0 16px; font-size: 12px; }

@media (max-width: 820px) {
  .queue-shell { width: 100%; }
  .queue-header { min-height: 70px; padding: 0 14px; }
  .queue-header h1 { font-size: 18px; }
  .queue-header p { display: none; }
  .create-button { height: 34px; padding: 0 12px; font-size: 12px; }
  .document-switcher { border-right: 0; border-left: 0; }
  .document-switcher button { min-width: auto; padding: 0 14px; }
  .status-summary { border-right: 0; border-left: 0; }
  .status-item { min-height: 64px; padding: 10px 12px; }
  .status-item strong { font-size: 20px; }
  .queue-panel { margin-top: 10px; border-right: 0; border-left: 0; }
  .queue-toolbar { align-items: stretch; flex-direction: column; gap: 10px; }
  .queue-search { width: 100%; }
  .table-header { display: none; }
  .queue-row { grid-template-columns: minmax(0, 1fr) auto; gap: 8px 14px; min-height: 108px; padding: 14px; }
  .subject-cell { grid-column: 1; }.state-cell { grid-column: 2; grid-row: 1; align-self: start; }
  .material-cell { grid-column: 1 / 3; }.match-cell { grid-column: 1; display: flex; align-items: baseline; gap: 6px; }
  .queue-row time { display: none; }.open-button { grid-column: 2; grid-row: 3; }
}

@media (max-width: 480px) {
  .status-summary { grid-template-columns: repeat(4, minmax(72px, 1fr)); overflow-x: auto; }
  .status-item { min-width: 72px; padding: 9px 10px; }
  .status-item span { white-space: nowrap; }
}
</style>
