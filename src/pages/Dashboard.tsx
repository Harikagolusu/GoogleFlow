import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, ChevronRight } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import type { Workflow } from '../types/workflow';
import type { Service } from '../types/service';
import { ServiceLogo } from '../components/ServiceLogo';

export const Dashboard: React.FC = () => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([workflowService.getWorkflows(), workflowService.getServices()]).then(([w, s]) => {
      setWorkflows(w);
      setServices(s);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="p-8 text-center text-gray-500 mt-20">Loading...</div>;
  }

  const featuredFlow = workflows.find(w => w.readiness < 100) || workflows[0];
  const recentFlows = workflows.filter(w => w.id !== featuredFlow?.id);

  return (
    <div className="flex flex-col items-center justify-center pt-24 px-6 w-full">
      <div className="text-center mb-10">
        <p className="text-gray-500 mb-4 font-medium">Good morning 👋</p>
        <h1 className="text-5xl md:text-6xl text-gray-900 mb-10">What would you like to accomplish?</h1>

        <div className="w-full max-w-2xl mx-auto relative bg-[#F8FAFC] rounded-full p-2 pl-6 flex items-center border border-gray-200/50 shadow-sm transition-all focus-within:ring-2 focus-within:ring-google-blue/20 focus-within:border-google-blue/30">
          <input
            type="text"
            placeholder="Plan my trip to Delhi..."
            className="flex-1 bg-transparent border-none outline-none text-gray-700 placeholder-gray-400 text-lg"
          />
          <Link
            to="/ask"
            className="bg-google-blue hover:bg-blue-600 text-white rounded-full px-6 py-3 font-medium flex items-center gap-2 transition-colors"
          >
            <Sparkles className="w-4 h-4" />
            Ask LifeFlow
          </Link>
        </div>

        <div className="flex flex-wrap justify-center gap-3 mt-6">
          {['Plan my trip to Delhi...', 'Prepare for my interview...', 'Help me organize my passport appointment...'].map((suggestion, idx) => (
            <Link
              key={idx}
              to="/ask"
              className="px-5 py-2 rounded-full border border-gray-200 bg-white/50 text-gray-500 text-sm hover:bg-white hover:text-gray-900 transition-colors"
            >
              {suggestion}
            </Link>
          ))}
        </div>
      </div>

      {featuredFlow && (
        <div className="w-full max-w-3xl mt-16">
          <Link to={`/flows/${featuredFlow.id}`} className="block">
            <div className="bg-white rounded-[2rem] p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
              <div className="flex justify-between items-start mb-6">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-full bg-[#F4F4F5] flex items-center justify-center text-2xl">
                    {featuredFlow.emoji}
                  </div>
                  <div>
                    <h3 className="text-2xl font-medium text-gray-900 tracking-tight">{featuredFlow.title}</h3>
                    <p className="text-gray-500 text-sm mt-0.5">{featuredFlow.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-serif text-gray-900">{featuredFlow.readiness}%</div>
                  <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mt-1">Ready</div>
                </div>
              </div>

              <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden mb-4">
                <div
                  className="bg-google-blue h-full rounded-full transition-all duration-1000 ease-out"
                  style={{ width: `${featuredFlow.readiness}%` }}
                />
              </div>

              <div className="flex items-center gap-6 mb-8">
                {featuredFlow.connectedServices.slice(0, 3).map((service, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
                    <ServiceLogo name={service} className="w-4 h-4" />
                    {service}
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between pt-6 border-t border-gray-50">
                <span className="text-gray-500 text-sm">
                  {featuredFlow.checklist.filter(i => !i.completed).length > 0
                    ? `${featuredFlow.checklist.filter(i => !i.completed).length} things still need your attention`
                    : 'Everything is ready!'}
                </span>
                <span className="flex items-center gap-2 text-google-blue font-medium hover:text-blue-700 transition-colors">
                  Continue
                  <ChevronRight className="w-4 h-4" />
                </span>
              </div>
            </div>
          </Link>
        </div>
      )}

      <div className="w-full max-w-5xl mt-20">
        <h2 className="text-2xl font-serif text-gray-900 mb-6">Everything working for you</h2>
        <div className="flex flex-wrap gap-4">
          {services.map(service => (
            <Link
              key={service.id}
              to={`/service/${service.name.toLowerCase()}`}
              className="flex items-center gap-3 bg-white rounded-2xl px-5 py-3 border border-gray-100 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="w-8 h-8 rounded-xl bg-[#F4F4F5] flex items-center justify-center text-gray-600">
                <ServiceLogo name={service.name} className="w-5 h-5" />
              </div>
              <span className="text-sm font-medium text-gray-700">{service.name}</span>
            </Link>
          ))}
        </div>
      </div>

      {recentFlows.length > 0 && (
        <div className="w-full max-w-5xl mt-20">
          <div className="flex justify-between items-end mb-6">
            <h2 className="text-2xl font-serif text-gray-900">Recent LifeFlows</h2>
            <Link to="/flows" className="text-sm font-medium text-gray-500 hover:text-gray-900 transition-colors flex items-center gap-1">
              See all <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
          <div className="space-y-3">
            {recentFlows.map(flow => (
              <Link
                key={flow.id}
                to={`/flows/${flow.id}`}
                className="flex items-center justify-between bg-white rounded-2xl px-6 py-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-center gap-4">
                  <span className="text-2xl">{flow.emoji}</span>
                  <div>
                    <h3 className="font-medium text-gray-900">{flow.title}</h3>
                    <p className="text-sm text-gray-500">{flow.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <span className="text-lg font-serif text-gray-900">{flow.readiness}%</span>
                  <span className="text-xs text-gray-400 block">ready</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
