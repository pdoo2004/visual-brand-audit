import { useNavigate } from "react-router-dom";

export default function InputPage() {
  const navigate = useNavigate();
  return (
    <main>
      <h1>Add photographs</h1>
      <p>Screen 1: upload photos or enter a URL, select brand standards.</p>
      <button onClick={() => navigate("/jobs/demo")}>Analyze</button>
    </main>
  );
}