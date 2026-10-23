import { Link, useParams } from "react-router-dom";

export default function DashboardPage() {
  const { jobId } = useParams();
  return (
    <main>
      <h1>Batch results</h1>
      <p>Screen 3: dashboard for job {jobId}.</p>
      <Link to={`/jobs/${jobId}/results/demo-image`}>Open an image</Link>
      <br />
      <Link to="/">New analysis</Link>
    </main>
  );
}