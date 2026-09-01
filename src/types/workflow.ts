export type WorkflowStatus = 'Completed' | 'In Progress' | 'Action Needed';

export interface ChecklistItem {
  id: string;
  title: string;
  completed: boolean;
}

export interface Workflow {
  id: string;
  title: string;
  emoji: string;
  date: string;
  location?: string;
  status: WorkflowStatus;
  readiness: number;
  nextUp?: string;
  checklist: ChecklistItem[];
  connectedServices: string[];
}
