"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface Project {
  id: string;
  name: string;
  description: string;
  message_count?: number;
  source_count?: number;
  created_at?: string;
}

interface ProjectContextType {
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;
}

const ProjectContext = createContext<ProjectContextType | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [currentProject, setCurrentProjectState] = useState<Project | null>(() => {
    if (typeof window === "undefined") return null;
    const stored = localStorage.getItem("currentProject");
    return stored ? JSON.parse(stored) : null;
  });

  const setCurrentProject = useCallback((project: Project | null) => {
    setCurrentProjectState(project);
    if (project) {
      localStorage.setItem("currentProject", JSON.stringify(project));
    } else {
      localStorage.removeItem("currentProject");
    }
  }, []);

  return (
    <ProjectContext.Provider value={{ currentProject, setCurrentProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}
