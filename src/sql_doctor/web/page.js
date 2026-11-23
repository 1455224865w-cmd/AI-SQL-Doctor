document.getElementById("diagnose").addEventListener("click", () => run(() => api("/api/diagnose", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    sql: document.getElementById("sql").value,
    explain: document.getElementById("explain").value || null,
    dialect: "postgres"
  })
})));
document.getElementById("history").addEventListener("click", () => run(() => api("/api/reports")));
document.getElementById("compare").addEventListener("click", () => run(() => api(
  "/api/reports/" + encodeURIComponent(document.getElementById("left").value) + "/compare/" + encodeURIComponent(document.getElementById("right").value)
)));
