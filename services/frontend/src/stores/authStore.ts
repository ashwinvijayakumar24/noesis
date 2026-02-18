import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { supabase } from '../lib/supabase'
import type { User, Session } from '@supabase/supabase-js'
import { analytics } from '../lib/analytics'

interface AuthState {
  user: User | null
  session: Session | null
  loading: boolean
  initialized: boolean

  // Actions
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  initialize: () => Promise<void>
  setSession: (session: Session) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, _get) => ({
      user: null,
      session: null,
      loading: false,
      initialized: false,

      signIn: async (email: string, password: string) => {
        set({ loading: true })
        try {
          const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password,
          })

          if (error) throw error

          // Set analytics auth token
          if (data.session?.access_token) {
            analytics.setAuthToken(data.session.access_token)
          }

          set({
            user: data.user,
            session: data.session,
            loading: false,
          })
        } catch (error) {
          set({ loading: false })
          throw error
        }
      },

      signUp: async (email: string, password: string) => {
        set({ loading: true })
        try {
          const { data, error } = await supabase.auth.signUp({
            email,
            password,
            options: {
              emailRedirectTo: `${window.location.origin}/auth/callback`
            }
          })

          if (error) throw error

          // Set analytics auth token
          if (data.session?.access_token) {
            analytics.setAuthToken(data.session.access_token)
          }

          set({
            user: data.user,
            session: data.session,
            loading: false,
          })
        } catch (error) {
          set({ loading: false })
          throw error
        }
      },

      signOut: async () => {
        set({ loading: true })
        try {
          const { error } = await supabase.auth.signOut()
          if (error) throw error

          // Clear analytics auth token
          analytics.setAuthToken(null)

          set({
            user: null,
            session: null,
            loading: false,
          })
        } catch (error) {
          set({ loading: false })
          throw error
        }
      },

      initialize: async () => {
        try {
          // Get current session
          const { data: { session } } = await supabase.auth.getSession()

          // Set analytics auth token if session exists
          if (session?.access_token) {
            analytics.setAuthToken(session.access_token)
          }

          set({
            user: session?.user ?? null,
            session: session,
            initialized: true,
          })

          // Listen for auth changes
          supabase.auth.onAuthStateChange((_event, session) => {
            // Update analytics auth token on auth changes
            if (session?.access_token) {
              analytics.setAuthToken(session.access_token)
            } else {
              analytics.setAuthToken(null)
            }

            set({
              user: session?.user ?? null,
              session: session,
            })
          })
        } catch (error) {
          console.error('Failed to initialize auth:', error)
          set({ initialized: true })
        }
      },

      setSession: (session: Session) => {
        // Set analytics auth token
        if (session?.access_token) {
          analytics.setAuthToken(session.access_token)
        }

        set({
          user: session?.user ?? null,
          session: session,
          loading: false,
        })
      },
    }),
    {
      name: 'noesis-auth',
      partialize: (state) => ({
        // Only persist session, not user or loading states
        session: state.session,
      }),
    }
  )
)
