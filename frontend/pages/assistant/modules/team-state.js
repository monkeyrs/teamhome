const { setCurrentTeamId } = require("../../../utils/request");
const { getCurrentTeamState } = require("../../../utils/bootstrap");

function resolveTeamIndex(teams, teamId) {
  return Math.max(0, (teams || []).findIndex((item) => item.id === teamId));
}

function resolveCurrentTeam(teams, teamIndex) {
  const state = getCurrentTeamState();
  const currentTeamId = state.teamId || "";
  if (currentTeamId) {
    const matched = (teams || []).find((item) => item.id === currentTeamId);
    if (matched) {
      return matched;
    }
  }
  return (teams || [])[teamIndex] || null;
}

function syncTeamsToApp(teams) {
  const app = getApp();
  app.globalData.teams = teams || [];

  const currentTeamId = app.globalData.currentTeamId || "";
  const teamIndex = resolveTeamIndex(app.globalData.teams, currentTeamId);

  if (app.globalData.teams.length > 0) {
    setCurrentTeamId(app.globalData.teams[Math.max(0, teamIndex)].id);
  } else {
    setCurrentTeamId("");
  }
  return teamIndex;
}

module.exports = {
  resolveTeamIndex,
  resolveCurrentTeam,
  syncTeamsToApp
};
