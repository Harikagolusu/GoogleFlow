import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Loader2 } from 'lucide-react';
import { workflowService } from '../services/workflowService';
import { ApiError } from '../services/http';

export const Ask: React.FC = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const suggestions = [
    'Plan my trip to Delhi...',
    'Prepare for my interview...',
    'Help me organize my passport appointment...',
  ];

  const canSubmit = query.trim().length > 0 && !loading;

  const handleSubmit = async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError('');
    try {
      const workflow = await workflowService.ask(trimmed);
      navigate(`/flows/${workflow.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Something went wrong while creating your LifeFlow. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pt-12 px-6 max-w-3xl mx-auto">
      <header className="mb-12 text-center">
        <h1 className="text-4xl md:text-5xl font-serif text-gray-900 mb-4">Ask LifeFlow</h1>
        <p className="text-lg text-gray-500">Say it the way you'd say it to a friend. We'll handle the rest.</p>
      </header>

      <div className="bg-white rounded-3xl p-8 border border-gray-100 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-google-blue flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">LifeFlow Assistant</p>
            <p className="text-xs text-gray-400">Describe a situation and I'll turn it into a LifeFlow</p>
          </div>
        </div>

        <textarea
          value={query}
          onChange={(e) => { setQuery(e.target.value); if (error) setError(''); }}
          placeholder="Describe what you'd like to accomplish..."
          disabled={loading}
          className="w-full h-32 bg-[#F8FAFC] rounded-2xl p-5 border border-gray-200 outline-none text-gray-700 placeholder-gray-400 text-lg resize-none transition-all focus:ring-2 focus:ring-google-blue/20 focus:border-google-blue/30 disabled:opacity-60"
        />

        {error && (
          <p className="mt-3 text-sm text-red-500">{error}</p>
        )}

        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="mt-4 w-full bg-google-blue hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-full py-3 font-medium flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Creating your LifeFlow...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Create My LifeFlow
            </>
          )}
        </button>
      </div>

      <div className="flex flex-wrap justify-center gap-3 mt-8">
        {suggestions.map((suggestion, idx) => (
          <button
            key={idx}
            onClick={() => setQuery(suggestion)}
            disabled={loading}
            className="px-5 py-2 rounded-full border border-gray-200 bg-white/50 text-gray-500 text-sm hover:bg-white hover:text-gray-900 transition-colors disabled:opacity-60"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
};
