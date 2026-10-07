import axios from 'axios'
import { useSyncExternalStore } from 'react'

// URLs that count as "AI is thinking" (LLM-bound).
// /api/github/push and /api/health are excluded.
const AI_URL_RE = /\/api\/(analyze|waf-review|pricing|terraform)/

let count = 0
const listeners = new Set()
const emit = () => listeners.forEach((l) => l())
const subscribe = (cb) => {
  listeners.add(cb)
  return () => listeners.delete(cb)
}
const getSnapshot = () => count > 0

export const useThinking = () =>
  useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

export const isThinking = () => count > 0

let installed = false
export function installThinkingInterceptors() {
  if (installed) return
  installed = true
  axios.interceptors.request.use((config) => {
    if (AI_URL_RE.test(config.url || '')) {
      config.__archlensThinking = true
      count += 1
      emit()
    }
    return config
  })
  const dec = () => {
    count = Math.max(0, count - 1)
    emit()
  }
  axios.interceptors.response.use(
    (res) => {
      if (res.config?.__archlensThinking) dec()
      return res
    },
    (err) => {
      if (err.config?.__archlensThinking) dec()
      return Promise.reject(err)
    },
  )
}
