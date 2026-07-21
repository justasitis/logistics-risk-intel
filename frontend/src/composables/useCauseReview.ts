import { computed, reactive } from 'vue'
import type {
  CauseCandidate,
  CauseDecision,
  CauseDecisionRecord,
} from '@/types/causeAnalysis'

const state = reactive({
  decisions: {} as Record<
    string,
    CauseDecisionRecord | undefined
  >,
})

export function useCauseReview() {
  function decisionFor(
    candidateId: string,
  ): CauseDecision {
    return state.decisions[candidateId]?.decision
      ?? 'PENDING'
  }

  function setDecision(
    candidateId: string,
    decision: CauseDecision,
  ): void {
    state.decisions[candidateId] = {
      decision,
      updated_at: new Date().toISOString(),
    }
  }

  function applyDecision(
    candidate: CauseCandidate,
  ): CauseCandidate {
    return {
      ...candidate,
      decision: decisionFor(candidate.candidate_id),
    }
  }

  function clearDecisions(
    candidateIds?: string[],
  ): void {
    if (!candidateIds) {
      Object.keys(state.decisions).forEach((key) => {
        delete state.decisions[key]
      })
      return
    }

    candidateIds.forEach((candidateId) => {
      delete state.decisions[candidateId]
    })
  }

  const confirmedCount = computed(() =>
    Object.values(state.decisions).filter(
      (record) => record?.decision === 'CONFIRMED',
    ).length,
  )

  const excludedCount = computed(() =>
    Object.values(state.decisions).filter(
      (record) => record?.decision === 'EXCLUDED',
    ).length,
  )

  return {
    state,
    confirmedCount,
    excludedCount,
    decisionFor,
    setDecision,
    applyDecision,
    clearDecisions,
  }
}
