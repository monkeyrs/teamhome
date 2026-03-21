const { request } = require("../../../utils/request");

function updateLanguage(locale) {
  return request({
    path: "/auth/me",
    method: "PUT",
    data: { language: locale }
  });
}

function listTeams() {
  return request({ path: "/teams" });
}

function createTeam(name) {
  return request({
    path: "/teams",
    method: "POST",
    data: { name }
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

module.exports = {
  updateLanguage,
  listTeams,
  createTeam,
  leaveTeam,
  executeAssistant,
  undoAssistant
};
