import { useParams } from "react-router-dom";

export default function ProjectPage() {
  const { workspaceId, projectId } = useParams();

  return (
    <main>
      <h1>Project</h1>
      <p>
        Workspace: {workspaceId} / Project: {projectId}
      </p>
    </main>
  );
}
