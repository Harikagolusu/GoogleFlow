import React, { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Sparkles,
  Trash2,
  Search,
  ChevronRight,
  AlertCircle,
  LayoutGrid,
  List,
} from 'lucide-react';
import { workflowService } from '../services/workflowService';
import type { Workflow } from '../types/workflow';
import { useAuthUser } from '../hooks/useAuthUser';
import { ServiceLogo } from '../components/ServiceLogo';
import { Button } from '../components/ui/Button';
import { Badge, PriorityBadge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { SkeletonCard } from '../components/ui/Skeleton';

type FilterType = 'all' | 'high' | 'due' | 'upcoming' | 'completed';
type SortType = 'priority' | 'date' | 'recent' | 'readiness';
type ViewMode = 'grid' | 'list';

export const FlowsList: React.FC = () => {
  const { signedIn, isAuthEnabled } = useAuthUser();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<FilterType>('all');
  const [sort, setSort] = useState<SortType>('priority');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const navigate = useNavigate();

  useEffect(() => {
    workflowService.getWorkflows().then(data => {
      setWorkflows(data);
      setLoading(false);
    });
  }, []);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await workflowService.deleteWorkflow(id);
      setWorkflows(prev => prev.filter(w => w.id !== id));
    } finally {
      setDeleteId(null);
    }
  };

  const filteredAndSortedWorkflows = useMemo(() => {
    let filtered = [...workflows];

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        w =>
          w.title.toLowerCase().includes(query) ||
          w.connectedServices.some(s => s.toLowerCase().includes(query)) ||
          w.priority?.toLowerCase().includes(query)
      );
    }

    // Apply status filter
    switch (filter) {
      case 'high':
        filtered = filtered.filter(w => w.priority === 'high');
        break;
      case 'due':
        filtered = filtered.filter(w => w.status === 'Action Needed');
        break;
      case 'upcoming':
        filtered = filtered.filter(w => w.status === 'In Progress');
        break;
      case 'completed':
        filtered = filtered.filter(w => w.status === 'Completed');
        break;
    }

    // Apply sort
    switch (sort) {
      case 'priority':
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        filtered.sort((a, b) => {
          const pa = priorityOrder[a.priority || 'medium'] ?? 1;
          const pb = priorityOrder[b.priority || 'medium'] ?? 1;
          return pa - pb;
        });
        break;
      case 'date':
        filtered.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
        break;
      case 'recent':
        filtered.sort((a, b) => b.id.localeCompare(a.id));
        break;
      case 'readiness':
        filtered.sort((a, b) => b.readiness - a.readiness);
        break;
    }

    return filtered;
  }, [workflows, filter, sort, searchQuery]);

  if (loading) {
    return (
      <div className="pt-12 px-4 md:px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <SkeletonCard />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  const isAuthenticated = isAuthEnabled && signedIn;
  const stats = {
    total: workflows.length,
    active: workflows.filter(w => w.status !== 'Completed').length,
    high: workflows.filter(w => w.priority === 'high').length,
    completed: workflows.filter(w => w.status === 'Completed').length,
  };

  return (
    <div className="pt-12 px-4 md:px-6 pb-24 md:pb-20 max-w-6xl mx-auto">
      {/* Header */}
      <header className="mb-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl md:text-4xl font-serif text-text-primary">My LifeFlows</h1>
            <p className="text-text-secondary mt-1">
              {stats.total > 0
                ? `${stats.active} active · ${stats.high} high priority · ${stats.completed} completed`
                : 'No LifeFlows yet'}
            </p>
          </div>
          <Button
            variant="primary"
            onClick={() => navigate('/')}
            icon={<Sparkles className="w-4 h-4" />}
          >
            New LifeFlow
          </Button>
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col md:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary pointer-events-none" />
            <input
              type="text"
              placeholder="Search LifeFlows..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="input pl-10 py-2 text-sm rounded-lg"
            />
          </div>
          <div className="flex items-center gap-2">
            <select
              value={filter}
              onChange={e => setFilter(e.target.value as FilterType)}
              className="input py-2 pr-8 text-sm rounded-lg bg-white appearance-none cursor-pointer"
            >
              <option value="all">All</option>
              <option value="high">High Priority</option>
              <option value="due">Action Needed</option>
              <option value="upcoming">In Progress</option>
              <option value="completed">Completed</option>
            </select>
            <select
              value={sort}
              onChange={e => setSort(e.target.value as SortType)}
              className="input py-2 pr-8 text-sm rounded-lg bg-white appearance-none cursor-pointer"
            >
              <option value="priority">Priority</option>
              <option value="date">Date</option>
              <option value="recent">Recently Created</option>
              <option value="readiness">Readiness</option>
            </select>
            <div className="flex items-center border border-border rounded-lg overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 ${viewMode === 'grid' ? 'bg-primary text-white' : 'bg-surface text-text-secondary hover:bg-gray-50'}`}
                title="Grid view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 ${viewMode === 'list' ? 'bg-primary text-white' : 'bg-surface text-text-secondary hover:bg-gray-50'}`}
                title="List view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Empty State */}
      {workflows.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title={isAuthenticated ? 'No LifeFlows yet' : 'Demo Mode'}
          description={
            isAuthenticated
              ? 'Connect your Google apps and let AI discover important events, deadlines, and commitments.'
              : 'Sign in with Google to create your own LifeFlows based on your Gmail, Calendar, and Drive data.'
          }
          action={
            isAuthenticated
              ? { label: 'Go to Dashboard', onClick: () => navigate('/'), variant: 'primary' }
              : { label: 'Go to Dashboard', onClick: () => navigate('/'), variant: 'secondary' }
          }
          className="py-16"
        />
      ) : filteredAndSortedWorkflows.length === 0 ? (
        <EmptyState
          title="No matching LifeFlows"
          description="Try adjusting your search or filters."
          action={{ label: 'Clear filters', onClick: () => { setSearchQuery(''); setFilter('all'); }, variant: 'secondary' }}
          className="py-16"
        />
      ) : (
        <>
          <p className="text-sm text-text-secondary mb-4">
            Showing {filteredAndSortedWorkflows.length} of {workflows.length} LifeFlows
          </p>

          {viewMode === 'grid' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredAndSortedWorkflows.map(workflow => (
                <WorkflowCard
                  key={workflow.id}
                  workflow={workflow}
                  onDelete={(e) => { e.preventDefault(); e.stopPropagation(); setDeleteId(workflow.id); }}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredAndSortedWorkflows.map(workflow => (
                <WorkflowListItem
                  key={workflow.id}
                  workflow={workflow}
                  onDelete={(e) => { e.preventDefault(); e.stopPropagation(); setDeleteId(workflow.id); }}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Delete Confirmation Modal */}
      {deleteId && (
        <div className="modal-backdrop flex items-center justify-center p-4" onClick={() => setDeleteId(null)}>
          <div
            className="bg-surface rounded-xl p-6 max-w-sm w-full shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="text-lg font-medium text-text-primary mb-2">Delete LifeFlow?</h3>
            <p className="text-text-secondary text-sm mb-6">
              Are you sure you want to delete this LifeFlow? This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <Button variant="secondary" onClick={() => setDeleteId(null)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={e => handleDelete(e, deleteId)}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

interface WorkflowCardProps {
  workflow: Workflow;
  onDelete: (e: React.MouseEvent) => void;
}

const WorkflowCard: React.FC<WorkflowCardProps> = ({ workflow, onDelete }) => {
  const completedCount = workflow.checklist.filter(i => i.completed).length;
  const totalCount = workflow.checklist.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <Link
      to={`/flows/${workflow.id}`}
      className="group block bg-surface rounded-xl border border-border-light p-5 hover:shadow-md hover:border-border transition-all duration-200 relative"
    >
      {/* Delete Button */}
      <button
        onClick={onDelete}
        className="absolute top-3 right-3 p-2 rounded-lg text-text-tertiary hover:text-error hover:bg-error-light opacity-0 group-hover:opacity-100 transition-all z-10"
        title="Delete"
      >
        <Trash2 className="w-4 h-4" />
      </button>

      {/* Header */}
      <div className="flex items-start gap-3 mb-4">
        <div className="w-11 h-11 rounded-xl bg-background flex items-center justify-center text-xl">
          {workflow.emoji}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="font-medium text-text-primary line-clamp-1 group-hover:text-primary transition-colors">
              {workflow.title}
            </h3>
          </div>
          <p className="text-xs text-text-secondary">{workflow.date}</p>
        </div>
      </div>

      {/* Priority & Status */}
      <div className="flex items-center gap-2 mb-4">
        <PriorityBadge priority={workflow.priority} />
        <Badge
          variant={
            workflow.status === 'Completed' ? 'success' :
            workflow.status === 'In Progress' ? 'primary' : 'warning'
          }
          size="sm"
        >
          {workflow.status === 'Action Needed' && <AlertCircle className="w-3 h-3 mr-1" />}
          {workflow.status}
        </Badge>
      </div>

      {/* Progress */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs mb-1.5">
          <span className="text-text-secondary">
            {completedCount}/{totalCount} tasks
          </span>
          <span className="font-medium text-text-primary">{Math.round(progress)}%</span>
        </div>
        <div className="h-1.5 bg-background rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${progress}%`,
              backgroundColor: progress === 100 ? '#34A853' : '#4285F4',
            }}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-border-light">
        <div className="flex items-center gap-1.5">
          {workflow.connectedServices.slice(0, 4).map(service => (
            <div
              key={service}
              className="w-6 h-6 rounded-md bg-background flex items-center justify-center"
              title={service}
            >
              <ServiceLogo name={service} className="w-3.5 h-3.5" />
            </div>
          ))}
          {workflow.connectedServices.length > 4 && (
            <span className="text-xs text-text-tertiary ml-1">+{workflow.connectedServices.length - 4}</span>
          )}
        </div>
        <ChevronRight className="w-4 h-4 text-text-tertiary group-hover:text-primary group-hover:translate-x-1 transition-all" />
      </div>
    </Link>
  );
};

interface WorkflowListItemProps {
  workflow: Workflow;
  onDelete: (e: React.MouseEvent) => void;
}

const WorkflowListItem: React.FC<WorkflowListItemProps> = ({ workflow, onDelete }) => {
  const completedCount = workflow.checklist.filter(i => i.completed).length;
  const totalCount = workflow.checklist.length;
  const progress = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <Link
      to={`/flows/${workflow.id}`}
      className="group flex items-center gap-4 bg-surface rounded-xl border border-border-light p-4 hover:shadow-md hover:border-border transition-all duration-200"
    >
      <div className="w-10 h-10 rounded-xl bg-background flex items-center justify-center text-xl flex-shrink-0">
        {workflow.emoji}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <h3 className="font-medium text-text-primary line-clamp-1 group-hover:text-primary transition-colors">
            {workflow.title}
          </h3>
          <PriorityBadge priority={workflow.priority} />
        </div>
        <div className="flex items-center gap-3 text-xs text-text-secondary">
          <span>{workflow.date}</span>
          <span className="flex items-center gap-1">
            <Badge
              variant={
                workflow.status === 'Completed' ? 'success' :
                workflow.status === 'In Progress' ? 'primary' : 'warning'
              }
              size="sm"
            >
              {workflow.status}
            </Badge>
          </span>
        </div>
      </div>

      <div className="hidden md:flex items-center gap-6 flex-shrink-0">
        <div className="w-32">
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-text-secondary">{completedCount}/{totalCount}</span>
            <span className="font-medium text-text-primary">{Math.round(progress)}%</span>
          </div>
          <div className="h-1.5 bg-background rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 ease-out"
              style={{
                width: `${progress}%`,
                backgroundColor: progress === 100 ? '#34A853' : '#4285F4',
              }}
            />
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {workflow.connectedServices.slice(0, 3).map(service => (
            <div
              key={service}
              className="w-6 h-6 rounded-md bg-background flex items-center justify-center"
              title={service}
            >
              <ServiceLogo name={service} className="w-3.5 h-3.5" />
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onDelete}
        className="p-2 rounded-lg text-text-tertiary hover:text-error hover:bg-error-light opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
        title="Delete"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </Link>
  );
};

export default FlowsList;
