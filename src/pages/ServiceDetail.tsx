import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Mail } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import type { Service } from '../types/service';
import { ServiceLogo } from '../components/ServiceLogo';

export const ServiceDetail: React.FC = () => {
  const { name } = useParams<{ name: string }>();
  const [service, setService] = useState<Service | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (name) {
      workflowService.getServiceByName(name).then(data => {
        setService(data || null);
        setLoading(false);
      });
    }
  }, [name]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500 mt-20">Loading...</div>;
  }

  if (!service) {
    return <div className="p-8 text-center text-gray-500 mt-20">Service not found.</div>;
  }

  return (
    <div className="pt-12 px-6 max-w-3xl mx-auto">
      <Link
        to="/"
        className="flex items-center gap-2 text-gray-400 hover:text-gray-900 mb-12 transition-colors font-medium text-sm"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back</span>
      </Link>

      <header className="mb-12">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-14 h-14 rounded-[1.25rem] bg-[#F4F4F5] flex items-center justify-center text-gray-700">
            <ServiceLogo name={service.name} className="w-9 h-9" />
          </div>
          <h1 className="text-4xl md:text-5xl font-serif text-gray-900">{service.name}</h1>
        </div>
        <p className="text-xl text-gray-500">{service.description}</p>
      </header>

      {service.relatedEmails && service.relatedEmails.length > 0 && (
        <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)] mb-8">
          <h3 className="text-2xl font-serif text-gray-900 mb-6">We found related items</h3>
          <div className="space-y-4">
            {service.relatedEmails.map((email, i) => (
              <div key={i} className="flex items-start gap-4 p-4 rounded-2xl bg-[#F8FAFC] border border-gray-100">
                <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center text-red-500 flex-shrink-0">
                  <Mail className="w-5 h-5" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">{email.subject}</p>
                  <p className="text-sm text-gray-500">{email.from} · {email.time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-4">Connected to</h3>
        <Link
          to="/flows/interview"
          className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-[#F8FAFC] border border-gray-100 hover:shadow-sm transition-shadow"
        >
          <span className="text-2xl">💼</span>
          <span className="font-medium text-gray-900">AI Engineer Interview</span>
        </Link>
        <Link
          to="/flows"
          className="mt-4 inline-flex items-center gap-2 text-google-blue font-medium hover:text-blue-700 transition-colors text-sm"
        >
          Open LifeFlow →
        </Link>
      </div>
    </div>
  );
};
