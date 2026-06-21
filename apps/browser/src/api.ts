const API_BASE = import.meta.env.VITE_ROUTELY_API_URL ?? '';

export type ChatMessage = { role: 'user' | 'assistant'; content: string };

export type ChatResponse = {
  answer: string;
  brain_used: string;
  powered_by: string;
  collaborative: boolean;
  confidence: number;
  thread_id?: string;
};

export async function sendChat(
  message: string,
  apiKey: string,
  threadId?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/v1/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ message, thread_id: threadId, work_mode: 'auto' }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}
