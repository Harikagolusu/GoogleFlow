import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Check } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import type { Workflow } from '../types/workflow';
import { ServiceLogo } from '../components/ServiceLogo';

export const WorkflowDetails: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      workflowService.getWorkflowById(id).then(data => {
        setWorkflow(data || null);
        setLoading(false);
      });
    }
  }, [id]);

  const handleToggle = async (itemId: string) => {
    if (!workflow) return;
    const updated = await workflowService.toggleChecklistItem(workflow.id, itemId);
    setWorkflow(updated);
  };

  if (loading) {
    return <div className="p-8 text-center text-gray-500 mt-20">Loading flow details...</div>;
  }

  if (!workflow) {
    return <div className="p-8 text-center text-gray-500 mt-20">Flow not found.</div>;
  }

  const completedCount = workflow.checklist.filter(i => i.completed).length;
  const pendingCount = workflow.checklist.length - completedCount;

  return (
    <div className="pt-12 px-6 max-w-5xl mx-auto">
      <Link
        to="/flows"
        className="flex items-center gap-2 text-gray-400 hover:text-gray-900 mb-12 transition-colors font-medium text-sm"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back</span>
      </Link>

      <header className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <h1 className="text-4xl md:text-5xl font-serif text-gray-900 mb-3">
            <span className="mr-3">{workflow.emoji}</span>
            {workflow.title}
          </h1>
          <p className="text-xl text-gray-500 tracking-tight">{workflow.date}</p>
        </div>
        <div className="text-left md:text-right">
          <div className="text-4xl font-serif text-gray-900">{workflow.readiness}%</div>
          <div className="text-sm text-gray-400 font-medium">Ready</div>
        </div>
      </header>

      {workflow.nextUp && (
        <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-2">Next up</h3>
          <p className="text-lg font-medium text-gray-900">{workflow.nextUp}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        <div className="lg:col-span-7">
          <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <h3 className="text-2xl font-serif text-gray-900 mb-8">Your checklist</h3>
            <div className="space-y-3">
              {workflow.checklist.map(item => (
                <button
                  key={item.id}
                  onClick={() => handleToggle(item.id)}
                  className={`w-full flex items-center gap-4 p-4 rounded-2xl border text-left transition-all duration-300 ${
                    item.completed
                      ? 'bg-[#F8FAFC] border-gray-100'
                      : 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm'
                  }`}
                >
                  <div className={`w-6 h-6 rounded-full border flex items-center justify-center transition-colors ${
                    item.completed ? 'bg-gray-900 border-gray-900 text-white' : 'border-gray-300'
                  }`}>
                    {item.completed && <Check className="w-3.5 h-3.5" />}
                  </div>
                  <span className={`text-base tracking-tight ${item.completed ? 'text-gray-400 line-through' : 'text-gray-800 font-medium'}`}>
                    {item.title}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="lg:col-span-5 space-y-6">
          <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <h3 className="text-2xl font-serif text-gray-900 mb-6">Connected</h3>
            <div className="flex flex-wrap gap-3">
              {workflow.connectedServices.map((service, i) => (
                <Link
                  key={i}
                  to={`/service/${service.toLowerCase()}`}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-full bg-[#F4F4F5] text-sm font-medium text-gray-700 hover:bg-gray-200 transition-colors"
                >
                  <ServiceLogo name={service} className="w-4 h-4" />
                  {service}
                </Link>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
            <h3 className="text-2xl font-serif text-gray-900 mb-4">Safety</h3>
            <p className="text-gray-500">
              {pendingCount > 0
                ? `${pendingCount} thing${pendingCount > 1 ? 's' : ''} need${pendingCount === 1 ? 's' : ''} your attention`
                : 'Everything is ready!'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
