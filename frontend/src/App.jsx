import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import GovernanceForm from './pages/GovernanceForm';
import GitHubCallback from './pages/GitHubCallback';

import LandingPage from './pages/LandingPage';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/status-dashboard" element={<Dashboard />} />
        <Route path="/a/:projectToken" element={<Dashboard />} />
        <Route path="/governance" element={<GovernanceForm />} />
        <Route path="/github/callback" element={<GitHubCallback />} />
        <Route path="/" element={<LandingPage />} />
      </Routes>
    </Router>
  );
}

export default App;
