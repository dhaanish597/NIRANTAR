import type { Geometry } from 'geojson'
import type { CommanderChatResponse, CommanderIntent, CommanderResponseBlock, CommanderRoute, CommanderStructuredResponse, RoadSegmentRisk, SettlementPriority, VillageIsolation, EvacuationRoute } from '../types/schemas'

const lower = (value: string) => value.toLowerCase()

export function commanderIntent(message: string): CommanderIntent {
  const q = lower(message)
  if (q.includes('route') || q.includes('path') || q.includes('evacuat')) return 'SAFE_ROUTE'
  if (q.includes('road') || q.includes('cut off') || q.includes('isolat')) return 'ROAD_ISOLATION'
  if (q.includes('shelter') || q.includes('evacuate')) return 'SHELTERS'
  if (q.includes('announce') || q.includes('alert') || q.includes('warning')) return 'ANNOUNCEMENT'
  if (q.includes('village') || q.includes('danger')) return 'HIGH_RISK_VILLAGES'
  if (q.includes('why') || q.includes('risk high')) return 'EXPLAIN_RISK'
  return 'GENERAL'
}

const riskLevel = (score: number) => score >= .8 ? 'CRITICAL' : score >= .6 ? 'HIGH' : score >= .35 ? 'ELEVATED' : 'NORMAL'

function mapBlock(routeGeometry: Geometry | null = null): CommanderResponseBlock {
  return { type: 'map', data: { routeGeometry } }
}

function routeBlocks(routes: CommanderRoute[]): CommanderResponseBlock[] {
  return routes.map((item) => ({ type: 'route', data: { ...item } }))
}

export function structuredFromLive(response: CommanderChatResponse, message: string, priorities: SettlementPriority[] = [], roads: RoadSegmentRisk[] = [], isolations: VillageIsolation[] = [], shelters: EvacuationRoute[] = []): CommanderStructuredResponse {
  const intent = commanderIntent(message)
  const blocks: CommanderResponseBlock[] = [{ type: 'text', data: { text: response.answer } }]
  if (intent === 'SAFE_ROUTE' && response.routes.length) {
    blocks.push(mapBlock(response.routes[0].route.geometry), ...routeBlocks(response.routes))
  } else if (intent === 'HIGH_RISK_VILLAGES' || intent === 'EXPLAIN_RISK') blocks.push({ type: 'risk', data: { priorities } })
  else if (intent === 'ROAD_ISOLATION') blocks.push({ type: 'road', data: { roads, isolations } }, mapBlock())
  else if (intent === 'SHELTERS') blocks.push(mapBlock(shelters[0]?.geometry ?? null), { type: 'shelter', data: { shelters } })
  return { type: 'commander_response', intent, summary: response.answer, blocks, source: response.source }
}

export function demoResponse(message: string, priorities: SettlementPriority[], roads: RoadSegmentRisk[], isolations: VillageIsolation[], routes: CommanderRoute[], shelters: EvacuationRoute[]): CommanderStructuredResponse {
  const intent = commanderIntent(message)
  const top = priorities[0]
  const blocks: CommanderResponseBlock[] = []
  if (intent === 'SAFE_ROUTE') {
    blocks.push({ type: 'text', data: { text: routes.length ? 'I found the safest verified movement option in the current simulation snapshot. The recommended route avoids exposed segments and ends at the nearest available shelter.' : 'No verified route is available in the current snapshot. An authorised officer should confirm movement before issuing guidance.' } })
    if (routes[0]) blocks.push(mapBlock(routes[0].route.geometry), ...routeBlocks(routes), { type: 'evidence', data: { title: 'Why this route', factors: routes[0].risk_snapshot, confidence: 'Verified route snapshot' } })
  } else if (intent === 'HIGH_RISK_VILLAGES' || intent === 'EXPLAIN_RISK') {
    blocks.push({ type: 'text', data: { text: top ? `The highest priority settlement in this simulation snapshot is ${top.village_id}. Risk is driven by the verified decision-pipeline signals below.` : 'The verified priority feed is still loading.' } })
    blocks.push({ type: 'risk', data: { priorities } })
    if (top) blocks.push({ type: 'evidence', data: { title: `Risk evidence · ${top.village_id}`, factors: Object.entries(top.components).slice(0, 5).map(([name, value]) => `${name.replaceAll('_', ' ')} · ${Math.round(value * 100)}% contribution`), confidence: 'Pipeline confidence available in live feed' } })
  } else if (intent === 'ROAD_ISOLATION') {
    blocks.push({ type: 'text', data: { text: 'These road segments have the highest connectivity impact in the current simulation snapshot. Review the affected villages before selecting a movement plan.' } }, { type: 'road', data: { roads, isolations } }, mapBlock())
  } else if (intent === 'SHELTERS') {
    blocks.push({ type: 'text', data: { text: 'Available destinations are drawn from verified evacuation routes. Capacity is only shown when supplied by the current data feed.' } }, mapBlock(shelters[0]?.geometry ?? null), { type: 'shelter', data: { shelters } })
  } else if (intent === 'ANNOUNCEMENT') {
    blocks.push({ type: 'text', data: { text: 'A village-level alert is recommended for officer review. This is a proposal only; nothing will be published automatically.' } }, { type: 'action', data: { title: 'Recommended next step', text: top ? `Prepare an announcement for ${top.village_id}.` : 'Wait for a verified priority feed before drafting an alert.' } })
  } else {
    blocks.push({ type: 'text', data: { text: 'I can help inspect priority villages, road isolation, verified routes, shelters, risk evidence, or prepare an announcement for review.' } })
  }
  return { type: 'commander_response', intent, summary: blocks[0]?.data.text as string, blocks, source: 'fallback' }
}

export { riskLevel }
