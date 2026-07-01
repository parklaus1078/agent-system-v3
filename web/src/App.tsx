import { Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { ProjectsHome } from './components/home/ProjectsHome';
import { RulesPage } from './components/governance/RulesPage';
import { ModelsPage } from './components/governance/ModelsPage';

/** Path-routed: "/" = projects landing (home), "/project/:pid" = that project's map/cockpit,
 *  "/project/:pid/{rules,models}" = the CP0 governance (Rules / Models) pages. */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectsHome />} />
      <Route path="/project/:pid" element={<Shell />} />
      <Route path="/project/:pid/rules" element={<RulesPage />} />
      <Route path="/project/:pid/models" element={<ModelsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
