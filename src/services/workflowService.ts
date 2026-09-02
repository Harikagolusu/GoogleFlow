import type { Workflow, ChecklistItem } from '../types/workflow';
import type { Service } from '../types/service';
import { mockWorkflows, mockServices } from '../data/mockWorkflows';
import { apiGet, apiPatch, apiPost } from './http';
import { authService } from './authService';

// In-memory copy of the seed workflows (demo data + checklist toggles).
let currentWorkflows: Workflow[] = [...mockWorkflows];
// Backend-persisted workflows (Firestore via FastAPI), cached locally so
// pages can toggle checklists without a round-trip.
let generatedWorkflows: Workflow[] = [];

function allWorkflows(): Workflow[] {
  return [...currentWorkflows, ...generatedWorkflows];
}

function cacheGenerated(workflow: Workflow): void {
  generatedWorkflows = [
    ...generatedWorkflows.filter(w => w.id !== workflow.id),
    workflow,
  ];
}

/** True when the user is signed in with Google (Firebase Auth enabled). */
function isUserAuthenticated(): boolean {
  return authService.isAvailable() && Boolean(authService.getCurrentUser());
}

/** Authorization header for protected backend calls (empty in demo mode). */
async function authHeaders(): Promise<Record<string, string>> {
  const token = await authService.getIdToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function toggleIn(workflow: Workflow, itemId: string): Workflow {
  const updatedChecklist: ChecklistItem[] = workflow.checklist.map(item =>
    item.id === itemId ? { ...item, completed: !item.completed } : item,
  );
  const completedCount = updatedChecklist.filter(i => i.completed).length;
  const readiness = Math.round((completedCount / updatedChecklist.length) * 100);
  const nextItem = updatedChecklist.find(i => !i.completed);

  return {
    ...workflow,
    checklist: updatedChecklist,
    readiness,
    nextUp: nextItem?.title,
    status: readiness === 100 ? 'Completed' : readiness > 0 ? 'In Progress' : 'Action Needed',
  };
}

export const workflowService = {
  async getWorkflows(): Promise<Workflow[]> {
    // Authenticated: the user's real workflows from Firestore (via FastAPI)
    // are the source of truth. Demo data is shown only when signed out.
    if (isUserAuthenticated()) {
      try {
        const headers = await authHeaders();
        const userWorkflows = await apiGet<Workflow[]>('/api/workflows', { headers });
        generatedWorkflows = [...userWorkflows].reverse();
        return allWorkflows();
      } catch {
        return allWorkflows();
      }
    }

    // Signed out / demo mode: local demo data merged with anything the demo
    // backend generated this session. Frontend state wins for known ids.
    const local = allWorkflows();
    try {
      const backend = await apiGet<Workflow[]>('/api/workflows');
      const byId = new Map<string, Workflow>();
      for (const w of local) byId.set(w.id, w);
      for (const b of backend) {
        if (!byId.has(b.id)) byId.set(b.id, b);
      }
      const merged = [...byId.values()];
      const mockIds = new Set(currentWorkflows.map(w => w.id));
      generatedWorkflows = merged.filter(w => !mockIds.has(w.id));
      return merged;
    } catch {
      return local;
    }
  },

  async getWorkflowById(id: string): Promise<Workflow | undefined> {
    // 1) Cached copy covers the 3 demo workflows and any workflow already
    //    fetched this session.
    const cached = allWorkflows().find(w => w.id === id);
    if (cached) return cached;

    // 2) Fall back to the backend (Firestore), scoped to the signed-in user.
    try {
      const headers = await authHeaders();
      const fetched = await apiGet<Workflow>(`/api/workflows/${id}`, { headers });
      cacheGenerated(fetched);
      return fetched;
    } catch {
      return undefined;
    }
  },

  async toggleChecklistItem(workflowId: string, itemId: string): Promise<Workflow> {
    const target = allWorkflows().find(w => w.id === workflowId);
    if (!target) throw new Error('Workflow not found');
    const optimistic = toggleIn(target, itemId);
    const isDemoWorkflow = currentWorkflows.some(w => w.id === workflowId);

    // Persisted workflows: recompute + save on the backend (Firestore).
    if (!isDemoWorkflow && isUserAuthenticated()) {
      try {
        const headers = await authHeaders();
        const completed =
          optimistic.checklist.find(item => item.id === itemId)?.completed ?? false;
        const updated = await apiPatch<Workflow>(
          `/api/workflows/${workflowId}/checklist/${itemId}`,
          { completed },
          { headers },
        );
        cacheGenerated(updated);
        return updated;
      } catch {
        // Network hiccup — keep the optimistic local update.
      }
    }

    if (isDemoWorkflow) {
      currentWorkflows = currentWorkflows.map(w => (w.id === workflowId ? optimistic : w));
    } else {
      generatedWorkflows = generatedWorkflows.map(w => (w.id === workflowId ? optimistic : w));
    }
    return optimistic;
  },

  async ask(query: string): Promise<Workflow> {
    // Single data-access path:
    // Ask.tsx -> this -> http.ts (+ Firebase ID token) -> FastAPI -> Gemini
    // -> Firestore (when signed in).
    const headers = await authHeaders();
    const workflow = await apiPost<Workflow>('/api/ask', { query }, { headers });
    cacheGenerated(workflow);
    return workflow;
  },

  async getServices(): Promise<Service[]> {
    return Promise.resolve(mockServices);
  },

  async getServiceByName(name: string): Promise<Service | undefined> {
    // Normalize both sides so canonical names from generated workflows
    // ("Google Drive") resolve to the seeded service ("Drive").
    const normalize = (value: string) =>
      value.toLowerCase().replace(/^google\s+/, '').replace(/\s+/g, ' ').trim();
    return Promise.resolve(
      mockServices.find(s => normalize(s.name) === normalize(name)),
    );
  },
};
