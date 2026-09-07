import React from 'react';

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className = '',
  width,
  height,
}) => {
  return (
    <div
      className={`bg-border animate-pulse rounded ${className}`}
      style={{
        width: width ?? '100%',
        height: height ?? '1rem',
      }}
    />
  );
};

export const SkeletonText: React.FC<{ lines?: number; className?: string }> = ({
  lines = 1,
  className = '',
}) => {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="0.75rem"
          width={i === lines - 1 && lines > 1 ? '75%' : '100%'}
        />
      ))}
    </div>
  );
};

export const SkeletonCard: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`bg-surface rounded-xl border border-border-light p-6 ${className}`}>
    <div className="flex items-center gap-4 mb-4">
      <Skeleton width="3rem" height="3rem" className="rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton height="1rem" width="60%" />
        <Skeleton height="0.75rem" width="40%" />
      </div>
      <Skeleton width="4rem" height="2rem" />
    </div>
    <SkeletonText lines={3} />
  </div>
);

export const SkeletonListItem: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div className={`flex items-center gap-4 p-4 bg-surface rounded-xl border border-border-light ${className}`}>
    <Skeleton width="2.5rem" height="2.5rem" className="rounded-lg" />
    <div className="flex-1 space-y-2">
      <Skeleton height="0.875rem" width="50%" />
      <Skeleton height="0.75rem" width="30%" />
    </div>
  </div>
);

export const PageSkeleton: React.FC = () => (
  <div className="pt-12 px-4 md:px-6 max-w-6xl mx-auto space-y-6">
    <div className="space-y-4">
      <Skeleton height="2.5rem" width="40%" className="max-w-md" />
      <Skeleton height="1.25rem" width="60%" />
    </div>
    <Skeleton height="8rem" className="rounded-2xl" />
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {[1, 2, 3].map(i => (
        <SkeletonCard key={i} />
      ))}
    </div>
  </div>
);
