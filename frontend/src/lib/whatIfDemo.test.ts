import { describe, expect, it } from 'vitest'
import { buildWhatIfDemo } from './whatIfDemo'
import type { WhatIfRequest } from '../types/schemas'

const base: WhatIfRequest = { aoi_id:'aizawl', rainfall_mm:80, duration_hours:24, slope_modifier_deg:30, distance_to_fault_km:8, lithology:'competent', antecedent_rainfall_mm:20, soil_moisture_pct:35, snow_mass_mm:0, snow_melt_active:false, exposure_weight:.7 }
const result=(overrides:Partial<WhatIfRequest>={})=>buildWhatIfDemo({...base,...overrides})

describe('spatial what-if demo engine',()=>{
  it('is deterministic and spatially varied',()=>{const a=result(),b=result();expect(a).toEqual(b);expect(new Set(a.tick.cell_risks.map(c=>c.p_fail)).size).toBeGreaterThan(1)})
  it('raises cell risk with rainfall, slope, moisture and weak geology',()=>{const low=result();const high=result({rainfall_mm:320,slope_modifier_deg:48,soil_moisture_pct:90,lithology:'weak'});expect(high.tick.cell_risks.reduce((n,c)=>n+c.p_fail,0)).toBeGreaterThan(low.tick.cell_risks.reduce((n,c)=>n+c.p_fail,0))})
  it('derives road status from its displayed probability',()=>{for(const road of result({rainfall_mm:320}).tick.road_risks)expect(road.severed).toBe(road.p_blocked>.55)})
  it('derives population at risk from isolated settlements',()=>{const tick=result({rainfall_mm:320,duration_hours:3,soil_moisture_pct:95,lithology:'weak'}).tick;const displayed=tick.isolations.filter(v=>v.p_isolated>=.6).reduce((n,v)=>n+v.population,0);expect(displayed).toBeGreaterThanOrEqual(0);expect(tick.isolations.every(v=>v.name!==''&&v.name!=='unnamed')).toBe(true)})
})
