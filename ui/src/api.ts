export type Story = { title: string; themes: string[]; buildable_objects: string[]; vocabulary_opportunities: string[]; key_events: string[] };
export type Lesson = {
  session_id: string; phase: string; revision?: number;
  storybook_text?: string;
  storybook_analysis?: Story;
  teacher_messages: {role: string; content: string}[];
  planning_state: Record<string, unknown>;
  build_constraints?: {max_validated_blocks?:number;max_semantic_segments?:number};
  rag_status: string;
  connector_review?: {job_id?: string;notes?: string};
  model_preview_job_id?: string; segment_job_id?: string; document_job_id?: string;
};
export type Job = { job_id: string; status: string; stage: string; progress: number; message: string; retryable?: boolean; result?: Record<string, unknown>; events: {at:string;stage:string;message:string}[] };

export async function request<T>(path: string, data?: unknown): Promise<T> {
  const form = data instanceof FormData;
  const result = await fetch(`/api/v1${path}`, {
    method: data === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: data === undefined ? {} : { 'X-KidSpark-Request': '1', ...(form ? {} : {'Content-Type': 'application/json'}) },
    body: data === undefined ? undefined : form ? data : JSON.stringify(data),
  });
  if (!result.ok) {
    const error = await result.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'This request could not be completed. Please try again.');
  }
  return result.json();
}
