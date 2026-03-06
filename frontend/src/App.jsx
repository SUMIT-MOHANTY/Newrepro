import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ResourceOnboarding from './pages/ResourceOnboarding';
import GovernanceForm from './pages/GovernanceForm';
import PrerequisiteClassification from './pages/PrerequisiteClassification';
import TaskCreation from './pages/TaskCreation';
import GitHubCallback from './pages/GitHubCallback';
import AzureDevOpsCallback from './pages/AzureDevOpsCallback';
import SsoCallback from './pages/SsoCallback';
import LandingPage from './pages/LandingPage';
import HowItWorks from './pages/HowItWorks';
import OrganizationAdmin from './pages/OrganizationAdmin';
import AppPreview from './pages/AppPreview';
import AppLayout from './components/AppLayout';
import AgentsPage from './components/AgentsPage';

function App() {
  return (
    <Router>
      <Routes>
        {/* Public routes — no sidebar/navbar */}
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/" element={<LandingPage />} />
        <Route path="/how-it-works" element={<HowItWorks />} />
        <Route path="/github/callback" element={<GitHubCallback />} />
        <Route path="/azure-devops/callback" element={<AzureDevOpsCallback />} />
        <Route path="/sso/callback" element={<SsoCallback />} />

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
        <Route path="/app/:projectId" element={
          <AppPreview />
        } />
      </Routes>
    </Router>
  );
}

export default App;
