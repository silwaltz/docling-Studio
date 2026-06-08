<template>
  <div class="ask-tab" data-e2e="ask-tab">
    <!-- Settings bar -->
    <div class="ask-topbar">
      <div class="ask-topbar-left">
        <span class="ask-topbar-label">{{ t('ask.model') }}</span>
        <input
          v-model="modelId"
          class="ask-model-input"
          :placeholder="t('ask.modelPlaceholder')"
          :disabled="streaming"
          data-e2e="ask-model-input"
        />
      </div>
      <button
        v-if="messages.length > 0"
        class="ask-clear-btn"
        :disabled="streaming"
        :title="t('ask.clear')"
        data-e2e="ask-clear-btn"
        @click="clearChat"
      >
        {{ t('ask.clear') }}
      </button>
    </div>

    <!-- Message list -->
    <div class="ask-messages" ref="messagesEl" data-e2e="ask-messages">
      <!-- Ollama connectivity warning -->
      <div v-if="ollamaWarning" class="ask-error ask-ollama-warning" data-e2e="ask-ollama-warning">
        ⚠ {{ ollamaWarning }}
      </div>
      <!-- Empty state -->
      <div v-if="messages.length === 0" class="ask-empty">
        <div class="ask-empty-icon">💬</div>
        <p class="ask-empty-title">{{ t('ask.emptyTitle') }}</p>
        <p class="ask-empty-sub">{{ t('ask.emptySub') }}</p>
        <div class="ask-suggestions">
          <button
            v-for="s in suggestions"
            :key="s"
            class="ask-suggestion"
            :disabled="streaming"
            @click="sendSuggestion(s)"
          >
            {{ s }}
          </button>
        </div>
      </div>

      <!-- Messages -->
      <template v-else>
        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="ask-message"
          :class="msg.role"
          :data-e2e="`ask-message-${msg.role}`"
        >
          <div class="ask-message-bubble">
            <div class="ask-message-content" v-html="renderMarkdown(msg.content)" />
            <button
              v-if="msg.role === 'assistant' && extractJson(msg.content)"
              class="ask-download-btn"
              :title="t('ask.downloadJson')"
              @click="downloadJson(msg.content)"
            >
              <svg viewBox="0 0 20 20" fill="currentColor" class="ask-download-icon">
                <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd" />
              </svg>
              {{ t('ask.downloadJson') }}
            </button>
          </div>
        </div>

        <!-- Streaming assistant bubble -->
        <div v-if="streaming" class="ask-message assistant" data-e2e="ask-streaming">
          <div class="ask-message-bubble">
            <div
              v-if="streamBuffer"
              class="ask-message-content"
              v-html="renderMarkdown(streamBuffer)"
            />
            <span v-else class="ask-thinking">
              <span class="ask-dot" /><span class="ask-dot" /><span class="ask-dot" />
            </span>
          </div>
        </div>

        <!-- Error -->
        <div v-if="chatError" class="ask-error" data-e2e="ask-error">
          ⚠ {{ chatError }}
        </div>
      </template>
    </div>

    <!-- Input area -->
    <div class="ask-input-area">
      <textarea
        ref="inputEl"
        v-model="draft"
        class="ask-input"
        :placeholder="t('ask.inputPlaceholder')"
        :disabled="streaming"
        rows="1"
        data-e2e="ask-input"
        @keydown.enter.exact.prevent="onSend"
        @input="autoResize"
      />
      <button
        class="ask-send-btn"
        :disabled="!canSend"
        :title="t('ask.send')"
        data-e2e="ask-send-btn"
        @click="onSend"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" class="ask-send-icon">
          <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useI18n } from '../shared/i18n'
import { useChatStore } from '../features/chat/store'

const props = defineProps<{ docId: string }>()

const { t } = useI18n()
const chatStore = useChatStore()

const draft = ref('')
const streaming = ref(false)
const streamBuffer = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const inputEl = ref<HTMLTextAreaElement | null>(null)

const DEFAULT_MODEL = 'gemma4:e4b'
const modelId = ref('')

const ollamaWarning = ref<string | null>(null)

const docChat = computed(() => chatStore.getChat(props.docId))
const messages = computed(() => docChat.value.messages)
const chatError = computed(() => docChat.value.error)

const suggestions = [t('ask.suggestion1')]

onMounted(async () => {
  try {
    const resp = await fetch('/api/documents/ollama-status')
    if (resp.ok) {
      const status = await resp.json()
      if (!status.reachable) {
        ollamaWarning.value =
          `Ollama is not reachable at ${status.host}. ` +
          `Make sure Ollama is running and the model "${status.model}" is pulled ` +
          `(ollama pull ${status.model}).`
      }
    }
  } catch {
    // silently ignore — the chat endpoint will surface the error when needed
  }
})

const canSend = computed(() => draft.value.trim().length > 0 && !streaming.value)

function extractJson(text: string): string | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]+?)```/)
  if (fenced) return fenced[1].trim()
  const bare = text.match(/({[\s\S]+}|\[[\s\S]+\])/)
  if (bare) {
    try { JSON.parse(bare[1]); return bare[1].trim() } catch { /* not valid json */ }
  }
  return null
}

function downloadJson(content: string): void {
  const json = extractJson(content)
  if (!json) return
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.docId}-extracted.json`
  a.click()
  URL.revokeObjectURL(url)
}

function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^#{3} (.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{2} (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(.+)$/, '<p>$1</p>')
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

function autoResize(): void {
  if (!inputEl.value) return
  inputEl.value.style.height = 'auto'
  inputEl.value.style.height = Math.min(inputEl.value.scrollHeight, 160) + 'px'
}

function clearChat(): void {
  if (streaming.value) return
  chatStore.clear(props.docId)
  draft.value = ''
}

function sendSuggestion(text: string): void {
  draft.value = text
  onSend()
}

async function onSend(): Promise<void> {
  const text = draft.value.trim()
  if (!text || streaming.value) return

  draft.value = ''
  chatStore.setError(props.docId, null)
  await nextTick()
  if (inputEl.value) {
    inputEl.value.style.height = 'auto'
  }

  chatStore.pushMessage(props.docId, { role: 'user', content: text })
  await scrollToBottom()

  streaming.value = true
  streamBuffer.value = ''

  const model = modelId.value.trim() || DEFAULT_MODEL

  try {
    const resp = await fetch(`/api/documents/${props.docId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: messages.value.map((m) => ({ role: m.role, content: m.content })),
        model,
      }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }))
      throw new Error(err.detail ?? `HTTP ${resp.status}`)
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })

      const lines = buf.split('\n')
      buf = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const json = line.slice(6).trim()
        if (!json) continue
        try {
          const event = JSON.parse(json)
          if (event.error) {
            chatStore.setError(props.docId, event.error)
            streaming.value = false
            if (streamBuffer.value) {
              chatStore.pushMessage(props.docId, { role: 'assistant', content: streamBuffer.value })
            }
            streamBuffer.value = ''
            await scrollToBottom()
            return
          }
          if (event.delta) {
            streamBuffer.value += event.delta
            await scrollToBottom()
          }
          if (event.done) {
            chatStore.pushMessage(props.docId, { role: 'assistant', content: streamBuffer.value })
            streamBuffer.value = ''
            streaming.value = false
            await scrollToBottom()
          }
        } catch {
          // skip malformed lines
        }
      }
    }

    if (streamBuffer.value) {
      chatStore.pushMessage(props.docId, { role: 'assistant', content: streamBuffer.value })
      streamBuffer.value = ''
    }
  } catch (e) {
    chatStore.setError(props.docId, (e as Error).message)
  } finally {
    streaming.value = false
    await scrollToBottom()
  }
}
</script>

<style scoped>
.ask-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg);
}

/* Top bar */
.ask-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 12px;
  background: var(--bg-surface);
}

.ask-topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.ask-topbar-label {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.ask-model-input {
  font-size: 12px;
  padding: 4px 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  width: 180px;
}

.ask-model-input::placeholder {
  color: var(--text-muted);
}

.ask-model-input:focus {
  outline: none;
  border-color: var(--accent);
}

.ask-model-input:disabled {
  opacity: 0.5;
}

.ask-clear-btn {
  font-size: 12px;
  padding: 4px 10px;
  color: var(--text-muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition);
}

.ask-clear-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--border-light);
}

.ask-clear-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Messages area */
.ask-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Empty state */
.ask-empty {
  margin: auto;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  max-width: 420px;
}

.ask-empty-icon {
  font-size: 36px;
  line-height: 1;
}

.ask-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.ask-empty-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.5;
}

.ask-suggestions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  margin-top: 8px;
}

.ask-suggestion {
  padding: 8px 14px;
  font-size: 12px;
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition);
}

.ask-suggestion:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text);
  border-color: var(--accent);
}

/* Message bubbles */
.ask-message {
  display: flex;
}

.ask-message.user {
  justify-content: flex-end;
}

.ask-message.assistant {
  justify-content: flex-start;
}

.ask-message-bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.ask-message.user .ask-message-bubble {
  background: var(--accent);
  color: white;
  border-bottom-right-radius: 3px;
}

.ask-message.assistant .ask-message-bubble {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  border-bottom-left-radius: 3px;
}

.ask-message-content :deep(p) {
  margin: 0 0 6px;
}

.ask-message-content :deep(p:last-child) {
  margin-bottom: 0;
}

.ask-message-content :deep(h1),
.ask-message-content :deep(h2),
.ask-message-content :deep(h3) {
  margin: 8px 0 4px;
  font-weight: 600;
}

.ask-message-content :deep(h1) { font-size: 15px; }
.ask-message-content :deep(h2) { font-size: 14px; }
.ask-message-content :deep(h3) { font-size: 13px; }

.ask-message-content :deep(ul) {
  margin: 4px 0;
  padding-left: 18px;
}

.ask-message-content :deep(code) {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  background: rgba(0, 0, 0, 0.15);
  padding: 1px 4px;
  border-radius: 3px;
}

.ask-message.user .ask-message-content :deep(code) {
  background: rgba(255, 255, 255, 0.2);
}

.ask-message.user .ask-message-content :deep(strong) {
  color: white;
}

/* Thinking dots */
.ask-thinking {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
}

.ask-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: ask-pulse 1.2s ease-in-out infinite;
}

.ask-dot:nth-child(2) { animation-delay: 0.2s; }
.ask-dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes ask-pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* Error */
.ask-error {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--error);
  font-size: 12px;
  line-height: 1.5;
}

.ask-ollama-warning {
  flex-shrink: 0;
}

/* Input */
.ask-input-area {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg-surface);
}

.ask-input {
  flex: 1;
  resize: none;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text);
  font-family: inherit;
  line-height: 1.5;
  min-height: 38px;
  max-height: 160px;
  overflow-y: auto;
  transition: border-color var(--transition);
}

.ask-input::placeholder {
  color: var(--text-muted);
}

.ask-input:focus {
  outline: none;
  border-color: var(--accent);
}

.ask-input:disabled {
  opacity: 0.5;
}

.ask-send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: filter var(--transition);
}

.ask-send-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.ask-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ask-send-icon {
  width: 16px;
  height: 16px;
  color: white;
}

/* Download JSON button */
.ask-download-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  padding: 4px 10px;
  font-size: 11px;
  font-family: inherit;
  background: var(--bg-surface);
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  color: var(--accent);
  cursor: pointer;
  transition: all var(--transition);
}

.ask-download-btn:hover {
  background: var(--accent);
  color: white;
}

.ask-download-icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
}
</style>
