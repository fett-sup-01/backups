import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

// GET simples com reload e (opcional) polling.
export function useFetch(path, { pollMs = 0 } = {}) {
  const [data, setData] = useState(null)
  const [erro, setErro] = useState(null)
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let alive = true
    api('GET', path)
      .then((d) => alive && (setData(d), setErro(null)))
      .catch((e) => alive && setErro(e.message))
    return () => { alive = false }
  }, [path, tick])

  useEffect(() => {
    if (!pollMs) return
    const id = setInterval(() => setTick((t) => t + 1), pollMs)
    return () => clearInterval(id)
  }, [pollMs])

  return { data, erro, reload }
}
