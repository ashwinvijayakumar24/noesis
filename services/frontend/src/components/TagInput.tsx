import { useState, useEffect, useRef } from 'react'
import { XMarkIcon, PlusIcon, TagIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

interface Tag {
  id: string
  tag_name: string
  tag_color: string
}

interface TagSuggestion {
  name: string
  color: string
}

interface TagInputProps {
  projectId: string
  initialTags?: Tag[]
  suggestions?: TagSuggestion[]
  onTagsChange?: (tags: Tag[]) => void
}

export default function TagInput({
  projectId,
  initialTags,
  suggestions: providedSuggestions,
  onTagsChange,
}: TagInputProps) {
  const { session } = useAuthStore()
  const [tags, setTags] = useState<Tag[]>([])
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>([])
  const [inputValue, setInputValue] = useState('')
  const [showInput, setShowInput] = useState(false)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Load tags for this project
  useEffect(() => {
    if (session?.access_token) {
      if (initialTags) {
        setTags(initialTags)
      } else {
        loadTags()
      }

      if (providedSuggestions) {
        setSuggestions(providedSuggestions)
      } else {
        loadSuggestions()
      }
    }
  }, [projectId, session, initialTags, providedSuggestions])

  // Focus input when it's shown
  useEffect(() => {
    if (showInput && inputRef.current) {
      inputRef.current.focus()
    }
  }, [showInput])

  const loadTags = async () => {
    if (!session?.access_token) return

    try {
      const data = await api.tags.getProjectTags(session.access_token, projectId)
      setTags(data)
      onTagsChange?.(data)
    } catch (error) {
      console.error('Failed to load tags:', error)
    }
  }

  const loadSuggestions = async () => {
    if (!session?.access_token) return

    try {
      const data = await api.tags.getSuggestions(session.access_token)
      setSuggestions(data)
    } catch (error) {
      console.error('Failed to load tag suggestions:', error)
    }
  }

  const addTag = async (tagName: string) => {
    if (!session?.access_token || !tagName.trim()) return

    const normalizedTag = tagName.trim().toLowerCase()

    // Check if already exists
    if (tags.some(t => t.tag_name === normalizedTag)) {
      toast.error('Tag already exists on this project')
      return
    }

    // Check max limit
    if (tags.length >= 5) {
      toast.error('Maximum 5 tags per project')
      return
    }

    try {
      setLoading(true)
      const newTag = await api.tags.addTag(session.access_token, projectId, normalizedTag)
      const nextTags = [...tags, newTag]
      setTags(nextTags)
      setInputValue('')
      setShowInput(false)
      onTagsChange?.(nextTags)
      toast.success('Tag added')
    } catch (error: any) {
      console.error('Failed to add tag:', error)
      toast.error(error.message || 'Failed to add tag')
    } finally {
      setLoading(false)
    }
  }

  const removeTag = async (tagId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!session?.access_token) return

    try {
      await api.tags.removeTag(session.access_token, projectId, tagId)
      const nextTags = tags.filter((tag) => tag.id !== tagId)
      setTags(nextTags)
      onTagsChange?.(nextTags)
      toast.success('Tag removed')
    } catch (error) {
      console.error('Failed to remove tag:', error)
      toast.error('Failed to remove tag')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault()
      addTag(inputValue)
    } else if (e.key === 'Escape') {
      setInputValue('')
      setShowInput(false)
    }
  }

  // Filter suggestions based on input
  const filteredSuggestions = suggestions.filter(
    s =>
      s.name.toLowerCase().includes(inputValue.toLowerCase()) &&
      !tags.some(t => t.tag_name === s.name)
  ).slice(0, 5)

  // Map color names to Tailwind classes
  const getColorClasses = (color: string) => {
    const colorMap: Record<string, { bg: string; text: string; border: string }> = {
      'red-500': { bg: 'bg-red-500/20', text: 'text-red-300', border: 'border-red-500/50' },
      'orange-500': { bg: 'bg-orange-500/20', text: 'text-orange-300', border: 'border-orange-500/50' },
      'yellow-500': { bg: 'bg-yellow-500/20', text: 'text-yellow-300', border: 'border-yellow-500/50' },
      'green-500': { bg: 'bg-green-500/20', text: 'text-green-300', border: 'border-green-500/50' },
      'blue-500': { bg: 'bg-blue-500/20', text: 'text-blue-300', border: 'border-blue-500/50' },
      'purple-500': { bg: 'bg-purple-500/20', text: 'text-purple-300', border: 'border-purple-500/50' },
      'pink-500': { bg: 'bg-pink-500/20', text: 'text-pink-300', border: 'border-pink-500/50' },
      'cyan-500': { bg: 'bg-cyan-500/20', text: 'text-cyan-300', border: 'border-cyan-500/50' },
      'indigo-500': { bg: 'bg-indigo-500/20', text: 'text-indigo-300', border: 'border-indigo-500/50' },
      'rose-500': { bg: 'bg-rose-500/20', text: 'text-rose-300', border: 'border-rose-500/50' },
    }
    return colorMap[color] || colorMap['gray-500']
  }

  return (
    <div className="flex flex-wrap gap-1.5 items-center" onClick={(e) => e.stopPropagation()}>
      {/* Existing tags */}
      {tags.map((tag) => {
        const colors = getColorClasses(tag.tag_color)
        return (
          <span
            key={tag.id}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${colors.bg} ${colors.text} border ${colors.border}`}
          >
            <TagIcon className="h-3 w-3" />
            {tag.tag_name}
            <button
              onClick={(e) => removeTag(tag.id, e)}
              className="hover:text-white transition"
            >
              <XMarkIcon className="h-3 w-3" />
            </button>
          </span>
        )
      })}

      {/* Add tag button or input */}
      {!showInput && tags.length < 5 && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            setShowInput(true)
          }}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs text-text-tertiary hover:text-text-secondary border border-dashed border-border-subtle hover:border-border-base transition"
        >
          <PlusIcon className="h-3 w-3" />
          Add tag
        </button>
      )}

      {showInput && (
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              setTimeout(() => {
                setShowInput(false)
                setInputValue('')
              }, 200)
            }}
            placeholder="Type tag name..."
            disabled={loading}
            className="w-32 px-2 py-0.5 text-xs bg-surface-hover border border-border-base rounded-md text-text-primary placeholder-text-muted focus:outline-none focus:border-pink-500"
          />

          {/* Suggestions dropdown */}
          {inputValue && filteredSuggestions.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-40 bg-surface-hover border border-border-base rounded-md shadow-lg z-10 max-h-40 overflow-y-auto">
              {filteredSuggestions.map((suggestion) => {
                const colors = getColorClasses(suggestion.color)
                return (
                  <button
                    key={suggestion.name}
                    onClick={(e) => {
                      e.stopPropagation()
                      addTag(suggestion.name)
                    }}
                    className="w-full px-3 py-2 text-xs text-left text-text-secondary hover:bg-surface-active flex items-center gap-2"
                  >
                    <span className={`w-2 h-2 rounded-full ${colors.bg.replace('/20', '')}`} />
                    {suggestion.name}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
