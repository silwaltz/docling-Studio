<template>
  <div class="parse-tab" data-e2e="parse-tab">
    <LayersBar
      :elements="currentPageElements"
      :hidden-types="hiddenTypes"
      @update:hidden-types="(next) => (hiddenTypes = next)"
    >
      <template #action>
        <button
          type="button"
          class="tab-action-cta"
          :disabled="analysisStore.running"
          :title="t('newAnalysis.title')"
          data-e2e="parse-new-analysis"
          @click="onLaunchAnalysis"
        >
          <span v-if="analysisStore.running" class="tab-action-spinner" />
          <span v-else>+</span>
          {{ analysisStore.running ? t('newAnalysis.running') : t('newAnalysis.title') }}
        </button>
      </template>
    </LayersBar>

    <PipelineConfigDialog
      :open="configDialogOpen"
      @cancel="onDialogCancel"
      @confirm="onDialogConfirm"
    />

    <!-- View tabs -->
    <div class="parse-view-tabs">
      <button
        class="parse-view-tab"
        :class="{ active: activeView === 'visual' }"
        @click="activeView = 'visual'"
      >
        {{ t('parse.viewVisual') }}
      </button>
      <button
        class="parse-view-tab"
        :class="{ active: activeView === 'markdown' }"
        @click="activeView = 'markdown'"
      >
        {{ t('parse.viewMarkdown') }}
      </button>
      <button
        class="parse-view-tab"
        :class="{ active: activeView === 'json' }"
        @click="activeView = 'json'"
      >
        {{ t('parse.viewJson') }}
      </button>
    </div>

    <!-- Visual view -->
    <div v-if="activeView === 'visual'" class="parse-body">
      <aside class="parse-structure">
        <header class="parse-structure-header">
          <h2 class="parse-structure-title">{{ t('parse.structureTitle') }}</h2>
          <span class="parse-structure-count">
            {{ t('parse.structureNodes', { n: nodeCount }) }}
          </span>
          <div class="parse-structure-actions">
            <button
              type="button"
              class="tree-action-btn"
              :title="t('parse.expandAll')"
              :aria-label="t('parse.expandAll')"
              data-e2e="tree-expand-all"
              @click="onExpandAll"
            >
              ⊕
            </button>
            <button
              type="button"
              class="tree-action-btn"
              :title="t('parse.collapseAll')"
              :aria-label="t('parse.collapseAll')"
              data-e2e="tree-collapse-all"
              @click="onCollapseAll"
            >
              ⊖
            </button>
          </div>
        </header>
        <input
          v-model="filter"
          type="text"
          class="parse-structure-filter"
          :placeholder="t('parse.filterPlaceholder')"
          data-e2e="structure-filter"
        />
        <DocTreeRail
          :key="treeRemountKey"
          :nodes="filteredNodes"
          :loading="treeLoading"
          :error="treeError"
          :selected="selectedNodeRef"
          :highlight="selectedNodeRef"
          :default-open="treeDefaultOpen"
          @select="onTreeSelect"
          @reload="loadTree"
        />
      </aside>
      <div class="parse-stage">
        <PagePreviewWithOverlay
          v-if="documentStore.workspacePages.length"
          :key="previewKey"
          :document-id="docId"
          :pages="documentStore.workspacePages"
          :current-page="currentPage"
          :hidden-types="hiddenTypes"
          :show-labels="true"
          :highlighted-refs="highlightedRefs"
          @update:current-page="(p) => (currentPage = p)"
          @hover-element="onHoverElement"
          @click-element="onClickElement"
        />
        <div v-else-if="documentStore.workspaceLoading" class="parse-state">
          <span class="spinner" />
        </div>
        <div v-else class="parse-state parse-state--empty">
          <p>{{ t('parse.noAnalysis') }}</p>
        </div>
      </div>
      <ElementProperties
        :element="selectedElement"
        :page-width="currentPageWidth"
        :page-height="currentPageHeight"
        :page-number="currentPage"
        :linked-chunk="linkedChunk"
        :saving="chunksStore.saving"
        @save-chunk="onSaveChunk"
      />
    </div>

    <!-- Markdown view -->
    <div v-else-if="activeView === 'markdown'" class="parse-markdown-view">
      <div v-if="documentStore.workspaceActiveAnalysis?.contentMarkdown || analysisStore.currentAnalysis?.contentMarkdown" class="parse-markdown-content">
        <MarkdownViewer :content="documentStore.workspaceActiveAnalysis?.contentMarkdown || analysisStore.currentAnalysis?.contentMarkdown || ''" />
      </div>
      <div v-else-if="documentStore.workspaceLoading || analysisStore.running" class="parse-state">
        <span class="spinner" />
      </div>
      <div v-else class="parse-state parse-state--empty">
        <p>{{ t('parse.noAnalysis') }}</p>
      </div>
    </div>

    <!-- JSON view (VLM extraction result) -->
    <div v-else-if="activeView === 'json'" class="parse-json-view" data-e2e="json-view">
      <div v-if="!jsonData" class="parse-state parse-state--empty">
        <p>No JSON data available. Use VLM pipeline to extract structured data.</p>
      </div>
      <template v-else>
        <div class="json-actions">
          <button
            class="copy-btn"
            :title="t('results.copy')"
            @click="copyJson"
            data-e2e="json-copy"
          >
            <svg v-if="!copiedJson" viewBox="0 0 20 20" fill="currentColor" class="copy-icon">
              <path d="M8 2a1 1 0 000 2h2a1 1 0 100-2H8z" />
              <path
                d="M3 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v6h-4.586l1.293-1.293a1 1 0 00-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L10.414 13H15v3a2 2 0 01-2 2H5a2 2 0 01-2-2V5zM15 11h2a1 1 0 110 2h-2v-2z"
              />
            </svg>
            <svg v-else viewBox="0 0 20 20" fill="currentColor" class="copy-icon copied">
              <path
                fill-rule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
          <button
            class="copy-btn"
            :title="t('analysis.downloadJson')"
            @click="downloadJson"
            data-e2e="json-download"
            aria-label="Download JSON"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" class="copy-icon" aria-hidden="true">
              <path
                fill-rule="evenodd"
                d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                clip-rule="evenodd"
              />
            </svg>
          </button>
        </div>
        <pre class="raw-content json-content" data-e2e="json-content">{{ formattedJson }}</pre>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Parse view (#264). Shows the Docling extraction graph for a document:
 *
 *   - LAYERS bar (chip filters per element type + Show labels toggle)
 *   - Structure tree (left rail — element hierarchy per page)
 *   - Page preview with bbox overlay (center)
 *
 * Two-way link between tree and overlay:
 *   - Selecting a node in the tree → highlight its bbox on the preview
 *   - Clicking a bbox → select the matching node in the tree
 */
import { computed, onMounted, ref, watch } from 'vue'
import type { DocChunk, DocTreeNode, PageElement } from '../shared/types'
import { useAnalysisStore } from '../features/analysis/store'
import { useChunksStore } from '../features/chunks/store'
import { fetchDocumentTree } from '../features/document/api'
import { useDocumentStore } from '../features/document/store'
import { chunkForElement } from '../features/document/linkedView'
import DocTreeRail from '../features/document/ui/DocTreeRail.vue'
import ElementProperties from '../features/document/ui/ElementProperties.vue'
import LayersBar from '../features/document/ui/LayersBar.vue'
import PagePreviewWithOverlay from '../features/document/ui/PagePreviewWithOverlay.vue'
import PipelineConfigDialog from '../features/analysis/ui/PipelineConfigDialog.vue'
import MarkdownViewer from '../features/analysis/ui/MarkdownViewer.vue'
import type { PipelineOptions } from '../shared/types'
import { useI18n } from '../shared/i18n'

const props = defineProps<{ docId: string }>()

const { t } = useI18n()
const documentStore = useDocumentStore()
const chunksStore = useChunksStore()
const analysisStore = useAnalysisStore()

const configDialogOpen = ref(false)
const activeView = ref<'visual' | 'markdown' | 'json'>('visual')

// --- JSON view (VLM extraction result) ---
const jsonData = computed(() => {
  return analysisStore.currentAnalysis?.contentJson || null
})

const formattedJson = computed(() => {
  if (!jsonData.value) return ''
  try {
    const parsed = JSON.parse(jsonData.value)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return jsonData.value
  }
})

const copiedJson = ref(false)

async function copyJson(): Promise<void> {
  try {
    await navigator.clipboard.writeText(formattedJson.value)
    copiedJson.value = true
    setTimeout(() => {
      copiedJson.value = false
    }, 1500)
  } catch {
    /* clipboard not available */
  }
}

/** Replace `\_` (gemma4's escape for spaces inside JSON string values) with a
 *  plain space so the downloaded file matches what a human would type. */
function cleanJsonForDownload(json: string): string {
  return json.replace(/\\_/g, ' ')
}

function downloadJson(): void {
  if (!jsonData.value) return
  const cleaned = cleanJsonForDownload(jsonData.value)
  let pretty = formattedJson.value
  try {
    pretty = JSON.stringify(JSON.parse(cleaned), null, 2)
  } catch {
    /* fall back to the raw formatted string if re-parse fails */
  }
  const blob = new Blob([pretty], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.docId}-extracted.json`
  a.click()
  URL.revokeObjectURL(url)
}

function onLaunchAnalysis(): void {
  if (analysisStore.running) return
  configDialogOpen.value = true
}

function onDialogCancel(): void {
  configDialogOpen.value = false
}

async function onDialogConfirm(options: PipelineOptions): Promise<void> {
  configDialogOpen.value = false
  await analysisStore.run(props.docId, options)
}

// Watch for analysis completion and refresh document store to get markdown content
watch(
  () => analysisStore.currentAnalysis?.status,
  async (newStatus, oldStatus) => {
    if (oldStatus === 'RUNNING' && (newStatus === 'COMPLETED' || newStatus === 'FAILED')) {
      // Refresh workspace to get the new analysis data including markdown
      await documentStore.reloadWorkspaceVersions(props.docId)
    }
  },
)

const currentPage = ref(1)
const hiddenTypes = ref<Set<string>>(new Set())

// Expand/Collapse all — bumping `treeRemountKey` re-keys the rail so every
// DocTreeNode mounts fresh and picks up the new `treeDefaultOpen` value.
const treeRemountKey = ref(0)
const treeDefaultOpen = ref<boolean | null>(null)
function onExpandAll(): void {
  treeDefaultOpen.value = true
  treeRemountKey.value++
}
function onCollapseAll(): void {
  treeDefaultOpen.value = false
  treeRemountKey.value++
}

// Re-mount the PagePreviewWithOverlay whenever the active analysis changes
// (e.g. user picks a different version from the History drawer). Without
// this, the preview keeps stale internal state (current page, hovered
// element, bbox overlay) from the previous version. Same idea as
// `treeRemountKey` above — the watch() in onMounted() handles data reload
// for the tree, but the preview needs a hard re-mount to drop its DOM state.
const previewKey = computed(
  () => `preview-${documentStore.workspaceActiveAnalysis?.id ?? 'none'}-${treeRemountKey.value}`,
)

const tree = ref<DocTreeNode[]>([])
const treeLoading = ref(false)
const treeError = ref<string | null>(null)
const filter = ref('')
const selectedNodeRef = ref<string | null>(null)

const currentPageData = computed(() => {
  return documentStore.workspacePages.find((p) => p.page_number === currentPage.value) ?? null
})

const currentPageElements = computed<PageElement[]>(() => currentPageData.value?.elements ?? [])
const currentPageWidth = computed(() => currentPageData.value?.width ?? 0)
const currentPageHeight = computed(() => currentPageData.value?.height ?? 0)

const selectedElement = computed<PageElement | null>(() => {
  if (!selectedNodeRef.value) return null
  // Search every page — selectedNodeRef may point to an element on a
  // different page than the one currently rendered (the click also
  // triggers a page change, but until that lands the panel still wants
  // to show the element's data).
  for (const page of documentStore.workspacePages) {
    const el = page.elements.find((e) => e.self_ref === selectedNodeRef.value)
    if (el) return el
  }
  return null
})

const linkedChunk = computed<DocChunk | null>(() => {
  if (!selectedElement.value) return null
  return chunkForElement(selectedElement.value, currentPage.value, chunksStore.chunks)
})

const nodeCount = computed(() => countNodes(tree.value))

const filteredNodes = computed<DocTreeNode[]>(() => {
  const needle = filter.value.trim().toLowerCase()
  if (!needle) return tree.value
  return filterTree(tree.value, needle)
})

const highlightedRefs = computed<ReadonlySet<string>>(() => {
  if (!selectedNodeRef.value) return new Set()
  return new Set([selectedNodeRef.value])
})

async function loadTree(): Promise<void> {
  treeLoading.value = true
  treeError.value = null
  try {
    tree.value = await fetchDocumentTree(props.docId)
  } catch (e) {
    treeError.value = (e as Error).message || 'Failed to load tree'
  } finally {
    treeLoading.value = false
  }
}

function onTreeSelect(ref: string): void {
  selectedNodeRef.value = ref
  const pageOfRef = findPageOfRef(documentStore.workspacePages, ref)
  if (pageOfRef !== null && pageOfRef !== currentPage.value) {
    currentPage.value = pageOfRef
  }
}

function onHoverElement(_el: PageElement | null): void {
  // Hover is informational only — selection drives the tree highlight.
}

function onClickElement(el: PageElement): void {
  if (el.self_ref) selectedNodeRef.value = el.self_ref
}

async function onSaveChunk(chunkId: string, text: string): Promise<void> {
  await chunksStore.updateText(props.docId, chunkId, text)
}

onMounted(async () => {
  await Promise.all([
    documentStore.loadWorkspace(props.docId),
    chunksStore.load(props.docId),
    loadTree(),
  ])
  await documentStore.reloadWorkspaceVersions(props.docId)
  const first = documentStore.workspacePages[0]?.page_number
  if (first) currentPage.value = first
})

watch(
  () => props.docId,
  async (id) => {
    selectedNodeRef.value = null
    filter.value = ''
    await Promise.all([documentStore.loadWorkspace(id), chunksStore.load(id), loadTree()])
    const first = documentStore.workspacePages[0]?.page_number
    if (first) currentPage.value = first
  },
)

// Refetch the tree when the active analysis changes (#266 / #267).
// Triggered after an in-place analysis completes or after the user
// restores a different version from the History drawer — the tree
// is built server-side from the active analysis's `document_json`,
// so it has to be reloaded.
watch(
  () => documentStore.workspaceActiveAnalysis?.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      selectedNodeRef.value = null
      loadTree()
    }
  },
)

// --- pure helpers ----------------------------------------------------------

function countNodes(nodes: readonly DocTreeNode[]): number {
  let n = 0
  for (const node of nodes) {
    n += 1 + countNodes(node.children)
  }
  return n
}

function filterTree(nodes: readonly DocTreeNode[], needle: string): DocTreeNode[] {
  const out: DocTreeNode[] = []
  for (const node of nodes) {
    const childMatches = filterTree(node.children, needle)
    const selfMatch =
      node.label.toLowerCase().includes(needle) || node.type.toLowerCase().includes(needle)
    if (selfMatch || childMatches.length > 0) {
      out.push({ ...node, children: childMatches })
    }
  }
  return out
}

function findPageOfRef(
  pages: readonly { page_number: number; elements: readonly { self_ref?: string }[] }[],
  ref: string,
): number | null {
  for (const page of pages) {
    if (page.elements.some((e) => e.self_ref === ref)) return page.page_number
  }
  return null
}
</script>

<style scoped>
.parse-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.parse-view-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  flex-shrink: 0;
  padding: 0 16px;
}

.parse-view-tab {
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition);
  margin-bottom: -1px;
}

.parse-view-tab:hover {
  color: var(--text-secondary);
}

.parse-view-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.parse-markdown-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
}

.parse-markdown-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
}

.parse-json-view {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
}

.parse-json-view .json-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.parse-json-view .json-content {
  flex: 1;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg-elevated);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  overflow: auto;
}

.parse-body {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 360px;
  flex: 1;
  min-height: 0;
}

.parse-structure {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--bg-surface);
  min-height: 0;
  overflow: hidden;
}

.parse-structure-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.parse-structure-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  color: var(--text);
}

.parse-structure-count {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'IBM Plex Mono', monospace;
}

.parse-structure-actions {
  margin-left: auto;
  display: inline-flex;
  gap: 4px;
}

.tree-action-btn {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  line-height: 1;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}

.tree-action-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.parse-structure-filter {
  margin: 8px 14px;
  padding: 6px 10px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font-size: 12px;
}

.parse-stage {
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  overflow: hidden;
  min-height: 0;
}

.parse-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}

.parse-state--empty {
  flex-direction: column;
  gap: 12px;
}

.tab-action-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: var(--accent);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  color: white;
  font-size: 12px;
  cursor: pointer;
  transition: filter var(--transition);
}

.tab-action-cta:hover:not(:disabled) {
  filter: brightness(1.1);
}

.tab-action-cta:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.tab-action-spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(255, 255, 255, 0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border-light);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
