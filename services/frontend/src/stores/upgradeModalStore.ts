import { create } from 'zustand'

interface UpgradeModalState {
  isOpen: boolean
  quotaType: 'drafts' | 'documents' | 'chat_messages' | 'paper_discovery' | null
  limitMessage: string | null
  open: (quotaType: UpgradeModalState['quotaType'], message?: string) => void
  close: () => void
}

export const useUpgradeModalStore = create<UpgradeModalState>((set) => ({
  isOpen: false,
  quotaType: null,
  limitMessage: null,
  open: (quotaType, message) => set({ isOpen: true, quotaType, limitMessage: message ?? null }),
  close: () => set({ isOpen: false, quotaType: null, limitMessage: null }),
}))
