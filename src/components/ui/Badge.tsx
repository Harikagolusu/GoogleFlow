import React from 'react';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'error' | 'high' | 'medium' | 'low';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'sm',
  className = '',
}) => {
  const variants = {
    default: 'bg-gray-100 text-gray-700',
    primary: 'bg-primary-light text-primary',
    success: 'bg-success-light text-success',
    warning: 'bg-warning-light text-amber-700',
    error: 'bg-error-light text-error',
    high: 'bg-error-light text-error',
    medium: 'bg-warning-light text-amber-700',
    low: 'bg-success-light text-success',
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-1 text-sm',
  };

  return (
    <span
      className={`
        inline-flex items-center font-medium rounded-full
        ${variants[variant]}
        ${sizes[size]}
        ${className}
      `}
    >
      {children}
    </span>
  );
};

interface PriorityBadgeProps {
  priority?: 'high' | 'medium' | 'low';
  showLabel?: boolean;
  className?: string;
}

export const PriorityBadge: React.FC<PriorityBadgeProps> = ({
  priority,
  showLabel = false,
  className = '',
}) => {
  if (!priority) return null;

  const labels = {
    high: 'High',
    medium: 'Medium',
    low: 'Low',
  };

  return (
    <Badge variant={priority} size="sm" className={className}>
      {priority === 'high' && '↑ '}{showLabel ? labels[priority] : priority.charAt(0).toUpperCase() + priority.slice(1)}
    </Badge>
  );
};

interface StatusBadgeProps {
  status?: 'Completed' | 'In Progress' | 'Action Needed';
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  if (!status) return null;

  const variants: Record<string, 'success' | 'warning' | 'error'> = {
    'Completed': 'success',
    'In Progress': 'warning',
    'Action Needed': 'error',
  };

  return (
    <Badge variant={variants[status] || 'default'} size="sm" className={className}>
      {status}
    </Badge>
  );
};
