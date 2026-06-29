import { useState } from 'react';
import { Shell } from './components/Shell';
import { ProjectsHome } from './components/home/ProjectsHome';

export default function App() {
  // Boots into the project (Navigator), as the wireframe does; the Control Tower
  // brand opens the project-management home, and a project card re-enters it.
  const [view, setView] = useState<'home' | 'project'>('project');
  return view === 'home' ? (
    <ProjectsHome onOpenProject={() => setView('project')} />
  ) : (
    <Shell onHome={() => setView('home')} />
  );
}
