export type WorkflowStatus = 'Completed' | 'In Progress' | 'Action Needed';

export type WorkflowPriority = 'high' | 'medium' | 'low';

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
  priority?: WorkflowPriority;
  confidence?: number;
}

export interface RelatedEmail {
  id: string;
  sender: string;
  subject: string;
  date: string;
  snippet: string;
}

export interface RelatedCalendarEvent {
  id: string;
  summary: string;
  start: string;
  end: string;
  location: string;
  displayStart: string;
  htmlLink: string;
  meetingUrl: string;
}

export interface RelatedDriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime: string;
  webViewLink: string;
}

export interface RelatedResources {
  emails: RelatedEmail[];
  calendarEvents: RelatedCalendarEvent[];
  driveFiles: RelatedDriveFile[];
}

export interface VideoRecommendation {
  id: string;
  title: string;
  channelTitle: string;
  thumbnail: string;
  publishedAt: string;
  url: string;
}

export interface WorkflowDetail {
  workflow: Workflow;
  relatedResources: RelatedResources;
  helpfulVideos: VideoRecommendation[];
}
