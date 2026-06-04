import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface DocChat {
  messages: ChatMessage[]
  error: string | null
}

export const useChatStore = defineStore('chat', () => {
  const chats = ref<Record<string, DocChat>>({})

  function getChat(docId: string): DocChat {
    if (!chats.value[docId]) {
      chats.value[docId] = { messages: [], error: null }
    }
    return chats.value[docId]
  }

  function pushMessage(docId: string, msg: ChatMessage): void {
    getChat(docId).messages.push(msg)
  }

  function setError(docId: string, error: string | null): void {
    getChat(docId).error = error
  }

  function clear(docId: string): void {
    chats.value[docId] = { messages: [], error: null }
  }

  return { chats, getChat, pushMessage, setError, clear }
})
