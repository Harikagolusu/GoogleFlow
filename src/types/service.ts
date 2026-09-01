export interface Service {
  id: string;
  name: string;
  icon: string;
  description: string;
  connected: boolean;
  relatedEmails?: { subject: string; from: string; time: string }[];
}
