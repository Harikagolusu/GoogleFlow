import type { Workflow } from '../types/workflow';
import type { Service } from '../types/service';

export const mockWorkflows: Workflow[] = [
  {
    id: 'interview',
    title: 'AI Engineer Interview',
    emoji: '💼',
    date: 'Tomorrow · 10:30 AM',
    status: 'Action Needed',
    readiness: 76,
    nextUp: 'Complete company research',
    checklist: [
      { id: 'c1', title: 'Resume', completed: true },
      { id: 'c2', title: 'Portfolio', completed: true },
      { id: 'c3', title: 'Company research', completed: false },
      { id: 'c4', title: 'Interview preparation', completed: false },
    ],
    connectedServices: ['Gmail', 'Drive', 'Calendar', 'Maps', 'YouTube', 'News'],
  },
  {
    id: 'delhi-trip',
    title: 'Delhi Trip',
    emoji: '✈️',
    date: 'Sat · 6:40 AM flight',
    status: 'In Progress',
    readiness: 91,
    nextUp: 'Download boarding pass',
    checklist: [
      { id: 'c1', title: 'Flight booked', completed: true },
      { id: 'c2', title: 'Hotel reserved', completed: true },
      { id: 'c3', title: 'Web check-in', completed: true },
      { id: 'c4', title: 'Download boarding pass', completed: false },
    ],
    connectedServices: ['Gmail', 'Calendar', 'Maps', 'Drive'],
  },
  {
    id: 'certification',
    title: 'Cloud Certification',
    emoji: '🎓',
    date: 'In 3 weeks',
    status: 'In Progress',
    readiness: 64,
    nextUp: 'Complete practice exam',
    checklist: [
      { id: 'c1', title: 'Enrolled in course', completed: true },
      { id: 'c2', title: 'Study materials downloaded', completed: true },
      { id: 'c3', title: 'Complete practice exam', completed: false },
      { id: 'c4', title: 'Schedule exam date', completed: false },
    ],
    connectedServices: ['Gmail', 'Drive', 'YouTube', 'Calendar'],
  },
];

export const mockServices: Service[] = [
  {
    id: 'gmail',
    name: 'Gmail',
    icon: 'Mail',
    description: 'Scans emails for actionable items like appointments, flights, and deadlines.',
    connected: true,
    relatedEmails: [
      { subject: 'Interview confirmation — AI Engineer', from: 'Nimbus AI', time: '2 days ago' },
      { subject: 'Panel details and joining link', from: 'recruiting@nimbus.ai', time: 'yesterday' },
      { subject: 'Reminder: bring a photo ID', from: 'recruiting@nimbus.ai', time: 'yesterday' },
    ],
  },
  {
    id: 'drive',
    name: 'Drive',
    icon: 'HardDrive',
    description: 'Searches for required documents and reference materials.',
    connected: true,
  },
  {
    id: 'calendar',
    name: 'Calendar',
    icon: 'Calendar',
    description: 'Syncs workflow events and helps you manage your schedule.',
    connected: true,
  },
  {
    id: 'maps',
    name: 'Maps',
    icon: 'MapPin',
    description: 'Provides travel time and location context.',
    connected: true,
  },
  {
    id: 'youtube',
    name: 'YouTube',
    icon: 'Play',
    description: 'Finds tutorials and preparation videos.',
    connected: true,
  },
  {
    id: 'search',
    name: 'Search',
    icon: 'Search',
    description: 'Web search for research and references.',
    connected: true,
  },
  {
    id: 'news',
    name: 'News',
    icon: 'Newspaper',
    description: 'Curated news and updates relevant to your flows.',
    connected: true,
  },
  {
    id: 'photos',
    name: 'Photos',
    icon: 'Image',
    description: 'Manages and organizes your photos.',
    connected: true,
  },
  {
    id: 'gemini',
    name: 'Gemini',
    icon: 'Sparkles',
    description: 'AI engine that understands content and generates action plans.',
    connected: true,
  },
];
