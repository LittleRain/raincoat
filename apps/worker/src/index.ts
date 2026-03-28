export const createWorkerSummary = () => ({
  service: "raincoat-worker",
  responsibilities: [
    "discover-manifests",
    "prepare-run-directories",
    "execute-tool-jobs",
    "collect-artifacts"
  ]
});

if (require.main === module) {
  console.log(JSON.stringify(createWorkerSummary(), null, 2));
}
