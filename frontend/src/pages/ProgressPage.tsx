import { Link, useParams } from "react-router-dom";

export default function ProgressPage() {
  const { jobId } = useParams();
  return (
    <main>
      <h1>Analyzing photographs</h1>
      <p>Screen 2: status for job {jobId}.</p>
      <Link to={`/jobs/${jobId}/results`}>View results</Link>
    </main>
  );
}