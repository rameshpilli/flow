import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ShieldCheck,
  ShieldX,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Eye,
  Plus,
  ChevronDown,
  ChevronRight,
  Wrench,
  Plug,
  PlugZap,
} from 'lucide-react';
import { ComplianceRecord, ComplianceDashboard, ComplianceStatus, Tool } from '@/types';
import { getApiUrl } from '@/utils/runtime';

interface ReviewModalData {
  serverId: string;
  serverName: string;
  action: 'approve' | 'reject' | 'suspend';
}

/**
 * Read-only tool card for compliance reviewers.
 * Shows tool name, description, and input schema — but no toggle or execute.
 */
const ComplianceToolCard: React.FC<{ tool: Tool; serverName: string }> = ({ tool, serverName }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Strip the server name prefix from tool name for cleaner display
  const displayName = tool.name.includes('-')
    ? tool.name.replace(new RegExp(`^${serverName}-`), '')
    : tool.name;

  return (
    <div className="bg-white border border-gray-200 rounded-lg">
      <div
        className="flex justify-between items-center cursor-pointer px-3 py-2"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center space-x-2 flex-1 min-w-0">
          <Wrench className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
          <span className="text-sm font-medium text-gray-900 truncate">{displayName}</span>
          {tool.description && (
            <span className="text-xs text-gray-500 truncate hidden sm:inline">
              — {tool.description}
            </span>
          )}
        </div>
        <div className="flex items-center space-x-2 flex-shrink-0">
          {tool.enabled === false ? (
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded">disabled</span>
          ) : (
            <span className="text-xs px-2 py-0.5 bg-green-50 text-green-600 rounded">enabled</span>
          )}
          <button className="text-gray-400 hover:text-gray-600">
            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="px-3 pb-3 border-t border-gray-100">
          {tool.description && (
            <p className="text-xs text-gray-600 mt-2 mb-2">{tool.description}</p>
          )}
          {tool.inputSchema && Object.keys(tool.inputSchema).length > 0 && (
            <div className="bg-gray-50 rounded p-2 border border-gray-200">
              <h5 className="text-xs font-medium text-gray-700 mb-1">Input Schema</h5>
              <pre className="text-xs text-gray-600 overflow-auto max-h-48">
                {JSON.stringify(tool.inputSchema, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const CompliancePage: React.FC = () => {
  const { t } = useTranslation();
  const [dashboard, setDashboard] = useState<ComplianceDashboard | null>(null);
  const [records, setRecords] = useState<ComplianceRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<ComplianceStatus | 'all'>('all');
  const [reviewModal, setReviewModal] = useState<ReviewModalData | null>(null);
  const [reviewerName, setReviewerName] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [showNewServerForm, setShowNewServerForm] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [newServerData, setNewServerData] = useState({
    serverId: '',
    serverName: '',
    mcpUrl: '',
  });

  // Toggle row expansion for tool visibility
  const toggleRowExpansion = (serverId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(serverId)) {
        next.delete(serverId);
      } else {
        next.add(serverId);
      }
      return next;
    });
  };

  // Fetch dashboard stats and records (with tools enrichment)
  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [dashboardRes, recordsRes] = await Promise.all([
        fetch(getApiUrl('/compliance/dashboard')),
        fetch(getApiUrl('/compliance/servers-with-tools')),
      ]);

      if (!dashboardRes.ok || !recordsRes.ok) {
        throw new Error('Failed to fetch compliance data');
      }

      const dashboardData = await dashboardRes.json();
      const recordsData = await recordsRes.json();

      setDashboard(dashboardData.data || dashboardData);
      setRecords(recordsData.data || recordsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Filter records by status
  const filteredRecords = records.filter(
    (record) => statusFilter === 'all' || record.status === statusFilter
  );

  // Get status badge color
  const getStatusColor = (status: ComplianceStatus) => {
    switch (status) {
      case 'approved':
        return 'bg-green-50 text-green-700 border-green-200';
      case 'pending_review':
        return 'bg-yellow-50 text-yellow-700 border-yellow-200';
      case 'rejected':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'suspended':
        return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'conditionally_approved':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      default:
        return 'bg-gray-50 text-gray-700 border-gray-200';
    }
  };

  // Get status icon
  const getStatusIcon = (status: ComplianceStatus) => {
    switch (status) {
      case 'approved':
        return <CheckCircle className="w-4 h-4" />;
      case 'pending_review':
        return <Clock className="w-4 h-4" />;
      case 'rejected':
        return <XCircle className="w-4 h-4" />;
      case 'suspended':
        return <AlertTriangle className="w-4 h-4" />;
      case 'conditionally_approved':
        return <Eye className="w-4 h-4" />;
      default:
        return <ShieldCheck className="w-4 h-4" />;
    }
  };

  // Get connection status badge
  const getConnectionBadge = (status?: string) => {
    switch (status) {
      case 'connected':
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-green-600">
            <PlugZap className="w-3 h-3" />
            <span>Connected</span>
          </span>
        );
      case 'connecting':
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-yellow-600">
            <Plug className="w-3 h-3" />
            <span>Connecting</span>
          </span>
        );
      case 'disconnected':
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-gray-400">
            <Plug className="w-3 h-3" />
            <span>Disconnected</span>
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center space-x-1 text-xs text-gray-400">
            <Plug className="w-3 h-3" />
            <span>Not registered</span>
          </span>
        );
    }
  };

  // Handle compliance action
  const handleComplianceAction = async (
    serverId: string,
    action: 'approve' | 'reject' | 'suspend',
    reviewer: string,
    notes: string
  ) => {
    try {
      const endpoint = action === 'approve'
        ? `/compliance/approve/${serverId}`
        : action === 'reject'
        ? `/compliance/reject/${serverId}`
        : `/compliance/suspend/${serverId}`;

      const response = await fetch(getApiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          reviewer: reviewer,
          notes: notes,
          reason: notes, // suspend endpoint expects 'reason'
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to ${action} server`);
      }

      // Refresh data
      await fetchData();
      setReviewModal(null);
      setReviewerName('');
      setReviewNotes('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  };

  // Handle new server registration
  const handleRegisterNewServer = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const response = await fetch(getApiUrl('/compliance/check'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          serverId: newServerData.serverId,
          serverName: newServerData.serverName,
          mcpUrl: newServerData.mcpUrl,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to register server for compliance');
      }

      // Reset form and refresh
      setNewServerData({ serverId: '', serverName: '', mcpUrl: '' });
      setShowNewServerForm(false);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    }
  };

  return (
    <div>
      {/* Page Header */}
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Compliance Management</h1>
        <button
          onClick={() => setShowNewServerForm(!showNewServerForm)}
          className="px-4 py-2 bg-blue-100 text-blue-800 rounded hover:bg-blue-200 flex items-center transition-all duration-200"
        >
          <Plus className="w-4 h-4 mr-2" />
          Register Server
        </button>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-gray-600">{error}</p>
            <button
              onClick={() => setError(null)}
              className="ml-4 text-gray-500 hover:text-gray-700 transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* New Server Form */}
      {showNewServerForm && (
        <div className="mb-6 bg-white shadow rounded-lg p-6 border-l-4 border-blue-500">
          <h2 className="text-lg font-semibold mb-4">Register Server for Compliance</h2>
          <form onSubmit={handleRegisterNewServer} className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Server ID
                </label>
                <input
                  type="text"
                  required
                  value={newServerData.serverId}
                  onChange={(e) =>
                    setNewServerData({ ...newServerData, serverId: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g., server-1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Server Name
                </label>
                <input
                  type="text"
                  required
                  value={newServerData.serverName}
                  onChange={(e) =>
                    setNewServerData({ ...newServerData, serverName: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="e.g., My Server"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  MCP URL
                </label>
                <input
                  type="url"
                  value={newServerData.mcpUrl}
                  onChange={(e) =>
                    setNewServerData({ ...newServerData, mcpUrl: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="https://..."
                />
              </div>
            </div>
            <div className="flex space-x-2">
              <button
                type="submit"
                className="px-4 py-2 bg-green-100 text-green-800 rounded hover:bg-green-200 transition-colors"
              >
                Submit for Review
              </button>
              <button
                type="button"
                onClick={() => setShowNewServerForm(false)}
                className="px-4 py-2 bg-gray-100 text-gray-800 rounded hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Dashboard Stats */}
      {dashboard && !isLoading && (
        <div className="grid grid-cols-5 gap-4 mb-8">
          <div className="bg-white shadow rounded-lg p-4 border-l-4 border-blue-500">
            <div className="text-2xl font-bold text-gray-900">{dashboard.total}</div>
            <div className="text-sm text-gray-600">Total Servers</div>
          </div>
          <div className="bg-white shadow rounded-lg p-4 border-l-4 border-green-500">
            <div className="text-2xl font-bold text-green-700">{dashboard.approved}</div>
            <div className="text-sm text-gray-600">Approved</div>
          </div>
          <div className="bg-white shadow rounded-lg p-4 border-l-4 border-yellow-500">
            <div className="text-2xl font-bold text-yellow-700">{dashboard.pendingReview}</div>
            <div className="text-sm text-gray-600">Pending Review</div>
          </div>
          <div className="bg-white shadow rounded-lg p-4 border-l-4 border-red-500">
            <div className="text-2xl font-bold text-red-700">{dashboard.rejected}</div>
            <div className="text-sm text-gray-600">Rejected</div>
          </div>
          <div className="bg-white shadow rounded-lg p-4 border-l-4 border-orange-500">
            <div className="text-2xl font-bold text-orange-700">{dashboard.suspended}</div>
            <div className="text-sm text-gray-600">Suspended</div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="bg-white shadow rounded-lg p-6 flex items-center justify-center">
          <div className="flex flex-col items-center">
            <svg
              className="animate-spin h-10 w-10 text-blue-500 mb-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            <p className="text-gray-600">Loading compliance data...</p>
          </div>
        </div>
      )}

      {/* Status Filter and Table */}
      {!isLoading && records.length > 0 && (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          {/* Filter Bar */}
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Filter by Status
              </label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as ComplianceStatus | 'all')}
                className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All</option>
                <option value="approved">Approved</option>
                <option value="pending_review">Pending Review</option>
                <option value="rejected">Rejected</option>
                <option value="suspended">Suspended</option>
                <option value="conditionally_approved">Conditionally Approved</option>
              </select>
            </div>
            <div className="text-sm text-gray-600">
              Showing {filteredRecords.length} of {records.length} servers
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase w-8">
                    {/* Expand toggle */}
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Server Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Connection
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Tools
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Score
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Reviewed By
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredRecords.map((record) => {
                  const isExpanded = expandedRows.has(record.serverId);
                  const toolCount = record.toolCount || record.tools?.length || 0;
                  const hasTools = toolCount > 0;

                  return (
                    <React.Fragment key={record.id}>
                      {/* Main row */}
                      <tr
                        className={`hover:bg-gray-50 cursor-pointer ${isExpanded ? 'bg-blue-50/30' : ''}`}
                        onClick={() => hasTools && toggleRowExpansion(record.serverId)}
                      >
                        {/* Expand chevron */}
                        <td className="px-4 py-4 w-8">
                          {hasTools ? (
                            <button
                              className="text-gray-400 hover:text-gray-600"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleRowExpansion(record.serverId);
                              }}
                            >
                              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            </button>
                          ) : (
                            <span className="text-gray-200">
                              <ChevronRight size={16} />
                            </span>
                          )}
                        </td>

                        {/* Server Name + URL */}
                        <td className="px-4 py-4">
                          <div className="text-sm font-medium text-gray-900">
                            {record.serverName}
                          </div>
                          {record.mcpUrl && (
                            <div className="text-xs text-gray-500 truncate max-w-xs" title={record.mcpUrl}>
                              {record.mcpUrl}
                            </div>
                          )}
                        </td>

                        {/* Connection Status */}
                        <td className="px-4 py-4 whitespace-nowrap">
                          {getConnectionBadge(record.connectionStatus)}
                        </td>

                        {/* Tool Count */}
                        <td className="px-4 py-4 whitespace-nowrap">
                          {hasTools ? (
                            <span className="inline-flex items-center space-x-1 text-xs font-medium text-blue-700 bg-blue-50 px-2 py-1 rounded-full border border-blue-200">
                              <Wrench className="w-3 h-3" />
                              <span>{toolCount} tool{toolCount !== 1 ? 's' : ''}</span>
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400">—</span>
                          )}
                        </td>

                        {/* Compliance Status */}
                        <td className="px-4 py-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center space-x-1 px-3 py-1 rounded-full text-xs font-medium border ${getStatusColor(
                              record.status
                            )}`}
                          >
                            {getStatusIcon(record.status)}
                            <span>{record.status.replace(/_/g, ' ')}</span>
                          </span>
                        </td>

                        {/* Score */}
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600">
                          {record.complianceScore !== undefined && record.complianceScore !== null
                            ? `${record.complianceScore}%`
                            : '-'}
                        </td>

                        {/* Reviewed By */}
                        <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-600">
                          {record.reviewedBy || '-'}
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-4 whitespace-nowrap text-sm space-x-2" onClick={(e) => e.stopPropagation()}>
                          {record.status === 'pending_review' && (
                            <>
                              <button
                                onClick={() =>
                                  setReviewModal({
                                    serverId: record.serverId,
                                    serverName: record.serverName,
                                    action: 'approve',
                                  })
                                }
                                className="inline-block px-3 py-1 bg-green-100 text-green-800 rounded hover:bg-green-200 transition-colors text-xs font-medium"
                              >
                                Approve
                              </button>
                              <button
                                onClick={() =>
                                  setReviewModal({
                                    serverId: record.serverId,
                                    serverName: record.serverName,
                                    action: 'reject',
                                  })
                                }
                                className="inline-block px-3 py-1 bg-red-100 text-red-800 rounded hover:bg-red-200 transition-colors text-xs font-medium"
                              >
                                Reject
                              </button>
                              <button
                                onClick={() =>
                                  setReviewModal({
                                    serverId: record.serverId,
                                    serverName: record.serverName,
                                    action: 'suspend',
                                  })
                                }
                                className="inline-block px-3 py-1 bg-orange-100 text-orange-800 rounded hover:bg-orange-200 transition-colors text-xs font-medium"
                              >
                                Suspend
                              </button>
                            </>
                          )}
                          {record.status === 'approved' && (
                            <button
                              onClick={() =>
                                setReviewModal({
                                  serverId: record.serverId,
                                  serverName: record.serverName,
                                  action: 'suspend',
                                })
                              }
                              className="inline-block px-3 py-1 bg-orange-100 text-orange-800 rounded hover:bg-orange-200 transition-colors text-xs font-medium"
                            >
                              Suspend
                            </button>
                          )}
                          {(record.status === 'rejected' || record.status === 'suspended') && (
                            <span className="text-gray-400 text-xs">—</span>
                          )}
                        </td>
                      </tr>

                      {/* Expanded tools row */}
                      {isExpanded && record.tools && record.tools.length > 0 && (
                        <tr>
                          <td colSpan={8} className="px-0 py-0">
                            <div className="bg-gray-50 border-t border-b border-gray-200 px-8 py-4">
                              <div className="flex items-center space-x-2 mb-3">
                                <Wrench className="w-4 h-4 text-gray-500" />
                                <h4 className="text-sm font-semibold text-gray-700">
                                  Tools exposed by {record.serverName}
                                </h4>
                                <span className="text-xs text-gray-500">
                                  ({record.tools.length} tool{record.tools.length !== 1 ? 's' : ''})
                                </span>
                              </div>
                              <div className="space-y-2 max-h-96 overflow-y-auto">
                                {record.tools.map((tool, index) => (
                                  <ComplianceToolCard
                                    key={tool.name || index}
                                    tool={tool}
                                    serverName={record.serverId}
                                  />
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Empty state */}
          {filteredRecords.length === 0 && (
            <div className="px-6 py-8 text-center">
              <ShieldX className="w-12 h-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-600">No servers found for the selected status.</p>
            </div>
          )}
        </div>
      )}

      {/* No Data */}
      {!isLoading && records.length === 0 && (
        <div className="bg-white shadow rounded-lg p-6 text-center">
          <ShieldX className="w-12 h-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-600">No compliance records found.</p>
        </div>
      )}

      {/* Review Modal */}
      {reviewModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg p-6 max-w-md w-full mx-4">
            <h2 className="text-lg font-semibold mb-4">
              {reviewModal.action.charAt(0).toUpperCase() + reviewModal.action.slice(1)}{' '}
              Server
            </h2>
            <p className="text-gray-600 mb-4">Server: {reviewModal.serverName}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Reviewer Name
                </label>
                <input
                  type="text"
                  value={reviewerName}
                  onChange={(e) => setReviewerName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Your name"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {reviewModal.action === 'suspend' ? 'Reason for Suspension' : 'Review Notes'}
                </label>
                <textarea
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                  placeholder={
                    reviewModal.action === 'suspend'
                      ? 'Enter reason for suspension...'
                      : 'Enter your review notes...'
                  }
                />
              </div>

              <div className="flex space-x-3">
                <button
                  onClick={() =>
                    handleComplianceAction(
                      reviewModal.serverId,
                      reviewModal.action,
                      reviewerName,
                      reviewNotes
                    )
                  }
                  className={`flex-1 px-4 py-2 rounded font-medium text-white transition-colors ${
                    reviewModal.action === 'approve'
                      ? 'bg-green-600 hover:bg-green-700'
                      : reviewModal.action === 'reject'
                      ? 'bg-red-600 hover:bg-red-700'
                      : 'bg-orange-600 hover:bg-orange-700'
                  }`}
                >
                  {reviewModal.action.charAt(0).toUpperCase() + reviewModal.action.slice(1)}
                </button>
                <button
                  onClick={() => {
                    setReviewModal(null);
                    setReviewerName('');
                    setReviewNotes('');
                  }}
                  className="flex-1 px-4 py-2 bg-gray-200 text-gray-800 rounded font-medium hover:bg-gray-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CompliancePage;
