import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'

export function Review() {
  const { jobId } = useParams()
  const [job, setJob] = useState<any>(null)

  useEffect(() => {
    if (!jobId) return
    api.getJob(jobId).then(setJob).catch(() => setJob(null))
  }, [jobId])

  return (
    <div className="pt-14 max-w-2xl mx-auto px-4">
      <h1 className="text-2xl font-bold text-ink-100 mb-4">
        Review: {job?.source?.title || 'Untitled'}
      </h1>
      {job && (
        <div className="mt-4 p-4 bg-ink-850/30 border border-ink-700 rounded-lg">
          <p className="text-ink-400">Job ID: {job.id}</p>
          <p className="text-ink-400">Status: {job.status}</p>
          <p className="text-ink-400">Provider: {job.provider}</p>
        </div>
      )}
      <button onClick={() => window.location.href = '/'} className="mt-4 btn btn-primary">
        Back to home
      </button>
    </div>
  )
}