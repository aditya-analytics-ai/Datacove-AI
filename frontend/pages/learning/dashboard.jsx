import { useState, useEffect } from 'react';

export default function LearningDashboard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchLearningStatus();
  }, []);

  const fetchLearningStatus = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/learning/status');
      const data = await response.json();
      setStatus(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <h3 className="text-red-800 font-medium">Error Loading Learning Status</h3>
        <p className="text-red-600 text-sm">{error}</p>
      </div>
    );
  }

  const statCards = [
    { label: 'Datasets Analyzed', value: status?.datasets_processed || 0, color: 'bg-emerald-500' },
    { label: 'Avg Quality Score', value: `${(status?.avg_quality_score || 0).toFixed(1)}%`, color: 'bg-blue-500' },
    { label: 'Total Rows Processed', value: (status?.total_rows || 0).toLocaleString(), color: 'bg-purple-500' },
    { label: 'Total Cells Cleaned', value: (status?.total_cells_cleaned || 0).toLocaleString(), color: 'bg-amber-500' },
  ];

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'domains', label: 'Domains' },
    { id: 'rules', label: 'Cleaning Rules' },
    { id: 'patterns', label: 'Patterns' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Learning Dashboard</h1>
          <p className="text-gray-600">DataCoVe Intelligent Cleaning System</p>
        </div>
        <button
          onClick={fetchLearningStatus}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition"
        >
          Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center gap-4">
              <div className={`${card.color} p-3 rounded-lg`}>
                <div className="w-8 h-8 bg-white/20 rounded"></div>
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{card.value}</p>
                <p className="text-sm text-gray-500">{card.label}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 font-medium border-b-2 transition ${
                activeTab === tab.id
                  ? 'border-emerald-500 text-emerald-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold">Learning System Overview</h3>
            
            {/* Domain Distribution */}
            <div>
              <h4 className="font-medium text-gray-700 mb-3">Domain Distribution</h4>
              <div className="space-y-2">
                {status?.domains && Object.entries(status.domains).map(([domain, count]) => (
                  <div key={domain} className="flex items-center gap-3">
                    <span className="w-24 text-sm text-gray-600 capitalize">{domain}</span>
                    <div className="flex-1 bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-emerald-500 h-2 rounded-full"
                        style={{ width: `${(count / status.datasets_processed) * 100}%` }}
                      ></div>
                    </div>
                    <span className="text-sm text-gray-500">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Cleaning Actions */}
            <div>
              <h4 className="font-medium text-gray-700 mb-3">Cleaning Actions Used</h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {status?.cleaning_actions && Object.entries(status.cleaning_actions)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 8)
                  .map(([action, count]) => (
                    <div key={action} className="bg-gray-50 rounded-lg p-3">
                      <p className="text-2xl font-bold text-emerald-600">{count}</p>
                      <p className="text-xs text-gray-500">{action.replace(/_/g, ' ')}</p>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'domains' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Domain Statistics</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Domain</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">Count</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">Avg Quality</th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">Avg Cells Cleaned</th>
                  </tr>
                </thead>
                <tbody>
                  {status?.domains && Object.entries(status.domains).map(([domain, count]) => (
                    <tr key={domain} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-3 px-4 capitalize font-medium">{domain}</td>
                      <td className="py-3 px-4 text-right">{count}</td>
                      <td className="py-3 px-4 text-right">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          (status.domain_stats?.[domain]?.avg_quality || 0) >= 90
                            ? 'bg-green-100 text-green-700'
                            : (status.domain_stats?.[domain]?.avg_quality || 0) >= 70
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {(status.domain_stats?.[domain]?.avg_quality || 0).toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {(status.domain_stats?.[domain]?.avg_cells_cleaned || 0).toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'rules' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Learned Cleaning Rules</h3>
            <div className="grid gap-3">
              {status?.cleaning_actions && Object.entries(status.cleaning_actions)
                .sort((a, b) => b[1] - a[1])
                .map(([action, count]) => {
                  const confidence = Math.min(100, (count / 100) * 100);
                  return (
                    <div key={action} className="flex items-center gap-4 p-3 bg-gray-50 rounded-lg">
                      <div className="flex-1">
                        <p className="font-medium text-gray-900">{action.replace(/_/g, ' ')}</p>
                        <p className="text-sm text-gray-500">Applied {count} times</p>
                      </div>
                      <div className="w-32">
                        <div className="bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-emerald-500 h-2 rounded-full"
                            style={{ width: `${confidence}%` }}
                          ></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1 text-right">{confidence.toFixed(0)}% confidence</p>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {activeTab === 'patterns' && (
          <div className="space-y-6">
            <h3 className="text-lg font-semibold">Common Patterns Detected</h3>
            
            <div>
              <h4 className="font-medium text-gray-700 mb-3">Column Types</h4>
              <div className="flex flex-wrap gap-2">
                {status?.column_types && Object.entries(status.column_types).map(([type, data]) => (
                  <span key={type} className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
                    {type}: {data.total} ({data.unique} unique)
                  </span>
                ))}
              </div>
            </div>

            <div>
              <h4 className="font-medium text-gray-700 mb-3">Common Issues</h4>
              <div className="space-y-2">
                {status?.common_issues && Object.entries(status.common_issues).map(([issue, count]) => (
                  <div key={issue} className="flex items-center gap-3 p-2 bg-red-50 rounded">
                    <div className="w-2 h-2 bg-red-500 rounded-full"></div>
                    <span className="text-sm text-gray-700 capitalize flex-1">{issue.replace(/_/g, ' ')}</span>
                    <span className="text-sm text-red-600 font-medium">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Last Updated */}
      <p className="text-center text-sm text-gray-500">
        Last updated: {status?.last_updated ? new Date(status.last_updated).toLocaleString() : 'Never'}
      </p>
    </div>
  );
}
