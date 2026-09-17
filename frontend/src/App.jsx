import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ModalProvider } from './contexts/ModalContext';
import SessionMonitor from './components/SessionMonitor';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ResourceOnboarding from './pages/ResourceOnboarding';
import GovernanceForm from './pages/GovernanceForm';
import PrerequisiteClassification from './pages/PrerequisiteClassification';
import TaskCreation from './pages/TaskCreation';
import AgentAnalysis from './pages/AgentAnalysis';
import GitHubCallback from './pages/GitHubCallback';
import AzureDevOpsCallback from './pages/AzureDevOpsCallback';
import SsoCallback from './pages/SsoCallback';
import LandingPage from './pages/LandingPage';
import Documentation from './pages/Documentation';
import OrganizationAdmin from './pages/OrganizationAdmin';
import GovernanceManagement from './pages/GovernanceManagement';
import AppPreview from './pages/AppPreview';
import AppLayout from './components/AppLayout';
import AgentsPage from './components/AgentsPage';
import Plugins from './pages/Plugins';
import InviteSignup from './pages/InviteSignup';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import ShareDocument from './pages/ShareDocument';
import SharedDocumentViewer from './pages/SharedDocumentViewer';
import Billing from './pages/Billing';
import SuperAdminDashboard from './pages/SuperAdminDashboard';
import SuperAdminCapacityRequests from './pages/SuperAdminCapacityRequests';
import SuperAdminGlobalBilling from './pages/SuperAdminGlobalBilling';
import SuperAdminRoles from './pages/SuperAdminRoles';
import SuperAdminAuditLogs from './pages/SuperAdminAuditLogs';
import SuperAdminTokenOps from './pages/SuperAdminTokenOps';
import SupportTickets from './pages/SupportTickets';

function App() {
  return (
    <ModalProvider>
      <Router>
        <SessionMonitor />
        <Routes>
        {/* Public routes — no sidebar/navbar */}
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/invite" element={<InviteSignup />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/" element={<LandingPage />} />
        <Route path="/docs" element={<Documentation />} />
        <Route path="/github/callback" element={<GitHubCallback />} />
        <Route path="/azure-devops/callback" element={<AzureDevOpsCallback />} />
        <Route path="/sso/callback" element={<SsoCallback />} />
        <Route path="/shared/:shareToken" element={<SharedDocumentViewer />} />

        {/* Authenticated routes — wrapped with AppLayout for uniform sidebar/navbar */}
        <Route path="/dashboard" element={
          <AppLayout>
            {(layoutProps) => <Dashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/status-dashboard" element={
          <AppLayout>
            {(layoutProps) => <Dashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/agents" element={
          <AppLayout>
            {(layoutProps) => <AgentsPage {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/resource-onboarding" element={
          <AppLayout>
            {(layoutProps) => <ResourceOnboarding {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/a/:projectToken" element={
          <AppLayout>
            {(layoutProps) => <Dashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/new-project" element={
          <AppLayout>
            {(layoutProps) => <GovernanceForm {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/new-project/governance" element={
          <AppLayout>
            {(layoutProps) => <GovernanceForm {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/prerequisites" element={
          <AppLayout>
            {(layoutProps) => <PrerequisiteClassification {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/organization-admin" element={
          <AppLayout>
            {(layoutProps) => <OrganizationAdmin {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/task-creation" element={
          <AppLayout>
            {(layoutProps) => <TaskCreation {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/agent-analysis" element={
          <AppLayout>
            {(layoutProps) => <AgentAnalysis {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/plugins" element={
          <AppLayout>
            {(layoutProps) => <Plugins {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/governance-management" element={
          <AppLayout>
            {(layoutProps) => <GovernanceManagement {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/share-doc" element={
          <AppLayout>
            {(layoutProps) => <ShareDocument {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/billing" element={
          <AppLayout>
            {(layoutProps) => <Billing {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/tickets" element={
          <AppLayout>
            {(layoutProps) => <SupportTickets {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/tickets" element={
          <AppLayout>
            {(layoutProps) => <SupportTickets {...layoutProps} />}
          </AppLayout>
        } />
        {/* Super Admin routes */}
        <Route path="/superadmin/dashboard" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminDashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/requests" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminCapacityRequests {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/organizations" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminDashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/global-billing" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminGlobalBilling {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/tokenops" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminTokenOps {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/roles" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminRoles {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/capacity" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminDashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/superadmin/logs" element={
          <AppLayout>
            {(layoutProps) => <SuperAdminAuditLogs {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/app/:projectId" element={
          <AppPreview />
        } />
      </Routes>
    </Router>
    </ModalProvider>
  );
}

export default App;
