import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import TerraformRunner from './TerraformRunner'

const CHECKS = [
  {
    key: 'fmt',
    label: 'Syntax Check',
    subtitle: 'terraform fmt',
    icon: '📝',
    description: 'Validates HCL formatting and syntax correctness',
  },
  {
    key: 'validate',
    label: 'Config Validation',
    subtitle: 'tf validate',
    icon: '✅',
    description: 'Validates provider resource schemas and references',
  },
  {
    key: 'tflint',
    label: 'Provider Rules',
    subtitle: 'tflint',
    icon: '🔍',
    description: 'Detects deprecated fields, wrong argument types',
  },
  {
    key: 'checkov',
    label: 'Security Scan',
    subtitle: 'checkov',
    icon: '🛡',
    description: 'Scans for security misconfigurations and CIS benchmarks',
  },
  {
    key: 'trivy',
    label: 'Vulnerability Scan',
    subtitle: 'trivy',
    icon: '🔒',
    description: 'Scans for known CVEs and IaC misconfigurations',
  },
]

function ScoreBadge({ score }) {
  const color =
    score >= 85 ? 'text-green-400 bg-green-500/10 border-green-500/30' :
    score >= 60 ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30' :
                  'text-red-400 bg-red-500/10 border-red-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs font-bold ${color}`}>
      {score}/100
    </span>
  )
}

// Static fallback lookup: check-ID → human description.
// Used when the backend detail string contains an empty meaning field.
const CKV_LOOKUP = {
  // AWS
  CKV_AWS_1:   'IAM policy allows full "*:*" admin privileges',
  CKV_AWS_6:   'S3 bucket logging not enabled',
  CKV_AWS_8:   'Launch config EBS not encrypted',
  CKV_AWS_16:  'RDS storage not encrypted at rest',
  CKV_AWS_17:  'RDS instance publicly accessible',
  CKV_AWS_18:  'S3 bucket access logging not enabled',
  CKV_AWS_19:  'S3 bucket not encrypted at rest',
  CKV_AWS_20:  'S3 bucket allows public READ access',
  CKV_AWS_21:  'S3 bucket versioning not enabled',
  CKV_AWS_23:  'Security group / rule has no description',
  CKV_AWS_24:  'ACM cert auto-renewal not enabled',
  CKV_AWS_25:  'ElastiCache no in-transit encryption',
  CKV_AWS_27:  'CloudTrail logging not enabled',
  CKV_AWS_28:  'CloudTrail log file validation not enabled',
  CKV_AWS_34:  'CloudFront ViewerProtocolPolicy not set to HTTPS',
  CKV_AWS_35:  'CloudTrail logs not encrypted with KMS CMK',
  CKV_AWS_36:  'CloudTrail not enabled in all regions',
  CKV_AWS_43:  'Kinesis Stream not encrypted',
  CKV_AWS_45:  'Hard-coded secrets in Lambda environment',
  CKV_AWS_50:  'X-Ray tracing not enabled on Lambda',
  CKV_AWS_53:  'S3 block public ACLs not enabled',
  CKV_AWS_54:  'S3 block public policy not enabled',
  CKV_AWS_55:  'S3 ignore public ACLs not enabled',
  CKV_AWS_56:  "S3 'restrict_public_buckets' not enabled",
  CKV_AWS_57:  'S3 bucket ACL allows public WRITE',
  CKV_AWS_58:  'EKS cluster secrets encryption not enabled',
  CKV_AWS_66:  'CloudWatch Log Group retention not set',
  CKV_AWS_67:  'CloudTrail not enabled in all regions',
  CKV_AWS_68:  'CloudFront distribution has no WAF',
  CKV_AWS_69:  'MQ Broker publicly exposed',
  CKV_AWS_70:  'S3 bucket allows any Principal action',
  CKV_AWS_71:  'Redshift cluster logging not enabled',
  CKV_AWS_72:  'SQS policy allows all (*) actions',
  CKV_AWS_76:  'API Gateway access logging not enabled',
  CKV_AWS_79:  'IMDSv1 (metadata v1) not disabled on EC2',
  CKV_AWS_86:  'CloudFront access logging not enabled',
  CKV_AWS_87:  'Redshift cluster publicly accessible',
  CKV_AWS_88:  'EC2 instance has public IP',
  CKV_AWS_91:  'ELBv2 (ALB/NLB) access logging not enabled',
  CKV_AWS_96:  'RDS Aurora cluster storage not encrypted',
  CKV_AWS_105: 'Redshift not using SSL',
  CKV_AWS_106: 'EBS default encryption not enabled',
  CKV_AWS_111: 'IAM policy allows write access without constraint',
  CKV_AWS_119: 'DynamoDB table not encrypted with KMS CMK',
  CKV_AWS_126: 'EC2 detailed monitoring not enabled',
  CKV_AWS_130: 'VPC subnet assigns public IP by default',
  CKV_AWS_131: 'ALB not dropping HTTP headers',
  CKV_AWS_133: 'RDS instance has no backup policy',
  CKV_AWS_139: 'RDS cluster deletion protection not enabled',
  CKV_AWS_143: 'S3 bucket object lock not enabled',
  CKV_AWS_144: 'S3 cross-region replication not enabled',
  CKV_AWS_145: 'S3 bucket not encrypted with KMS by default',
  CKV_AWS_148: 'Default VPC planned to be provisioned',
  CKV_AWS_157: 'RDS Multi-AZ not enabled',
  CKV_AWS_158: 'CloudWatch Log Group not encrypted with KMS',
  CKV_AWS_163: 'ECR image scanning on push not enabled',
  CKV_AWS_174: 'CloudFront TLS viewer certificate below v1.2',
  CKV_AWS_189: 'ElastiCache replication group not encrypted with CMK',
  CKV_AWS_227: 'KMS key not enabled',
  CKV_AWS_293: 'RDS database instance deletion protection not enabled',
  CKV_AWS_315: 'EC2 Auto Scaling group not using launch template',
  CKV_AWS_382: 'Security group allows unrestricted egress to all ports',
  // CKV2 AWS
  CKV2_AWS_5:  'EC2 security group allows unrestricted ingress',
  CKV2_AWS_6:  'S3 bucket has no public access block',
  CKV2_AWS_11: 'VPC flow logging not enabled',
  CKV2_AWS_12: 'Default VPC security group does not restrict all traffic',
  CKV2_AWS_20: 'ALB does not redirect HTTP to HTTPS',
  CKV2_AWS_23: 'Route53 A record has no attached resource',
  CKV2_AWS_28: 'ElastiCache replication group not encrypted in transit',
  CKV2_AWS_31: 'WAFv2 has no logging configuration',
  CKV2_AWS_34: 'SSM parameter not encrypted',
  CKV2_AWS_38: 'Route53 DNSSEC signing not enabled',
  CKV2_AWS_39: 'Route53 hosted zone DNS query logging not enabled',
  CKV2_AWS_40: 'IAM policy allows full IAM privileges',
  CKV2_AWS_46: 'CloudFront S3 origin missing Origin Access Identity',
  CKV2_AWS_61: 'S3 bucket lifecycle configuration not set',
  CKV2_AWS_62: 'S3 bucket event notifications not enabled',
  CKV2_AWS_64: 'KMS key policy not defined',
  CKV2_AWS_65: 'S3 bucket ACLs not disabled',
  CKV2_AWS_73: 'SQS queue not encrypted with CMK',
  CKV2_AWS_74: 'Load balancer using weak TLS ciphers',
  // Azure
  CKV_AZURE_1:   'AKS RBAC not enabled',
  CKV_AZURE_2:   'AKS no Azure AD integration',
  CKV_AZURE_3:   'VM managed disk not encrypted',
  CKV_AZURE_7:   'AKS no network policy configured',
  CKV_AZURE_9:   'App Service TLS version below 1.2',
  CKV_AZURE_13:  'App Service authentication not set',
  CKV_AZURE_14:  'App Service not redirecting HTTP to HTTPS',
  CKV_AZURE_15:  'App Service not using latest TLS encryption',
  CKV_AZURE_16:  'App Service AAD registration not enabled',
  CKV_AZURE_17:  'Storage account does not enforce HTTPS',
  CKV_AZURE_18:  'Storage account secure transfer not required',
  CKV_AZURE_22:  'Key Vault activity retention log under 1 year',
  CKV_AZURE_23:  'Azure Security Center Defender not enabled',
  CKV_AZURE_35:  'App Service not using latest TLS version',
  CKV_AZURE_36:  'App Service HTTP logging not enabled',
  CKV_AZURE_37:  'App Service detailed error messages not enabled',
  CKV_AZURE_38:  'App Service failed request tracing not enabled',
  CKV_AZURE_41:  'Azure Key Vault publicly accessible',
  CKV_AZURE_42:  'Key Vault is not recoverable',
  CKV_AZURE_43:  'Storage not encrypted with Customer Managed Key',
  CKV_AZURE_44:  'Storage account not using latest TLS version',
  // GCP
  CKV_GCP_3:  'GCS bucket not using uniform access',
  CKV_GCP_5:  'Firewall allows unrestricted SSH (port 22) ingress',
  CKV_GCP_6:  'Firewall allows unrestricted RDP (port 3389) ingress',
  CKV_GCP_12: 'Cloud SQL instance has public IP',
  CKV_GCP_13: 'Default service account used for project access',
  CKV_GCP_25: 'GCP VPC subnet flow logs not enabled',
  CKV_GCP_26: 'Cloud SQL instance has public IP',
  CKV_GCP_29: 'Cloud SQL not restricted from internet',
  CKV_GCP_54: 'GCP resource not labeled',
  CKV_GCP_62: 'GCS bucket logging not enabled',
  CKV_GCP_63: 'GKE nodes not auto-upgraded',
  CKV_GCP_67: 'GKE Shielded Nodes not enabled',
  CKV_GCP_68: 'GKE Workload Identity not enabled',
}

function parseCheckovRows(details) {
  // Detail format: "[SEVERITY] CKV_XXX_N — meaning | resource: xxx | file:Lxxx"
  return details
    .map((d) => {
      const m = d.match(/\[(\w+)\]\s+(CKV[\w]+)\s+[\u2014\u2013-]+\s+([^|]*)/)
      if (!m) return null
      const meaning = m[3].trim() || CKV_LOOKUP[m[2]] || ''
      return { severity: m[1], checkId: m[2], meaning }
    })
    .filter((r) => r !== null)
}

function CheckovTable({ details }) {
  const rows = parseCheckovRows(details)
  if (!rows.length) return null
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wide">Security Finding Explanations</p>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-900 border-b border-gray-800">
              <th className="text-left px-3 py-2 text-gray-400 font-semibold w-36">Check ID</th>
              <th className="text-left px-3 py-2 text-gray-400 font-semibold w-20">Severity</th>
              <th className="text-left px-3 py-2 text-gray-400 font-semibold">Meaning</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={`border-b border-gray-800/60 ${i % 2 === 0 ? 'bg-gray-950' : 'bg-gray-900/40'}`}>
                <td className="px-3 py-2 font-mono text-blue-400 whitespace-nowrap">{row.checkId}</td>
                <td className="px-3 py-2 whitespace-nowrap">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                    row.severity === 'HIGH' || row.severity === 'CRITICAL'
                      ? 'bg-red-500/20 text-red-400'
                      : row.severity === 'MEDIUM'
                      ? 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-gray-700 text-gray-400'
                  }`}>{row.severity}</span>
                </td>
                <td className="px-3 py-2 text-gray-300">{row.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function LineNumberedEditor({ content, onChange }) {
  const taRef = useRef(null)
  const lnRef = useRef(null)
  const syncScroll = () => {
    if (lnRef.current && taRef.current)
      lnRef.current.scrollTop = taRef.current.scrollTop
  }
  const lineCount = (content.match(/\n/g) || []).length + 1
  return (
    <div className="flex bg-gray-900 overflow-hidden" style={{ height: '18rem' }}>
      <div
        ref={lnRef}
        className="overflow-hidden shrink-0 bg-gray-950 select-none border-r border-gray-800 py-3 pr-3 pl-2 text-right text-gray-600 font-mono text-xs leading-5"
        style={{ minWidth: '3rem' }}
      >
        {Array.from({ length: lineCount }, (_, i) => (
          <div key={i} className="leading-5">{i + 1}</div>
        ))}
      </div>
      <textarea
        ref={taRef}
        value={content}
        onChange={e => onChange(e.target.value)}
        onScroll={syncScroll}
        spellCheck={false}
        autoFocus
        className="flex-1 resize-none outline-none bg-gray-900 text-gray-200 p-3 leading-5 text-xs font-mono"
      />
    </div>
  )
}

function CheckRow({ check, result, loading }) {
  const [expanded, setExpanded] = useState(false)

  const status = loading ? 'loading' : !result ? 'pending' : result.skipped ? 'skipped' : result.passed ? 'passed' : 'failed'

  const statusUI = {
    loading: { icon: <span className="animate-spin text-blue-400 text-lg">⟳</span>, label: 'Running...', cls: 'text-blue-400' },
    pending: { icon: <span className="text-gray-600 text-lg">○</span>, label: 'Pending', cls: 'text-gray-500' },
    skipped: { icon: <span className="text-yellow-400 text-lg">⊘</span>, label: 'Skipped', cls: 'text-yellow-400' },
    passed:  { icon: <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-500 text-white text-sm font-bold">✓</span>, label: 'Passed', cls: 'text-green-400' },
    failed:  { icon: <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-500 text-white text-sm font-bold">✗</span>, label: 'Failed', cls: 'text-red-400' },
  }[status]

  return (
    <div className={`rounded-xl border transition-all ${
      status === 'passed' ? 'border-green-500/30 bg-green-500/5' :
      status === 'failed' ? 'border-red-500/30 bg-red-500/5' :
      status === 'skipped' ? 'border-yellow-500/30 bg-yellow-500/5' :
      'border-gray-800 bg-gray-900/40'
    }`}>
      <div
        className="flex items-center gap-4 p-4 cursor-pointer select-none"
        onClick={() => result?.details?.length && setExpanded(e => !e)}
      >
        <span className="text-2xl shrink-0">{check.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white text-sm">{check.label}</span>
            <span className="text-xs text-gray-600 font-mono">{check.subtitle}</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {result ? result.message : check.description}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {statusUI.icon}
          {result?.details?.length > 0 && (
            <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
          )}
        </div>
      </div>

      {expanded && result?.details?.length > 0 && (
        <div className="px-4 pb-4">
          <div className="bg-gray-950 rounded-lg p-3 font-mono text-xs space-y-1 max-h-48 overflow-y-auto border border-gray-800">
            {result.details.map((d, i) => (
              <div key={i} className={
                d.includes('[ERROR]') || d.includes('[HIGH]') ? 'text-red-400' :
                d.includes('[WARN') || d.includes('[MED') ? 'text-yellow-400' :
                'text-gray-400'
              }>{d}</div>
            ))}
          </div>
          {result.passed_checks !== undefined && (
            <p className="text-xs text-gray-500 mt-2">
              {result.passed_checks} checks passed · {result.failed_checks} failed
            </p>
          )}
          {/* Checkov explanation table */}
          {check.key === 'checkov' && <CheckovTable details={result.details} />}
        </div>
      )}
    </div>
  )
}

function ValidationPipeline({ results, loading }) {
  return (
    <div className="mb-5 p-4 rounded-xl border border-gray-800 bg-gray-900/40 overflow-x-auto">
      <p className="text-[10px] text-gray-600 uppercase tracking-widest mb-3 font-semibold">Validation Pipeline</p>
      <div className="flex items-center gap-2">
        {CHECKS.map((check, i) => {
          const result = results?.[check.key]
          const status = loading
            ? 'loading'
            : !result ? 'pending'
            : result.skipped ? 'skipped'
            : result.passed ? 'passed' : 'failed'
          const styles = {
            loading: 'border-blue-500/60 bg-blue-500/10 text-blue-400',
            pending: 'border-gray-700 bg-gray-900 text-gray-500',
            skipped: 'border-yellow-500/40 bg-yellow-500/5 text-yellow-400',
            passed:  'border-green-500/40 bg-green-500/10 text-green-400',
            failed:  'border-red-500/40 bg-red-500/10 text-red-400',
          }[status]
          const icon = {
            loading: <span className="animate-spin text-sm">⟳</span>,
            pending: <span className="text-sm text-gray-600">○</span>,
            skipped: <span className="text-sm">⊘</span>,
            passed:  <span className="text-sm">✓</span>,
            failed:  <span className="text-sm">✗</span>,
          }[status]
          return (
            <div key={check.key} className="flex items-center gap-2 shrink-0">
              <div className={`flex flex-col items-center px-4 py-3 rounded-xl border min-w-[96px] ${styles}`}>
                <div className="text-xl mb-1">{check.icon}</div>
                <div className="flex items-center gap-1 text-[12px] font-semibold whitespace-nowrap">
                  {icon} {check.subtitle}
                </div>
              </div>
              {i < CHECKS.length - 1 && (
                <span className="text-gray-600 text-sm font-bold">→</span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function downloadValidationReport(results, currentFiles, cloud) {
  const ts = new Date().toISOString()
  const lines = [
    '# ArchLens Validation Report',
    `Generated: ${ts}`,
    `Cloud: ${(cloud || 'terraform').toUpperCase()}`,
    '',
    '## Summary',
    `Overall Score: ${results.overall_score}/100`,
    `Status: ${results.passed ? '✅ All checks passed' : '❌ Issues found'}`,
    results.summary || '',
    '',
  ]
  CHECKS.forEach(check => {
    const r = results[check.key]
    if (!r) return
    const status = r.skipped ? 'SKIPPED' : r.passed ? 'PASSED' : 'FAILED'
    lines.push(`## ${check.label} (${check.subtitle})`)
    lines.push(`Status: ${status}`)
    lines.push(`Score: ${r.score}/100`)
    lines.push(`Message: ${r.message}`)
    if (r.details?.length > 0) {
      lines.push('', '### Details')
      r.details.forEach(d => lines.push(`- ${d}`))
    }
    lines.push('')
  })
  lines.push('## Files Validated')
  currentFiles.forEach(f => lines.push(`- ${f.filename}`))
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `archlens-validation-${ts.slice(0, 10)}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function OverallScore({ score, summary, passed }) {
  const color = score >= 85 ? 'text-green-400' : score >= 60 ? 'text-yellow-400' : 'text-red-400'
  const ring = score >= 85 ? 'border-green-500' : score >= 60 ? 'border-yellow-500' : 'border-red-500'
  const bg = score >= 85 ? 'bg-green-500/10' : score >= 60 ? 'bg-yellow-500/10' : 'bg-red-500/10'

  return (
    <div className={`flex items-center gap-6 p-5 rounded-xl border ${ring} ${bg} mb-6`}>
      <div className={`text-5xl font-black ${color} leading-none shrink-0`}>
        {score}
        <span className="text-2xl font-normal text-gray-500">/100</span>
      </div>
      <div>
        <p className={`font-bold text-lg ${color}`}>
          {score >= 85 ? '🎉 Excellent' : score >= 70 ? '👍 Good' : score >= 50 ? '⚠ Needs Attention' : '❌ Issues Found'}
        </p>
        <p className="text-sm text-gray-400 mt-0.5">{summary}</p>
      </div>
    </div>
  )
}

export default function TerraformValidation({ files, cloud, onValidationDone, onFilesFixed }) {
  const [loading, setLoading] = useState(false)
  const [fixing, setFixing] = useState(false)
  const [fixPass, setFixPass] = useState(0)   // current pass number (0 = not fixing)
  const [activeCheck, setActiveCheck] = useState(null)
  const [results, setResults] = useState(null)
  const [currentFiles, setCurrentFiles] = useState(files)
  const [actionTab, setActionTab]       = useState(null)   // 'ai' | 'manual' | null
  const [editIdx,    setEditIdx]         = useState(0)
  const [mainTab, setMainTab]            = useState('static')  // 'static' | 'run'

  // Keep currentFiles in sync when parent passes a different file set
  // (e.g. switching cloud, regenerating) — but not while AI is mid-fix
  useEffect(() => {
    if (!fixing) {
      setCurrentFiles(files)
    }
  }, [files])

  const runValidation = async (filesToValidate) => {
    const target = filesToValidate || currentFiles
    setLoading(true)
    setResults(null)
    setActiveCheck('fmt')
    try {
      const { data } = await axios.post('/api/terraform/validate', { files: target })
      setResults(data)
      if (onValidationDone) onValidationDone(data)
      return data   // return so callers can inspect score
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Validation failed')
      return null
    } finally {
      setLoading(false)
      setActiveCheck(null)
    }
  }

  const hasIssues = results && CHECKS.some(
    c => results[c.key] && !results[c.key].passed && !results[c.key].skipped
  )

  const MAX_PASSES = 3

  const fixWithAI = async () => {
    setFixing(true)
    let latestFiles = currentFiles
    let latestResults = results
    let prevScore = results?.overall_score ?? 0

    try {
      for (let pass = 1; pass <= MAX_PASSES; pass++) {
        setFixPass(pass)

        // Collect ALL findings from every check — fmt, validate, tflint, checkov, trivy
        const findings = [
          ...(latestResults?.fmt?.details      || []).filter(Boolean).map(d => `[FORMAT] ${d}`),
          ...(latestResults?.validate?.details || []).filter(Boolean).map(d => `[VALIDATE] ${d}`),
          ...(latestResults?.tflint?.details   || []).filter(Boolean),
          ...(latestResults?.checkov?.details  || []).filter(Boolean),
          ...(latestResults?.trivy?.details    || []).filter(Boolean).map(d => `[SECURITY] ${d}`),
        ]

        if (findings.length === 0) break  // nothing left to fix

        toast(`🔧 Fix pass ${pass}/${MAX_PASSES} — sending ${findings.length} findings to AI…`, { icon: '⟳' })

        const { data } = await axios.post('/api/terraform/fix', {
          files: latestFiles,
          cloud: cloud || 'aws',
          findings,
        })

        latestFiles = data.files
        setCurrentFiles(latestFiles)
        if (onFilesFixed) onFilesFixed(latestFiles)

        toast(`✅ Pass ${pass} done — re-validating…`, { icon: '📋' })
        const newResults = await runValidation(latestFiles)
        if (!newResults) break

        const newScore = newResults.overall_score ?? 0

        // Stop early if score is perfect or no longer improving
        if (newScore >= 100) {
          toast.success(`🎉 All issues fixed after ${pass} pass${pass > 1 ? 'es' : ''}!`)
          break
        }
        if (newScore <= prevScore) {
          toast(`Score plateaued at ${newScore}/100 — stopping after ${pass} pass${pass > 1 ? 'es' : ''}.`, { icon: '⚠' })
          break
        }

        prevScore = newScore
        latestResults = newResults

        if (pass === MAX_PASSES) {
          toast(`Reached ${MAX_PASSES} passes — final score: ${newScore}/100`, { icon: '📋' })
        }
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'AI fix failed')
    } finally {
      setFixing(false)
      setFixPass(0)
    }
  }

  return (
    <div className="mt-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-white flex items-center gap-2">
            🔬 Terraform Validation
          </h3>
          <p className="text-xs text-gray-500">fmt · tf validate · tflint · checkov · trivy</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => runValidation()}
            disabled={loading || fixing || mainTab !== 'static'}
            className="btn-primary text-sm"
          >
            {loading
              ? <span className="flex items-center gap-2"><span className="animate-spin">⟳</span> Running...</span>
              : results ? '↻ Re-run Validation' : '▶ Run Validation'
            }
          </button>
        </div>
      </div>

      {/* Main tab switcher */}
      <div className="flex gap-1 mb-5 border-b border-gray-800">
        <button
          onClick={() => setMainTab('static')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            mainTab === 'static'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-300'
          }`}
        >
          🧪 Static Analysis
        </button>
        <button
          onClick={() => setMainTab('run')}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            mainTab === 'run'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-300'
          }`}
        >
          ⚡ Real Execution
        </button>
      </div>

      {/* Real Execution tab */}
      {mainTab === 'run' && (
        <TerraformRunner
          files={currentFiles}
          cloud={cloud}
          onFilesUpdated={(updatedFiles) => {
            setCurrentFiles(updatedFiles)
            if (onFilesFixed) onFilesFixed(updatedFiles)
          }}
        />
      )}

      {/* Static Analysis tab */}
      {mainTab === 'static' && (
        <>
          {/* Pipeline */}
          <ValidationPipeline results={results} loading={loading} />

      {/* Check rows */}
      <div className="space-y-3">
        {CHECKS.map((check) => (
          <CheckRow
            key={check.key}
            check={check}
            result={results?.[check.key]}
            loading={loading && activeCheck === check.key}
          />
        ))}
      </div>

      {!results && !loading && (
        <p className="text-center text-gray-600 text-sm mt-4">
          Click "Run Validation" to validate the generated Terraform code
        </p>
      )}

      {/* ── Action Panel: Fix with AI / Manual Fix / Revalidate ── */}
      {results && (
        <div className="mt-5 rounded-xl border border-gray-700 bg-gray-900 overflow-hidden">
          {/* Tab bar */}
          <div className="flex border-b border-gray-800">
            {hasIssues && (
              <button
                onClick={() => setActionTab(t => t === 'ai' ? null : 'ai')}
                disabled={fixing || loading}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors border-r border-gray-800 disabled:opacity-50 ${
                  actionTab === 'ai' ? 'bg-orange-600/20 text-orange-300' : 'text-gray-400 hover:text-orange-300'
                }`}
              >
                {fixing
                  ? <><span className="animate-spin">⟳</span> Fixing ({fixPass}/{MAX_PASSES})…</>
                  : '🤖 Fix with AI'}
              </button>
            )}
            <button
              onClick={() => setActionTab(t => t === 'manual' ? null : 'manual')}
              className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors border-r border-gray-800 ${
                actionTab === 'manual' ? 'bg-blue-600/20 text-blue-300' : 'text-gray-400 hover:text-blue-300'
              }`}
            >
              ✏️ Manual Fix
            </button>
            <button
              onClick={() => { setActionTab(null); runValidation(currentFiles) }}
              disabled={loading || fixing}
              className="flex items-center gap-2 px-4 py-3 text-sm font-medium text-gray-400 hover:text-green-300 transition-colors disabled:opacity-40 border-r border-gray-800"
            >
              ↻ Revalidate
            </button>
            <div className="flex-1" />
            {results && (
              <span className={`self-center pr-4 text-xs font-semibold ${
                results.overall_score >= 85 ? 'text-green-400' :
                results.overall_score >= 60 ? 'text-yellow-400' : 'text-red-400'
              }`}>
                Score: {results.overall_score}/100
              </span>
            )}
          </div>

          {/* Fix with AI panel */}
          {actionTab === 'ai' && hasIssues && (
            <div className="p-4">
              <p className="text-sm text-gray-300 mb-3">
                AI will fix <strong className="text-white">{
                  CHECKS.reduce((n, c) => n + (results?.[c.key]?.details?.length || 0), 0)
                }</strong> findings across all checks (fmt · validate · tflint · checkov · trivy) — up to{' '}
                <strong className="text-white">{MAX_PASSES} passes</strong>, re-validating after each.
              </p>
              <div className="mb-4 rounded-lg border border-gray-800 bg-gray-950 p-3 max-h-44 overflow-y-auto space-y-1 text-xs font-mono">
                {CHECKS.flatMap(c =>
                  (results?.[c.key]?.details || []).map((d, i) => (
                    <div key={`${c.key}-${i}`} className={
                      d.includes('[HIGH]') || d.includes('[CRITICAL]') || d.includes('Error') ? 'text-red-400' :
                      d.includes('[MEDIUM]') || d.includes('[WARN') ? 'text-yellow-400' :
                      'text-gray-400'
                    }>
                      <span className="text-gray-600 mr-2">[{c.subtitle}]</span>{d}
                    </div>
                  ))
                )}
              </div>
              <button
                onClick={fixWithAI}
                disabled={fixing || loading}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-semibold transition-colors disabled:opacity-50"
              >
                {fixing
                  ? <><span className="animate-spin">⟳</span> Pass {fixPass}/{MAX_PASSES} — AI fixing…</>
                  : '🔧 Fix All Findings with AI'}
              </button>
            </div>
          )}

          {/* Manual Fix panel */}
          {actionTab === 'manual' && (
            <div>
              {/* File tabs */}
              <div className="flex overflow-x-auto border-b border-gray-800 bg-gray-950">
                {currentFiles.map((f, i) => {
                  const hasErr = CHECKS.some(c =>
                    (results?.[c.key]?.details || []).some(d => d.includes(f.filename))
                  )
                  return (
                    <button
                      key={f.filename}
                      onClick={() => setEditIdx(i)}
                      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-mono whitespace-nowrap border-r border-gray-800 transition-colors ${
                        editIdx === i ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'
                      }`}
                    >
                      {hasErr && <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block shrink-0" />}
                      {f.filename}
                    </button>
                  )
                })}
              </div>
              {/* Line-numbered editor — line numbers always visible */}
              <LineNumberedEditor
                content={currentFiles[editIdx]?.content || ''}
                onChange={content =>
                  setCurrentFiles(prev => prev.map((f, i) => i === editIdx ? { ...f, content } : f))
                }
              />
              {/* Save bar */}
              <div className="flex items-center justify-between px-4 py-2.5 border-t border-gray-800 bg-gray-950">
                <span className="text-xs text-gray-500">Editing {currentFiles[editIdx]?.filename}</span>
                <button
                  onClick={() => { if (onFilesFixed) onFilesFixed(currentFiles); runValidation(currentFiles) }}
                  className="text-xs px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                >
                  Save &amp; Revalidate
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Download panel — shown after validation runs */}
      {results && (
        <div className="mt-5 p-4 rounded-xl border border-gray-800 bg-gray-900/40">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="text-sm font-medium text-white">⬇ Download Terraform Files</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {currentFiles.length} file{currentFiles.length !== 1 ? 's' : ''}
              </p>
              <button
                onClick={() => downloadValidationReport(results, currentFiles, cloud)}
                className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-purple-600/20 border border-purple-500/40 text-purple-300 hover:bg-purple-600/30 transition-colors font-medium"
              >
                📋 Download Validation Report
              </button>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {currentFiles.map((f) => (
                <button
                  key={f.filename}
                  onClick={() => {
                    const blob = new Blob([f.content], { type: 'text/plain' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = f.filename
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                  className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white transition-colors font-mono border border-gray-700"
                >
                  {f.filename}
                </button>
              ))}
              <button
                onClick={() => {
                  const combined = currentFiles
                    .map((f) => `# === ${f.filename} ===\n${f.content}`)
                    .join('\n\n')
                  const blob = new Blob([combined], { type: 'text/plain' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `archlens-${cloud || 'terraform'}-all.tf`
                  a.click()
                  URL.revokeObjectURL(url)
                  toast.success('All files downloaded')
                }}
                className="px-3 py-1.5 text-xs rounded-lg bg-blue-600/20 border border-blue-500/40 text-blue-300 hover:bg-blue-600/30 transition-colors font-medium"
              >
                ⬇ All in one file
              </button>
            </div>
          </div>
        </div>
      )}
        </>
      )}
    </div>
  )
}
