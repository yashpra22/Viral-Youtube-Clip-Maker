import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, formatDuration, type StatusResponse, type VideoItem } from '../api'

const initialStatus: StatusResponse = {
  statuses: {}, active: false, phase: 'idle', message: 'Ready to find trading videos.',
  total: 0, completed: 0, eta_seconds: null, error: null,
}

function formatEta(seconds: number | null): string {
  if (seconds === null) return 'Calculating…'
  if (seconds <= 0) return 'Almost done'
  const totalMinutes = Math.ceil(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours ? `~${hours}h ${minutes}m remaining` : `~${minutes}m remaining`
}

function statusTone(status: string): string {
  if (status === 'done') return 'text-signal-good'
  if (status === 'failed' || status === 'error') return 'text-signal-bad'
  if (status === 'processing' || status === 'downloading') return 'text-accent-600'
  return 'text-ink-500'
}

export function Automation() {
  const [videos, setVideos] = useState<VideoItem[]>([])
  const [status, setStatus] = useState<StatusResponse>(initialStatus)
  const [query, setQuery] = useState('trading investing stock market trading strategies')
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [videosResponse, statusResponse] = await Promise.all([
        api.getAutomationVideos(), api.getAutomationStatus(),
      ])
      setVideos(videosResponse.videos)
      setStatus(statusResponse)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not connect to AutoClip.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchData()
    const interval = window.setInterval(() => void fetchData(), 3000)
    return () => window.clearInterval(interval)
  }, [fetchData])

  const start = async (fresh: boolean) => {
    setStarting(true)
    setError(null)
    try {
      setStatus(await api.startAutomation(query.trim(), fresh))
      await fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start automation.')
    } finally {
      setStarting(false)
    }
  }

  const finished = videos.filter(video => video.status === 'done').length
  const failed = videos.filter(video => video.status === 'failed' || video.status === 'error').length
  const current = videos.find(video => video.status === 'processing' || video.status === 'downloading')
  const percent = status.total ? Math.round(status.completed / status.total * 100) : 0

  return (
    <div className="pt-14 max-w-7xl mx-auto px-4">
      <div className="rise">
        <p className="eyebrow">Automation Pipeline</p>
        <h1 className="mt-5 font-display text-4xl leading-tight text-ink-900">Trading Shorts</h1>
        <p className="mt-3 text-ink-500">Find 20 YouTube videos, create vertical captioned shorts, then review them here.</p>
      </div>

      <section className="mt-8 p-5 bg-surface-elevated/50 border border-ink-700 rounded-lg">
        <label htmlFor="trading-query" className="block text-sm text-ink-300">YouTube search topic</label>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row">
          <input
            id="trading-query" value={query} onChange={event => setQuery(event.target.value)}
            disabled={status.active || starting}
            className="min-w-0 flex-1 rounded-md border border-ink-700 bg-surface px-3 py-2 text-sm text-ink-900 outline-none focus:border-sodium-500"
            placeholder="e.g. price action trading strategies"
          />
          <button onClick={() => void start(status.phase === 'complete')} disabled={status.active || starting || query.trim().length < 3} className="btn btn-primary min-w-40">
            {status.active || starting
              ? 'Running…'
              : status.phase === 'complete'
                ? 'Find next 20 videos'
                : status.phase === 'failed'
                  ? 'Retry failed videos'
                  : status.phase === 'interrupted'
                    ? 'Resume batch'
                  : 'Start · find 20 videos'}
          </button>
          {status.phase === 'complete' && failed > 0 && (
            <button
              onClick={() => void start(false)}
              disabled={status.active || starting || query.trim().length < 3}
              className="btn btn-secondary"
            >
              Retry {failed} failed videos
            </button>
          )}
        </div>
        <p className="mt-2 text-xs text-ink-500">One at a time to keep the machine responsive. Each finished video is automatically clipped and rendered as 9:16 MP4s.</p>
      </section>

      {(error || status.error) && (
        <div className="mt-5 rounded-lg border border-signal-bad/30 bg-signal-bad/10 p-4 text-sm text-signal-bad">
          {error || status.error}
        </div>
      )}

      <section className="mt-6 p-5 bg-surface-elevated/50 border border-ink-700 rounded-lg" aria-live="polite">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="eyebrow">{status.active ? status.phase : status.phase === 'complete' ? 'Complete' : 'Status'}</p>
            <p className="mt-2 text-sm text-ink-800">{status.message}</p>
          </div>
          <p className="numeric text-sm text-accent-600">{status.active ? formatEta(status.eta_seconds) : status.phase === 'complete' ? 'Ready to review' : ''}</p>
        </div>
        {status.total > 0 && (
          <>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-ink-700">
              <div className="h-full bg-sodium-500 transition-all" style={{ width: `${percent}%` }} />
            </div>
            <p className="mt-2 text-xs text-ink-500">{status.completed}/{status.total} videos completed · {finished} ready · {failed} failed</p>
          </>
        )}
        {current && (
          <div className="mt-4">
            <div className="flex justify-between gap-3 text-xs text-ink-500">
              <span className="truncate">{current.title}</span>
              <span>{current.stage || current.status} {current.status === 'processing' ? `· ${current.progress ?? 0}%` : ''}</span>
            </div>
            {current.status === 'processing' && <div className="mt-2 h-1 overflow-hidden rounded bg-ink-700"><div className="h-full bg-sodium-500" style={{ width: `${current.progress ?? 0}%` }} /></div>}
          </div>
        )}
      </section>

      <div className="mt-6 grid gap-4 sm:grid-cols-4">
        <Summary label="Videos found" value={videos.length} />
        <Summary label="Shorts ready" value={finished} tone="text-signal-good" />
        <Summary label="In progress" value={current ? 1 : 0} tone="text-accent-600" />
        <Summary label="Failed" value={failed} tone="text-signal-bad" />
      </div>

      <div className="mt-8 overflow-x-auto rounded-lg border border-ink-300">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-ink-700 text-left text-xs uppercase tracking-wider text-ink-500">
            <th className="p-3">#</th><th className="p-3">Video</th><th className="p-3">Duration</th><th className="p-3">Views</th><th className="p-3">Status</th><th className="p-3">Review</th>
          </tr></thead>
          <tbody className="divide-y divide-ink-800">
            {loading && <tr><td colSpan={6} className="p-8 text-center text-ink-500">Loading…</td></tr>}
            {!loading && videos.length === 0 && <tr><td colSpan={6} className="p-8 text-center text-ink-500">Press Start to discover at least 20 trading videos.</td></tr>}
            {videos.map((video, index) => (
              <tr key={video.url} className="hover:bg-surface-elevated/40">
                <td className="p-3 text-ink-500">{index + 1}</td>
                <td className="max-w-xl p-3">
                  <a href={video.url} target="_blank" rel="noreferrer" className="block truncate text-ink-900 hover:text-accent-600">{video.title}</a>
                  {video.error && <p className="mt-1 text-xs text-signal-bad">{video.error}</p>}
                </td>
                <td className="p-3 text-ink-300">{formatDuration(video.duration)}</td>
                <td className="p-3 text-ink-300">{video.view_count.toLocaleString()}</td>
                <td className={`p-3 capitalize ${statusTone(video.status)}`}>{video.status}{video.stage && video.status !== 'done' ? ` · ${video.stage}` : ''}</td>
                <td className="p-3">{video.job_id && video.status === 'done' ? <Link className="btn btn-secondary text-xs" to={`/jobs/${video.job_id}/clips`}>View shorts</Link> : <span className="text-xs text-ink-500">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Summary({ label, value, tone = 'text-ink-900' }: { label: string; value: number; tone?: string }) {
  return <div className="rounded-lg border border-ink-700 bg-surface-elevated/50 p-4"><p className={`font-display text-3xl font-bold ${tone}`}>{value}</p><p className="text-xs text-ink-500">{label}</p></div>
}
