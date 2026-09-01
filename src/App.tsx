import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { Ask } from './pages/Ask';
import { FlowsList } from './pages/FlowsList';
import { WorkflowDetails } from './pages/WorkflowDetails';
import { Profile } from './pages/Profile';
import { ServiceDetail } from './pages/ServiceDetail';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/flows" element={<FlowsList />} />
        <Route path="/flows/:id" element={<WorkflowDetails />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/service/:name" element={<ServiceDetail />} />
      </Routes>
    </Layout>
  );
}

export default App;
