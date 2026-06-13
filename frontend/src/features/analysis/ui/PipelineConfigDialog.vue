<template>
  <Teleport to="body">
    <div v-if="open" class="dialog-backdrop" @click.self="onCancel">
      <div class="dialog" role="dialog" aria-modal="true" data-e2e="pipeline-config-dialog">
        <header class="dialog-header">
          <h2 class="dialog-title">{{ t('newAnalysis.title') }}</h2>
          <button class="dialog-close" :title="t('newAnalysis.cancel')" @click="onCancel">✕</button>
        </header>

        <div class="dialog-body">
          <!-- Engine selection -->
          <div class="config-section">
            <label class="config-label">{{ t('config.pipeline') }}</label>

            <div class="config-toggle-row">
              <label class="toggle-label">
                <input type="checkbox" v-model="local.force_vlm_pipeline" class="toggle-input" />
                <span class="toggle-switch" />
                <span class="toggle-text">{{ t('config.forceVlmPipeline') }}</span>
              </label>
              <span class="config-hint">
                <span class="config-tooltip">{{ t('config.forceVlmPipelineHint') }}</span
                >?
              </span>
            </div>

            <!-- Deep Extract: standard + VLM-json in parallel, merged. -->
            <div v-if="!local.force_vlm_pipeline" class="config-toggle-row">
              <label class="toggle-label">
                <input
                  type="checkbox"
                  v-model="local.extract_mode"
                  true-value="deep"
                  false-value="standard"
                  class="toggle-input"
                  data-e2e="deep-extract-toggle"
                />
                <span class="toggle-switch" />
                <span class="toggle-text">{{ t('config.deepExtract') }}</span>
              </label>
              <span class="config-hint">
                <span class="config-tooltip">{{ t('config.deepExtractHint') }}</span
                >?
              </span>
            </div>
          </div>

          <!-- Standard pipeline options -->
          <div v-if="!local.force_vlm_pipeline" class="config-section">
            <label class="config-label">{{ t('config.standardOptions') }}</label>

            <div class="config-toggle-row">
              <label class="toggle-label">
                <input type="checkbox" v-model="local.do_ocr" class="toggle-input" />
                <span class="toggle-switch" />
                <span class="toggle-text">{{ t('config.ocr') }}</span>
              </label>
              <span class="config-hint">
                <span class="config-tooltip">{{ t('config.ocrHint') }}</span
                >?
              </span>
            </div>

            <div class="config-sub-option" v-if="local.do_ocr">
              <div class="config-toggle-row">
                <label class="toggle-label">
                  <input type="checkbox" v-model="local.force_full_page_ocr" class="toggle-input" />
                  <span class="toggle-switch" />
                  <span class="toggle-text">{{ t('config.forceFullPageOcr') }}</span>
                </label>
                <span class="config-hint">
                  <span class="config-tooltip">{{ t('config.forceFullPageOcrHint') }}</span
                  >?
                </span>
              </div>
            </div>

            <div class="config-toggle-row">
              <label class="toggle-label">
                <input type="checkbox" v-model="local.do_table_structure" class="toggle-input" />
                <span class="toggle-switch" />
                <span class="toggle-text">{{ t('config.tableStructure') }}</span>
              </label>
              <span class="config-hint">
                <span class="config-tooltip">{{ t('config.tableStructureHint') }}</span
                >?
              </span>
            </div>

            <div class="config-sub-option" v-if="local.do_table_structure">
              <label class="config-label-sm">{{ t('config.tableMode') }}</label>
              <select class="config-select" v-model="local.table_mode">
                <option value="accurate">{{ t('config.tableModeAccurate') }}</option>
                <option value="fast">{{ t('config.tableModeFast') }}</option>
              </select>
            </div>
          </div>

          <!-- VLM pipeline options -->
          <div v-else class="config-section">
            <label class="config-label">{{ t('config.vlmOptions') }}</label>

            <div class="config-sub-option">
              <label class="config-label-sm">{{ t('config.vlmBackend') }}</label>
              <select class="config-select" v-model="local.vlm_backend">
                <option value="">{{ t('config.vlmBackendGranite') }}</option>
                <option value="ollama">{{ t('config.vlmBackendOllama') }}</option>
              </select>
              <span class="config-input-hint">{{ t('config.vlmBackendHint') }}</span>
            </div>

            <div class="config-sub-option" v-if="local.vlm_backend === 'ollama'">
              <label class="config-label-sm">{{ t('config.vlmOutputMode') }}</label>
              <select class="config-select" v-model="local.vlm_output_mode">
                <option value="json">{{ t('config.vlmOutputModeJson') }}</option>
                <option value="markdown">{{ t('config.vlmOutputModeMarkdown') }}</option>
              </select>
              <span class="config-input-hint">{{ t('config.vlmOutputModeHint') }}</span>
            </div>

            <div class="config-sub-option">
              <label class="config-label-sm">{{ t('config.vlmImageScale') }}</label>
              <select class="config-select" v-model.number="local.vlm_image_scale">
                <option :value="2">{{ t('config.vlmScaleFast') }}</option>
                <option :value="3">{{ t('config.vlmScaleBalanced') }}</option>
                <option :value="4">{{ t('config.vlmScaleHigh') }}</option>
                <option :value="5">{{ t('config.vlmScaleMax') }}</option>
              </select>
              <span class="config-input-hint">{{ t('config.vlmImageScaleHint') }}</span>
            </div>
          </div>
        </div>

        <footer class="dialog-footer">
          <button class="btn-secondary" @click="onCancel">{{ t('newAnalysis.cancel') }}</button>
          <button class="btn-primary" @click="onConfirm">{{ t('newAnalysis.run') }}</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { PipelineOptions } from '../../../shared/types'
import { useI18n } from '../../../shared/i18n'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', options: PipelineOptions): void
}>()

const { t } = useI18n()

const DEFAULT_OPTIONS: PipelineOptions = {
  do_ocr: true,
  force_full_page_ocr: false,
  do_table_structure: true,
  table_mode: 'accurate',
  force_vlm_pipeline: false,
  vlm_backend: '',
  vlm_image_scale: 4,
  vlm_output_mode: 'json',
  extract_mode: 'standard',
}

const local = reactive<PipelineOptions>({ ...DEFAULT_OPTIONS })

watch(
  () => props.open,
  (opened) => {
    if (opened) Object.assign(local, DEFAULT_OPTIONS)
  },
)

function onCancel(): void {
  emit('cancel')
}

function onConfirm(): void {
  emit('confirm', { ...local })
}
</script>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 420px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.dialog-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.dialog-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all var(--transition);
}

.dialog-close:hover {
  color: var(--text);
  background: var(--bg-hover);
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-secondary {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}

.btn-secondary:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.btn-primary {
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background: var(--accent);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: filter var(--transition);
}

.btn-primary:hover {
  filter: brightness(1.1);
}

/* Config form styles (mirrors StudioPage config panel) */
.config-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.config-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-switch {
  position: relative;
  width: 36px;
  height: 20px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: all var(--transition);
  flex-shrink: 0;
}

.toggle-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--text-muted);
  border-radius: 50%;
  transition: all var(--transition);
}

.toggle-input:checked + .toggle-switch {
  background: var(--accent);
  border-color: var(--accent);
}

.toggle-input:checked + .toggle-switch::after {
  left: 18px;
  background: white;
}

.toggle-text {
  font-size: 13px;
  color: var(--text);
}

.config-hint {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid var(--border-light);
  font-size: 10px;
  color: var(--text-muted);
  cursor: help;
  flex-shrink: 0;
}

.config-hint:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.config-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 8px);
  right: -8px;
  width: 240px;
  padding: 8px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 100;
  pointer-events: none;
}

/* PDF Preprocessing input styles */
.config-input-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  gap: 12px;
}

.config-input-label {
  font-size: 13px;
  color: var(--text);
}

.config-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.config-number-input {
  width: 70px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  text-align: center;
}

.config-number-input:focus {
  outline: none;
  border-color: var(--accent);
}

.config-input-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.config-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  right: 12px;
  border: 5px solid transparent;
  border-top-color: var(--border-light);
}

.config-hint:hover .config-tooltip {
  display: block;
}

.config-sub-option {
  padding-left: 46px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-label-sm {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
}

.config-select {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='%23A1A1AA' viewBox='0 0 20 20'%3E%3Cpath fill-rule='evenodd' d='M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z' clip-rule='evenodd'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}

.config-select:focus {
  outline: none;
  border-color: var(--accent);
}

.config-select option {
  background: var(--bg-surface);
  color: var(--text);
}
</style>
