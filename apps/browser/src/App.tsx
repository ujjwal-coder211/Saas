import { useCallback, useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { ChatMessage, checkHealth, sendChat } from './api';

const API_KEY_STORAGE = 'routely_api_key';
const THREAD_STORAGE = 'routely_thread_id';

export default function App() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem(API_KEY_STORAGE) ?? '');
  const [threadId, setThreadId] = useState(() => localStorage.getItem(THREAD_STORAGE) ?? '');
  const [code, setCode] = useState('// Ask Routely to write or fix code\n');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    checkHealth().then(setOnline);
  }, []);

  const onSaveKey = useCallback(() => {
    localStorage.setItem(API_KEY_STORAGE, apiKey.trim());
  }, [apiKey]);

  const onSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    if (!apiKey.trim()) {
      setError('Add your Routely API key first.');
      return;
    }
    setError('');
    setLoading(true);
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setInput('');
    try {
      const fileContext = code.length < 12000 ? `Current file:\n\`\`\`\n${code}\n\`\`\`` : undefined;
      const res = await sendChat(
        fileContext ? `${text}\n\n${fileContext}` : text,
        apiKey.trim(),
        threadId || undefined,
      );
      if (res.thread_id) {
        setThreadId(res.thread_id);
        localStorage.setItem(THREAD_STORAGE, res.thread_id);
      }
      setMessages((m) => [...m, { role: 'assistant', content: res.answer }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [apiKey, code, input, loading, threadId]);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo">Routely</span>
          <span className="tag">AI coding · best free model per task</span>
        </div>
        <div className="status">
          {online === null ? '…' : online ? 'API online' : 'API offline'}
        </div>
      </header>

      <div className="main">
        <section className="editor-pane">
          <div className="pane-title">Editor</div>
          <Editor
            height="100%"
            defaultLanguage="typescript"
            theme="vs-dark"
            value={code}
            onChange={(v) => setCode(v ?? '')}
            options={{ fontSize: 14, minimap: { enabled: false } }}
          />
        </section>

        <section className="chat-pane">
          <div className="pane-title">Chat</div>
          <div className="key-row">
            <input
              type="password"
              placeholder="API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onBlur={onSaveKey}
            />
            <button type="button" onClick={onSaveKey}>
              Save
            </button>
          </div>
          <div className="messages">
            {messages.length === 0 && (
              <p className="hint">Describe what to build or fix. Routely picks the best free model.</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>
                <strong>{m.role === 'user' ? 'You' : 'Routely'}</strong>
                <pre>{m.content}</pre>
              </div>
            ))}
            {loading && <p className="hint">Routely is thinking…</p>}
          </div>
          {error && <p className="error">{error}</p>}
          <div className="composer">
            <textarea
              rows={3}
              placeholder="Fix this bug, add a login API, refactor this file…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void onSend();
                }
              }}
            />
            <button type="button" disabled={loading} onClick={() => void onSend()}>
              Send
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
