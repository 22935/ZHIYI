import { describe, expect, it } from 'vitest'
import {
  ACHIEVEMENTS, FEED_COOLDOWN_MS, MAX_LEVEL, PAT_COOLDOWN_MS, PET_STORAGE_KEY,
  applyPetAction, applyTimeDecay, createPetProfile, levelOf, levelProgress,
  loadPetProfile, localDateKey, moodOf, previousDateKey, sanitizePetProfile,
  savePetProfile, titleOf
} from './pet'

const at = (day: number, hour = 12): number => new Date(2026, 10, day, hour, 0, 0).getTime()
const rng = () => 0.42

describe('companion pet profile', () => {
  it('starts with bounded defaults and a local calendar day', () => {
    const profile = createPetProfile(at(6))
    expect(profile.affinity).toBe(0)
    expect(profile.energy).toBe(80)
    expect(profile.achievements).toEqual([])
    expect(localDateKey(at(6))).toBe('2026-11-06')
    expect(previousDateKey('2026-11-06')).toBe('2026-11-05')
    expect(previousDateKey('2026-03-01')).toBe('2026-02-28')
  })

  it('sanitizes hostile localStorage values instead of trusting them', () => {
    const profile = sanitizePetProfile({
      affinity: -999, energy: 1e9, totalPats: 'oops', streakDays: -4,
      lastActiveDate: 'not-a-date', achievements: ['chatty', 'fake', 'chatty', 7],
      lastPatAt: Number.NaN
    }, at(6))
    expect(profile.affinity).toBe(0)
    expect(profile.energy).toBe(100)
    expect(profile.totalPats).toBe(0)
    expect(profile.streakDays).toBe(0)
    expect(profile.lastActiveDate).toBe('')
    expect(profile.achievements).toEqual(['chatty'])
    expect(Number.isFinite(profile.lastPatAt)).toBe(true)
    expect(sanitizePetProfile(null, at(6)).energy).toBe(80)
  })

  it('maps affinity to levels, progress and titles with a hard cap', () => {
    expect(levelOf(0)).toBe(1)
    expect(levelOf(59)).toBe(1)
    expect(levelOf(60)).toBe(2)
    expect(levelOf(60 * 99)).toBe(MAX_LEVEL)
    expect(levelProgress(30)).toBeCloseTo(0.5)
    expect(levelProgress(60 * 99)).toBe(1)
    expect(titleOf(1)).toBe('初来乍到')
    expect(titleOf(MAX_LEVEL)).toBe('传说中的知宝')
  })

  it('decays energy by hours and only penalizes absence longer than two days', () => {
    const base = createPetProfile(at(1))
    const short = applyTimeDecay({ ...base, affinity: 40 }, at(1) + 90 * 60_000)
    expect(short.energy).toBe(76)
    expect(short.affinity).toBe(40)
    const long = applyTimeDecay({ ...base, affinity: 40 }, at(1) + 3 * 86_400_000)
    expect(long.energy).toBe(0)
    expect(long.affinity).toBe(36)
  })

  it('derives mood from state, energy, hour and recent interaction', () => {
    const fresh = createPetProfile(at(6))
    expect(moodOf(fresh, at(6))).toBe('excited')
    expect(moodOf(fresh, at(6), 'error')).toBe('concerned')
    expect(moodOf(fresh, at(6, 1))).toBe('sleepy')
    expect(moodOf({ ...fresh, energy: 10 }, at(6))).toBe('sleepy')
    expect(moodOf({ ...fresh, totalChats: 4, energy: 50 }, at(6) + 120_000, 'idle')).toBe('content')
  })
})

describe('companion pet interactions', () => {
  it('gives affinity for a pat and unlocks the first-meet achievement', () => {
    const result = applyPetAction(createPetProfile(at(6)), 'pat', at(6), rng)
    expect(result.gained).toBe(1)
    expect(result.profile.affinity).toBe(1)
    expect(result.profile.totalPats).toBe(1)
    expect(result.state).toBe('happy')
    expect(result.message).toContain('+1 好感')
    expect(result.unlocked.map(item => item.id)).toEqual(['first_meet'])
  })

  it('blocks rapid pat farming but still answers playfully', () => {
    const first = applyPetAction(createPetProfile(at(6)), 'pat', at(6), rng)
    const second = applyPetAction(first.profile, 'pat', at(6) + PAT_COOLDOWN_MS - 1, rng)
    expect(second.tone).toBe('cooldown')
    expect(second.gained).toBe(0)
    expect(second.profile.affinity).toBe(1)
    expect(second.profile.totalPats).toBe(2)
    expect(second.message).toContain('摸得太快')
    const later = applyPetAction(second.profile, 'pat', second.profile.lastPatAt + PAT_COOLDOWN_MS + 1, rng)
    expect(later.gained).toBe(1)
  })

  it('restores energy on feeding and spends energy on play, with cooldowns', () => {
    const base = { ...createPetProfile(at(6)), energy: 50 }
    const fed = applyPetAction(base, 'feed', at(6), rng)
    expect(fed.profile.energy).toBe(68)
    expect(fed.gained).toBe(4)
    const fedAgain = applyPetAction(fed.profile, 'feed', at(6) + FEED_COOLDOWN_MS - 1, rng)
    expect(fedAgain.tone).toBe('cooldown')
    expect(fedAgain.profile.energy).toBe(68)
    const played = applyPetAction(fedAgain.profile, 'play', at(6) + FEED_COOLDOWN_MS, rng)
    expect(played.profile.energy).toBe(56)
    expect(played.gained).toBe(5)
  })

  it('tracks consecutive days and resets after a gap', () => {
    const day1 = applyPetAction(createPetProfile(at(6)), 'visit', at(6), rng).profile
    expect(day1.streakDays).toBe(1)
    const sameDay = applyPetAction(day1, 'chat', at(6) + 3600_000, rng).profile
    expect(sameDay.streakDays).toBe(1)
    const day2 = applyPetAction(sameDay, 'visit', at(7), rng).profile
    expect(day2.streakDays).toBe(2)
    const day4 = applyPetAction(day2, 'visit', at(10), rng).profile
    expect(day4.streakDays).toBe(1)
  })

  it('unlocks night-owl, streak and chat achievements once each', () => {
    let profile = applyPetAction(createPetProfile(at(6, 1)), 'visit', at(6, 1), rng).profile
    expect(profile.achievements).toContain('night_owl')
    for (let i = 0; i < 9; i += 1) {
      profile = applyPetAction(profile, 'chat', at(6) + i * 1000, rng).profile
    }
    expect(profile.totalChats).toBe(9)
    const tenth = applyPetAction(profile, 'chat', at(6) + 20_000, rng)
    expect(tenth.profile.totalChats).toBe(10)
    expect(tenth.unlocked.map(item => item.id)).toContain('chatty')
    expect(tenth.profile.achievements.filter(id => id === 'chatty')).toHaveLength(1)
    expect(ACHIEVEMENTS.every(item => item.label && item.description)).toBe(true)
  })

  it('never grows affinity past the level cap', () => {
    const maxed = { ...createPetProfile(at(6)), affinity: 60 * MAX_LEVEL }
    const result = applyPetAction(maxed, 'feed', at(6), rng)
    expect(result.profile.affinity).toBe(60 * MAX_LEVEL)
  })
})

describe('companion pet persistence', () => {
  it('round-trips through storage and survives malformed JSON', () => {
    const map = new Map<string, string>()
    const storage = {
      getItem: (key: string) => map.get(key) ?? null,
      setItem: (key: string, value: string) => { map.set(key, value) }
    }
    const profile = applyPetAction(createPetProfile(at(6)), 'pat', at(6), rng).profile
    savePetProfile(storage, profile)
    expect(map.has(PET_STORAGE_KEY)).toBe(true)
    expect(loadPetProfile(storage, at(6)).totalPats).toBe(1)
    map.set(PET_STORAGE_KEY, '{broken')
    expect(loadPetProfile(storage, at(6)).totalPats).toBe(0)
    expect(loadPetProfile(null, at(6)).energy).toBe(80)
  })
})
