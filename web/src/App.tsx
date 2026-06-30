import { Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { ProjectsHome } from './components/home/ProjectsHome';

/** Path-routed: "/" = projects landing (home), "/project/:pid" = that project's map/cockpit. */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectsHome />} />
      <Route path="/project/:pid" element={<Shell />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
