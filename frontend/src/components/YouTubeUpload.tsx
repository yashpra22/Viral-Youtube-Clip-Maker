import { useEffect, useState } from 'react'

const API_BASE = 'http://localhost:8000/api/youtube'

export function YouTubeUpload({
  clip,
  onClose,
}: {
  clip: any
  onClose: () => void
}) {
  const [uploading, setUploading] = useState(false)
  const [metadata, setMetadata] = useState<{ title: string; description: string; tags: string[] } | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)
  const [userToken, setUserToken] = useState<string | null>(null)

  useEffect(() => {
    checkAuth()
  }, [])

  const checkAuth = async () => {
    const token = localStorage.getItem('autoclip_yt_token')
    if (!token) return
    try {
      const res = await fetch(`${API_BASE}/auth/status?user_token=${token}`)
      const data = await res.json()
      setAuthenticated(data.authenticated)
      setUserToken(token)
    } catch {
      setAuthenticated(false)
    }
  }

  const generateMetadata = async () => {
    try {
      const res = await fetch(`${API_BASE}/generate-metadata`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: clip.title,
          description: clip.hook,
          duration: clip.duration_s,
          category: 'General',
        }),
      })
      const data = await res.json()
      setMetadata(data)
    } catch (err) {
      setError(err as Error)
    }
  }

  const doUpload = async () => {
    if (!userToken) return
    setUploading(true)
    try {
      const exportRecord = clip.exports[0]
      if (!exportRecord) throw new Error('No exported video file found')

      const res = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_token: userToken,
          video_path: exportRecord.download_url.replace('/api/', 'http://localhost:8000/api/'),
          title: metadata?.title || clip.title,
          description: metadata?.description || clip.hook,
          tags: metadata?.tags || [],
          category_id: '22',
          privacy_status: 'public',
        }),
      })
      if (!res.ok) throw new Error('Upload failed')
      const data = await res.json()
      window.open(data.video_url, '_blank')
      onClose()
    } catch (err) {
      setError(err as Error)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-surface border border-ink-300 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto">
        <div className="flex items-baseline justify-between mb-6">
          <h2 className="font-display text-2xl text-ink-900">Upload to YouTube</h2>
          <button onClick={onClose} className="text-ink-500 hover:text-ink-900">✕</button>
        </div>

        {!authenticated ? (
          <div className="p-6 bg-ink-50 rounded-lg text-center">
            <p className="text-sm text-ink-600 mb-4">Connect YouTube to upload clips directly.</p>
            <button onClick={startAuth} className="btn btn-primary">
              Connect YouTube
            </button>
            <p className="mt-3 text-xs text-ink-500">
              You'll be redirected to Google to authorize AutoClip to upload videos on your behalf.
            </p>
          </div>
        ) : (
          <>
            {metadata ? (
              <>
                <div className="mb-6">
                  <label className="block mb-1 text-xs font-medium text-ink-600">Title</label>
                  <input type="text" value={metadata.title} readOnly className="w-full border border-ink-300 rounded-lg p-2 bg-surface-elevated" />
                </div>
                <div className="mb-6">
                  <label className="block mb-1 text-xs font-medium text-ink-600">Description</label>
                  <textarea value={metadata.description} readOnly rows={4} className="w-full border border-ink-300 rounded-lg p-2 bg-surface-elevated" />
                </div>
                <div className="mb-6">
                  <label className="block mb-1 text-xs font-medium text-ink-600">Tags</label>
                  <div className="flex flex-wrap gap-2">
                    {metadata.tags.map((tag) => (
                      <span key={tag} className="px-2 py-1 rounded bg-accent-600/10 text-accent-600 text-xs border border-accent-600/30">#{tag}</span>
                    ))}
                  </div>
                </div>
                <div className="mb-6 flex items-baseline gap-6">
                  <span className="text-xs text-ink-500">{Math.floor(clip.duration_s / 60)}:{String(Math.floor(clip.duration_s % 60)).padStart(2, '0')}</span>
                  <span className="text-xs text-ink-500">{clip.exports.length > 0 ? 'Exported' : 'Not exported'}</span>
                </div>
                <button onClick={doUpload} disabled={uploading} className="w-full btn btn-primary disabled:opacity-50">
                  {uploading ? 'Uploading to YouTube...' : 'Publish to YouTube'}
                </button>
              </>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm text-ink-500 mb-4">Generating AI metadata...</p>
                <button onClick={generateMetadata} className="btn btn-primary">Generate AI Metadata</button>
              </div>
            )}
            {error && (
              <div className="mt-4 p-3 bg-signal-bad/10 border border-signal-bad/30 rounded text-xs text-signal-bad">{error.message}</div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

  const startAuth = async () => {
    const res = await fetch(`${API_BASE}/auth/start`)
    const data = await res.json()
    window.open(data.auth_url, '_blank', 'width=600,height=700')
  }