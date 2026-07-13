/** AI Assistant / Chat page — Phase 9 frontend */
import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Loader2, Sparkles } from 'lucide-react'
import { chatApi } from '@/api/client'
import { clsx } from 'clsx'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  contextUsed?: boolean
}

const SUGGESTED_QUESTIONS = [
  'How much did I spend on dining last month?',
  'Am I on track for my savings goal?',
  'What are my top spending categories?',
  'How does my spending compare to my income?',
  'Where can I cut costs to save more?',
]

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '0',
      role: 'assistant',
      content: 'Hi! I\'m your FinScope AI assistant. I can answer questions about your finances, spending patterns, and savings goals using your actual transaction data. What would you like to know?',
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const { data } = await chatApi.send(text)
      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.answer,
        timestamp: new Date(data.timestamp),
        contextUsed: data.context_used,
      }
      setMessages((prev) => [...prev, botMsg])
    } catch {
      setMessages((prev) => [...prev, {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-400 to-violet-500 flex items-center justify-center">
          <Sparkles className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">FinScope Assistant</h1>
          <p className="text-sm text-gray-400">AI-powered answers about your finances</p>
        </div>
      </div>

      {/* Chat window */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        {messages.map((msg) => (
          <div key={msg.id} className={clsx('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
            {/* Avatar */}
            <div className={clsx('w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
              msg.role === 'user' ? 'bg-brand-500/30' : 'bg-violet-500/30'
            )}>
              {msg.role === 'user' ? <User className="h-4 w-4 text-brand-300" /> : <Bot className="h-4 w-4 text-violet-300" />}
            </div>

            {/* Bubble */}
            <div className={clsx('max-w-[75%] rounded-2xl px-4 py-3',
              msg.role === 'user'
                ? 'bg-brand-500/20 border border-brand-500/30 text-white'
                : 'glass text-gray-100'
            )}>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              <div className="flex items-center gap-2 mt-2">
                <span className="text-xs text-gray-600">
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
                {msg.contextUsed && (
                  <span className="text-xs text-brand-400/70">📊 Used your data</span>
                )}
              </div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-violet-500/30 flex items-center justify-center flex-shrink-0">
              <Bot className="h-4 w-4 text-violet-300" />
            </div>
            <div className="glass rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 text-brand-400 animate-spin" />
                <span className="text-sm text-gray-400">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {messages.length === 1 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-xs px-3 py-1.5 glass rounded-full text-gray-400 hover:text-white glass-hover transition-all"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="flex gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage(input)}
          placeholder="Ask anything about your finances..."
          className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500 transition-colors text-sm"
          disabled={loading}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className="w-12 h-12 bg-gradient-to-br from-brand-500 to-violet-600 rounded-xl flex items-center justify-center hover:from-brand-400 hover:to-violet-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="h-4 w-4 text-white" />
        </button>
      </div>
    </div>
  )
}
