import { useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'

export default function GithubPush({ analysis, terraformData, onBack, onReset }) {
  const [token, setToken] = useState('')
  const [repoName, setRepoName] = useState(
    `archlens-${(analysis?.architecture_type || 'tf').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 30)}`,
  )
  const [createIfMissing, setCreateIfMissing] = useState(true)
  const [isPrivate, setIsPrivate] = useState(true)
  const [branch, setBranch] = useState('main')
  const [basePath, setBasePath] = useState('terraform')
  const [commitMessage, setCommitMessage] = useState(
    `ArchLens: ${terraformData?.cloud?.toUpperCase() || ''} Terraform from ${analysis?.architecture_type || 'architecture'}`,
  )
  const [includeReadme, setIncludeReadme] = useState(true)
  const [showToken, setShowToken] = useState(false)

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const canPush = token.trim() && repoName.trim() && terraformData?.files?.length > 0

  const handlePush = async () => {
    if (!canPush) return
    setLoading(true)
    setResult(null)
    try {
      const { data } = await axios.post('/api/github/push', {
        token: token.trim(),
        repo_name: repoName.trim(),
        create_if_missing: createIfMissing,
        private: isPrivate,
        branch: branch.trim() || 'main',
        base_path: basePath.trim(),
        commit_message: commitMessage.trim() || 'ArchLens commit',
        files: terraformData.files,
        include_readme: includeReadme,
        readme_extra: `Architecture: **${analysis?.architecture_type}**\n\n${analysis?.description || ''}`,
      })
      setResult(data)
      toast.success(data.created_repo ? `Repo ${data.repo_full_name} created` : `Pushed to ${data.repo_full_name}`)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message
      toast.error(`GitHub push failed: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Push to GitHub</h2>
          <p className="text-gray-400 mt-1">
            Commit your generated Terraform to a GitHub repository
          </p>
        </div>
        {terraformData && (
          <span className="badge bg-blue-500/20 text-blue-300 border border-blue-500/30">
            {terraformData.cloud?.toUpperCase()} · {terraformData.files?.length} files
          </span>
        )}
      </div>

      {!terraformData && (
        <div className="card border-amber-500/30 bg-amber-500/5 text-amber-200 text-sm">
          ⚠️ No Terraform generated yet. Go back and generate Terraform first.
        </div>
      )}

      {terraformData && !result && (
        <div className="card space-y-4">
          {/* Token */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              GitHub Personal Access Token <span className="text-red-400">*</span>
            </label>
            <div className="flex gap-2">
              <input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                autoComplete="off"
                className="flex-1 bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="text-xs text-gray-500 hover:text-gray-300 px-2"
              >
                {showToken ? '🙈' : '👁'}
              </button>
            </div>
            <p className="text-[11px] text-gray-500 mt-1">
              Needs <code className="text-gray-400">repo</code> scope. Token is used only for this
              request — never stored or logged.{' '}
              <a
                href="https://github.com/settings/tokens/new?scopes=repo&description=ArchLens"
                target="_blank"
                rel="noreferrer"
                className="text-blue-400 hover:text-blue-300"
              >
                Create one →
              </a>
            </p>
          </div>

          {/* Repo + branch */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Repository name <span className="text-red-400">*</span>
              </label>
              <input
                value={repoName}
                onChange={(e) => setRepoName(e.target.value)}
                placeholder="my-tf-repo OR org/my-tf-repo"
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 focus:outline-none"
              />
              <p className="text-[11px] text-gray-500 mt-1">
                Plain name → your account. Use <code>owner/name</code> for an org.
              </p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Branch</label>
              <input
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Path + commit message */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Subfolder for .tf files
              </label>
              <input
                value={basePath}
                onChange={(e) => setBasePath(e.target.value)}
                placeholder="terraform"
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Commit message</label>
              <input
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Toggles */}
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={createIfMissing}
                onChange={(e) => setCreateIfMissing(e.target.checked)}
                className="accent-blue-500"
              />
              Create repo if missing
            </label>
            <label className="flex items-center gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={isPrivate}
                onChange={(e) => setIsPrivate(e.target.checked)}
                className="accent-blue-500"
                disabled={!createIfMissing}
              />
              Private (when creating)
            </label>
            <label className="flex items-center gap-2 text-gray-300 cursor-pointer">
              <input
                type="checkbox"
                checked={includeReadme}
                onChange={(e) => setIncludeReadme(e.target.checked)}
                className="accent-blue-500"
              />
              Include README.md
            </label>
          </div>

          {/* File preview */}
          <div className="bg-gray-950 border border-gray-800 rounded-lg p-3">
            <p className="text-xs font-medium text-gray-400 mb-2">
              Files to commit ({terraformData.files.length}{includeReadme ? ' + README.md' : ''}):
            </p>
            <ul className="text-xs text-gray-500 font-mono space-y-0.5">
              {terraformData.files.map((f) => (
                <li key={f.filename}>
                  📄 {basePath ? `${basePath}/` : ''}
                  {f.filename}
                </li>
              ))}
              {includeReadme && <li>📘 README.md</li>}
            </ul>
          </div>
        </div>
      )}

      {/* Success */}
      {result && (
        <div className="card border-green-500/40 bg-green-500/5 space-y-3">
          <div className="flex items-center gap-2 text-green-400 font-semibold">
            <span className="text-2xl">✅</span>
            <span>Pushed successfully!</span>
          </div>
          <div className="text-sm text-gray-300 space-y-1">
            <p>
              <span className="text-gray-500">Repository:</span>{' '}
              <a
                href={result.repo_url}
                target="_blank"
                rel="noreferrer"
                className="text-blue-400 hover:text-blue-300 font-mono"
              >
                {result.repo_full_name} ↗
              </a>
              {result.created_repo && (
                <span className="ml-2 badge bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  newly created
                </span>
              )}
            </p>
            <p>
              <span className="text-gray-500">Branch:</span>{' '}
              <span className="font-mono text-gray-200">{result.branch}</span>
            </p>
            <p>
              <span className="text-gray-500">Files written:</span>{' '}
              <span className="text-gray-200">{result.files_written}</span>
            </p>
          </div>

          <div className="border-t border-gray-800 pt-3">
            <p className="text-xs font-medium text-gray-400 mb-2">Commits:</p>
            <ul className="text-xs space-y-0.5">
              {result.commits.map((c) => (
                <li key={c.path}>
                  <a
                    href={c.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-mono text-gray-400 hover:text-blue-400"
                  >
                    📄 {c.path}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex gap-2 pt-2">
            <a
              href={result.repo_url}
              target="_blank"
              rel="noreferrer"
              className="btn-primary text-sm"
            >
              🚀 Open repository
            </a>
            <button onClick={() => setResult(null)} className="btn-secondary text-sm">
              ← Push again
            </button>
          </div>
        </div>
      )}

      <div className="flex gap-3 mt-6">
        <button className="btn-secondary" onClick={onBack}>
          ← Back to Terraform
        </button>
        {!result && (
          <button
            className="btn-primary flex-1 flex items-center justify-center gap-2"
            disabled={!canPush || loading}
            onClick={handlePush}
          >
            {loading ? (
              <>
                <span className="animate-spin">⟳</span> Pushing to GitHub…
              </>
            ) : (
              <>🐙 Push to GitHub</>
            )}
          </button>
        )}
        {result && (
          <button className="btn-primary flex-1" onClick={onReset}>
            ✨ Start a new analysis
          </button>
        )}
      </div>
    </div>
  )
}
