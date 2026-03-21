function ensureSyncStore() {
  const app = getApp();
  if (!app.globalData.dataSync) {
    app.globalData.dataSync = {
      financeByTeam: {},
      scheduleByTeam: {}
    };
  }
  return app.globalData.dataSync;
}

function normalizeScope(scope) {
  if (scope === "finance") return "financeByTeam";
  if (scope === "schedule") return "scheduleByTeam";
  return "";
}

function markDataDirty(params) {
  const teamId = params && params.teamId;
  const scopes = (params && params.scopes) || [];
  if (!teamId || !Array.isArray(scopes) || scopes.length === 0) {
    return;
  }
  const sync = ensureSyncStore();
  const now = Date.now();
  scopes.forEach((scope) => {
    const field = normalizeScope(scope);
    if (!field) return;
    sync[field][teamId] = now;
  });
}

function getDataVersion(scope, teamId) {
  if (!teamId) return 0;
  const sync = ensureSyncStore();
  const field = normalizeScope(scope);
  if (!field) return 0;
  return sync[field][teamId] || 0;
}

module.exports = {
  markDataDirty,
  getDataVersion
};
