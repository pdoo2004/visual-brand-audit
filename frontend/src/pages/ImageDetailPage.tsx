import { Link, useParams } from "react-router-dom";

export default function ImageDetailPage() {
  const { jobId, imageId } = useParams();
  return (
    <main>
      <h1>Image detail</h1>
      <p>Scores and feedback for {imageId}.</p>
      <Link to={`/jobs/${jobId}/results`}>Save feedback, return</Link>
    </main>
  );
}