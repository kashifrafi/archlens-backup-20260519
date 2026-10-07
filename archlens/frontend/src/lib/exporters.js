import * as XLSX from 'xlsx'

const STAMP = () => new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')

function autoFit(ws, rows) {
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  ws['!cols'] = cols.map((c) => {
    const maxLen = Math.max(c.length, ...rows.map((r) => String(r[c] ?? '').length))
    return { wch: Math.min(Math.max(maxLen + 2, 10), 60) }
  })
}

function addSheet(wb, name, rows) {
  const ws = XLSX.utils.json_to_sheet(rows)
  autoFit(ws, rows)
  XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31))
}

function safeName(name) {
  return (name || 'architecture').toString().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'architecture'
}

/* ---------------- WAF ---------------- */
export function exportWAFToExcel(wafData, archName) {
  if (!wafData?.length) return
  const wb = XLSX.utils.book_new()

  const summary = wafData.map((r) => ({
    Cloud: r.cloud.toUpperCase(),
    'Overall Score': r.overall_score,
    Status: r.overall_status,
    Summary: r.summary,
    'Critical Gaps': (r.critical_gaps || []).join(' | '),
  }))
  addSheet(wb, 'Summary', summary)

  for (const r of wafData) {
    const rows = []
    for (const p of r.pillars || []) {
      const findings = p.findings || []
      const recs = p.recommendations || []
      const max = Math.max(1, findings.length, recs.length)
      for (let i = 0; i < max; i++) {
        rows.push({
          Pillar: i === 0 ? p.pillar : '',
          Score: i === 0 ? p.score : '',
          Status: i === 0 ? p.status : '',
          Finding: findings[i] || '',
          Recommendation: recs[i] || '',
        })
      }
    }
    addSheet(wb, `${r.cloud.toUpperCase()} Details`, rows)
  }

  XLSX.writeFile(wb, `archlens-waf-${safeName(archName)}-${STAMP()}.xlsx`)
}

/* -------------- Pricing -------------- */
export function exportPricingToExcel(pricingData, archName) {
  if (!pricingData) return
  const clouds = ['aws', 'azure', 'gcp']
    .map((c) => pricingData[c])
    .filter(Boolean)
  if (!clouds.length) return

  const wb = XLSX.utils.book_new()

  const summary = clouds.map((e) => ({
    Cloud: e.cloud.toUpperCase(),
    Region: e.region,
    'Monthly (USD)': Math.round(e.monthly_estimate),
    'Annual (USD)': Math.round(e.annual_estimate),
    Services: e.breakdown?.length || 0,
    Cheapest: pricingData.cheapest === e.cloud ? 'Yes' : '',
  }))
  addSheet(wb, 'Summary', summary)

  if (pricingData.recommendation) {
    addSheet(wb, 'Recommendation', [
      { Section: 'AI Recommendation', Text: pricingData.recommendation },
    ])
  }

  for (const e of clouds) {
    const rows = (e.breakdown || []).map((b) => ({
      Service: b.service,
      Component: b.component,
      Quantity: b.quantity,
      'Unit Price (USD)': b.unit_price,
      'Monthly Cost (USD)': Number((b.monthly_cost || 0).toFixed(2)),
      Notes: b.notes || '',
    }))
    addSheet(wb, `${e.cloud.toUpperCase()} Breakdown`, rows)

    if (e.assumptions?.length) {
      addSheet(
        wb,
        `${e.cloud.toUpperCase()} Assumptions`,
        e.assumptions.map((a, i) => ({ '#': i + 1, Assumption: a })),
      )
    }
  }

  // Cross-cloud side-by-side
  const services = new Set()
  clouds.forEach((c) => c.breakdown?.forEach((b) => services.add(b.service)))
  const compare = [...services].map((svc) => {
    const row = { Service: svc }
    for (const c of clouds) {
      const found = c.breakdown?.filter((b) => b.service === svc) || []
      row[`${c.cloud.toUpperCase()} ($/mo)`] = Number(
        found.reduce((s, b) => s + (b.monthly_cost || 0), 0).toFixed(2),
      )
    }
    return row
  })
  addSheet(wb, 'Cross-Cloud Comparison', compare)

  XLSX.writeFile(wb, `archlens-pricing-${safeName(archName)}-${STAMP()}.xlsx`)
}
