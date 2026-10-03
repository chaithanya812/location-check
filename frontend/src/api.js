// Every call to the backend goes through here.
async function request(method, path, body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI validation errors come back as {detail: [{msg: ...}]}.
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ")
      : detail || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

export const listAssessments = () => request("GET", "/assessments");
export const getAssessment = (id) => request("GET", `/assessments/${id}`);
export const createAssessment = (body) => request("POST", "/assessments", body);
export const retryAssessment = (id) => request("POST", `/assessments/${id}/retry`);
