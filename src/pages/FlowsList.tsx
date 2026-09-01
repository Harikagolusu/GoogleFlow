import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { workflowService } from '../services/workflowService';
import type { Workflow } from '../types/workflow';

export const FlowsList: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    workflowService.getWorkflows().then(data => {
      setWorkflows(data);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-gray-500 mt-20">Loading your flows...</div>;
  }

  const activeCount = workflows.filter(w => w.status !== 'Completed').length;

  return (
    <div className="pt-12 px-6 max-w-5xl mx-auto">
      <header className="mb-12 text-center">
        <h1 className="text-4xl md:text-5xl font-serif text-gray-900 mb-4">My LifeFlows</h1>
        <p className="text-lg text-gray-500">{activeCount} active · nothing overdue</p>
      </header>

      <div className="space-y-3">
        {workflows.map(workflow => (
          <Link
            key={workflow.id}
            to={`/flows/${workflow.id}`}
            className="flex items-center justify-between bg-white rounded-2xl px-6 py-5 border border-gray-100 shadow-sm hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] transition-all"
          >
            <div className="flex items-center gap-4">
              <span className="text-3xl">{workflow.emoji}</span>
              <div>
                <h3 className="text-lg font-medium text-gray-900 tracking-tight">{workflow.title}</h3>
                <p className="text-sm text-gray-500 mt-0.5">{workflow.date}</p>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-serif text-gray-900">{workflow.readiness}%</div>
              <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium">Ready</div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
};
