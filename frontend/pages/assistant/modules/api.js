const { request, downloadFile } = require("../../../utils/request");

function updateLanguage(locale) {
  return updateProfile({ language: locale });
}

function updateProfile(payload) {
  return request({
    path: "/auth/me",
    method: "PUT",
    data: payload
  });
}

function discoverTeam(name) {
  return request({
    path: `/teams/discover?name=${encodeURIComponent(name)}`
  });
}

function listTeams() {
  return request({ path: "/teams" });
}

function createTeam(payload) {
  return request({
    path: "/teams",
    method: "POST",
    data: payload
  });
}

function leaveTeam(teamId) {
  return request({
    path: `/teams/${teamId}/members/me`,
    method: "DELETE"
  });
}

function executeAssistant(params) {
  return request({
    path: "/assistant/execute",
    method: "POST",
    data: {
      team_id: params.teamId,
      message: params.message,
      session_id: params.sessionId || null
    }
  });
}

function undoAssistant(teamId) {
  return request({
    path: "/assistant/undo",
    method: "POST",
    data: { team_id: teamId }
  });
}

function getAssistantGraphState(params) {
  return request({
    path: `/assistant/graph-state?team_id=${encodeURIComponent(params.teamId)}&session_id=${encodeURIComponent(params.sessionId)}`
  });
}

function getOrchestration() {
  return request({
    path: "/assistant/orchestration",
    method: "GET"
  });
}

function downloadAssistantData() {
  return downloadFile({
    path: "/assistant/export-data"
  });
}

module.exports = {
  updateLanguage,
  updateProfile,
  discoverTeam,
  listTeams,
  createTeam,
  leaveTeam,
  executeAssistant,
  undoAssistant,
  getAssistantGraphState,
  getOrchestration,
  downloadAssistantData
};
