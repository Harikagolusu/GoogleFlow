import type { Workflow, ChecklistItem, WorkflowDetail } from '../types/workflow';
import type { Service } from '../types/service';
import { mockWorkflows, mockServices } from '../data/mockWorkflows';
import { apiGet, apiPatch, apiPost } from './http';
import { authService } from './authService';

// Demo workflows — ONLY used when Firebase auth is not configured (demo mode).
const demoWorkflows: Workflow[] = [...mockWorkflows];

// Backend-persisted workflows (Firestore via FastAPI), cached locally so
// pages can toggle checklists without a round-trip.
let generatedWorkflows: Workflow[] = [];

function isUserAuthenticated(): boolean {
  return authService.isAvailable() && Boolean(authService.getCurrentUser());
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await authService.waitForToken();
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

export interface AnalyzeResult {
  success: boolean;
  emailsAnalyzed: number;
  flowsCreated: number;
  flowsUpdated: number;
  flowsIgnored: number;
  lowConfidenceIgnored?: number;
  message: string;
  gmailAnalyzed?: number;
  calendarAnalyzed?: number;
  driveAnalyzed?: number;
  mapsUsed?: boolean;
}

export interface UnifiedAnalyzeResult {
  success: boolean;
  flowsCreated: number;
  flowsIgnored: number;
  lowConfidenceIgnored?: number;
  message: string;
  gmailAnalyzed: number;
  calendarAnalyzed: number;
  driveAnalyzed: number;
  mapsUsed: boolean;
  emailsAnalyzed: number;
}

export const workflowService = {
  async getWorkflows(): Promise<Workflow[]> {
    if (isUserAuthenticated()) {
      // AUTHENTICATED: only real backend workflows, NEVER mock data.
      try {
        const headers = await authHeaders();
        const userWorkflows = await apiGet<Workflow[]>('/api/workflows', { headers });
        generatedWorkflows = [...userWorkflows];
        return [...generatedWorkflows];
      } catch {
        return [];
      }
    }

    // DEMO MODE: mock data + anything generated this session.
    const local = [...demoWorkflows];
    try {
      const backend = await apiGet<Workflow[]>('/api/workflows');
      const byId = new Map<string, Workflow>();
      for (const w of local) byId.set(w.id, w);
      for (const b of backend) {
        if (!byId.has(b.id)) byId.set(b.id, b);
      }
      const merged = [...byId.values()];
      const mockIds = new Set(demoWorkflows.map(w => w.id));
      generatedWorkflows = merged.filter(w => !mockIds.has(w.id));
      return merged;
    } catch {
      return local;
    }
  },

  async getWorkflowById(id: string): Promise<Workflow | undefined> {
    // Check cached real workflows first.
    const cached = generatedWorkflows.find(w => w.id === id);
    if (cached) return cached;

    // In demo mode, also check mock workflows.
    if (!isUserAuthenticated()) {
      const mock = demoWorkflows.find(w => w.id === id);
      if (mock) return mock;
    }

    // Fall back to the backend.
    try {
      const headers = await authHeaders();
      const fetched = await apiGet<Workflow>(`/api/workflows/${id}`, { headers });
      generatedWorkflows = [
        ...generatedWorkflows.filter(w => w.id !== id),
        fetched,
      ];
      return fetched;
    } catch {
      return undefined;
    }
  },

  async getWorkflowDetail(id: string): Promise<WorkflowDetail | undefined> {
    try {
      const headers = await authHeaders();
      return await apiGet<WorkflowDetail>(`/api/workflows/${id}/detail`, { headers });
    } catch {
      return undefined;
    }
  },

  async toggleChecklistItem(workflowId: string, itemId: string): Promise<Workflow> {
    const allWorkflows = isUserAuthenticated()
      ? generatedWorkflows
      : [...demoWorkflows, ...generatedWorkflows];
    const target = allWorkflows.find(w => w.id === workflowId);
    if (!target) throw new Error('Workflow not found');
    const optimistic = toggleIn(target, itemId);
    const isDemoWorkflow = !isUserAuthenticated() && demoWorkflows.some(w => w.id === workflowId);

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
        generatedWorkflows = generatedWorkflows.map(w => (w.id === workflowId ? updated : w));
        return updated;
      } catch {
        // Network hiccup — keep the optimistic local update.
      }
    }

    if (isDemoWorkflow) {
      // Demo workflows are read-only in this model.
    } else {
      generatedWorkflows = generatedWorkflows.map(w => (w.id === workflowId ? optimistic : w));
    }
    return optimistic;
  },

  async ask(query: string): Promise<Workflow> {
    const headers = await authHeaders();
    const workflow = await apiPost<Workflow>('/api/ask', { query }, { headers });
    generatedWorkflows = [workflow, ...generatedWorkflows.filter(w => w.id !== workflow.id)];
    return workflow;
  },

  async analyzeGmail(): Promise<AnalyzeResult> {
    const headers = await authHeaders();
    return apiPost<AnalyzeResult>('/api/gmail/analyze', {}, { headers });
  },

  async analyzeServices(payload: { services?: string[]; query?: string; origin?: string; destination?: string } = {}): Promise<UnifiedAnalyzeResult> {
    const headers = await authHeaders();
    return apiPost<UnifiedAnalyzeResult>('/api/analyze', payload, { headers });
  },

  async getGmailStatus(): Promise<{ connected: boolean; service: string; scopes: string[] }> {
    const headers = await authHeaders();
    return apiGet<{ connected: boolean; service: string; scopes: string[] }>(
      '/api/auth/gmail/status',
      { headers },
    );
  },

  async getServices(): Promise<Service[]> {
    return Promise.resolve(mockServices);
  },

  async getServiceByName(name: string): Promise<Service | undefined> {
    const normalize = (value: string) =>
      value.toLowerCase().replace(/^google\s+/, '').replace(/\s+/g, ' ').trim();
    return Promise.resolve(
      mockServices.find(s => normalize(s.name) === normalize(name)),
    );
  },

  async deleteWorkflow(id: string): Promise<void> {
    const headers = await authHeaders();
    await fetch(`/api/workflows/${id}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', ...headers },
    });
    generatedWorkflows = generatedWorkflows.filter(w => w.id !== id);
  },
};
