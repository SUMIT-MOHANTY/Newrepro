import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import GovernanceForm from './pages/GovernanceForm';
import PrerequisiteClassification from './pages/PrerequisiteClassification';
import GitHubCallback from './pages/GitHubCallback';
import SsoCallback from './pages/SsoCallback';
import LandingPage from './pages/LandingPage';
import HowItWorks from './pages/HowItWorks';
import OrganizationAdmin from './pages/OrganizationAdmin';
import AppLayout from './components/AppLayout';

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
        <Route path="/a/:projectToken" element={
          <AppLayout>
            {(layoutProps) => <Dashboard {...layoutProps} />}
          </AppLayout>
        } />
        <Route path="/governance" element={
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
      </Routes>
    </Router>
  );
}

export default App;
