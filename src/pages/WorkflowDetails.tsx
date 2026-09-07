import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  ExternalLink,
  Mail,
  Calendar,
  FileText,
  Video,
  Trash2,
  MapPin,
  Clock,
  Play,
  Link as LinkIcon,
  AlertCircle,
} from 'lucide-react';
import { workflowService } from '../services/workflowService';
import type {
  WorkflowDetail,
  RelatedEmail,
  RelatedCalendarEvent,
  RelatedDriveFile,
  VideoRecommendation,
} from '../types/workflow';
import { ServiceLogo } from '../components/ServiceLogo';
import { Button } from '../components/ui/Button';
import { Badge, PriorityBadge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';

function ResourceSection<E extends { id: string }>({
  title,
  icon: Icon,
  items,
  renderItem,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  items: E[];
  renderItem: (item: E) => React.ReactNode;
}) {
  if (items.length === 0) return null;
  return (
    <Card padding="md">
      <h3 className="text-base font-medium text-text-primary mb-4 flex items-center gap-2">
        <Icon className="w-4 h-4 text-text-tertiary" />
        {title}
        <span className="text-xs text-text-tertiary font-normal">({items.length})</span>
      </h3>
      <div className="space-y-2">
        {items.map(item => renderItem(item))}
      </div>
    </Card>
  );
}

function EmailItem({ email }: { email: RelatedEmail }) {
  return (
    <a
      href={`https://mail.google.com/mail/u/0/#inbox/${email.id}`}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-start gap-3 p-3 rounded-lg border border-border-light hover:border-border hover:bg-background transition-all group"
    >
      <div className="w-8 h-8 rounded-lg bg-primary-light flex items-center justify-center flex-shrink-0">
        <Mail className="w-4 h-4 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary line-clamp-1 group-hover:text-primary transition-colors">
          {email.subject || '(no subject)'}
        </p>
        <p className="text-xs text-text-secondary mt-0.5">{email.sender}</p>
        <p className="text-xs text-text-tertiary mt-1 line-clamp-2">{email.snippet}</p>
      </div>
      <div className="flex flex-col items-end gap-1 flex-shrink-0">
        <span className="text-xs text-text-tertiary">{email.date}</span>
        <ExternalLink className="w-3 h-3 text-text-tertiary opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>
    </a>
  );
}

function CalendarItem({ event }: { event: RelatedCalendarEvent }) {
  const hasMeeting = !!event.meetingUrl;
  const hasLocation = !!event.location;

  return (
    <div className="p-4 rounded-lg border border-border-light hover:border-border transition-all">
      <div className="flex items-start gap-3 mb-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${hasMeeting ? 'bg-primary-light' : 'bg-background'}`}>
          <Calendar className={`w-4 h-4 ${hasMeeting ? 'text-primary' : 'text-text-tertiary'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-text-primary">{event.summary || '(no title)'}</p>
          <div className="flex items-center gap-2 mt-1 text-xs text-text-secondary">
            <Clock className="w-3 h-3" />
            <span>{event.displayStart || event.start}</span>
          </div>
          {hasLocation && (
            <a
              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(event.location || '')}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 mt-1 text-xs text-text-secondary hover:text-primary transition-colors"
            >
              <MapPin className="w-3 h-3" />
              <span className="line-clamp-1">{event.location}</span>
            </a>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 ml-11">
        {hasMeeting && (
          <a
            href={event.meetingUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-hover transition-colors"
          >
            <Video className="w-3.5 h-3.5" />
            Join Meeting
          </a>
        )}
        {event.htmlLink && (
          <a
            href={event.htmlLink}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-background text-text-secondary text-xs font-medium rounded-lg hover:bg-border transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open Calendar
          </a>
        )}
      </div>
    </div>
  );
}

function DriveItem({ file }: { file: RelatedDriveFile }) {
  const typeLabel = file.mimeType.includes('spreadsheet') ? 'Spreadsheet' :
    file.mimeType.includes('document') ? 'Document' :
    file.mimeType.includes('pdf') ? 'PDF' :
    file.mimeType.includes('folder') ? 'Folder' : 'File';

  return (
    <a
      href={file.webViewLink || '#'}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-3 p-3 rounded-lg border border-border-light hover:border-border hover:bg-background transition-all group"
    >
      <div className="w-8 h-8 rounded-lg bg-background flex items-center justify-center flex-shrink-0">
        <FileText className="w-4 h-4 text-text-tertiary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-text-primary line-clamp-1 group-hover:text-primary transition-colors">
          {file.name}
        </p>
        <p className="text-xs text-text-secondary mt-0.5">
          {typeLabel} · {file.modifiedTime ? new Date(file.modifiedTime).toLocaleDateString() : 'Unknown'}
        </p>
      </div>
      <ExternalLink className="w-4 h-4 text-text-tertiary opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
    </a>
  );
}

function VideoCard({ video }: { video: VideoRecommendation }) {
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex gap-4 p-3 rounded-xl border border-border-light hover:border-border hover:shadow-sm transition-all group"
    >
      {video.thumbnail ? (
        <div className="relative flex-shrink-0">
          <img
            src={video.thumbnail}
            alt={video.title}
            className="w-32 h-20 object-cover rounded-lg"
            loading="lazy"
          />
          <div className="absolute inset-0 flex items-center justify-center bg-black/30 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity">
            <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center">
              <Play className="w-5 h-5 text-gray-900 ml-0.5" />
            </div>
          </div>
        </div>
      ) : (
        <div className="w-32 h-20 rounded-lg bg-background flex items-center justify-center flex-shrink-0">
          <Video className="w-8 h-8 text-text-tertiary" />
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col justify-center">
        <p className="text-sm font-medium text-text-primary line-clamp-2 group-hover:text-primary transition-colors">
          {video.title}
        </p>
        <p className="text-xs text-text-secondary mt-1">{video.channelTitle}</p>
        {video.publishedAt && (
          <p className="text-xs text-text-tertiary mt-0.5">
            {new Date(video.publishedAt).toLocaleDateString()}
          </p>
        )}
      </div>
      <ExternalLink className="w-4 h-4 text-text-tertiary flex-shrink-0 self-center opacity-0 group-hover:opacity-100 transition-opacity" />
    </a>
  );
}

export const WorkflowDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<WorkflowDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    workflowService.getWorkflowDetail(id)
      .then(data => {
        setDetail(data || null);
        setLoading(false);
      })
      .catch(() => {
        setError('Failed to load workflow details.');
        setLoading(false);
      });
  }, [id]);

  const handleToggle = async (itemId: string) => {
    if (!detail) return;
    const updated = await workflowService.toggleChecklistItem(detail.workflow.id, itemId);
    setDetail(prev => prev ? { ...prev, workflow: updated } : null);
  };

  const handleDelete = async () => {
    if (!id || deleting) return;
    setDeleting(true);
    try {
      await workflowService.deleteWorkflow(id);
      navigate('/flows');
    } catch {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  if (loading) {
    return (
      <div className="pt-12 px-4 md:px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <Skeleton width="6rem" height="1rem" className="mb-4" />
          <Skeleton width="70%" height="3rem" className="mb-6" />
          <Skeleton width="40%" height="1.5rem" className="mb-2" />
        </div>
        <div className="space-y-4">
          <Skeleton height="4rem" className="rounded-xl" />
          <Skeleton height="4rem" className="rounded-xl" />
          <Skeleton height="4rem" className="rounded-xl" />
        </div>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="pt-12 px-4 md:px-6 max-w-6xl mx-auto">
        <EmptyState
          icon={AlertCircle}
          title="Failed to load"
          description={error || 'This LifeFlow could not be found.'}
          action={{ label: 'Go back', onClick: () => navigate('/flows'), variant: 'secondary' }}
        />
      </div>
    );
  }

  const { workflow, relatedResources, helpfulVideos } = detail;
  const completedCount = workflow.checklist.filter(i => i.completed).length;
  const totalCount = workflow.checklist.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const pendingCount = totalCount - completedCount;

  const hasResources =
    relatedResources.emails.length > 0 ||
    relatedResources.calendarEvents.length > 0 ||
    relatedResources.driveFiles.length > 0;

  const hasMeeting = relatedResources.calendarEvents.some(e => e.meetingUrl);

  return (
    <div className="pt-8 md:pt-12 px-4 md:px-6 pb-24 md:pb-20 max-w-6xl mx-auto">
      {/* Back Navigation */}
      <Link
        to="/flows"
        className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors text-sm mb-6"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to LifeFlows</span>
      </Link>

      {/* Header */}
      <header className="mb-8">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="flex-1 min-w-0">
            {/* Category & Priority */}
            <div className="flex items-center gap-2 mb-3">
              <PriorityBadge priority={workflow.priority} />
              <Badge
                variant={
                  workflow.status === 'Completed' ? 'success' :
                  workflow.status === 'In Progress' ? 'primary' : 'warning'
                }
              >
                {workflow.status}
              </Badge>
            </div>

            {/* Title */}
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-serif text-text-primary mb-3">
              <span className="mr-3">{workflow.emoji}</span>
              {workflow.title}
            </h1>

            {/* Meta */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-text-secondary">
              <div className="flex items-center gap-1.5">
                <Calendar className="w-4 h-4" />
                <span>{workflow.date}</span>
              </div>
              {workflow.location && (
                <div className="flex items-center gap-1.5">
                  <MapPin className="w-4 h-4" />
                  <span>{workflow.location}</span>
                </div>
              )}
            </div>

            {/* Connected Services */}
            <div className="flex flex-wrap gap-2 mt-4">
              {workflow.connectedServices.map((service, i) => (
                <Link
                  key={i}
                  to={`/service/${service.toLowerCase()}`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-background text-xs font-medium text-text-secondary hover:bg-border hover:text-text-primary transition-colors"
                >
                  <ServiceLogo name={service} className="w-3.5 h-3.5" />
                  {service}
                </Link>
              ))}
            </div>
          </div>

          {/* Readiness */}
          <div className="flex-shrink-0 text-left md:text-right">
            <div className="inline-flex flex-col items-center p-4 rounded-xl bg-surface border border-border-light">
              <span className="text-3xl font-semibold text-text-primary">{workflow.readiness}%</span>
              <span className="text-xs text-text-secondary">Ready</span>
            </div>
          </div>
        </div>

        {/* Meeting Actions */}
        {hasMeeting && (
          <div className="mt-6 p-4 rounded-xl bg-primary-light border border-primary/20">
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
              <div className="flex items-center gap-2 text-primary">
                <Video className="w-5 h-5" />
                <span className="font-medium">Meeting detected</span>
              </div>
              {relatedResources.calendarEvents.find(e => e.meetingUrl) && (
                <div className="flex gap-2 sm:ml-auto">
                  <a
                    href={relatedResources.calendarEvents.find(e => e.meetingUrl)?.meetingUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-hover transition-colors"
                  >
                    <Video className="w-4 h-4" />
                    Join Meeting
                  </a>
                </div>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Next Up */}
      {workflow.nextUp && (
        <Card className="mb-6 border-l-4 border-l-primary">
          <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1">Next up</p>
          <p className="text-base font-medium text-text-primary">{workflow.nextUp}</p>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Checklist */}
        <div className="lg:col-span-7">
          <Card padding="lg" className="mb-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-serif text-text-primary">What to do</h2>
              <span className="text-sm text-text-secondary">
                {completedCount}/{totalCount} complete
              </span>
            </div>

            {/* Progress Bar */}
            <div className="mb-6">
              <div className="h-2 bg-background rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500 ease-out"
                  style={{
                    width: `${progress}%`,
                    backgroundColor: progress === 100 ? '#34A853' : '#4285F4',
                  }}
                />
              </div>
            </div>

            {/* Checklist Items */}
            <div className="space-y-2">
              {workflow.checklist.map(item => (
                <button
                  key={item.id}
                  onClick={() => handleToggle(item.id)}
                  className={`w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all duration-200 ${
                    item.completed
                      ? 'bg-background/50 border-border-light'
                      : 'bg-surface border-border-light hover:border-border hover:shadow-sm'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all flex-shrink-0 ${
                      item.completed
                        ? 'bg-success border-success'
                        : 'border-border-light group-hover:border-primary'
                    }`}
                  >
                    {item.completed && <Check className="w-3 h-3 text-white" />}
                  </div>
                  <span
                    className={`flex-1 text-sm ${
                      item.completed
                        ? 'text-text-tertiary line-through'
                        : 'text-text-primary font-medium'
                    }`}
                  >
                    {item.title}
                  </span>
                </button>
              ))}
            </div>

            {pendingCount === 0 && (
              <div className="mt-6 p-4 rounded-xl bg-success-light border border-success/20">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-success" />
                  <span className="text-sm font-medium text-success">All tasks completed!</span>
                </div>
              </div>
            )}
          </Card>

          {!hasResources && helpfulVideos.length === 0 && (
            <Card padding="lg">
              <p className="text-sm text-text-secondary text-center">
                No related resources yet. Connect Gmail, Calendar, or Drive to see relevant content.
              </p>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-5 space-y-4">
          <Card padding="md">
            <h3 className="text-base font-medium text-text-primary mb-3">Status</h3>
            <div className="flex items-center gap-2">
              {pendingCount > 0 ? (
                <>
                  <AlertCircle className="w-4 h-4 text-warning" />
                  <span className="text-sm text-text-secondary">
                    {pendingCount} thing{pendingCount > 1 ? 's' : ''} need your attention
                  </span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  <span className="text-sm text-success">You're all set!</span>
                </>
              )}
            </div>
          </Card>

          {/* Quick Actions */}
          <Card padding="md">
            <h3 className="text-base font-medium text-text-primary mb-3">Quick actions</h3>
            <div className="space-y-2">
              <Button
                variant="secondary"
                onClick={() => navigate('/')}
                className="w-full justify-start"
                icon={<LinkIcon className="w-4 h-4" />}
              >
                Create new LifeFlow
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowDeleteConfirm(true)}
                className="w-full justify-start text-error hover:bg-error-light hover:border-error/20"
                icon={<Trash2 className="w-4 h-4" />}
              >
                Delete this LifeFlow
              </Button>
            </div>
          </Card>
        </div>
      </div>

      {/* Related Resources */}
      {hasResources && (
        <section className="mt-8">
          <h2 className="text-xl font-serif text-text-primary mb-4">Related Resources</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <ResourceSection
              title="Gmail"
              icon={Mail}
              items={relatedResources.emails}
              renderItem={(email) => <EmailItem key={email.id} email={email} />}
            />
            <ResourceSection
              title="Calendar"
              icon={Calendar}
              items={relatedResources.calendarEvents}
              renderItem={(event) => <CalendarItem key={event.id} event={event} />}
            />
            <ResourceSection
              title="Drive"
              icon={FileText}
              items={relatedResources.driveFiles}
              renderItem={(file) => <DriveItem key={file.id} file={file} />}
            />
          </div>
        </section>
      )}

      {/* Helpful Videos */}
      {helpfulVideos.length > 0 && (
        <section className="mt-8">
          <div className="flex items-center gap-2 mb-4">
            <Video className="w-5 h-5 text-text-tertiary" />
            <h2 className="text-xl font-serif text-text-primary">Helpful Videos</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {helpfulVideos.map(video => (
              <VideoCard key={video.id} video={video} />
            ))}
          </div>
        </section>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-backdrop flex items-center justify-center p-4" onClick={() => setShowDeleteConfirm(false)}>
          <div
            className="bg-surface rounded-xl p-6 max-w-sm w-full shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="text-lg font-medium text-text-primary mb-2">Delete LifeFlow?</h3>
            <p className="text-text-secondary text-sm mb-6">
              Are you sure you want to delete "{workflow.title}"? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleDelete} loading={deleting}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkflowDetails;
